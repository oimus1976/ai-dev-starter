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
POLICY_CHECK = Path(".github/workflows/policy-check.yml")


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

    def test_canonical_template_rejects_active_project_ci(self) -> None:
        repo = self.make_copy()
        path = repo / ".github/workflows/project-ci.yml"
        path.write_text("name: should-not-ship\n", encoding="utf-8")
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("template repository must not ship", result.stdout)

    def test_canonical_template_requires_local_closeout_helper(self) -> None:
        repo = self.make_copy()
        (repo / "scripts/verify_local_closeout.py").unlink()
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required file: scripts/verify_local_closeout.py", result.stdout)

    def test_policy_check_uses_exact_pr_head_without_persisted_credentials(self) -> None:
        text = (ROOT / POLICY_CHECK).read_text(encoding="utf-8")
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("persist-credentials: true", text)
        self.assertIn("python -m unittest discover -s starter_tests -v", text)
        self.assertNotIn("python -m unittest discover -s tests -v", text)
        self.assertIn("scripts/verify_local_closeout.py", text)

    def test_copied_template_fails_until_initialized(self) -> None:
        repo = self.make_copy()
        result = self.run_verify(repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PROJECT SETUP INCOMPLETE", result.stdout)
        self.assertIn("Fresh-copy shortcut:", result.stdout)
        self.assertIn("NEXT STEPS:", result.stdout)
        self.assertIn("starter placeholder", result.stdout)
        self.assertIn("project-specific CI workflow is missing", result.stdout)
        self.assertLess(result.stdout.index("PROJECT SETUP INCOMPLETE"), result.stdout.index("starter placeholder"))

    def test_partial_initialization_does_not_offer_fresh_copy_bootstrap(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'name = "TODO"', 'name = "Example"')
        self.mutate_profile(repo, 'purpose = "TODO"', 'purpose = "Example purpose"')
        status_path = repo / "PROJECT_STATUS.md"
        status = status_path.read_text(encoding="utf-8")
        self.assertIn("- **Goal:** TODO", status)
        status_path.write_text(status.replace("- **Goal:** TODO", "- **Goal:** Example purpose", 1), encoding="utf-8")

        result = self.run_verify(repo)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PROJECT SETUP INCOMPLETE", result.stdout)
        self.assertIn("Complete only the remaining TODO/TODO_OR_NA values", result.stdout)
        self.assertNotIn("Fresh-copy shortcut:", result.stdout)

    def test_legacy_numeric_risk_code_is_rejected(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'default_level = "ROUTINE"', 'default_level = "R1"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("use ROUTINE, ELEVATED, or HIGH_IMPACT", result.stdout)

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
        self.mutate_profile(repo, 'exact_head_required_from_level = "HIGH_IMPACT"', 'exact_head_required_from_level = "ELEVATED"')
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
    def test_bootstrapped_project_tests_are_not_polluted_by_starter_regressions(self) -> None:
        repo = self.make_copy()
        bootstrap = subprocess.run(
            [sys.executable, str(BOOTSTRAP), "--name", "Example", "--purpose", "Example purpose"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(bootstrap.returncode, 0, bootstrap.stdout)

        tests = repo / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_project.py").write_text(
            "import unittest\n\n"
            "class ProjectTests(unittest.TestCase):\n"
            "    def test_project_suite(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("test_project_suite", result.stdout)
        self.assertNotIn("VerifyRepoTests", result.stdout)

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
