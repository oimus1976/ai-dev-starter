"""GitHub read adapter for branch audit: metadata, branches, and pull requests only.

The current implementation uses authenticated gh GET reads on github.com. This
module is a review boundary, not a sandbox against arbitrary future Python code.
"""

from __future__ import annotations

import subprocess
from typing import Any
from urllib.parse import quote

if __package__:
    from .branch_cleanup_core import AuditError, GITHUB_HOST, parse_json, validate_repository
else:
    from branch_cleanup_core import AuditError, GITHUB_HOST, parse_json, validate_repository


def _get(endpoint: str) -> Any:
    """Perform the helper's only native operation: a fixed GET-style github.com API read."""

    completed = subprocess.run(
        ["gh", "api", "--hostname", GITHUB_HOST, endpoint],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        stdout = completed.stdout.decode("utf-8")
        stderr = completed.stderr.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError(f"native command returned non-UTF-8 output: {exc}") from exc
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or "no diagnostic output"
        raise AuditError(
            f"gh api GET {GITHUB_HOST}/{endpoint} failed with exit {completed.returncode}: {detail}"
        )
    if not stdout.strip():
        return None
    return parse_json(stdout, endpoint)


def _repository_path(repository: str) -> str:
    # Encode each segment so operator input cannot inject a query or CLI option.
    return "/".join(quote(part, safe="") for part in validate_repository(repository).split("/"))


def repository_metadata(repository: str) -> Any:
    return _get(f"repos/{_repository_path(repository)}")


def branches(repository: str) -> list[dict[str, Any]]:
    return _paged_list(repository, "branches")


def pulls(repository: str) -> list[dict[str, Any]]:
    return _paged_list(repository, "pulls")


def _paged_list(repository: str, resource: str) -> list[dict[str, Any]]:
    if resource not in {"branches", "pulls"}:
        raise AuditError("unsupported audit resource")
    repository = _repository_path(repository)
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        query = f"per_page=100&page={page}"
        if resource == "pulls":
            query = f"state=all&{query}"
        endpoint = f"repos/{repository}/{resource}?{query}"
        payload = _get(endpoint)
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
