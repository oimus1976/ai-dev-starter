#!/usr/bin/env python3
"""Verify local post-merge closeout without destructive cleanup."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from closeout_state import (
    FULL_SHA_RE,
    canonical_worktree,
    current_branch,
    refresh_remote_branch,
    resolve_worktree,
    rev_parse,
    worktree_failures,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify post-merge local closeout without reset/stash/delete cleanup."
    )
    parser.add_argument("--repo", default=".", help="Tracked PR worktree/repository path.")
    parser.add_argument("--branch", default="main", help="Canonical local branch.")
    parser.add_argument("--remote", default="origin", help="Canonical Git remote.")
    parser.add_argument(
        "--expected-pr-head",
        help=(
            "Full 40-character PR head SHA from an independent GitHub merge read. "
            "Required when running from a non-canonical topic worktree."
        ),
    )
    args = parser.parse_args()

    task_worktree, error = resolve_worktree(Path(args.repo))
    if error or task_worktree is None:
        print("LOCAL CLOSEOUT: FAIL")
        print(f"- {error}")
        return 1

    failures: list[str] = []
    remote_sha, freshness_error = refresh_remote_branch(task_worktree, args.remote, args.branch)
    if freshness_error:
        failures.append(freshness_error)

    failures.extend(worktree_failures(task_worktree, "task"))
    task_branch = current_branch(task_worktree)
    task_head = rev_parse(task_worktree, "HEAD") or ""

    canonical = task_worktree if task_branch == args.branch else None
    topic_mode = canonical is None

    if topic_mode:
        expected = (args.expected_pr_head or "").strip()
        if not expected:
            failures.append(
                "topic worktree closeout requires --expected-pr-head from the independently confirmed merged PR"
            )
        elif not FULL_SHA_RE.fullmatch(expected):
            failures.append("--expected-pr-head must be a full 40-character hexadecimal GitHub commit SHA")
        elif task_head.lower() != expected.lower():
            failures.append(
                f"task HEAD {task_head[:12]} does not match expected PR head {expected[:12]}"
            )

        canonical = canonical_worktree(task_worktree, args.branch)
        if canonical is None:
            failures.append(
                f"canonical branch {args.branch!r} is not checked out in exactly one available worktree"
            )
        else:
            failures.extend(worktree_failures(canonical, "canonical"))
            canonical_branch = current_branch(canonical)
            if canonical_branch != args.branch:
                failures.append(
                    f"canonical worktree branch is {canonical_branch or '<detached HEAD>'!r}; expected {args.branch!r}"
                )

    canonical_head = ""
    if remote_sha and canonical is not None:
        canonical_head = rev_parse(canonical, "HEAD") or ""
        if canonical_head != remote_sha:
            failures.append(
                f"canonical HEAD {canonical_head[:12]} does not match {args.remote}/{args.branch} {remote_sha[:12]}"
            )

    if failures:
        print("LOCAL CLOSEOUT: FAIL")
        for failure in failures:
            print(f"- {failure}")
        print("NEXT STEPS:")
        print("1. Preserve or commit any intentional local changes before cleanup.")
        if topic_mode:
            print(
                "2. Resolve every task-worktree finding first; do not switch away from the topic worktree to bypass the confirmed PR-head check."
            )
            if canonical is None:
                print(
                    f"3. Check out {args.branch} in a separate canonical worktree, then fast-forward it only from {args.remote}/{args.branch}."
                )
            else:
                print(
                    f"3. Repair/synchronize the existing {args.branch} worktree; fast-forward only: git pull --ff-only {args.remote} {args.branch}"
                )
            print(
                "4. Re-run this verifier from the topic worktree with the full --expected-pr-head confirmed from GitHub."
            )
        else:
            print(f"2. Switch to {args.branch}: git switch {args.branch}")
            print(f"3. Fast-forward only: git pull --ff-only {args.remote} {args.branch}")
            print("4. Re-run this verifier.")
        print("Do not use reset/stash/delete merely to make the gate pass.")
        return 1

    print("LOCAL CLOSEOUT: PASS")
    print(f"task_worktree_role={'topic' if topic_mode else 'canonical'}")
    if topic_mode:
        print("task_worktree=clean")
        print(f"task_head={task_head}")
        print("expected_pr_head=matched")
    print("canonical_worktree=ready")
    print(f"branch={args.branch}")
    print(f"head={canonical_head or task_head}")
    print(f"remote={args.remote}/{args.branch}")
    print("freshness=canonical-branch-fetch-completed")
    print("next_task_checkout=canonical-worktree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
