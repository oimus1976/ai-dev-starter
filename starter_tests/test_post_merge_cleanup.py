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
        list(args), cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check
    )


class CleanupTests(unittest.TestCase):
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

    def add_linked_topic(self, push: bool = False) -> tuple[Path, str]:
        linked = self.temp / "topic-worktree"
        run("git", "worktree", "add", "-b", self.topic, str(linked), "main", cwd=self.repo)
        self.configure(linked)
        (linked / "topic.txt").write_text("topic\n", encoding="utf-8")
        run("git", "add", "topic.txt", cwd=linked)
        run("git", "commit", "-m", "topic", cwd=linked)
        if push:
            run("git", "push", "-u", "origin", self.topic, cwd=linked)
        return linked, run("git", "rev-parse", "HEAD", cwd=linked).stdout.strip()

    def advance_remote_main(self, content: str = "merged result\n") -> str:
        other = self.temp / f"other-{len(list(self.temp.glob('other-*')))}"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        self.configure(other)
        (other / "merged.txt").write_text(content, encoding="utf-8")
        run("git", "add", "merged.txt", cwd=other)
        run("git", "commit", "-m", "merged result", cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        return run("git", "rev-parse", "HEAD", cwd=other).stdout.strip()

    def evidence(
        self,
        head: str,
        state: str = "MERGED",
        merged_at: str | None = "2026-09-02T00:00:00Z",
    ) -> cleanup.PREvidence:
        return cleanup.PREvidence(
            number=self.pr_number,
            state=state,
            merged_at=merged_at,
            base_ref="main",
            head_ref=self.topic,
            head_sha=head,
            is_cross_repository=False,
        )

    def reader(self, ev: cleanup.PREvidence):
        def _read(pr: int, repository: str) -> cleanup.PREvidence:
            self.assertEqual(pr, self.pr_number)
            self.assertEqual(repository, "oimus1976/ai-dev-starter")
            return ev

        return _read

    def plan(
        self,
        head: str,
        delete_remote: bool = False,
        ev: cleanup.PREvidence | None = None,
    ):
        evidence = ev or self.evidence(head)
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ):
            return cleanup.build_plan(
                self.repo,
                self.pr_number,
                "main",
                "origin",
                None,
                delete_remote,
                self.reader(evidence),
            )

    def execute(self, plan: cleanup.CleanupPlan, ev: cleanup.PREvidence):
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ):
            return cleanup.execute_plan(plan, self.repo, self.reader(ev))

    def test_linked_squash_like_cleanup_removes_worktree_but_retains_ref(self) -> None:
        linked, head = self.add_linked_topic()
        self.advance_remote_main()  # topic head intentionally is not an ancestor of main
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        ev = self.evidence(head)

        plan, reasons = self.plan(head, ev=ev)
        self.assertFalse(reasons)
        self.assertEqual(plan.mode, "linked")
        self.assertTrue(linked.exists())
        self.assertIn("retain local topic branch", "\n".join(plan.actions))

        ok, failures = self.execute(plan, ev)
        self.assertTrue(ok, failures)
        self.assertFalse(linked.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )
        self.assertEqual(
            run("git", "branch", "--show-current", cwd=self.repo).stdout.strip(), "main"
        )

    def test_default_plan_does_not_delete(self) -> None:
        linked, head = self.add_linked_topic()
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)

        plan, reasons = self.plan(head)
        self.assertFalse(reasons)
        self.assertTrue(linked.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )
        self.assertIn("retain local topic branch", "\n".join(plan.actions))

    def test_closed_unmerged_is_blocked(self) -> None:
        _, head = self.add_linked_topic()
        plan, reasons = self.plan(
            head, ev=self.evidence(head, state="CLOSED", merged_at=None)
        )
        self.assertIsNone(plan)
        self.assertTrue(any("not merged" in reason for reason in reasons))

    def test_dirty_topic_is_blocked(self) -> None:
        linked, head = self.add_linked_topic()
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        (linked / "untracked.txt").write_text("leftover\n", encoding="utf-8")

        plan, reasons = self.plan(head)
        self.assertIsNone(plan)
        self.assertTrue(any("task working tree is not clean" in reason for reason in reasons))

    def test_local_head_drift_is_blocked(self) -> None:
        linked, head = self.add_linked_topic()
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        (linked / "later.txt").write_text("later\n", encoding="utf-8")
        run("git", "add", "later.txt", cwd=linked)
        run("git", "commit", "-m", "later", cwd=linked)

        plan, reasons = self.plan(head)
        self.assertIsNone(plan)
        self.assertTrue(
            any("local topic ref" in reason or "task HEAD" in reason for reason in reasons)
        )

    def test_single_checkout_switches_and_fast_forwards_canonical_but_retains_ref(self) -> None:
        run("git", "switch", "-c", self.topic, cwd=self.repo)
        (self.repo / "topic.txt").write_text("topic\n", encoding="utf-8")
        run("git", "add", "topic.txt", cwd=self.repo)
        run("git", "commit", "-m", "topic", cwd=self.repo)
        head = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        remote_main = self.advance_remote_main()
        ev = self.evidence(head)

        plan, reasons = self.plan(head, ev=ev)
        self.assertFalse(reasons)
        self.assertEqual(plan.mode, "single")
        self.assertIn("retain local topic branch", "\n".join(plan.actions))

        ok, failures = self.execute(plan, ev)
        self.assertTrue(ok, failures)
        self.assertEqual(
            run("git", "branch", "--show-current", cwd=self.repo).stdout.strip(), "main"
        )
        self.assertEqual(run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip(), remote_main)
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )

    def test_diverged_local_main_blocks_single_checkout(self) -> None:
        run("git", "switch", "-c", self.topic, cwd=self.repo)
        head = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        self.advance_remote_main()
        parking = self.temp / "parking"
        run("git", "worktree", "add", str(parking), "main", cwd=self.repo)
        self.configure(parking)
        (parking / "local.txt").write_text("local\n", encoding="utf-8")
        run("git", "add", "local.txt", cwd=parking)
        run("git", "commit", "-m", "local main drift", cwd=parking)
        run("git", "worktree", "remove", str(parking), cwd=self.repo)

        plan, reasons = self.plan(head)
        self.assertIsNone(plan)
        self.assertTrue(any("cannot fast-forward" in reason for reason in reasons))

    def test_remote_drift_blocks_even_without_remote_delete(self) -> None:
        _, head = self.add_linked_topic(push=True)
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        other = self.temp / "remote-topic-mutator"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        self.configure(other)
        run("git", "switch", self.topic, cwd=other)
        (other / "remote-new.txt").write_text("new\n", encoding="utf-8")
        run("git", "add", "remote-new.txt", cwd=other)
        run("git", "commit", "-m", "reuse branch", cwd=other)
        run("git", "push", "origin", self.topic, cwd=other)

        plan, reasons = self.plan(head)
        self.assertIsNone(plan)
        self.assertTrue(
            any("remote topic branch" in reason and "drifted" in reason for reason in reasons)
        )

    def test_remote_delete_uses_exact_head_and_removes_target(self) -> None:
        _, head = self.add_linked_topic(push=True)
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        ev = self.evidence(head)

        plan, reasons = self.plan(head, delete_remote=True, ev=ev)
        self.assertFalse(reasons)
        self.assertEqual(plan.remote_topic_sha, head)

        ok, failures = self.execute(plan, ev)
        self.assertTrue(ok, failures)
        ls = run(
            "git",
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{self.topic}",
            cwd=self.repo,
        )
        self.assertEqual(ls.stdout.strip(), "")
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )

    def test_execute_revalidates_github_state_before_effects(self) -> None:
        linked, head = self.add_linked_topic()
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        ev = self.evidence(head)
        plan, reasons = self.plan(head, ev=ev)
        self.assertFalse(reasons)

        closed = self.evidence(head, state="CLOSED", merged_at=None)
        result = self.execute(plan, closed)
        self.assertFalse(result.ok)
        self.assertTrue(linked.exists())
        self.assertTrue(any("not merged" in reason for reason in result.failures))
        self.assertFalse(result.effects_started)


if __name__ == "__main__":
    unittest.main()
