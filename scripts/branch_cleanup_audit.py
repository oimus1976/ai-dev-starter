#!/usr/bin/env python3
"""Authoritative, fail-closed GitHub branch cleanup audit.

The helper intentionally separates inventory/classification from destructive
mutation. GitHub is the authority for current remote branch existence and PR
state. Native command success is determined only by exit status; stderr is
captured as diagnostic evidence and is never treated as failure by itself.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote


CLASS_PROTECTED = "PROTECTED"
CLASS_MERGED = "MERGED_DELETE_CANDIDATE"
CLASS_MERGED_MOVED = "MERGED_HEAD_MOVED_REVIEW_REQUIRED"
CLASS_OPEN = "OPEN_PR"
CLASS_CLOSED = "CLOSED_UNMERGED_REVIEW_REQUIRED"
CLASS_NO_PR = "NO_PR_REVIEW_REQUIRED"
CLASS_RETAINED = "RETAINED_LONG_LIVED"


@dataclass(frozen=True)
class NativeResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class AuditError(RuntimeError):
    """Failure before any protected cleanup effect begins."""


class AuditIncompleteError(AuditError):
    """Failure after a cleanup effect command began or completed."""


def run_native(args: Sequence[str], *, cwd: Path | None = None) -> NativeResult:
    """Run a native command without shell re-parsing.

    Passing an argv sequence preserves complex arguments (including jq-like
    expressions containing spaces/pipes) as one argument. stdout/stderr are
    decoded explicitly as UTF-8 so GitHub CLI JSON is not decoded through a
    Windows legacy console code page such as cp932. Returncode is authoritative.
    """

    completed = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        stdout = completed.stdout.decode("utf-8")
        stderr = completed.stderr.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError(f"native command returned non-UTF-8 output: {exc}") from exc
    return NativeResult(tuple(str(arg) for arg in args), completed.returncode, stdout, stderr)


def require_ok(result: NativeResult, context: str) -> str:
    if not result.ok:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise AuditError(f"{context} failed with exit {result.returncode}: {detail}")
    return result.stdout


def run_gh(args: Sequence[str]) -> NativeResult:
    return run_native(["gh", *args])


def parse_json(text: str, context: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuditError(f"{context} returned invalid JSON: {exc}") from exc


def detect_repository(explicit: str | None) -> str:
    if explicit:
        if explicit.count("/") != 1 or any(not part for part in explicit.split("/")):
            raise AuditError("--repository must be OWNER/REPO")
        return explicit
    result = run_gh(["repo", "view", "--json", "nameWithOwner"])
    payload = parse_json(require_ok(result, "repository detection"), "repository detection")
    repository = payload.get("nameWithOwner") if isinstance(payload, dict) else None
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise AuditError("could not determine OWNER/REPO from gh repo view")
    return repository


def api_json(endpoint: str) -> Any:
    result = run_gh(["api", endpoint])
    text = require_ok(result, f"gh api GET {endpoint}")
    if not text.strip():
        return None
    return parse_json(text, endpoint)


def paged_list(repository: str, resource: str, *, state: str | None = None) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        query = f"per_page=100&page={page}"
        if state is not None:
            query = f"state={quote(state, safe='')}&{query}"
        endpoint = f"repos/{repository}/{resource}?{query}"
        payload = api_json(endpoint)
        if not isinstance(payload, list):
            raise AuditError(f"{resource} page {page} was not a JSON array")
        for item in payload:
            if not isinstance(item, dict):
                raise AuditError(f"{resource} page {page} contained a non-object item")
            items.append(item)
        if len(payload) < 100:
            break
        page += 1
    return items


def repository_default_branch(repository: str) -> str:
    payload = api_json(f"repos/{repository}")
    branch = payload.get("default_branch") if isinstance(payload, dict) else None
    if not isinstance(branch, str) or not branch:
        raise AuditError("repository default_branch is missing")
    return branch


def branch_records(repository: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in paged_list(repository, "branches"):
        name = item.get("name")
        commit = item.get("commit")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        protected = item.get("protected")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(sha, str)
            or not sha
            or not isinstance(protected, bool)
        ):
            raise AuditError("branch response omitted name, commit SHA, or protected state")
        result[name] = {"sha": sha, "protected": protected}
    return result


def branch_map(repository: str) -> dict[str, str]:
    return {name: record["sha"] for name, record in branch_records(repository).items()}


def pull_map(repository: str) -> dict[str, list[dict[str, Any]]]:
    mapped: dict[str, list[dict[str, Any]]] = {}
    for pr in paged_list(repository, "pulls", state="all"):
        head = pr.get("head")
        ref = head.get("ref") if isinstance(head, dict) else None
        head_repo = head.get("repo") if isinstance(head, dict) else None
        head_repo_name = head_repo.get("full_name") if isinstance(head_repo, dict) else None
        if head_repo_name != repository:
            continue
        if isinstance(ref, str) and ref:
            mapped.setdefault(ref, []).append(pr)
    return mapped


def pr_head_sha(pr: dict[str, Any]) -> str | None:
    head = pr.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    return sha if isinstance(sha, str) and sha else None


def classify_branch(
    branch: str,
    current_sha: str,
    prs: Iterable[dict[str, Any]],
    *,
    default_branch: str,
    retained: set[str],
    github_protected: bool = False,
) -> str:
    if branch == default_branch or github_protected:
        return CLASS_PROTECTED
    if branch in retained:
        return CLASS_RETAINED

    prs = list(prs)
    if not prs:
        return CLASS_NO_PR
    if any(pr.get("state") == "open" for pr in prs):
        return CLASS_OPEN

    merged = [pr for pr in prs if pr.get("merged_at") is not None]
    if any(pr_head_sha(pr) == current_sha for pr in merged):
        return CLASS_MERGED
    if merged:
        return CLASS_MERGED_MOVED

    if all(pr.get("state") == "closed" and pr.get("merged_at") is None for pr in prs):
        return CLASS_CLOSED
    return CLASS_CLOSED


def compact_prs(prs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for pr in prs:
        compact.append(
            {
                "number": pr.get("number"),
                "state": pr.get("state"),
                "merged_at": pr.get("merged_at"),
                "head_sha": pr_head_sha(pr),
                "title": pr.get("title"),
                "html_url": pr.get("html_url"),
            }
        )
    return compact


def build_inventory(repository: str, retained: set[str]) -> dict[str, Any]:
    default_branch = repository_default_branch(repository)
    branches = branch_records(repository)
    prs = pull_map(repository)
    rows: list[dict[str, Any]] = []
    for branch, record in sorted(branches.items()):
        sha = record["sha"]
        branch_prs = prs.get(branch, [])
        rows.append(
            {
                "branch": branch,
                "sha": sha,
                "github_protected": record["protected"],
                "classification": classify_branch(
                    branch,
                    sha,
                    branch_prs,
                    default_branch=default_branch,
                    retained=retained,
                    github_protected=record["protected"],
                ),
                "pull_requests": compact_prs(branch_prs),
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": repository,
        "default_branch": default_branch,
        "retained": sorted(retained),
        "branches": rows,
    }


def audit_directory(repository: str, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit
    else:
        safe_repo = repository.replace("/", "-")
        path = Path(tempfile.gettempdir()) / f"{safe_repo}-branch-audit"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summarize(inventory: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in inventory["branches"]:
        classification = row["classification"]
        counts[classification] = counts.get(classification, 0) + 1
    return counts


def merged_targets(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in inventory["branches"] if row["classification"] == CLASS_MERGED]


def load_reviewed_targets(path: Path) -> list[dict[str, str]]:
    payload = parse_json(path.read_text(encoding="utf-8"), str(path))
    if not isinstance(payload, list):
        raise AuditError("reviewed target manifest must be a JSON array")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AuditError(f"reviewed target {index} is not an object")
        branch = item.get("branch")
        expected_sha = item.get("expected_sha")
        if not isinstance(branch, str) or not branch or not isinstance(expected_sha, str) or not expected_sha:
            raise AuditError(f"reviewed target {index} requires branch and expected_sha")
        if branch in seen:
            raise AuditError(f"duplicate reviewed branch: {branch}")
        seen.add(branch)
        result.append({"branch": branch, "expected_sha": expected_sha})
    return result


def validate_reviewed_targets(
    inventory: dict[str, Any], reviewed: list[dict[str, str]]
) -> list[dict[str, Any]]:
    by_name = {row["branch"]: row for row in inventory["branches"]}
    validated: list[dict[str, Any]] = []
    for target in reviewed:
        row = by_name.get(target["branch"])
        if row is None:
            raise AuditError(f"reviewed branch is no longer present: {target['branch']}")
        if row["classification"] != CLASS_CLOSED:
            raise AuditError(
                f"reviewed branch {target['branch']} is {row['classification']}, expected {CLASS_CLOSED}"
            )
        if row["sha"] != target["expected_sha"]:
            raise AuditError(
                f"reviewed branch {target['branch']} moved: expected {target['expected_sha']}, got {row['sha']}"
            )
        validated.append(row)
    return validated


def remote_urls(*, push: bool) -> list[str]:
    args = ["git", "remote", "get-url"]
    if push:
        args.append("--push")
    args += ["--all", "origin"]
    result = run_native(args)
    text = require_ok(result, "git origin push URL lookup" if push else "git origin fetch URL lookup")
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_github_repository(url: str) -> str:
    patterns = (
        r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$",
        r"ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?$",
        r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    raise AuditError("origin URL is not a recognized github.com OWNER/REPO remote")


def ensure_origin_matches(repository: str) -> None:
    fetch_urls = remote_urls(push=False)
    push_urls = remote_urls(push=True)
    if len(fetch_urls) != 1 or len(push_urls) != 1:
        raise AuditError(
            "origin must resolve to exactly one fetch URL and one push URL before branch deletion"
        )
    fetch_repo = parse_github_repository(fetch_urls[0])
    push_repo = parse_github_repository(push_urls[0])
    if fetch_repo.casefold() != repository.casefold():
        raise AuditError(f"origin fetch repository mismatch: expected {repository}, got {fetch_repo}")
    if push_repo.casefold() != repository.casefold():
        raise AuditError(f"origin push repository mismatch: expected {repository}, got {push_repo}")


def delete_branch_with_lease(branch: str, expected_sha: str) -> NativeResult:
    lease = f"--force-with-lease=refs/heads/{branch}:{expected_sha}"
    refspec = f":refs/heads/{branch}"
    result = run_native(["git", "push", lease, "origin", refspec])
    require_ok(result, f"exact-lease delete {branch}")
    return result


def _row_by_branch(inventory: dict[str, Any], branch: str) -> dict[str, Any] | None:
    return next((row for row in inventory["branches"] if row["branch"] == branch), None)


def _raise_phase_error(message: str, results: list[dict[str, Any]]) -> None:
    if results:
        raise AuditIncompleteError(message)
    raise AuditError(message)


def execute_deletion(
    repository: str,
    targets: list[dict[str, Any]],
    *,
    retained: set[str],
    audit_dir: Path,
) -> dict[str, Any]:
    target_names = [row["branch"] for row in targets]
    if len(target_names) != len(set(target_names)):
        raise AuditError("deletion target set contains duplicates")
    if any(name in retained for name in target_names):
        raise AuditError("deletion target intersects retained branches")
    if any(row.get("classification") not in {CLASS_MERGED, CLASS_CLOSED} for row in targets):
        raise AuditError("deletion target contains a non-authorized classification")

    ensure_origin_matches(repository)
    pre_inventory = build_inventory(repository, retained)
    must_remain = {
        row["branch"]
        for row in pre_inventory["branches"]
        if row["classification"] in {CLASS_PROTECTED, CLASS_RETAINED}
    }
    overlap = sorted(set(target_names) & must_remain)
    if overlap:
        raise AuditError(f"deletion target became protected/retained: {', '.join(overlap)}")

    results: list[dict[str, Any]] = []
    for planned in targets:
        branch = planned["branch"]
        expected_sha = planned["sha"]
        expected_classification = planned["classification"]
        try:
            fresh_inventory = build_inventory(repository, retained)
        except AuditError as exc:
            _raise_phase_error(f"fresh pre-effect inventory failed for {branch}: {exc}", results)
            raise AssertionError("unreachable")
        current = _row_by_branch(fresh_inventory, branch)
        if current is None:
            _raise_phase_error(f"pre-effect branch disappeared before delete: {branch}", results)
        if current["sha"] != expected_sha:
            _raise_phase_error(
                f"pre-effect branch identity changed for {branch}: expected {expected_sha}, got {current['sha']}",
                results,
            )
        if current["classification"] != expected_classification:
            _raise_phase_error(
                f"pre-effect classification changed for {branch}: expected {expected_classification}, got {current['classification']}",
                results,
            )

        try:
            native = delete_branch_with_lease(branch, expected_sha)
            results.append(
                {
                    "branch": branch,
                    "expected_sha": expected_sha,
                    "classification": expected_classification,
                    "result": "DELETE_EXIT_0",
                    "stderr": native.stderr,
                }
            )
        except AuditError as exc:
            results.append(
                {
                    "branch": branch,
                    "expected_sha": expected_sha,
                    "classification": expected_classification,
                    "result": "DELETE_FAILED",
                    "error": str(exc),
                }
            )
            write_json(audit_dir / "delete-results.json", results)
            raise AuditIncompleteError(
                f"delete command failed or became ambiguous for {branch}; stop and inspect audit evidence"
            ) from exc

    try:
        after_inventory = build_inventory(repository, retained)
    except AuditError as exc:
        write_json(audit_dir / "delete-results.json", results)
        raise AuditIncompleteError(
            f"post-delete authoritative inventory failed after effects: {exc}"
        ) from exc

    after_names = {row["branch"] for row in after_inventory["branches"]}
    residual = sorted(name for name in target_names if name in after_names)
    missing_must_remain = sorted(name for name in must_remain if name not in after_names)
    verification = {
        "targets": target_names,
        "results": results,
        "remaining_target_branches": residual,
        "remaining_target_count": len(residual),
        "required_retained_or_protected": sorted(must_remain),
        "missing_retained_or_protected": missing_must_remain,
    }
    write_json(audit_dir / "delete-results.json", verification)
    if residual:
        raise AuditIncompleteError(
            f"post-delete verification found residual targets: {', '.join(residual)}"
        )
    if missing_must_remain:
        raise AuditIncompleteError(
            "post-delete verification found protected/retained branches missing: "
            + ", ".join(missing_must_remain)
        )
    return verification


def print_summary(inventory: dict[str, Any], audit_dir: Path) -> None:
    counts = summarize(inventory)
    print(f"Repository: {inventory['repository']}")
    print(f"Current GitHub branches: {len(inventory['branches'])}")
    for classification in (
        CLASS_PROTECTED,
        CLASS_RETAINED,
        CLASS_MERGED,
        CLASS_MERGED_MOVED,
        CLASS_OPEN,
        CLASS_CLOSED,
        CLASS_NO_PR,
    ):
        print(f"{classification}: {counts.get(classification, 0)}")
    print(f"Audit directory: {audit_dir}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", help="GitHub repository as OWNER/REPO; defaults to gh repo view")
    parser.add_argument("--audit-dir", type=Path, help="directory for audit JSON; defaults below the OS temp directory")
    parser.add_argument(
        "--retain",
        action="append",
        default=[],
        metavar="BRANCH",
        help="explicit long-lived branch to classify as retained; repeatable",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--delete-merged",
        action="store_true",
        help="target only current branches whose exact current SHA matches a merged same-repository PR head",
    )
    group.add_argument(
        "--delete-reviewed",
        type=Path,
        metavar="MANIFEST.json",
        help="target explicit human-reviewed closed-unmerged branches using branch+expected_sha",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform the selected deletion; without this flag deletion modes are plan-only",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        repository = detect_repository(args.repository)
        retained = set(args.retain)
        inventory = build_inventory(repository, retained)
        out_dir = audit_directory(repository, args.audit_dir)
        write_json(out_dir / "inventory.json", inventory)
        print_summary(inventory, out_dir)

        targets: list[dict[str, Any]] = []
        if args.delete_merged:
            targets = merged_targets(inventory)
        elif args.delete_reviewed:
            reviewed = load_reviewed_targets(args.delete_reviewed)
            targets = validate_reviewed_targets(inventory, reviewed)

        if args.delete_merged or args.delete_reviewed:
            write_json(out_dir / "delete-plan.json", targets)
            print(f"Delete targets: {len(targets)}")
            if not args.execute:
                print("Mode: PLAN ONLY")
                return 0
            verification = execute_deletion(
                repository,
                targets,
                retained=retained,
                audit_dir=out_dir,
            )
            print("Mode: EXECUTE")
            print(f"Targets still present: {verification['remaining_target_count']}")
        elif args.execute:
            raise AuditError("--execute requires --delete-merged or --delete-reviewed")
        return 0
    except AuditIncompleteError as exc:
        print(f"BRANCH CLEANUP: INCOMPLETE: {exc}", file=sys.stderr)
        return 3
    except (AuditError, OSError) as exc:
        print(f"BRANCH CLEANUP: BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())