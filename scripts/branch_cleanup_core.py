"""Pure branch-audit interpretation and evidence generation; no process/network I/O."""

from __future__ import annotations

import json
from typing import Any, Iterable


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


class AuditError(RuntimeError):
    """Fail-closed audit error."""


def parse_json(text: str, context: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuditError(f"{context} returned invalid JSON: {exc}") from exc


def validate_repository(repository: str) -> str:
    if repository.count("/") != 1 or any(not part for part in repository.split("/")):
        raise AuditError("--repository must be OWNER/REPO")
    return repository


def repository_identity(payload: Any) -> tuple[str, str]:
    """Interpret canonical repository identity returned by GitHub."""

    if not isinstance(payload, dict):
        raise AuditError("repository metadata was not a JSON object")
    full_name = payload.get("full_name")
    default_branch = payload.get("default_branch")
    if (
        not isinstance(full_name, str)
        or full_name.count("/") != 1
        or any(not part for part in full_name.split("/"))
    ):
        raise AuditError("repository full_name is missing or invalid")
    if not isinstance(default_branch, str) or not default_branch:
        raise AuditError("repository default_branch is missing")
    return full_name, default_branch


def branch_records(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
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


def pull_map(repository: str, items: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    mapped: dict[str, list[dict[str, Any]]] = {}
    for pr in items:
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


def build_inventory(
    repository: str,
    retained: set[str],
    *,
    identity: tuple[str, str],
    branch_items: Iterable[dict[str, Any]],
    pull_items: Iterable[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    """Build evidence from supplied GitHub data, with the clock supplied by the caller."""
    canonical_repository, default_branch = identity
    branches = branch_records(branch_items)
    prs = pull_map(canonical_repository, pull_items)
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
        "generated_at": generated_at,
        "source_host": GITHUB_HOST,
        "repository": canonical_repository,
        "requested_repository": repository,
        "default_branch": default_branch,
        "retained": sorted(retained),
        "mutation_capability": "NONE",
        "branches": rows,
    }


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


def evidence_json(value: Any) -> str:
    """Serialize evidence without writing files."""
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"
