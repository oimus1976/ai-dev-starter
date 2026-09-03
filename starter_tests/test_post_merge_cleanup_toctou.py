from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import post_merge_cleanup as cleanup


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


class CleanupToctouTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.remote = self.temp / "remote.git"
        run("git", "init", "--bare", "--initial-branch=main", str(self.remote), cwd=self.temp)
        self.repo = self.temp / "repo"
        run("git", "clone", str(self.remote), str(self.repo), cwd=self.temp)
        self.configure(self.repo)
        (self.repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
        run("git", "add", "tracked.txt", cwd=self.repo)
        run("git", "commit", "-m", "initial", cwd=self.repo)
        run("git", "push", "-u", "origin", "main", cwd=self.repo)
        self.pr_number = 123
        self.topic = "codex/issue-123-safe-cleanup"

    def configure(self, repo: Path) -> None:
        run("git", "config", "user.name", "Starter Test", cwd=repo)
        run("git", "config", "user.email", "starter@example.invalid", cwd=repo)

    def add_topic(self) -> tuple[Path, str]:
        linked = self.temp / "topic-worktree"
        run("git", "worktree", "add", "-b", self.topic, str(linked), "main", cwd=self.repo)
        self.configure(linked)
        (linked / "topic.txt").write_text("topic\n", encoding="utf-8")
        run("git", "add", "topic.txt", cwd=linked)
        run("git", "commit", "-m", "topic", cwd=linked)
        return linked, run("git", "rev-parse", "HEAD", cwd=linked).stdout.strip()

    def advance_remote_main(self, name: str) -> str:
        other = self.temp / name
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        self.configure(other)
        marker = f"{name}.txt"
        (other / marker).write_text(name + "\n", encoding="utf-8")
        run("git", "add", marker, cwd=other)
        run("git", "commit", "-m", name, cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        return run("git", "rev-parse", "HEAD", cwd=other).stdout.strip()

    def evidence(self, head: str) -> cleanup.PREvidence:
        return cleanup.PREvidence(
            number=self.pr_number,
            state="MERGED",
            merged_at="2026-09-02T00:00:00Z",
            base_ref="main",
            head_ref=self.topic,
            head_sha=head,
            is_cross_repository=False,
        )

    def reader(self, evidence: cleanup.PREvidence):
        return lambda pr, repository: evidence

    def build_plan(self, evidence: cleanup.PREvidence) -> cleanup.CleanupPlan:
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ):
            plan, reasons = cleanup.build_plan(
                self.repo,
                self.pr_number,
                "main",
                "origin",
                None,
                False,
                self.reader(evidence),
            )
        self.assertFalse(reasons)
        self.assertIsNotNone(plan)
        return plan

    def prepare_linked(self) -> tuple[Path, str, cleanup.PREvidence, cleanup.CleanupPlan]:
        linked, head = self.add_topic()
        self.advance_remote_main("merged-result")
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        evidence = self.evidence(head)
        plan = self.build_plan(evidence)
        return linked, head, evidence, plan

    def test_canonical_remote_drift_after_revalidation_blocks_before_effect(self) -> None:
        linked, head, evidence, plan = self.prepare_linked()
        old_remote = plan.canonical_remote_sha
        new_remote = self.advance_remote_main("late-canonical-change")
        self.assertNotEqual(old_remote, new_remote)

        with patch.object(cleanup, "build_plan", return_value=(plan, [])):
            result = cleanup.execute_plan(plan, self.repo, self.reader(evidence))

        self.assertFalse(result.ok)
        self.assertFalse(result.effects_started)
        self.assertTrue(linked.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )
        self.assertTrue(any("canonical remote HEAD changed" in reason for reason in result.failures))

    def test_topic_reoccupied_after_worktree_removal_is_not_ref_deleted(self) -> None:
        linked, head = self.add_topic()
        run("git", "merge", "--no-ff", self.topic, "-m", "merge topic", cwd=self.repo)
        run("git", "push", "origin", "main", cwd=self.repo)
        evidence = self.evidence(head)
        plan = self.build_plan(evidence)
        self.assertTrue(plan.local_topic_delete_safe)

        replacement = self.temp / "replacement-topic-worktree"
        real_git = cleanup.git
        reoccupied = False

        def remove_then_reoccupy(*args: str, cwd: Path, check: bool = True):
            nonlocal reoccupied
            result = real_git(*args, cwd=cwd, check=check)
            if args[:2] == ("worktree", "remove") and result.returncode == 0 and not reoccupied:
                run("git", "worktree", "add", str(replacement), self.topic, cwd=self.repo)
                reoccupied = True
            return result

        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ), patch.object(cleanup, "git", side_effect=remove_then_reoccupy):
            result = cleanup.execute_plan(plan, self.repo, self.reader(evidence))

        self.assertFalse(result.ok)
        self.assertTrue(result.effects_started)
        self.assertFalse(linked.exists())
        self.assertTrue(replacement.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )
        self.assertEqual(run("git", "rev-parse", "HEAD", cwd=replacement).stdout.strip(), head)
        self.assertTrue(any("became occupied" in reason for reason in result.failures))

    def test_worktree_registry_read_failure_is_explicit_not_empty(self) -> None:
        _, _, evidence, _ = self.prepare_linked()
        real_git = cleanup.git

        def fail_registry(*args: str, cwd: Path, check: bool = True):
            if args[:3] == ("worktree", "list", "--porcelain"):
                return subprocess.CompletedProcess(["git", *args], 1, "registry unavailable\n")
            return real_git(*args, cwd=cwd, check=check)

        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ), patch.object(cleanup, "git", side_effect=fail_registry):
            plan, reasons = cleanup.build_plan(
                self.repo,
                self.pr_number,
                "main",
                "origin",
                None,
                False,
                self.reader(evidence),
            )

        self.assertIsNone(plan)
        self.assertTrue(any("worktree registry" in reason for reason in reasons))

    def test_remote_branch_appearing_after_absent_plan_is_not_deleted(self) -> None:
        linked, head, evidence, plan = self.prepare_linked()
        self.assertIsNone(plan.remote_topic_sha)
        run("git", "push", "origin", f"{head}:refs/heads/{self.topic}", cwd=self.repo)

        self.assertFalse(cleanup._remote_delete_with_lease(self.repo, plan))
        remote_head = run(
            "git",
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{self.topic}",
            cwd=self.repo,
        ).stdout.split()[0]
        self.assertEqual(remote_head, head)
        self.assertTrue(linked.exists())


if __name__ == "__main__":
    unittest.main()
