from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from closeout_state import cleanup_worktree_failures, apply_disposable_cleanup
import post_merge_cleanup as cleanup

# We will import CleanupTests directly to use its setup
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from test_post_merge_cleanup import CleanupTests

def setup_repo_with_profile(tmp_path: Path, profile_content: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)

    (repo / "PROJECT_PROFILE.toml").write_text(profile_content)
    (repo / ".gitignore").write_text("*\n!.gitignore\n!PROJECT_PROFILE.toml\n")

    subprocess.run(["git", "add", "PROJECT_PROFILE.toml", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True)

    return repo

class CleanupIgnoredTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cleanup_allows_disposable_ignored_paths(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/", "disposable.txt"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        pycache = repo / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("binary")

        (repo / "disposable.txt").write_text("text")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertFalse(failures)

    def test_cleanup_blocks_unknown_ignored_paths(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        unknown = repo / "unknown_dir"
        unknown.mkdir()
        (unknown / "file.txt").write_text("text")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("contains ignored files" in f for f in failures))

    def test_cleanup_blocks_calendar_sync_ignored(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        calendar = repo / "calendar-sync"
        calendar.mkdir()
        (calendar / "data.json").write_text("{}")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("contains ignored files" in f for f in failures))

    def test_cleanup_blocks_mixed_disposable_and_unknown(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        pycache = repo / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("binary")

        calendar = repo / "calendar-sync"
        calendar.mkdir()
        (calendar / "data.json").write_text("{}")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("contains ignored files" in f for f in failures))

    def test_cleanup_blocks_path_escape(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["../outside/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("cannot contain path escapes" in f for f in failures))

    def test_cleanup_blocks_absolute_paths(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["/absolute/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("cannot contain absolute paths" in f for f in failures))

    def test_cleanup_blocks_symlinks(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["symlink_dir/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        target = repo / "target"
        target.mkdir()
        symlink_dir = repo / "symlink_dir"
        try:
            symlink_dir.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks not supported on this platform")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("contains ignored files" in f for f in failures))

    def test_cleanup_blocks_ambiguous_filesystem_identity(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["AMBIGUOUS/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        ambiguous = repo / "ambiguous"
        ambiguous.mkdir()
        (ambiguous / "file.txt").write_text("text")

        import closeout_state
        original_git = closeout_state.git

        def mocked_git(*args, **kwargs):
            if args[0] == "status" and "--ignored=matching" in args:
                class MockResult:
                    returncode = 0
                    stdout = "!! ambiguous/\0"
                return MockResult()
            return original_git(*args, **kwargs)

        closeout_state.git = mocked_git
        try:
            failures = cleanup_worktree_failures(repo, "task")
            self.assertTrue(any("contains ignored files" in f for f in failures))
        finally:
            closeout_state.git = original_git

    def test_cleanup_deletes_only_exact_disposable_paths(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/", "disposable.txt"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        pycache = repo / "__pycache__"
        pycache.mkdir()
        pyc = pycache / "file.pyc"
        pyc.write_text("binary")

        disposable_file = repo / "disposable.txt"
        disposable_file.write_text("text")

        failures = apply_disposable_cleanup(repo)

        self.assertFalse(failures)
        self.assertFalse(pycache.exists())
        self.assertFalse(disposable_file.exists())

    def test_cleanup_blocks_unknown_before_deletion(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)

        pycache = repo / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("binary")

        unknown = repo / "unknown.txt"
        unknown.write_text("text")

        import closeout_state
        original_git = closeout_state.git
        def mocked_git(*args, **kwargs):
            if args[0] == "status" and "--ignored=matching" in args:
                class MockResult:
                    returncode = 0
                    stdout = "!! __pycache__/\0!! unknown.txt\0"
                return MockResult()
            return original_git(*args, **kwargs)

        closeout_state.git = mocked_git
        try:
            failures = apply_disposable_cleanup(repo)
            self.assertTrue(failures)
            self.assertTrue(pycache.exists())
            self.assertTrue(unknown.exists())
        finally:
            closeout_state.git = original_git

    def test_cleanup_blocks_escaping_path_before_deletion(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["../outside/"]
"""
        repo = setup_repo_with_profile(self.temp_dir, profile)
        failures = apply_disposable_cleanup(repo)
        self.assertTrue(any("cannot contain path escapes" in f for f in failures))

class IgnoredIntegrationTests(CleanupTests):
    def test_linked_topic_disposable_cleanup_integration(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/", "disposable.txt"]
"""
        (self.repo / "PROJECT_PROFILE.toml").write_text(profile)
        # Fix the gitignore so `advance_remote_main` works
        (self.repo / ".gitignore").write_text("__pycache__/\n*.txt\n!merged.txt\n!topic.txt\n")
        subprocess.run(["git", "add", "PROJECT_PROFILE.toml", ".gitignore"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "Add profile"], cwd=self.repo, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.repo, check=True)

        linked, head = self.add_linked_topic()

        pycache = linked / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("binary")
        (linked / "disposable.txt").write_text("text")

        self.advance_remote_main()
        subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=self.repo, check=True)

        ev = self.evidence(head)
        plan, reasons = self.plan(head, ev=ev)
        self.assertFalse(reasons)
        self.assertEqual(plan.mode, "linked")

        ok, failures = self.execute(plan, ev)
        self.assertTrue(ok, failures)

        self.assertFalse(linked.exists())
        self.assertEqual(
            subprocess.run(["git", "branch", "--show-current"], cwd=self.repo, capture_output=True, text=True).stdout.strip(), "main"
        )

    def test_primary_topic_blocks_disposable_cleanup(self):
        profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
        (self.repo / "PROJECT_PROFILE.toml").write_text(profile)
        (self.repo / ".gitignore").write_text("__pycache__/\n*.txt\n!merged.txt\n!topic.txt\n")
        subprocess.run(["git", "add", "PROJECT_PROFILE.toml", ".gitignore"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "Add profile"], cwd=self.repo, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.repo, check=True)

        subprocess.run(["git", "checkout", "-b", self.topic], cwd=self.repo, check=True)
        linked_main = self.temp / "linked-main"
        subprocess.run(["git", "worktree", "add", str(linked_main), "main"], cwd=self.repo, check=True)

        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True).stdout.strip()

        pycache = self.repo / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("binary")

        self.advance_remote_main()
        subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=linked_main, check=True)

        ev = self.evidence(head)
        plan, reasons = self.plan(head, ev=ev)

        self.assertIsNone(plan)
        self.assertTrue(any("primary topic worktree" in r for r in reasons))

        self.assertTrue(pycache.exists())

    def test_malformed_disposable_policy_blocks(self):
        profile = """
[cleanup]
disposable_ignored_paths = "not a list"
"""
        (self.repo / "PROJECT_PROFILE.toml").write_text(profile)
        (self.repo / ".gitignore").write_text("__pycache__/\n*.txt\n!merged.txt\n!topic.txt\nunknown.txt\n")
        subprocess.run(["git", "add", "PROJECT_PROFILE.toml", ".gitignore"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "Add profile"], cwd=self.repo, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.repo, check=True)

        linked, head = self.add_linked_topic()

        self.advance_remote_main()
        subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=self.repo, check=True)

        ev = self.evidence(head)
        plan, reasons = self.plan(head, ev=ev)
        self.assertIsNone(plan)
        self.assertTrue(any("must be a list" in f for f in reasons))
