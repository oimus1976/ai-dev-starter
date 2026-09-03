#!/usr/bin/env python3
"""Shared dependency-free Git state helpers for local closeout and cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
GIT_OPERATION_MARKERS = (
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "BISECT_LOG",
    "rebase-apply",
    "rebase-merge",
    "sequencer",
)


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    branch_ref: str | None
    head: str | None
    bare: bool = False
    detached: bool = False
    prunable: bool = False


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def resolve_worktree(requested: Path) -> tuple[Path | None, str | None]:
    requested = requested.resolve()
    if not requested.is_dir():
        return None, "requested repository/worktree path is unavailable"
    probe = git("rev-parse", "--show-toplevel", cwd=requested, check=False)
    if probe.returncode != 0:
        return None, "not a Git worktree/repository"
    candidate = Path(probe.stdout.strip()).resolve()
    if not candidate.is_dir():
        return None, "resolved Git worktree path is unavailable"
    return candidate, None


def git_dir_for(worktree: Path) -> Path | None:
    result = git("rev-parse", "--git-dir", cwd=worktree, check=False)
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = worktree / path
    return path.resolve()


def worktree_failures(worktree: Path, label: str) -> list[str]:
    failures: list[str] = []
    if not worktree.is_dir():
        return [f"{label} worktree path is unavailable"]

    status = git(
        "status", "--porcelain=v1", "--untracked-files=all", cwd=worktree, check=False
    )
    if status.returncode != 0:
        failures.append(f"could not read {label} working-tree status")
    elif status.stdout.strip():
        failures.append(f"{label} working tree is not clean")

    git_dir = git_dir_for(worktree)
    if git_dir is None:
        failures.append(f"could not resolve {label} Git directory")
        return failures

    for marker in GIT_OPERATION_MARKERS:
        if (git_dir / marker).exists():
            failures.append(f"{label} Git operation still in progress: {marker}")
    return failures


def cleanup_worktree_failures(worktree: Path, label: str) -> list[str]:
    """Return stricter failures required before cleanup may mutate a worktree.

    Ordinary Git cleanliness intentionally ignores ignored files and can also hide
    content behind assume-unchanged/skip-worktree index flags. Both states are
    acceptable for a non-destructive verifier but unsafe before removing a
    worktree or switching it as part of cleanup.
    """

    failures = worktree_failures(worktree, label)
    if not worktree.is_dir():
        return failures

    ignored = git(
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored=matching",
        cwd=worktree,
        check=False,
    )
    if ignored.returncode != 0:
        failures.append(f"could not inspect ignored files in {label} worktree")
    elif any(record.startswith("!! ") for record in ignored.stdout.split("\0") if record):
        failures.append(
            f"{label} worktree contains ignored files/directories that cleanup could overwrite or delete"
        )

    index_flags = git("ls-files", "-v", "-z", cwd=worktree, check=False)
    if index_flags.returncode != 0:
        failures.append(f"could not inspect {label} index visibility flags")
    else:
        hidden_flags = []
        for record in index_flags.stdout.split("\0"):
            if not record:
                continue
            flag = record[0]
            if flag == "S" or flag.islower():
                hidden_flags.append(flag)
        if hidden_flags:
            failures.append(
                f"{label} worktree uses skip-worktree/assume-unchanged index flags; cleanup cannot prove file contents safe"
            )

    staged = git("ls-files", "--stage", "-z", cwd=worktree, check=False)
    if staged.returncode != 0:
        failures.append(f"could not inspect {label} submodule entries")
    elif any(record.startswith("160000 ") for record in staged.stdout.split("\0") if record):
        failures.append(
            f"{label} worktree contains submodule gitlinks; destructive cleanup is unsupported in v1"
        )

    return failures


def list_worktrees(repo: Path) -> list[WorktreeInfo]:
    result = git("worktree", "list", "--porcelain", cwd=repo, check=False)
    if result.returncode != 0:
        return []

    raw_entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        if not raw_line:
            if current:
                raw_entries.append(current)
                current = {}
            continue
        key, separator, value = raw_line.partition(" ")
        current[key] = value if separator else ""
    if current:
        raw_entries.append(current)

    entries: list[WorktreeInfo] = []
    for entry in raw_entries:
        raw_path = entry.get("worktree")
        if not raw_path:
            continue
        entries.append(
            WorktreeInfo(
                path=Path(raw_path).resolve(),
                branch_ref=entry.get("branch"),
                head=entry.get("HEAD"),
                bare="bare" in entry,
                detached="detached" in entry,
                prunable="prunable" in entry,
            )
        )
    return entries


def worktrees_for_branch(repo: Path, branch: str) -> list[WorktreeInfo]:
    ref = f"refs/heads/{branch}"
    return [entry for entry in list_worktrees(repo) if entry.branch_ref == ref]


def canonical_worktree(repo: Path, branch: str) -> Path | None:
    matches = worktrees_for_branch(repo, branch)
    if len(matches) != 1:
        return None
    candidate = matches[0].path
    if not candidate.is_dir():
        return None
    return candidate


def rev_parse(repo: Path, ref: str) -> str | None:
    result = git("rev-parse", "--verify", ref, cwd=repo, check=False)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if FULL_SHA_RE.fullmatch(value) else None


def current_branch(repo: Path) -> str:
    result = git("branch", "--show-current", cwd=repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def refresh_remote_branch(repo: Path, remote: str, branch: str) -> tuple[str | None, str | None]:
    remote_ref = f"refs/remotes/{remote}/{branch}"
    refspec = f"+refs/heads/{branch}:{remote_ref}"
    result = git("fetch", remote, refspec, cwd=repo, check=False)
    if result.returncode != 0:
        return None, f"could not refresh {remote}/{branch}; remote freshness is unverified"
    sha = rev_parse(repo, remote_ref)
    if sha is None:
        return None, f"remote-tracking ref is unavailable: {remote}/{branch}"
    return sha, None


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = git("merge-base", "--is-ancestor", ancestor, descendant, cwd=repo, check=False)
    return result.returncode == 0


def remote_branch_sha(repo: Path, remote: str, branch: str) -> tuple[str | None, str | None]:
    ref = f"refs/heads/{branch}"
    result = git("ls-remote", "--heads", remote, ref, cwd=repo, check=False)
    if result.returncode != 0:
        return None, f"could not read remote topic branch {remote}/{branch}"
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None, None
    if len(lines) != 1:
        return None, f"remote topic branch identity is ambiguous: {remote}/{branch}"
    fields = lines[0].split()
    if len(fields) != 2 or fields[1] != ref or not FULL_SHA_RE.fullmatch(fields[0]):
        return None, f"remote topic branch identity is invalid: {remote}/{branch}"
    return fields[0], None


def github_repo_from_url(url: str) -> str | None:
    value = url.strip()
    if not value:
        return None

    if value.startswith("git@github.com:"):
        path = value[len("git@github.com:") :]
    else:
        parsed = urlparse(value)
        if (parsed.hostname or "").lower() != "github.com":
            return None
        path = parsed.path.lstrip("/")

    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def remote_repository_identity(repo: Path, remote: str) -> tuple[str | None, str | None]:
    fetch = git("remote", "get-url", remote, cwd=repo, check=False)
    push = git("remote", "get-url", "--push", remote, cwd=repo, check=False)
    if fetch.returncode != 0 or push.returncode != 0:
        return None, f"could not resolve {remote} repository identity"
    fetch_repo = github_repo_from_url(fetch.stdout.strip())
    push_repo = github_repo_from_url(push.stdout.strip())
    if fetch_repo is None or push_repo is None:
        return None, f"{remote} is not an unambiguous github.com repository remote"
    if fetch_repo.lower() != push_repo.lower():
        return None, f"{remote} fetch/push repository identities do not match"
    return fetch_repo, None


def delete_ref_cas(repo: Path, ref: str, expected: str) -> bool:
    result = git("update-ref", "-d", ref, expected, cwd=repo, check=False)
    return result.returncode == 0


def snapshot_refs(repo: Path) -> tuple[dict[str, str] | None, str | None]:
    """Return a complete local heads/remotes snapshot or an explicit error.

    Cleanup uses this as a postcondition boundary. An unreadable or malformed
    ref snapshot must never be represented as an empty set because that would
    turn uncertainty into a false PASS.
    """
    result = git(
        "for-each-ref",
        "--format=%(refname) %(objectname)",
        "refs/heads",
        "refs/remotes",
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        return None, "could not snapshot local refs"

    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        ref, sep, sha = line.partition(" ")
        if not sep or not ref or not FULL_SHA_RE.fullmatch(sha):
            return None, "local ref snapshot contained an invalid entry"
        refs[ref] = sha
    return refs, None
