#!/usr/bin/env python3
"""Plan or execute fail-closed cleanup for one merged same-repository PR."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable

from closeout_state import (
    FULL_SHA_RE,
    WorktreeInfo,
    current_branch,
    delete_ref_cas,
    git,
    is_ancestor,
    list_worktrees,
    refresh_remote_branch,
    remote_branch_sha,
    remote_repository_identity,
    resolve_worktree,
    rev_parse,
    snapshot_refs,
    worktree_failures,
    worktrees_for_branch,
)


@dataclass(frozen=True)
class PREvidence:
    number: int
    state: str
    merged_at: str | None
    base_ref: str
    head_ref: str
    head_sha: str
    is_cross_repository: bool


@dataclass(frozen=True)
class CleanupPlan:
    repository: str
    pr: int
    branch: str
    remote: str
    topic_branch: str
    expected_head: str
    mode: str
    target_worktree: Path | None
    canonical_worktree: Path | None
    canonical_remote_sha: str
    local_topic_present: bool
    remote_topic_sha: str | None
    remote_tracking_sha: str | None
    actions: tuple[str, ...]
    delete_remote: bool
    baseline_refs: tuple[tuple[str, str], ...]
    baseline_worktrees: tuple[tuple[str, str | None, str | None], ...]


GitHubReader = Callable[[int, str], PREvidence]


def read_github_pr(pr: int, repository: str) -> PREvidence:
    fields = "number,state,mergedAt,baseRefName,headRefName,headRefOid,isCrossRepository"
    result = subprocess.run(
        ["gh", "pr", "view", str(pr), "-R", repository, "--json", fields],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("GitHub PR evidence could not be read with authenticated gh")
    try:
        raw = json.loads(result.stdout)
        return PREvidence(
            number=int(raw["number"]),
            state=str(raw["state"]),
            merged_at=raw.get("mergedAt"),
            base_ref=str(raw["baseRefName"]),
            head_ref=str(raw["headRefName"]),
            head_sha=str(raw["headRefOid"]),
            is_cross_repository=bool(raw["isCrossRepository"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub PR evidence was incomplete or invalid") from exc


def _worktree_snapshot(repo: Path) -> tuple[tuple[str, str | None, str | None], ...]:
    return tuple(
        sorted((str(item.path), item.branch_ref, item.head) for item in list_worktrees(repo))
    )


def build_plan(
    repo: Path,
    pr: int,
    branch: str,
    remote: str,
    repository_override: str | None,
    delete_remote: bool,
    github_reader: GitHubReader = read_github_pr,
) -> tuple[CleanupPlan | None, list[str]]:
    requested, error = resolve_worktree(repo)
    if error or requested is None:
        return None, [error or "repository/worktree could not be resolved"]

    failures: list[str] = []
    repository, repo_error = remote_repository_identity(requested, remote)
    if repo_error or repository is None:
        failures.append(repo_error or "repository identity is unavailable")
        return None, failures
    if repository_override and repository.lower() != repository_override.lower():
        failures.append(
            f"configured repository {repository_override!r} does not match {remote} identity {repository!r}"
        )
        return None, failures

    try:
        evidence = github_reader(pr, repository)
    except RuntimeError as exc:
        return None, [str(exc)]

    if evidence.number != pr:
        failures.append("GitHub returned a different PR number")
    if evidence.state.upper() != "MERGED" or not evidence.merged_at:
        failures.append("GitHub PR is not merged")
    if evidence.is_cross_repository:
        failures.append("cross-repository/fork PR cleanup is not supported in v1")
    if evidence.base_ref != branch:
        failures.append(
            f"PR base branch is {evidence.base_ref!r}; expected canonical branch {branch!r}"
        )
    if not evidence.head_ref or evidence.head_ref == branch:
        failures.append("PR topic branch identity is unavailable or equals canonical branch")
    if not FULL_SHA_RE.fullmatch(evidence.head_sha):
        failures.append("GitHub PR head SHA is not a full 40-character commit SHA")
    if failures:
        return None, failures

    remote_main, freshness_error = refresh_remote_branch(requested, remote, branch)
    if freshness_error or remote_main is None:
        return None, [freshness_error or "canonical remote freshness is unavailable"]

    topic_ref = f"refs/heads/{evidence.head_ref}"
    local_topic_sha = rev_parse(requested, topic_ref)
    if local_topic_sha is not None and local_topic_sha.lower() != evidence.head_sha.lower():
        failures.append(
            f"local topic ref {evidence.head_ref!r} does not match GitHub PR head {evidence.head_sha[:12]}"
        )

    target_matches = worktrees_for_branch(requested, evidence.head_ref)
    if len(target_matches) > 1:
        failures.append("topic worktree identity/occupancy is ambiguous")
    target: WorktreeInfo | None = target_matches[0] if len(target_matches) == 1 else None
    if target is not None:
        if not target.path.is_dir() or target.prunable:
            failures.append("topic worktree registration is stale or unavailable")
        else:
            failures.extend(worktree_failures(target.path, "task"))
            target_head = rev_parse(target.path, "HEAD")
            if target_head is None or target_head.lower() != evidence.head_sha.lower():
                failures.append("task HEAD does not match GitHub PR head")
            if local_topic_sha is None:
                failures.append("topic worktree exists but local topic ref is unavailable")

    canonical_matches = worktrees_for_branch(requested, branch)
    if len(canonical_matches) > 1:
        failures.append("canonical branch is checked out in more than one worktree")

    canonical: WorktreeInfo | None = canonical_matches[0] if len(canonical_matches) == 1 else None
    mode = ""
    canonical_path: Path | None = None
    if canonical is not None:
        mode = "linked" if target is not None and target.path != canonical.path else "canonical-only"
        canonical_path = canonical.path
        if not canonical.path.is_dir() or canonical.prunable:
            failures.append("canonical worktree registration is stale or unavailable")
        else:
            failures.extend(worktree_failures(canonical.path, "canonical"))
            canonical_head = rev_parse(canonical.path, "HEAD")
            if canonical_head != remote_main:
                failures.append(
                    f"canonical HEAD {(canonical_head or '')[:12]} does not match {remote}/{branch} {remote_main[:12]}"
                )
    else:
        if target is None:
            failures.append(
                f"canonical branch {branch!r} is not checked out and no eligible topic worktree can become canonical"
            )
        else:
            mode = "single"
            canonical_local = rev_parse(requested, f"refs/heads/{branch}")
            if canonical_local is None:
                failures.append(f"local canonical branch {branch!r} is unavailable")
            elif not is_ancestor(requested, canonical_local, remote_main):
                failures.append(
                    f"local canonical branch {branch!r} cannot fast-forward to fresh {remote}/{branch}"
                )

    remote_topic, remote_error = remote_branch_sha(requested, remote, evidence.head_ref)
    if remote_error:
        failures.append(remote_error)
    elif remote_topic is not None and remote_topic.lower() != evidence.head_sha.lower():
        failures.append(
            f"remote topic branch {remote}/{evidence.head_ref} drifted from GitHub PR head"
        )

    remote_tracking_ref = f"refs/remotes/{remote}/{evidence.head_ref}"
    remote_tracking_sha = rev_parse(requested, remote_tracking_ref)
    if remote_tracking_sha is not None and remote_tracking_sha.lower() != evidence.head_sha.lower():
        failures.append(
            f"remote-tracking ref {remote}/{evidence.head_ref} drifted from GitHub PR head"
        )

    if failures:
        return None, failures

    actions: list[str] = []
    if mode == "linked" and target is not None:
        actions.append("remove linked topic worktree")
    elif mode == "single":
        actions.append(f"switch task worktree to canonical branch {branch}")
        local_main = rev_parse(requested, f"refs/heads/{branch}")
        if local_main != remote_main:
            actions.append(f"fast-forward canonical branch to fresh {remote}/{branch}")

    if local_topic_sha is not None:
        actions.append("conditionally delete local topic ref at expected PR head")

    if delete_remote:
        if remote_topic is None:
            actions.append("remote topic branch already absent")
        else:
            actions.append("delete remote topic branch with exact expected-SHA lease")

    if remote_topic is None and remote_tracking_sha is not None:
        actions.append("conditionally delete target stale remote-tracking ref")
    elif delete_remote and remote_tracking_sha is not None:
        actions.append("conditionally remove target remote-tracking ref after remote deletion")

    return (
        CleanupPlan(
            repository=repository,
            pr=pr,
            branch=branch,
            remote=remote,
            topic_branch=evidence.head_ref,
            expected_head=evidence.head_sha.lower(),
            mode=mode,
            target_worktree=target.path if target else None,
            canonical_worktree=canonical_path,
            canonical_remote_sha=remote_main,
            local_topic_present=local_topic_sha is not None,
            remote_topic_sha=remote_topic.lower() if remote_topic else None,
            remote_tracking_sha=remote_tracking_sha.lower() if remote_tracking_sha else None,
            actions=tuple(actions),
            delete_remote=delete_remote,
            baseline_refs=tuple(sorted(snapshot_refs(requested).items())),
            baseline_worktrees=_worktree_snapshot(requested),
        ),
        [],
    )


def print_blocked(reasons: list[str]) -> None:
    print("SAFE CLEANUP: BLOCKED")
    print("Reasons:")
    for reason in reasons:
        print(f"- {reason}")


def print_plan(plan: CleanupPlan) -> None:
    print("SAFE CLEANUP PLAN")
    print()
    print(f"PR: #{plan.pr}")
    print("PR state: merged")
    print(f"PR head: {plan.expected_head}")
    print(f"topic branch: {plan.topic_branch}")
    print(f"layout: {plan.mode}")
    print("task worktree: eligible" if plan.target_worktree else "task worktree: already absent")
    print("local branch: eligible" if plan.local_topic_present else "local branch: already absent")
    if plan.remote_topic_sha is None:
        print("remote branch: already absent")
    else:
        print("remote branch: eligible" if plan.delete_remote else "remote branch: retained")
    print(
        f"canonical {plan.branch}: ready"
        if plan.mode != "single"
        else f"canonical {plan.branch}: safe fast-forward path"
    )
    print()
    print("Planned actions:")
    if plan.actions:
        for action in plan.actions:
            print(f"- {action}")
    else:
        print("- no cleanup effect required")
    print()
    print("Remote branch deletion:")
    print("- requested" if plan.delete_remote else "- not requested")


def _remote_delete_with_lease(repo: Path, plan: CleanupPlan) -> bool:
    current, error = remote_branch_sha(repo, plan.remote, plan.topic_branch)
    if error:
        return False
    if current is None:
        return True
    if current.lower() != plan.expected_head:
        return False
    ref = f"refs/heads/{plan.topic_branch}"
    lease = f"--force-with-lease={ref}:{plan.expected_head}"
    refspec = f":{ref}"
    result = git("push", lease, plan.remote, refspec, cwd=repo, check=False)
    return result.returncode == 0


def execute_plan(
    plan: CleanupPlan,
    any_repo: Path,
    github_reader: GitHubReader = read_github_pr,
) -> tuple[bool, list[str]]:
    effects_started = False
    failures: list[str] = []
    repo, error = resolve_worktree(any_repo)
    if error or repo is None:
        return False, [error or "repository/worktree could not be resolved"]

    try:
        fresh, reasons = build_plan(
            repo,
            plan.pr,
            plan.branch,
            plan.remote,
            plan.repository,
            plan.delete_remote,
            github_reader,
        )
        if reasons or fresh is None:
            return False, reasons or ["cleanup revalidation failed"]
        plan = fresh

        topic_ref = f"refs/heads/{plan.topic_branch}"
        remote_tracking_ref = f"refs/remotes/{plan.remote}/{plan.topic_branch}"

        if plan.mode == "linked" and plan.target_worktree is not None:
            pre = worktree_failures(plan.target_worktree, "task")
            if pre or rev_parse(plan.target_worktree, "HEAD") != plan.expected_head:
                return False, pre or ["task HEAD changed before worktree removal"]
            result = git("worktree", "remove", str(plan.target_worktree), cwd=repo, check=False)
            if result.returncode != 0:
                return False, ["normal topic worktree removal failed; no force cleanup was attempted"]
            effects_started = True

        elif plan.mode == "single" and plan.target_worktree is not None:
            pre = worktree_failures(plan.target_worktree, "task")
            if pre or rev_parse(plan.target_worktree, "HEAD") != plan.expected_head:
                return False, pre or ["task HEAD changed before canonical switch"]
            switched = git("switch", plan.branch, cwd=plan.target_worktree, check=False)
            if switched.returncode != 0:
                return False, [f"could not switch clean task worktree to canonical branch {plan.branch!r}"]
            effects_started = True
            current_main = rev_parse(plan.target_worktree, "HEAD")
            if current_main != plan.canonical_remote_sha:
                merged = git(
                    "merge",
                    "--ff-only",
                    f"refs/remotes/{plan.remote}/{plan.branch}",
                    cwd=plan.target_worktree,
                    check=False,
                )
                if merged.returncode != 0:
                    return False, ["canonical fast-forward failed"]

        if plan.local_topic_present:
            current = rev_parse(repo, topic_ref)
            if current != plan.expected_head:
                return False, ["local topic ref changed before conditional deletion"]
            if not delete_ref_cas(repo, topic_ref, plan.expected_head):
                return False, ["conditional local topic ref deletion failed"]
            effects_started = True

        if plan.delete_remote:
            if not _remote_delete_with_lease(repo, plan):
                return False, ["remote topic branch deletion failed or lost its expected-SHA lease"]
            if plan.remote_topic_sha is not None:
                effects_started = True

        current_remote_topic, remote_error = remote_branch_sha(repo, plan.remote, plan.topic_branch)
        if remote_error:
            return False, [remote_error]
        if current_remote_topic is None:
            tracking = rev_parse(repo, remote_tracking_ref)
            if tracking is not None:
                if tracking != plan.expected_head:
                    return False, ["target remote-tracking ref changed before conditional deletion"]
                if not delete_ref_cas(repo, remote_tracking_ref, plan.expected_head):
                    return False, ["conditional target remote-tracking ref deletion failed"]
                effects_started = True

        remote_main, freshness_error = refresh_remote_branch(repo, plan.remote, plan.branch)
        if freshness_error or remote_main is None:
            return False, [freshness_error or "canonical freshness could not be re-established"]

        canonical_matches = worktrees_for_branch(repo, plan.branch)
        if len(canonical_matches) != 1 or not canonical_matches[0].path.is_dir():
            failures.append("canonical branch is not checked out in exactly one available worktree")
        else:
            canonical_path = canonical_matches[0].path
            failures.extend(worktree_failures(canonical_path, "canonical"))
            if rev_parse(canonical_path, "HEAD") != remote_main:
                failures.append("canonical HEAD does not match freshly fetched canonical remote HEAD")

        if worktrees_for_branch(repo, plan.topic_branch):
            failures.append("target topic worktree still exists")
        if rev_parse(repo, topic_ref) is not None:
            failures.append("target local topic branch still exists")
        if plan.delete_remote:
            remote_after, remote_error = remote_branch_sha(repo, plan.remote, plan.topic_branch)
            if remote_error:
                failures.append(remote_error)
            elif remote_after is not None:
                failures.append("requested remote topic branch still exists")
        remote_after, _ = remote_branch_sha(repo, plan.remote, plan.topic_branch)
        if remote_after is None and rev_parse(repo, remote_tracking_ref) is not None:
            failures.append("target stale remote-tracking ref still exists")

        baseline_refs = dict(plan.baseline_refs)
        post_refs = snapshot_refs(repo)
        allowed_refs = {
            topic_ref,
            remote_tracking_ref,
            f"refs/heads/{plan.branch}",
            f"refs/remotes/{plan.remote}/{plan.branch}",
        }
        for ref in sorted((set(baseline_refs) | set(post_refs)) - allowed_refs):
            if baseline_refs.get(ref) != post_refs.get(ref):
                failures.append(f"unrelated ref changed during cleanup: {ref}")

        allowed_paths = {
            str(path)
            for path in (plan.target_worktree, plan.canonical_worktree)
            if path is not None
        }
        baseline_worktrees = {
            item for item in plan.baseline_worktrees if item[0] not in allowed_paths
        }
        post_worktrees = {
            item for item in _worktree_snapshot(repo) if item[0] not in allowed_paths
        }
        if baseline_worktrees != post_worktrees:
            failures.append("unrelated worktree registration changed during cleanup")

        if failures:
            return False, failures
        return True, []
    finally:
        execute_plan.effects_started = effects_started  # type: ignore[attr-defined]


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or execute safe cleanup for one merged PR.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--remote", default="origin")
    parser.add_argument(
        "--repository", default=None, help="Optional owner/repo assertion; must match remote."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Perform the planned cleanup after full revalidation."
    )
    parser.add_argument(
        "--delete-remote",
        action="store_true",
        help="Also delete exact matching remote topic branch with a lease.",
    )
    args = parser.parse_args()

    plan, reasons = build_plan(
        Path(args.repo),
        args.pr,
        args.branch,
        args.remote,
        args.repository,
        args.delete_remote,
    )
    if reasons or plan is None:
        print_blocked(reasons or ["cleanup eligibility could not be established"])
        return 2

    print_plan(plan)
    if not args.execute:
        return 0

    print()
    print("SAFE CLEANUP EXECUTION")
    execute_plan.effects_started = False  # type: ignore[attr-defined]
    ok, failures = execute_plan(plan, Path(args.repo))
    if not ok:
        if getattr(execute_plan, "effects_started", False):
            print("SAFE CLEANUP: INCOMPLETE")
            print("Some authorized effects may already have completed; no force recovery was attempted.")
        else:
            print("SAFE CLEANUP: BLOCKED")
            print("No cleanup effect was authorized after revalidation.")
        for failure in failures:
            print(f"- {failure}")
        return 3

    print("POST-MERGE CLOSEOUT: PASS")
    print("cleanup: completed")
    print(f"canonical: {plan.branch}")
    print("next_task_checkout: ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
