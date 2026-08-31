from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/verify_local_closeout.py"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


class LocalCloseoutTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp, True)
        self.temp = temp
        self.remote = temp / "remote.git"
        run("git", "init", "--bare", "--initial-branch=main", str(self.remote), cwd=temp)
        self.repo = temp / "repo"
        run("git", "clone", str(self.remote), str(self.repo), cwd=temp)
        run("git", "config", "user.name", "Starter Test", cwd=self.repo)
        run("git", "config", "user.email", "starter@example.invalid", cwd=self.repo)
        (self.repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
        run("git", "add", "tracked.txt", cwd=self.repo)
        run("git", "commit", "-m", "initial", cwd=self.repo)
        run("git", "push", "-u", "origin", "main", cwd=self.repo)

    def verify(self) -> subprocess.CompletedProcess[str]:
        return run(
            sys.executable,
            str(VERIFY),
            "--repo",
            str(self.repo),
            cwd=self.repo,
            check=False,
        )

    def test_passes_when_main_is_clean_and_matches_fresh_origin(self) -> None:
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("LOCAL CLOSEOUT: PASS", result.stdout)
        self.assertIn("working_tree=clean", result.stdout)
        self.assertIn("freshness=fetch-completed", result.stdout)

    def test_fails_on_topic_branch(self) -> None:
        run("git", "switch", "-c", "topic", cwd=self.repo)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("current branch is 'topic'; expected 'main'", result.stdout)

    def test_fails_on_dirty_or_untracked_working_tree(self) -> None:
        (self.repo / "untracked.txt").write_text("leftover\n", encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("working tree is not clean", result.stdout)

    def test_fails_when_fresh_origin_main_is_ahead(self) -> None:
        other = self.temp / "other"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        run("git", "config", "user.name", "Other Test", cwd=other)
        run("git", "config", "user.email", "other@example.invalid", cwd=other)
        (other / "tracked.txt").write_text("remote advanced\n", encoding="utf-8")
        run("git", "add", "tracked.txt", cwd=other)
        run("git", "commit", "-m", "advance remote", cwd=other)
        run("git", "push", "origin", "main", cwd=other)

        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match origin/main", result.stdout)

    def test_fails_when_fetch_cannot_establish_freshness(self) -> None:
        run("git", "remote", "set-url", "origin", str(self.temp / "missing.git"), cwd=self.repo)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote freshness is unverified", result.stdout)

    def test_fails_when_git_operation_marker_remains(self) -> None:
        head = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        git_dir = self.repo / ".git"
        (git_dir / "CHERRY_PICK_HEAD").write_text(head + "\n", encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git operation still in progress: CHERRY_PICK_HEAD", result.stdout)


if __name__ == "__main__":
    unittest.main()
