from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = Path("scripts/verify_repo.py")
BOOTSTRAP = Path("scripts/bootstrap.py")


class StarterTestCase(unittest.TestCase):
    def make_copy(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp, True)
        shutil.copytree(ROOT, temp / "repo", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        return temp / "repo"


class VerifyRepoTests(StarterTestCase):
    def run_verify(self, repo: Path, identity: str = "example/project") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY), "--repository", identity],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def mutate_profile(self, repo: Path, old: str, new: str) -> None:
        path = repo / "PROJECT_PROFILE.toml"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_canonical_template_passes(self) -> None:
        result = self.run_verify(ROOT, "oimus1976/ai-dev-starter")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("BASELINE CHECK: PASS", result.stdout)

    def test_copied_template_fails_until_initialized(self) -> None:
        repo = self.make_copy()
        result = self.run_verify(repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("starter placeholder", result.stdout)
        self.assertIn("project-specific CI workflow is missing", result.stdout)

    def test_legacy_numeric_risk_code_is_rejected(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'default_level = "ROUTINE"', 'default_level = "R1"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("use ROUTINE, BOUNDARY, or HIGH_IMPACT", result.stdout)

    def test_credentials_cannot_remain_routine(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, "persistent_facets = []", 'persistent_facets = ["CREDENTIALS"]')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("facets require at least HIGH_IMPACT", result.stdout)

    def test_high_impact_requires_c2(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'default_level = "ROUTINE"', 'default_level = "HIGH_IMPACT"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HIGH_IMPACT requires at least C2", result.stdout)

    def test_empty_authority_is_rejected_in_copied_repo(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'planning = "TODO"', 'planning = ""')
        result = self.run_verify(repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires a non-empty string at authority.planning", result.stdout)

    def test_main_direct_write_policy_cannot_be_weakened(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'desired = "forbidden_normal_path"', 'desired = "allowed"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main_direct_write.desired must be forbidden_normal_path", result.stdout)

    def test_required_ci_policy_cannot_be_disabled(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, "desired = true", "desired = false")
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required_ci.desired must be true", result.stdout)

    def test_exact_head_high_impact_policy_cannot_be_weakened(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'exact_head_required_from_level = "HIGH_IMPACT"', 'exact_head_required_from_level = "BOUNDARY"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact_head_required_from_level must be HIGH_IMPACT", result.stdout)

    def test_project_ci_file_removes_ci_missing_error(self) -> None:
        repo = self.make_copy()
        first = self.run_verify(repo)
        self.assertIn("project-specific CI workflow is missing", first.stdout)
        path = repo / ".github/workflows/project-ci.yml"
        path.write_text("name: project-ci\non: [pull_request]\njobs: {}\n", encoding="utf-8")
        second = self.run_verify(repo)
        self.assertNotIn("project-specific CI workflow is missing", second.stdout)


class BootstrapTests(StarterTestCase):
    def test_preflight_failure_does_not_partially_change_profile(self) -> None:
        repo = self.make_copy()
        profile_path = repo / "PROJECT_PROFILE.toml"
        status_path = repo / "PROJECT_STATUS.md"
        original_profile = profile_path.read_text(encoding="utf-8")
        status = status_path.read_text(encoding="utf-8")
        self.assertIn("- **Goal:** TODO", status)
        status_path.write_text(status.replace("- **Goal:** TODO", "- **Goal:** missing-marker", 1), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(BOOTSTRAP), "--name", "Example", "--purpose", "Example purpose"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PROJECT_STATUS goal placeholder", result.stdout)
        self.assertEqual(profile_path.read_text(encoding="utf-8"), original_profile)


if __name__ == "__main__":
    unittest.main()
