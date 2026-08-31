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

    def git_dir(self, repo: Path) -> Path:
        raw = run("git", "rev-parse", "--git-dir", cwd=repo).stdout.strip()
        path = Path(raw)
        if not path.is_absolute():
            path = repo / path
        return path.resolve()

    def verify(
        self,
        repo: Path | None = None,
        expected_pr_head: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        target = repo or self.repo
        args = [
            sys.executable,
            str(VERIFY),
            "--repo",
            str(target),
        ]
        if expected_pr_head is not None:
            args.extend(["--expected-pr-head", expected_pr_head])
        return run(*args, cwd=target, check=False)

    def add_topic_worktree(self) -> tuple[Path, str]:
        linked = self.temp / "topic-worktree"
        run("git", "worktree", "add", "-b", "topic", str(linked), "main", cwd=self.repo)
        run("git", "config", "user.name", "Topic Test", cwd=linked)
        run("git", "config", "user.email", "topic@example.invalid", cwd=linked)
        (linked / "topic.txt").write_text("topic work\n", encoding="utf-8")
        run("git", "add", "topic.txt", cwd=linked)
        run("git", "commit", "-m", "topic work", cwd=linked)
        head = run("git", "rev-parse", "HEAD", cwd=linked).stdout.strip()
        return linked, head

    def advance_remote_main(self) -> Path:
        suffix = len(list(self.temp.glob("other-*")))
        other = self.temp / f"other-{suffix}"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        run("git", "config", "user.name", "Other Test", cwd=other)
        run("git", "config", "user.email", "other@example.invalid", cwd=other)
        (other / "remote.txt").write_text("remote advanced\n", encoding="utf-8")
        run("git", "add", "remote.txt", cwd=other)
        run("git", "commit", "-m", "advance remote", cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        return other

    def test_passes_when_main_is_clean_and_matches_fresh_origin(self) -> None:
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("LOCAL CLOSEOUT: PASS", result.stdout)
        self.assertIn("task_worktree_role=canonical", result.stdout)
        self.assertIn("canonical_worktree=ready", result.stdout)

    def test_passes_from_linked_worktree_on_canonical_main(self) -> None:
        run("git", "switch", "-c", "parking", cwd=self.repo)
        linked = self.temp / "linked-worktree"
        run("git", "worktree", "add", str(linked), "main", cwd=self.repo)

        result = self.verify(linked)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("task_worktree_role=canonical", result.stdout)
        self.assertIn("branch=main", result.stdout)

    def test_passes_from_topic_worktree_when_main_is_ready_elsewhere(self) -> None:
        linked, expected = self.add_topic_worktree()
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)

        result = self.verify(linked, expected)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("task_worktree_role=topic", result.stdout)
        self.assertIn("expected_pr_head=matched", result.stdout)
        self.assertIn("canonical_worktree=ready", result.stdout)
        self.assertIn("next_task_checkout=canonical-worktree", result.stdout)

    def test_topic_worktree_requires_expected_pr_head(self) -> None:
        linked, _ = self.add_topic_worktree()

        result = self.verify(linked)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --expected-pr-head", result.stdout)

    def test_topic_worktree_rejects_non_full_expected_pr_head(self) -> None:
        linked, expected = self.add_topic_worktree()

        result = self.verify(linked, expected[:12])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("full 40-character hexadecimal", result.stdout)

    def test_topic_worktree_fails_when_expected_head_moved(self) -> None:
        linked, _ = self.add_topic_worktree()

        result = self.verify(linked, "0" * 40)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match expected PR head", result.stdout)

    def test_topic_worktree_fails_when_canonical_main_is_stale(self) -> None:
        linked, expected = self.add_topic_worktree()
        self.advance_remote_main()

        result = self.verify(linked, expected)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical HEAD", result.stdout)
        self.assertIn("does not match origin/main", result.stdout)

    def test_topic_worktree_fails_when_canonical_main_is_dirty(self) -> None:
        linked, expected = self.add_topic_worktree()
        (self.repo / "untracked.txt").write_text("leftover\n", encoding="utf-8")

        result = self.verify(linked, expected)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical working tree is not clean", result.stdout)

    def test_topic_worktree_fails_when_canonical_git_operation_remains(self) -> None:
        linked, expected = self.add_topic_worktree()
        (self.git_dir(self.repo) / "CHERRY_PICK_HEAD").write_text(
            run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip() + "\n",
            encoding="utf-8",
        )

        result = self.verify(linked, expected)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "canonical Git operation still in progress: CHERRY_PICK_HEAD",
            result.stdout,
        )

    def test_topic_worktree_fails_when_topic_is_dirty(self) -> None:
        linked, expected = self.add_topic_worktree()
        (linked / "untracked.txt").write_text("leftover\n", encoding="utf-8")

        result = self.verify(linked, expected)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task working tree is not clean", result.stdout)

    def test_topic_worktree_fails_when_topic_git_operation_remains(self) -> None:
        linked, expected = self.add_topic_worktree()
        (self.git_dir(linked) / "CHERRY_PICK_HEAD").write_text(
            expected + "\n", encoding="utf-8"
        )

        result = self.verify(linked, expected)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "task Git operation still in progress: CHERRY_PICK_HEAD",
            result.stdout,
        )

    def test_fails_on_topic_branch_without_canonical_worktree(self) -> None:
        run("git", "switch", "-c", "topic", cwd=self.repo)
        expected = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()

        result = self.verify(expected_pr_head=expected)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical branch 'main' is not checked out", result.stdout)
        self.assertIn("separate canonical worktree", result.stdout)
        self.assertNotIn("git switch main", result.stdout)

    def test_topic_head_mismatch_cannot_be_guided_into_canonical_bypass(self) -> None:
        run("git", "switch", "-c", "topic", cwd=self.repo)

        result = self.verify(expected_pr_head="0" * 40)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match expected PR head", result.stdout)
        self.assertIn("do not switch away", result.stdout)
        self.assertIn("separate canonical worktree", result.stdout)
        self.assertNotIn("git switch main", result.stdout)

    def test_stale_canonical_worktree_registration_fails_without_crash(self) -> None:
        run("git", "switch", "-c", "topic", cwd=self.repo)
        expected = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        canonical = self.temp / "canonical-linked"
        run("git", "worktree", "add", str(canonical), "main", cwd=self.repo)
        shutil.rmtree(canonical)

        result = self.verify(expected_pr_head=expected)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical branch 'main' is not checked out", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_missing_requested_repo_fails_without_crash(self) -> None:
        missing = self.temp / "missing-worktree"
        result = run(
            sys.executable,
            str(VERIFY),
            "--repo",
            str(missing),
            cwd=self.temp,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requested repository/worktree path is unavailable", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_fails_on_dirty_or_untracked_working_tree(self) -> None:
        (self.repo / "untracked.txt").write_text("leftover\n", encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task working tree is not clean", result.stdout)

    def test_fails_when_fresh_origin_main_is_ahead(self) -> None:
        self.advance_remote_main()

        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match origin/main", result.stdout)

    def test_fails_when_local_main_is_ahead_of_origin(self) -> None:
        (self.repo / "tracked.txt").write_text("local advanced\n", encoding="utf-8")
        run("git", "add", "tracked.txt", cwd=self.repo)
        run("git", "commit", "-m", "local-only commit", cwd=self.repo)

        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match origin/main", result.stdout)

    def test_fails_when_fetch_cannot_establish_freshness(self) -> None:
        missing_remote = self.temp / "missing.git"
        run("git", "remote", "set-url", "origin", str(missing_remote), cwd=self.repo)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote freshness is unverified", result.stdout)
        self.assertNotIn(str(missing_remote), result.stdout)

    def test_fails_when_canonical_remote_branch_no_longer_exists(self) -> None:
        run(
            "git",
            "--git-dir",
            str(self.remote),
            "update-ref",
            "-d",
            "refs/heads/main",
            cwd=self.temp,
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote freshness is unverified", result.stdout)

    def test_fails_when_git_operation_marker_remains(self) -> None:
        head = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        (self.git_dir(self.repo) / "CHERRY_PICK_HEAD").write_text(
            head + "\n", encoding="utf-8"
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "task Git operation still in progress: CHERRY_PICK_HEAD",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
