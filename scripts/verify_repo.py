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
PROJECT_CI = Path(".github/workflows/project-ci.yml")

REQUIRED = [
    ".gitignore",
    "README.md",
    "BASELINE.md",
    "AGENTS.md",
    "PROJECT_PROFILE.toml",
    "PROJECT_STATUS.md",
    "CHANGELOG.md",
    "docs/BASELINE_PROVENANCE.md",
    "docs/branch-cleanup-policy.md",
    "docs/adr/README.md",
    ".github/pull_request_template.md",
    ".github/workflows/policy-check.yml",
    "scripts/bootstrap.py",
    "scripts/closeout_state.py",
    "scripts/verify_local_closeout.py",
    "scripts/post_merge_cleanup.py",
    "scripts/branch_cleanup_audit.py",
    "scripts/branch_cleanup_core.py",
    "scripts/branch_cleanup_github.py",
    "starter_tests/test_verify_repo.py",
    "starter_tests/test_local_closeout.py",
    "starter_tests/test_post_merge_cleanup.py",
    "starter_tests/test_post_merge_cleanup_adversarial.py",
    "starter_tests/test_post_merge_cleanup_opaque_state.py",
    "starter_tests/test_post_merge_cleanup_toctou.py",
    "starter_tests/test_branch_cleanup_audit.py",
]

RISK_ORDER = {"ROUTINE": 1, "ELEVATED": 2, "HIGH_IMPACT": 3}
COMP_ORDER = {"C0": 0, "C1": 1, "C2": 2}
FACET_MIN_LEVEL = {
    "PRIVATE_DATA": "ELEVATED",
    "EXTERNAL_WRITE": "ELEVATED",
    "AI_AGENT": "ELEVATED",  # Runtime agent authority/mutation, not AI-assisted coding.
    "PLATFORM_DEPENDENT": "ELEVATED",
    "WORKFLOW_PERMISSION": "ELEVATED",
    "DESTRUCTIVE_IO": "HIGH_IMPACT",
    "CREDENTIALS": "HIGH_IMPACT",
    "DEPLOYMENT": "HIGH_IMPACT",
    "SECURITY_BOUNDARY": "HIGH_IMPACT",
    "HIGH_AUTHORITY": "HIGH_IMPACT",
    "CRYPTOGRAPHY": "HIGH_IMPACT",
}
LEVEL_MIN_COMP = {"ROUTINE": "C1", "ELEVATED": "C1", "HIGH_IMPACT": "C2"}
ALLOWED_LIFECYCLES = {"experimental", "active", "production"}
ALLOWED_PROJECT_DEFAULT_LEVELS = set(RISK_ORDER)
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
    level = need(profile, ("risk", "default_level"))
    comp = need(profile, ("comprehension", "required_level"))

    if not isinstance(facets, list) or not all(isinstance(x, str) for x in facets):
        errors.append("risk.persistent_facets must be an array of strings")
        facets = []
    else:
        unknown = sorted(set(facets) - set(FACET_MIN_LEVEL))
        if unknown:
            errors.append(f"unknown risk facets: {', '.join(unknown)}")

    if level not in ALLOWED_PROJECT_DEFAULT_LEVELS:
        errors.append(
            f"invalid risk.default_level: {level!r}; use ROUTINE, ELEVATED, or HIGH_IMPACT"
        )
    if comp not in COMP_ORDER:
        errors.append(f"invalid comprehension.required_level: {comp!r}")

    if level in RISK_ORDER:
        required_level = "ROUTINE"
        for facet in facets:
            minimum = FACET_MIN_LEVEL.get(facet)
            if minimum and RISK_ORDER[minimum] > RISK_ORDER[required_level]:
                required_level = minimum
        if RISK_ORDER[level] < RISK_ORDER[required_level]:
            errors.append(
                f"risk downgrade: facets require at least {required_level}, but default_level is {level}"
            )

        if comp in COMP_ORDER:
            required_comp = LEVEL_MIN_COMP[level]
            if COMP_ORDER[comp] < COMP_ORDER[required_comp]:
                errors.append(
                    f"comprehension downgrade: {level} requires at least {required_comp}, but required_level is {comp}"
                )

    if need(profile, ("governance", "ready")) != "human_final":
        errors.append("house policy violation: governance.ready must be human_final")
    if need(profile, ("governance", "merge")) != "human_final":
        errors.append("house policy violation: governance.merge must be human_final")

    if need(profile, ("enforcement", "main_direct_write", "desired")) != "forbidden_normal_path":
        errors.append(
            "house policy violation: enforcement.main_direct_write.desired must be forbidden_normal_path"
        )
    if need(profile, ("enforcement", "required_ci", "desired")) is not True:
        errors.append("house policy violation: enforcement.required_ci.desired must be true")
    if need(profile, ("verification", "exact_head_required_from_level")) != "HIGH_IMPACT":
        errors.append(
            "house policy violation: verification.exact_head_required_from_level must be HIGH_IMPACT"
        )

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

        required_nonempty_strings = [
            ("project", "name"),
            ("project", "purpose"),
            ("authority", "planning"),
            ("authority", "execution"),
            ("authority", "source_code"),
            ("authority", "private_actual_data"),
            ("authority", "ci_result"),
            ("authority", "review_result"),
            ("authority", "production_state"),
            ("authority", "credentials"),
            ("authority", "release_artifacts"),
            ("comprehension", "owner_checkpoint"),
            ("enforcement", "main_direct_write", "evidence"),
            ("enforcement", "required_ci", "evidence"),
        ]
        for path in required_nonempty_strings:
            value = need(profile, path)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"PROJECT_PROFILE.toml requires a non-empty string at {'.'.join(path)}"
                )

status_path = ROOT / "PROJECT_STATUS.md"
status_text = ""
if status_path.is_file():
    status_text = status_path.read_text(encoding="utf-8")
    for marker in ["## 30-second state", "## Recovery / first diagnostic entry points"]:
        if marker not in status_text:
            errors.append(f"PROJECT_STATUS.md missing section: {marker}")
    if not is_template_repository and "TODO" in status_text:
        errors.append(
            "PROJECT_STATUS.md still contains TODO; replace each with a concrete value or explicit 'none/N/A'"
        )

project_ci_path = ROOT / PROJECT_CI
if is_template_repository:
    if project_ci_path.exists():
        errors.append(
            "template repository must not ship .github/workflows/project-ci.yml; generated projects add their real CI after creation"
        )
else:
    if not project_ci_path.is_file() or project_ci_path.stat().st_size == 0:
        errors.append(
            "project-specific CI workflow is missing; add .github/workflows/project-ci.yml before accepting tracked implementation"
        )

if errors:
    print("BASELINE CHECK: FAIL")
    profile_or_status_pending = any(
        marker in error
        for error in errors
        for marker in ("starter placeholder", "PROJECT_STATUS.md still contains TODO")
    )
    project_ci_missing = any(
        "project-specific CI workflow is missing" in error for error in errors
    )
    bootstrap_available = (
        not is_template_repository
        and profile.get("project", {}).get("name") == "TODO"
        and profile.get("project", {}).get("purpose") == "TODO"
        and "- **Goal:** TODO" in status_text
    )
    if not is_template_repository and (profile_or_status_pending or project_ci_missing):
        print("PROJECT SETUP INCOMPLETE: tracked implementation should not be accepted yet.")
        print("NEXT STEPS:")
        step = 1
        if bootstrap_available:
            print(
                f'{step}. Fresh-copy shortcut: python scripts/bootstrap.py --name "..." --purpose "..."'
            )
            step += 1
        if profile_or_status_pending:
            print(
                f"{step}. Complete only the remaining TODO/TODO_OR_NA values in PROJECT_PROFILE.toml and PROJECT_STATUS.md."
            )
            step += 1
        if project_ci_missing:
            print(
                f"{step}. Add .github/workflows/project-ci.yml with real checks for this project."
            )
            step += 1
        print(
            f'{step}. Re-run: python scripts/verify_repo.py --repository "owner/repo"'
        )
        print("DETAILS:")
    for err in errors:
        print(f"- {err}")
    sys.exit(1)

print("BASELINE CHECK: PASS")
