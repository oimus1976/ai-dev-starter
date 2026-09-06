from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from closeout_state import cleanup_worktree_failures

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
        profile = '''
[cleanup]
disposable_ignored_paths = ["__pycache__/", "disposable.txt"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        pycache = repo / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("binary")

        (repo / "disposable.txt").write_text("text")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertFalse(failures)

    def test_cleanup_blocks_unknown_ignored_paths(self):
        profile = '''
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        unknown = repo / "unknown_dir"
        unknown.mkdir()
        (unknown / "file.txt").write_text("text")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("contains ignored files" in f for f in failures))

    def test_cleanup_blocks_calendar_sync_ignored(self):
        profile = '''
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        calendar = repo / "calendar-sync"
        calendar.mkdir()
        (calendar / "data.json").write_text("{}")

        failures = cleanup_worktree_failures(repo, "task")
        self.assertTrue(any("contains ignored files" in f for f in failures))

    def test_cleanup_blocks_mixed_disposable_and_unknown(self):
        profile = '''
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
'''
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
        profile = '''
[cleanup]
disposable_ignored_paths = ["../outside/"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        import closeout_state
        original_git = closeout_state.git

        def mocked_git(*args, **kwargs):
            if args[0] == "status" and "--ignored=matching" in args:
                class MockResult:
                    returncode = 0
                    stdout = "!! ../outside/\0"
                return MockResult()
            return original_git(*args, **kwargs)

        closeout_state.git = mocked_git
        try:
            failures = cleanup_worktree_failures(repo, "task")
            self.assertTrue(any("contains ignored files" in f for f in failures))
        finally:
            closeout_state.git = original_git

    def test_cleanup_blocks_absolute_paths(self):
        profile = '''
[cleanup]
disposable_ignored_paths = ["/absolute/"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        import closeout_state
        original_git = closeout_state.git

        def mocked_git(*args, **kwargs):
            if args[0] == "status" and "--ignored=matching" in args:
                class MockResult:
                    returncode = 0
                    stdout = "!! /absolute/\0"
                return MockResult()
            return original_git(*args, **kwargs)

        closeout_state.git = mocked_git
        try:
            failures = cleanup_worktree_failures(repo, "task")
            self.assertTrue(any("contains ignored files" in f for f in failures))
        finally:
            closeout_state.git = original_git

    def test_cleanup_blocks_symlinks(self):
        profile = '''
[cleanup]
disposable_ignored_paths = ["symlink_dir/"]
'''
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
        profile = '''
[cleanup]
disposable_ignored_paths = ["AMBIGUOUS/"]
'''
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
        profile = '''
[cleanup]
disposable_ignored_paths = ["__pycache__/", "disposable.txt"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        pycache = repo / "__pycache__"
        pycache.mkdir()
        pyc = pycache / "file.pyc"
        pyc.write_text("binary")

        disposable_file = repo / "disposable.txt"
        disposable_file.write_text("text")

        from closeout_state import apply_disposable_cleanup
        failures = apply_disposable_cleanup(repo)

        self.assertFalse(failures)
        self.assertFalse(pycache.exists())
        self.assertFalse(disposable_file.exists())

    def test_cleanup_blocks_unknown_before_deletion(self):
        profile = '''
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        pycache = repo / "__pycache__"
        pycache.mkdir()
        (pycache / "file.pyc").write_text("binary")

        unknown = repo / "unknown.txt"
        unknown.write_text("text")

        from closeout_state import apply_disposable_cleanup

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
        profile = '''
[cleanup]
disposable_ignored_paths = ["../outside/"]
'''
        repo = setup_repo_with_profile(self.temp_dir, profile)

        from closeout_state import apply_disposable_cleanup
        import closeout_state
        original_git = closeout_state.git
        def mocked_git(*args, **kwargs):
            if args[0] == "status" and "--ignored=matching" in args:
                class MockResult:
                    returncode = 0
                    stdout = "!! ../outside/\0"
                return MockResult()
            return original_git(*args, **kwargs)

        closeout_state.git = mocked_git
        try:
            failures = apply_disposable_cleanup(repo)
            self.assertTrue(failures)
        finally:
            closeout_state.git = original_git
