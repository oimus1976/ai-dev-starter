from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from closeout_state import cleanup_worktree_failures


def setup_repo(tmp_path: Path, disposable: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)

    values = ", ".join(f'"{item}"' for item in disposable)
    (repo / "PROJECT_PROFILE.toml").write_text(
        f"[cleanup]\ndisposable_ignored_paths = [{values}]\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        "__pycache__/\ncalendar-sync/\nunknown-dir/\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "PROJECT_PROFILE.toml", ".gitignore"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True)
    return repo


class BlockingPathDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_calendar_sync_block_names_path(self) -> None:
        repo = setup_repo(self.temp_dir, ["__pycache__/"])
        calendar = repo / "calendar-sync"
        calendar.mkdir()
        (calendar / "state.json").write_text("{}", encoding="utf-8")

        failures = cleanup_worktree_failures(repo, "task")

        self.assertTrue(
            any(
                "require preservation or migration" in failure
                and "calendar-sync/" in failure
                for failure in failures
            ),
            failures,
        )

    def test_mixed_block_names_unknown_path_and_keeps_disposable_eligible(self) -> None:
        repo = setup_repo(self.temp_dir, ["__pycache__/"])
        pycache = repo / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("cache", encoding="utf-8")
        unknown = repo / "unknown-dir"
        unknown.mkdir()
        (unknown / "state.txt").write_text("state", encoding="utf-8")

        failures = cleanup_worktree_failures(repo, "task")

        diagnostic = next(
            failure
            for failure in failures
            if "require preservation or migration" in failure
        )
        self.assertIn("unknown-dir/", diagnostic)
        self.assertNotIn("__pycache__/", diagnostic)
        self.assertTrue(pycache.exists())
        self.assertTrue(unknown.exists())


if __name__ == "__main__":
    unittest.main()
