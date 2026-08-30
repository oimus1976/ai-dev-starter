#!/usr/bin/env python3
"""Minimal, dependency-free starter initializer.

This only initializes project identity. Authority, risk, enforcement, and current
state remain deliberate human/project decisions and must be completed before the
baseline check can pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def toml_string(value: str) -> str:
    # JSON string syntax for these single-line values is TOML basic-string compatible.
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()

    if not args.name.strip() or not args.purpose.strip():
        parser.error("name and purpose must be non-empty")
    if any(ch in args.name + args.purpose for ch in "\r\n"):
        parser.error("name and purpose must be single-line values")

    profile_path = ROOT / "PROJECT_PROFILE.toml"
    status_path = ROOT / "PROJECT_STATUS.md"

    # Preflight every file/marker before writing either file so a malformed starter
    # cannot leave project identity only partially initialized.
    profile = profile_path.read_text(encoding="utf-8")
    status = status_path.read_text(encoding="utf-8")

    if 'name = "TODO"' not in profile or 'purpose = "TODO"' not in profile:
        raise SystemExit("project identity placeholders are not in the expected starter state")

    status_marker = "- **Goal:** TODO"
    if status_marker not in status:
        raise SystemExit("PROJECT_STATUS goal placeholder is not in the expected starter state")

    new_profile = profile.replace('name = "TODO"', f"name = {toml_string(args.name)}", 1)
    new_profile = new_profile.replace('purpose = "TODO"', f"purpose = {toml_string(args.purpose)}", 1)
    new_status = status.replace(status_marker, f"- **Goal:** {args.purpose}", 1)

    profile_path.write_text(new_profile, encoding="utf-8")
    status_path.write_text(new_status, encoding="utf-8")

    print("Initialized project name/purpose.")
    print("Next: complete PROJECT_PROFILE.toml, PROJECT_STATUS.md, and project-specific CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
