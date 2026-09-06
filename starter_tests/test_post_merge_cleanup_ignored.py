from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from closeout_state import cleanup_worktree_failures

def setup_repo_with_profile(tmp_path: Path, profile_content: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    # Configure git
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)

    # Write profile
    (repo / "PROJECT_PROFILE.toml").write_text(profile_content)

    # Write gitignore
    (repo / ".gitignore").write_text("*\n!.gitignore\n!PROJECT_PROFILE.toml\n")

    subprocess.run(["git", "add", "PROJECT_PROFILE.toml", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True)

    return repo

def test_cleanup_allows_disposable_ignored_paths(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/", "disposable.txt"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

    # Create disposable ignored directory
    pycache = repo / "__pycache__"
    pycache.mkdir()
    (pycache / "file.pyc").write_text("binary")

    # Create disposable file
    (repo / "disposable.txt").write_text("text")

    # Check status
    failures = cleanup_worktree_failures(repo, "task")
    assert not failures

def test_cleanup_blocks_unknown_ignored_paths(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

    # Create unknown ignored directory
    unknown = repo / "unknown_dir"
    unknown.mkdir()
    (unknown / "file.txt").write_text("text")

    failures = cleanup_worktree_failures(repo, "task")
    assert any("contains ignored files" in f for f in failures)

def test_cleanup_blocks_calendar_sync_ignored(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

    calendar = repo / "calendar-sync"
    calendar.mkdir()
    (calendar / "data.json").write_text("{}")

    failures = cleanup_worktree_failures(repo, "task")
    assert any("contains ignored files" in f for f in failures)

def test_cleanup_blocks_mixed_disposable_and_unknown(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["__pycache__/"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

    pycache = repo / "__pycache__"
    pycache.mkdir()
    (pycache / "file.pyc").write_text("binary")

    calendar = repo / "calendar-sync"
    calendar.mkdir()
    (calendar / "data.json").write_text("{}")

    failures = cleanup_worktree_failures(repo, "task")
    assert any("contains ignored files" in f for f in failures)

def test_cleanup_blocks_path_escape(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["../outside/"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

    # We mock git status to return an escape path
    # Actually, we can just test the function directly with mocked git output or just see if the logic blocks it.
    # To test actual git status, git will not report ../ as untracked.
    # So we'll have to inject it or trust our unit test. Let's mock the `git` call.
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
        assert any("contains ignored files" in f for f in failures)
    finally:
        closeout_state.git = original_git

def test_cleanup_blocks_absolute_paths(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["/absolute/"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

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
        assert any("contains ignored files" in f for f in failures)
    finally:
        closeout_state.git = original_git

def test_cleanup_blocks_symlinks(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["symlink_dir/"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

    target = repo / "target"
    target.mkdir()
    symlink_dir = repo / "symlink_dir"
    try:
        symlink_dir.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    failures = cleanup_worktree_failures(repo, "task")
    assert any("contains ignored files" in f for f in failures)

def test_cleanup_blocks_ambiguous_filesystem_identity(tmp_path: Path):
    profile = """
[cleanup]
disposable_ignored_paths = ["AMBIGUOUS/"]
"""
    repo = setup_repo_with_profile(tmp_path, profile)

    # Create ambiguous
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
        # Since 'ambiguous/' is not exactly 'AMBIGUOUS/', it should be blocked
        assert any("contains ignored files" in f for f in failures)
    finally:
        closeout_state.git = original_git
