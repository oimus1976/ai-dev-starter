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


class CleanupInvocationTests(unittest.TestCase):
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
        self.topic = "codex/issue-123-safe-cleanup"
        self.pr_number = 123

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

    def evidence(self, head: str) -> cleanup.PREvidence:
        return cleanup.PREvidence(
            number=self.pr_number,
            state="MERGED",
            merged_at="2026-09-03T00:00:00Z",
            base_ref="main",
            head_ref=self.topic,
            head_sha=head,
            is_cross_repository=False,
        )

    def reader(self, evidence: cleanup.PREvidence):
        return lambda pr, repository: evidence

    def plan_from(self, path: Path, evidence: cleanup.PREvidence) -> cleanup.CleanupPlan:
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ):
            plan, reasons = cleanup.build_plan(
                path,
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

    def execute_from(
        self, path: Path, plan: cleanup.CleanupPlan, evidence: cleanup.PREvidence
    ) -> cleanup.ExecutionResult:
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ):
            return cleanup.execute_plan(plan, path, self.reader(evidence))

    def test_linked_squash_like_cleanup_can_be_invoked_from_removed_topic_worktree(self) -> None:
        linked, head = self.add_topic()
        other = self.temp / "other"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        self.configure(other)
        (other / "merged.txt").write_text("squash-like result\n", encoding="utf-8")
        run("git", "add", "merged.txt", cwd=other)
        run("git", "commit", "-m", "merged result", cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)

        evidence = self.evidence(head)
        plan = self.plan_from(linked, evidence)
        self.assertEqual(plan.mode, "linked")
        self.assertIn("retain local topic branch", "\n".join(plan.actions))

        result = self.execute_from(linked, plan, evidence)
        self.assertTrue(result.ok, result.failures)
        self.assertFalse(linked.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )
        self.assertEqual(run("git", "branch", "--show-current", cwd=self.repo).stdout.strip(), "main")

    def test_linked_normal_merge_can_be_invoked_from_removed_topic_worktree(self) -> None:
        linked, head = self.add_topic()
        run("git", "merge", "--no-ff", self.topic, "-m", "merge topic", cwd=self.repo)
        run("git", "push", "origin", "main", cwd=self.repo)

        evidence = self.evidence(head)
        plan = self.plan_from(linked, evidence)
        self.assertEqual(plan.mode, "linked")
        self.assertIn("retain local topic branch", "\n".join(plan.actions))

        result = self.execute_from(linked, plan, evidence)
        self.assertTrue(result.ok, result.failures)
        self.assertFalse(linked.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )
        self.assertEqual(run("git", "branch", "--show-current", cwd=self.repo).stdout.strip(), "main")


if __name__ == "__main__":
    unittest.main()
