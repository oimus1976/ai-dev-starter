#!/usr/bin/env python3
"""Plan or execute fail-closed cleanup for one merged same-repository PR.

v1 deliberately keeps local ref authority narrower than worktree cleanup.
Eligible linked topic worktrees may be removed and a single clean topic checkout
may be returned to canonical, but local topic branches and remote-tracking refs
are retained. Remote topic deletion remains a separate explicit opt-in protected
by an exact expected-SHA lease.
"""

from __future__ import annotations

import sys

# Prevent the cleanup tool's own local imports from creating ignored bytecode
# residue before the worktree safety inspection runs.
sys.dont_write_bytecode = True

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Callable, Iterator

from closeout_state import (
    FULL_SHA_RE,
    WorktreeInfo,
    apply_disposable_cleanup,
    cleanup_worktree_failures,
    git,
    is_ancestor,
    refresh_remote_branch,
    remote_branch_sha,
    remote_repository_identity,
    resolve_worktree,
    rev_parse,
    snapshot_refs,
    worktree_failures,
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


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    failures: tuple[str, ...]
    effects_started: bool

    def __iter__(self) -> Iterator[object]:
        yield self.ok
        yield self.failures


GitHubReader = Callable[[int, str], PREvidence]


def read_github_pr(pr: int, repository: str) -> PREvidence:
    fields = "number,state,mergedAt,baseRefName,headRefName,headRefOid,isCrossRepository"
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr), "-R", repository, "--json", fields],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError("GitHub PR evidence could not be read with authenticated gh") from exc
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


def _read_worktrees(repo: Path) -> tuple[list[WorktreeInfo] | None, str | None]:
    """Read and parse the worktree registry exactly once.

    A failed registry read is never represented as an empty registry.
    """
    from closeout_state import list_worktrees
    entries, err = list_worktrees(repo)
    if err:
        return None, err
    return entries, None


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
        return None, [repo_error or "repository identity is unavailable"]
    if repository_override and repository.lower() != repository_override.lower():
        return None, [
            f"configured repository {repository_override!r} does not match "
            f"{remote} identity {repository!r}"
        ]

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

    expected_head = evidence.head_sha.lower()
    remote_main, freshness_error = refresh_remote_branch(requested, remote, branch)
    if freshness_error or remote_main is None:
        return None, [freshness_error or "canonical remote freshness is unavailable"]

    worktrees, registry_error = _read_worktrees(requested)
    if registry_error or worktrees is None:
        return None, [registry_error or "worktree registry is unavailable"]

    topic_ref = f"refs/heads/{evidence.head_ref}"
    local_topic_sha = rev_parse(requested, topic_ref)
    if local_topic_sha is not None and local_topic_sha.lower() != expected_head:
        failures.append(
            f"local topic ref {evidence.head_ref!r} does not match "
            f"GitHub PR head {expected_head[:12]}"
        )

    topic_branch_ref = f"refs/heads/{evidence.head_ref}"
    target_matches = [item for item in worktrees if item.branch_ref == topic_branch_ref]
    if len(target_matches) > 1:
        failures.append("topic worktree identity/occupancy is ambiguous")
    target = target_matches[0] if len(target_matches) == 1 else None
    if target is not None:
        if not target.path.is_dir() or target.prunable:
            failures.append("topic worktree registration is stale or unavailable")
        else:
            failures.extend(cleanup_worktree_failures(target.path, "task"))
            target_head = rev_parse(target.path, "HEAD")
            if target_head is None or target_head.lower() != expected_head:
                failures.append("task HEAD does not match GitHub PR head")
            if local_topic_sha is None:
                failures.append("topic worktree exists but local topic ref is unavailable")

    canonical_branch_ref = f"refs/heads/{branch}"
    canonical_matches = [item for item in worktrees if item.branch_ref == canonical_branch_ref]
    if len(canonical_matches) > 1:
        failures.append("canonical branch is checked out in more than one worktree")

    canonical = canonical_matches[0] if len(canonical_matches) == 1 else None
    mode = ""
    canonical_path: Path | None = None
    if canonical is not None:
        mode = "linked" if target is not None and target.path != canonical.path else "canonical-only"

        if mode == "linked" and target is not None and getattr(target, "is_primary", False):
            failures.append("primary topic worktree with linked canonical worktree is not safely supported for removal")

        canonical_path = canonical.path
        if not canonical.path.is_dir() or canonical.prunable:
            failures.append("canonical worktree registration is stale or unavailable")
        else:
            failures.extend(worktree_failures(canonical.path, "canonical"))
            canonical_head = rev_parse(canonical.path, "HEAD")
            if canonical_head != remote_main:
                failures.append(
                    f"canonical HEAD {(canonical_head or '')[:12]} does not match "
                    f"{remote}/{branch} {remote_main[:12]}"
                )
    else:
        if target is None:
            failures.append(
                f"canonical branch {branch!r} is not checked out and no eligible "
                "topic worktree can become canonical"
            )
        else:
            mode = "single"
            canonical_local = rev_parse(requested, f"refs/heads/{branch}")
            if canonical_local is None:
                failures.append(f"local canonical branch {branch!r} is unavailable")
            elif not is_ancestor(requested, canonical_local, remote_main):
                failures.append(
                    f"local canonical branch {branch!r} cannot fast-forward to "
                    f"fresh {remote}/{branch}"
                )

    remote_topic, remote_error = remote_branch_sha(requested, remote, evidence.head_ref)
    if remote_error:
        failures.append(remote_error)
    elif remote_topic is not None and remote_topic.lower() != expected_head:
        failures.append(
            f"remote topic branch {remote}/{evidence.head_ref} drifted from GitHub PR head"
        )

    remote_tracking_ref = f"refs/remotes/{remote}/{evidence.head_ref}"
    remote_tracking_sha = rev_parse(requested, remote_tracking_ref)
    if remote_tracking_sha is not None and remote_tracking_sha.lower() != expected_head:
        failures.append(
            f"remote-tracking ref {remote}/{evidence.head_ref} drifted from GitHub PR head"
        )

    baseline_refs, refs_error = snapshot_refs(requested)
    if refs_error or baseline_refs is None:
        failures.append(refs_error or "local ref snapshot is unavailable")

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
        actions.append(
            "retain local topic branch; automatic local ref deletion is outside v1 safe cleanup"
        )

    if delete_remote:
        if remote_topic is None:
            actions.append("remote topic branch already absent")
        else:
            actions.append("delete remote topic branch with exact expected-SHA lease")

    if remote_tracking_sha is not None:
        actions.append(
            "retain remote-tracking ref; direct tracking-ref pruning is outside v1 safe cleanup"
        )

    assert baseline_refs is not None
    return (
        CleanupPlan(
            repository=repository,
            pr=pr,
            branch=branch,
            remote=remote,
            topic_branch=evidence.head_ref,
            expected_head=expected_head,
            mode=mode,
            target_worktree=target.path if target else None,
            canonical_worktree=canonical_path,
            canonical_remote_sha=remote_main,
            local_topic_present=local_topic_sha is not None,
            remote_topic_sha=remote_topic.lower() if remote_topic else None,
            remote_tracking_sha=remote_tracking_sha.lower() if remote_tracking_sha else None,
            actions=tuple(actions),
            delete_remote=delete_remote,
            baseline_refs=tuple(sorted(baseline_refs.items())),
            baseline_worktrees=tuple(
                sorted((str(item.path), item.branch_ref, item.head) for item in worktrees)
            ),
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
    if not plan.local_topic_present:
        print("local branch: already absent")
    else:
        print("local branch: retained by v1")
    if plan.remote_topic_sha is None:
        print("remote branch: already absent")
    else:
        print("remote branch: eligible" if plan.delete_remote else "remote branch: retained")
    if plan.remote_tracking_sha is not None:
        print("remote-tracking ref: retained by v1")
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
    if plan.remote_topic_sha is None:
        return current is None
    if current is None:
        return True
    if current.lower() != plan.expected_head:
        return False
    ref = f"refs/heads/{plan.topic_branch}"
    lease = f"--force-with-lease={ref}:{plan.expected_head}"
    refspec = f":{ref}"
    result = git("push", lease, plan.remote, refspec, cwd=repo, check=False)
    return result.returncode == 0


def _execution_failure(
    failures: list[str] | tuple[str, ...], effects_started: bool
) -> ExecutionResult:
    return ExecutionResult(False, tuple(failures), effects_started)


def _canonical_pre_effect_failures(repo: Path, plan: CleanupPlan) -> list[str]:
    failures: list[str] = []
    remote_main, error = refresh_remote_branch(repo, plan.remote, plan.branch)
    if error or remote_main is None:
        return [error or "canonical freshness could not be revalidated before cleanup effect"]
    if remote_main != plan.canonical_remote_sha:
        return ["canonical remote HEAD changed after cleanup revalidation; re-plan before effects"]

    worktrees, registry_error = _read_worktrees(repo)
    if registry_error or worktrees is None:
        return [registry_error or "worktree registry is unavailable before cleanup effect"]

    canonical_ref = f"refs/heads/{plan.branch}"
    canonical_matches = [item for item in worktrees if item.branch_ref == canonical_ref]
    if plan.mode in {"linked", "canonical-only"}:
        if len(canonical_matches) != 1 or not canonical_matches[0].path.is_dir():
            failures.append("canonical branch is not checked out in exactly one available worktree")
        else:
            failures.extend(worktree_failures(canonical_matches[0].path, "canonical"))
            if rev_parse(canonical_matches[0].path, "HEAD") != remote_main:
                failures.append("canonical HEAD changed after cleanup revalidation")
    elif plan.mode == "single":
        local_main = rev_parse(repo, f"refs/heads/{plan.branch}")
        if local_main is None or not is_ancestor(repo, local_main, remote_main):
            failures.append("local canonical branch no longer has a safe fast-forward path")
    return failures


def _stable_control_repo(repo: Path, plan: CleanupPlan) -> tuple[Path | None, str | None]:
    """Choose a worktree that will survive the planned effects.

    A linked topic worktree may remove itself, so subsequent repository-wide Git
    commands must use the separate canonical worktree as their cwd. In single
    mode the target worktree survives because it is switched to canonical.
    """
    if plan.mode in {"linked", "canonical-only"}:
        if plan.canonical_worktree is None or not plan.canonical_worktree.is_dir():
            return None, "canonical worktree is unavailable as a stable cleanup control path"
        return plan.canonical_worktree, None
    if plan.mode == "single":
        if plan.target_worktree is None or not plan.target_worktree.is_dir():
            return None, "single-checkout task worktree is unavailable as a cleanup control path"
        return plan.target_worktree, None
    return repo, None


def execute_plan(
    plan: CleanupPlan,
    any_repo: Path,
    github_reader: GitHubReader = read_github_pr,
) -> ExecutionResult:
    effects_started = False
    failures: list[str] = []
    repo, error = resolve_worktree(any_repo)
    if error or repo is None:
        return _execution_failure([error or "repository/worktree could not be resolved"], False)

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
        return _execution_failure(reasons or ["cleanup revalidation failed"], False)
    plan = fresh

    control_repo, control_error = _stable_control_repo(repo, plan)
    if control_error or control_repo is None:
        return _execution_failure(
            [control_error or "stable cleanup control worktree is unavailable"], False
        )

    pre_effect = _canonical_pre_effect_failures(control_repo, plan)
    if pre_effect:
        return _execution_failure(pre_effect, False)

    topic_ref = f"refs/heads/{plan.topic_branch}"

    if plan.mode == "linked" and plan.target_worktree is not None:
        pre = cleanup_worktree_failures(plan.target_worktree, "task")
        if pre or rev_parse(plan.target_worktree, "HEAD") != plan.expected_head:
            return _execution_failure(
                pre or ["task HEAD changed before worktree removal"], effects_started
            )
        effects_started = True

        del_failures = apply_disposable_cleanup(plan.target_worktree)
        if del_failures:
            return _execution_failure(del_failures, effects_started)

        result = git(
            "worktree", "remove", str(plan.target_worktree), cwd=control_repo, check=False
        )
        if result.returncode != 0:
            diagnostic = result.stdout.strip().split("\n")[0]
            if diagnostic.startswith("fatal: "):
                diagnostic = diagnostic[7:]
            if not diagnostic:
                diagnostic = "no diagnostic output"
            return _execution_failure(
                [f"normal topic worktree removal failed ({diagnostic}); no force cleanup was attempted"],
                effects_started,
            )

    elif plan.mode == "single" and plan.target_worktree is not None:
        pre = cleanup_worktree_failures(plan.target_worktree, "task")
        if pre or rev_parse(plan.target_worktree, "HEAD") != plan.expected_head:
            return _execution_failure(
                pre or ["task HEAD changed before canonical switch"], effects_started
            )
        effects_started = True
        switched = git("switch", plan.branch, cwd=plan.target_worktree, check=False)
        if switched.returncode != 0:
            return _execution_failure(
                [f"could not switch clean task worktree to canonical branch {plan.branch!r}"],
                effects_started,
            )
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
                return _execution_failure(["canonical fast-forward failed"], effects_started)

    if plan.delete_remote:
        if plan.remote_topic_sha is not None:
            effects_started = True
        if not _remote_delete_with_lease(control_repo, plan):
            return _execution_failure(
                ["remote topic branch deletion failed or lost its expected-SHA lease"],
                effects_started,
            )

    remote_main, freshness_error = refresh_remote_branch(control_repo, plan.remote, plan.branch)
    if freshness_error or remote_main is None:
        return _execution_failure(
            [freshness_error or "canonical freshness could not be re-established"],
            effects_started,
        )

    worktrees, registry_error = _read_worktrees(control_repo)
    if registry_error or worktrees is None:
        return _execution_failure(
            [registry_error or "worktree registry could not be read after cleanup"],
            effects_started,
        )

    canonical_ref = f"refs/heads/{plan.branch}"
    canonical_matches = [item for item in worktrees if item.branch_ref == canonical_ref]
    if len(canonical_matches) != 1 or not canonical_matches[0].path.is_dir():
        failures.append("canonical branch is not checked out in exactly one available worktree")
    else:
        canonical_path = canonical_matches[0].path
        failures.extend(worktree_failures(canonical_path, "canonical"))
        if rev_parse(canonical_path, "HEAD") != remote_main:
            failures.append("canonical HEAD does not match freshly fetched canonical remote HEAD")

    topic_worktrees = [
        item for item in worktrees if item.branch_ref == f"refs/heads/{plan.topic_branch}"
    ]
    if topic_worktrees:
        failures.append("target topic worktree still exists")

    local_after = rev_parse(control_repo, topic_ref)
    if plan.local_topic_present and local_after != plan.expected_head:
        failures.append("retained local topic branch changed or disappeared during cleanup")

    remote_after, remote_error = remote_branch_sha(
        control_repo, plan.remote, plan.topic_branch
    )
    if remote_error:
        failures.append(remote_error)
    elif plan.delete_remote and remote_after is not None:
        failures.append("requested remote topic branch still exists")

    post_refs, refs_error = snapshot_refs(control_repo)
    if refs_error or post_refs is None:
        return _execution_failure(
            [refs_error or "local ref postcondition snapshot is unavailable"],
            effects_started,
        )

    baseline_refs = dict(plan.baseline_refs)
    allowed_refs = {
        f"refs/remotes/{plan.remote}/{plan.topic_branch}",
        f"refs/heads/{plan.branch}",
        f"refs/remotes/{plan.remote}/{plan.branch}",
    }
    for ref in sorted((set(baseline_refs) | set(post_refs)) - allowed_refs):
        if baseline_refs.get(ref) != post_refs.get(ref):
            failures.append(f"unrelated or retained ref changed during cleanup: {ref}")

    allowed_paths = {
        str(path)
        for path in (plan.target_worktree, plan.canonical_worktree)
        if path is not None
    }
    baseline_worktrees = {
        item for item in plan.baseline_worktrees if item[0] not in allowed_paths
    }
    post_worktrees = {
        (str(item.path), item.branch_ref, item.head)
        for item in worktrees
        if str(item.path) not in allowed_paths
    }
    if baseline_worktrees != post_worktrees:
        failures.append("unrelated worktree registration changed during cleanup")

    if failures:
        return _execution_failure(failures, effects_started)
    return ExecutionResult(True, (), effects_started)


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
    result = execute_plan(plan, Path(args.repo))
    if not result.ok:
        if result.effects_started:
            print("SAFE CLEANUP: INCOMPLETE")
            print("Some authorized effects may already have completed; no force recovery was attempted.")
        else:
            print("SAFE CLEANUP: BLOCKED")
            print("No cleanup effect was authorized after revalidation.")
        for failure in result.failures:
            print(f"- {failure}")
        return 3

    print("POST-MERGE CLOSEOUT: PASS")
    print("cleanup: completed")
    print(f"canonical: {plan.branch}")
    print("next_task_checkout: ready")
    if plan.local_topic_present:
        print("local_topic_branch: retained by v1")
    if plan.remote_tracking_sha is not None:
        print("remote_tracking_ref: retained by v1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
