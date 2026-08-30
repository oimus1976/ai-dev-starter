#!/usr/bin/env python3
"""Dependency-free structural and baseline-consistency check.

Requires Python 3.11+ for tomllib. GitHub Actions uses Python 3.12.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_REPOSITORY = "oimus1976/ai-dev-starter"

REQUIRED = [
    ".gitignore",
    "README.md",
    "BASELINE.md",
    "AGENTS.md",
    "PROJECT_PROFILE.toml",
    "PROJECT_STATUS.md",
    "CHANGELOG.md",
    "docs/BASELINE_PROVENANCE.md",
    "docs/adr/README.md",
    ".github/pull_request_template.md",
    ".github/workflows/policy-check.yml",
    ".github/workflows/ci.yml",
    "scripts/bootstrap.py",
]

TIER_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
COMP_ORDER = {"C0": 0, "C1": 1, "C2": 2}
FACET_MIN_TIER = {
    "PRIVATE_DATA": "R2",
    "EXTERNAL_WRITE": "R2",
    "AI_AGENT": "R2",  # Runtime agent authority/mutation, not AI-assisted coding.
    "PLATFORM_DEPENDENT": "R2",
    "WORKFLOW_PERMISSION": "R2",
    "DESTRUCTIVE_IO": "R3",
    "CREDENTIALS": "R3",
    "DEPLOYMENT": "R3",
    "SECURITY_BOUNDARY": "R3",
    "HIGH_AUTHORITY": "R3",
    "CRYPTOGRAPHY": "R3",
}
TIER_MIN_COMP = {"R0": "C0", "R1": "C1", "R2": "C1", "R3": "C2"}
ALLOWED_LIFECYCLES = {"experimental", "active", "production"}
ALLOWED_ENFORCEMENT_STATES = {"DECLARED", "ENFORCED", "VERIFIED", "UNKNOWN"}

parser = argparse.ArgumentParser()
parser.add_argument(
    "--repository",
    default=None,
    help="Current owner/repo identity. GitHub Actions should pass github.repository.",
)
args = parser.parse_args()
is_template_repository = args.repository == TEMPLATE_REPOSITORY

errors: list[str] = []


def need(mapping: dict, path: tuple[str, ...]):
    current = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            errors.append(f"PROJECT_PROFILE.toml missing key: {'.'.join(path)}")
            return None
        current = current[key]
    return current


for rel in REQUIRED:
    if not (ROOT / rel).is_file():
        errors.append(f"missing required file: {rel}")

profile_path = ROOT / "PROJECT_PROFILE.toml"
profile: dict = {}
if profile_path.is_file():
    try:
        with profile_path.open("rb") as f:
            profile = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        errors.append(f"PROJECT_PROFILE.toml is not valid TOML: {exc}")

if profile:
    if need(profile, ("baseline", "version")) != "0.5":
        errors.append("PROJECT_PROFILE.toml baseline.version must be 0.5")

    lifecycle = need(profile, ("project", "lifecycle"))
    if lifecycle not in ALLOWED_LIFECYCLES:
        errors.append(f"invalid project.lifecycle: {lifecycle!r}")

    facets = need(profile, ("risk", "persistent_facets"))
    tier = need(profile, ("risk", "default_tier"))
    comp = need(profile, ("comprehension", "required_level"))

    if not isinstance(facets, list) or not all(isinstance(x, str) for x in facets):
        errors.append("risk.persistent_facets must be an array of strings")
        facets = []
    else:
        unknown = sorted(set(facets) - set(FACET_MIN_TIER))
        if unknown:
            errors.append(f"unknown risk facets: {', '.join(unknown)}")

    if tier not in TIER_ORDER:
        errors.append(f"invalid risk.default_tier: {tier!r}")
    if comp not in COMP_ORDER:
        errors.append(f"invalid comprehension.required_level: {comp!r}")

    if tier in TIER_ORDER:
        required_tier = "R0"
        for facet in facets:
            min_tier = FACET_MIN_TIER.get(facet)
            if min_tier and TIER_ORDER[min_tier] > TIER_ORDER[required_tier]:
                required_tier = min_tier
        if TIER_ORDER[tier] < TIER_ORDER[required_tier]:
            errors.append(
                f"risk downgrade: facets require at least {required_tier}, but default_tier is {tier}"
            )

        if comp in COMP_ORDER:
            required_comp = TIER_MIN_COMP[tier]
            if COMP_ORDER[comp] < COMP_ORDER[required_comp]:
                errors.append(
                    f"comprehension downgrade: {tier} requires at least {required_comp}, but required_level is {comp}"
                )

    if need(profile, ("governance", "ready")) != "human_final":
        errors.append("house policy violation: governance.ready must be human_final")
    if need(profile, ("governance", "merge")) != "human_final":
        errors.append("house policy violation: governance.merge must be human_final")

    for branch in ("main_direct_write", "required_ci"):
        state = need(profile, ("enforcement", branch, "state"))
        if state not in ALLOWED_ENFORCEMENT_STATES:
            errors.append(f"invalid enforcement.{branch}.state: {state!r}")

    if not is_template_repository:
        def find_placeholders(value, path: tuple[str, ...] = ()):
            if isinstance(value, dict):
                for key, child in value.items():
                    find_placeholders(child, path + (str(key),))
            elif isinstance(value, list):
                for i, child in enumerate(value):
                    find_placeholders(child, path + (str(i),))
            elif isinstance(value, str) and value in {"TODO", "TODO_OR_NA"}:
                errors.append(
                    f"PROJECT_PROFILE.toml still contains required starter placeholder at {'.'.join(path)}: {value}"
                )
        find_placeholders(profile)

status_path = ROOT / "PROJECT_STATUS.md"
if status_path.is_file():
    text = status_path.read_text(encoding="utf-8")
    for marker in ["## 30-second state", "## Recovery / first diagnostic entry points"]:
        if marker not in text:
            errors.append(f"PROJECT_STATUS.md missing section: {marker}")
    if not is_template_repository and "TODO" in text:
        errors.append(
            "PROJECT_STATUS.md still contains TODO; replace each with a concrete value or explicit 'none/N/A'"
        )

ci_path = ROOT / ".github/workflows/ci.yml"
if ci_path.is_file() and not is_template_repository:
    if "project-ci-not-configured" in ci_path.read_text(encoding="utf-8"):
        errors.append(
            "project CI is still the intentionally failing starter placeholder; "
            "replace .github/workflows/ci.yml before accepting tracked implementation"
        )

if errors:
    print("BASELINE CHECK: FAIL")
    for err in errors:
        print(f"- {err}")
    sys.exit(1)

print("BASELINE CHECK: PASS")
