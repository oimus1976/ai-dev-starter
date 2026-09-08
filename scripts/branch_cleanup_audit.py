#!/usr/bin/env python3
"""Authoritative, fail-closed GitHub branch audit.

This helper is intentionally audit-only. It reads current branch and pull-request
state from github.com, classifies current branches, and emits durable review
evidence. It contains no remote branch mutation path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote


GITHUB_HOST = "github.com"

CLASS_PROTECTED = "PROTECTED"
CLASS_RETAINED = "RETAINED_LONG_LIVED"
CLASS_MERGED = "MERGED_REVIEW_CANDIDATE"
CLASS_MERGED_MOVED = "MERGED_HEAD_MOVED_REVIEW_REQUIRED"
CLASS_OPEN = "OPEN_PR"
CLASS_CLOSED = "CLOSED_UNMERGED_REVIEW_REQUIRED"
CLASS_NO_PR = "NO_PR_REVIEW_REQUIRED"

REVIEW_CLASSES = {
    CLASS_MERGED,
    CLASS_MERGED_MOVED,
    CLASS_CLOSED,
    CLASS_NO_PR,
}


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
    """Fail-closed audit error."""


def run_native(args: Sequence[str], *, cwd: Path | None = None) -> NativeResult:
    """Run a native command with argv preserved and UTF-8 output decoding.

    Native exit status is authoritative. stderr is diagnostic output only.
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
    return NativeResult(
        tuple(str(arg) for arg in args),
        completed.returncode,
        stdout,
        stderr,
    )


def require_ok(result: NativeResult, context: str) -> str:
    if not result.ok:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise AuditError(f"{context} failed with exit {result.returncode}: {detail}")
    return result.stdout


def parse_json(text: str, context: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuditError(f"{context} returned invalid JSON: {exc}") from exc


def validate_repository(repository: str) -> str:
    if repository.count("/") != 1 or any(not part for part in repository.split("/")):
        raise AuditError("--repository must be OWNER/REPO")
    return repository


def api_json(endpoint: str) -> Any:
    """Read JSON from github.com explicitly, ignoring GH_HOST for authority."""

    result = run_native(["gh", "api", "--hostname", GITHUB_HOST, endpoint])
    text = require_ok(result, f"gh api GET {GITHUB_HOST}/{endpoint}")
    if not text.strip():
        return None
    return parse_json(text, endpoint)


def repository_identity(repository: str) -> tuple[str, str]:
    """Resolve operator input to GitHub's canonical full_name and default branch."""

    requested = validate_repository(repository)
    payload = api_json(f"repos/{requested}")
    if not isinstance(payload, dict):
        raise AuditError("repository metadata was not a JSON object")
    full_name = payload.get("full_name")
    default_branch = payload.get("default_branch")
    if not isinstance(full_name, str) or full_name.count("/") != 1:
        raise AuditError("repository full_name is missing or invalid")
    if not isinstance(default_branch, str) or not default_branch:
        raise AuditError("repository default_branch is missing")
    return full_name, default_branch


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
    canonical_repository, default_branch = repository_identity(repository)
    branches = branch_records(canonical_repository)
    prs = pull_map(canonical_repository)
    rows: list[dict[str, Any]] = []
    for branch, record in sorted(branches.items()):
        branch_prs = prs.get(branch, [])
        rows.append(
            {
                "branch": branch,
                "sha": record["sha"],
                "github_protected": record["protected"],
                "classification": classify_branch(
                    branch,
                    record["sha"],
                    branch_prs,
                    default_branch=default_branch,
                    retained=retained,
                    github_protected=record["protected"],
                ),
                "pull_requests": compact_prs(branch_prs),
            }
        )
    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_host": GITHUB_HOST,
        "repository": canonical_repository,
        "requested_repository": repository,
        "default_branch": default_branch,
        "retained": sorted(retained),
        "mutation_capability": "NONE",
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


def review_candidates(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in inventory["branches"]:
        if row["classification"] not in REVIEW_CLASSES:
            continue
        candidates.append(
            {
                "branch": row["branch"],
                "expected_sha": row["sha"],
                "classification": row["classification"],
                "pull_requests": row["pull_requests"],
                "human_review_required": True,
                "deletion_authority": False,
            }
        )
    return candidates


def print_summary(inventory: dict[str, Any], audit_dir: Path) -> None:
    counts = summarize(inventory)
    print(f"Repository: {inventory['repository']}")
    print(f"GitHub host: {inventory['source_host']}")
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
    print("Mutation capability: NONE")
    print(f"Audit directory: {audit_dir}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        required=True,
        help="GitHub repository as OWNER/REPO; github.com is the fixed authority host",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        help="directory for audit JSON; defaults below the OS temp directory",
    )
    parser.add_argument(
        "--retain",
        action="append",
        default=[],
        metavar="BRANCH",
        help="explicit long-lived branch to classify as retained; repeatable",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        repository = validate_repository(args.repository)
        retained = set(args.retain)
        inventory = build_inventory(repository, retained)
        out_dir = audit_directory(inventory["repository"], args.audit_dir)
        write_json(out_dir / "inventory.json", inventory)
        write_json(out_dir / "review-candidates.json", review_candidates(inventory))
        print_summary(inventory, out_dir)
        return 0
    except (AuditError, OSError) as exc:
        print(f"BRANCH AUDIT: BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
