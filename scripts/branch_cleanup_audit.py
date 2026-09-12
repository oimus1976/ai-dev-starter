#!/usr/bin/env python3
"""Audit current github.com branches and write evidence for human review only."""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# Keep direct CLI execution from leaving local bytecode residue.
sys.dont_write_bytecode = True
if __package__:
    from . import branch_cleanup_core as core
    from . import branch_cleanup_github as github
else:
    import branch_cleanup_core as core
    import branch_cleanup_github as github


def collect_inventory(repository: str, retained: set[str]) -> dict[str, Any]:
    """Read canonical identity first, then compose the read adapter and pure core."""
    identity = core.repository_identity(github.repository_metadata(repository))
    canonical_repository, _ = identity
    return core.build_inventory(
        repository,
        retained,
        identity=identity,
        branch_items=github.branches(canonical_repository),
        pull_items=github.pulls(canonical_repository),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def audit_directory(repository: str, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit
    else:
        safe_repo = repository.replace("/", "-")
        path = Path(tempfile.gettempdir()) / f"{safe_repo}-branch-audit"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, value: Any) -> None:
    path.write_text(core.evidence_json(value), encoding="utf-8")


def print_summary(inventory: dict[str, Any], audit_dir: Path) -> None:
    counts = core.summarize(inventory)
    print(f"Repository: {inventory['repository']}")
    print(f"GitHub host: {inventory['source_host']}")
    print(f"Current GitHub branches: {len(inventory['branches'])}")
    for classification in (
        core.CLASS_PROTECTED,
        core.CLASS_RETAINED,
        core.CLASS_MERGED,
        core.CLASS_MERGED_MOVED,
        core.CLASS_OPEN,
        core.CLASS_CLOSED,
        core.CLASS_NO_PR,
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
        repository = core.validate_repository(args.repository)
        retained = set(args.retain)
        inventory = collect_inventory(repository, retained)
        out_dir = audit_directory(inventory["repository"], args.audit_dir)
        write_json(out_dir / "inventory.json", inventory)
        write_json(out_dir / "review-candidates.json", core.review_candidates(inventory))
        print_summary(inventory, out_dir)
        return 0
    except (core.AuditError, OSError) as exc:
        print(f"BRANCH AUDIT: BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
