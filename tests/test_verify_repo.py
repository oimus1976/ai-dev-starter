from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = Path("scripts/verify_repo.py")


class VerifyRepoTests(unittest.TestCase):
    def make_copy(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp, True)
        shutil.copytree(ROOT, temp / "repo", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        return temp / "repo"

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
        self.assertIn("project CI is still", result.stdout)

    def test_persistent_default_cannot_be_r0(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'default_tier = "R1"', 'default_tier = "R0"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("persistent project defaults must be R1, R2, or R3", result.stdout)

    def test_credentials_cannot_remain_r1(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, "persistent_facets = []", 'persistent_facets = ["CREDENTIALS"]')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("facets require at least R3", result.stdout)

    def test_r3_requires_c2(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'default_tier = "R1"', 'default_tier = "R3"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("R3 requires at least C2", result.stdout)

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

    def test_exact_head_r3_policy_cannot_be_weakened(self) -> None:
        repo = self.make_copy()
        self.mutate_profile(repo, 'exact_head_required_from_tier = "R3"', 'exact_head_required_from_tier = "R2"')
        result = self.run_verify(repo, "oimus1976/ai-dev-starter")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact_head_required_from_tier must be R3", result.stdout)


if __name__ == "__main__":
    unittest.main()
