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


class CleanupAdversarialTests(unittest.TestCase):
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

    def git_dir(self, repo: Path) -> Path:
        raw = run("git", "rev-parse", "--git-dir", cwd=repo).stdout.strip()
        path = Path(raw)
        if not path.is_absolute():
            path = repo / path
        return path.resolve()

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

    def advance_remote_main(self) -> str:
        other = self.temp / f"other-{len(list(self.temp.glob('other-*')))}"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        self.configure(other)
        (other / "merged.txt").write_text("merged result\n", encoding="utf-8")
        run("git", "add", "merged.txt", cwd=other)
        run("git", "commit", "-m", "merged result", cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        return run("git", "rev-parse", "HEAD", cwd=other).stdout.strip()

    def evidence(
        self,
        head: str,
        *,
        state: str = "MERGED",
        merged_at: str | None = "2026-09-02T00:00:00Z",
        base_ref: str = "main",
        cross: bool = False,
    ) -> cleanup.PREvidence:
        return cleanup.PREvidence(
            number=self.pr_number,
            state=state,
            merged_at=merged_at,
            base_ref=base_ref,
            head_ref=self.topic,
            head_sha=head,
            is_cross_repository=cross,
        )

    def reader(self, evidence: cleanup.PREvidence):
        return lambda pr, repository: evidence

    def plan(self, evidence: cleanup.PREvidence, delete_remote: bool = False):
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

    def execute(self, plan: cleanup.CleanupPlan, evidence: cleanup.PREvidence):
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ):
            return cleanup.execute_plan(plan, self.repo, self.reader(evidence))

    def prepare_linked(self, push: bool = False) -> tuple[Path, str, cleanup.PREvidence]:
        linked, head = self.add_linked_topic(push=push)
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        return linked, head, self.evidence(head)

    def test_open_unmerged_is_blocked(self) -> None:
        _, head = self.add_linked_topic()
        plan, reasons = self.plan(self.evidence(head, state="OPEN", merged_at=None))
        self.assertIsNone(plan)
        self.assertTrue(any("not merged" in reason for reason in reasons))

    def test_cross_repository_is_blocked(self) -> None:
        _, head = self.add_linked_topic()
        plan, reasons = self.plan(self.evidence(head, cross=True))
        self.assertIsNone(plan)
        self.assertTrue(any("cross-repository" in reason for reason in reasons))

    def test_noncanonical_base_is_blocked(self) -> None:
        _, head = self.add_linked_topic()
        plan, reasons = self.plan(self.evidence(head, base_ref="release"))
        self.assertIsNone(plan)
        self.assertTrue(any("PR base branch" in reason for reason in reasons))

    def test_github_reader_failure_is_generic_and_blocks(self) -> None:
        _, _ = self.add_linked_topic()

        def fail(pr: int, repository: str) -> cleanup.PREvidence:
            raise RuntimeError("GitHub PR evidence could not be read with authenticated gh")

        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ):
            plan, reasons = cleanup.build_plan(
                self.repo, self.pr_number, "main", "origin", None, False, fail
            )
        self.assertIsNone(plan)
        self.assertEqual(reasons, ["GitHub PR evidence could not be read with authenticated gh"])

    def test_task_git_operation_is_blocked(self) -> None:
        linked, head, evidence = self.prepare_linked()
        (self.git_dir(linked) / "CHERRY_PICK_HEAD").write_text(head + "\n", encoding="utf-8")
        plan, reasons = self.plan(evidence)
        self.assertIsNone(plan)
        self.assertTrue(any("task Git operation still in progress" in reason for reason in reasons))

    def test_dirty_canonical_is_blocked(self) -> None:
        _, _, evidence = self.prepare_linked()
        (self.repo / "untracked.txt").write_text("leftover\n", encoding="utf-8")
        plan, reasons = self.plan(evidence)
        self.assertIsNone(plan)
        self.assertTrue(any("canonical working tree is not clean" in reason for reason in reasons))

    def test_normal_merge_removes_worktree_but_retains_local_branch(self) -> None:
        linked, head = self.add_linked_topic()
        run("git", "merge", "--no-ff", self.topic, "-m", "merge topic", cwd=self.repo)
        run("git", "push", "origin", "main", cwd=self.repo)
        evidence = self.evidence(head)
        plan, reasons = self.plan(evidence)
        self.assertFalse(reasons)
        self.assertIn("retain local topic branch", "\n".join(plan.actions))
        result = self.execute(plan, evidence)
        self.assertTrue(result.ok, result.failures)
        self.assertFalse(linked.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{self.topic}", cwd=self.repo).stdout.strip(),
            head,
        )

    def test_remote_tracking_drift_is_blocked(self) -> None:
        _, head, evidence = self.prepare_linked()
        remote_main = run("git", "rev-parse", "origin/main", cwd=self.repo).stdout.strip()
        run("git", "update-ref", f"refs/remotes/origin/{self.topic}", remote_main, cwd=self.repo)
        plan, reasons = self.plan(evidence)
        self.assertIsNone(plan)
        self.assertTrue(any("remote-tracking ref" in reason and "drifted" in reason for reason in reasons))
        self.assertNotEqual(head, remote_main)

    def test_stale_target_remote_tracking_ref_is_retained_in_v1(self) -> None:
        linked, head = self.add_linked_topic(push=True)
        run(
            "git",
            "--git-dir",
            str(self.remote),
            "update-ref",
            "-d",
            f"refs/heads/{self.topic}",
            cwd=self.temp,
        )
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        evidence = self.evidence(head)
        plan, reasons = self.plan(evidence)
        self.assertFalse(reasons)
        self.assertIn("retain remote-tracking ref", "\n".join(plan.actions))
        result = self.execute(plan, evidence)
        self.assertTrue(result.ok, result.failures)
        self.assertFalse(linked.exists())
        self.assertEqual(
            run(
                "git",
                "rev-parse",
                f"refs/remotes/origin/{self.topic}",
                cwd=self.repo,
            ).stdout.strip(),
            head,
        )

    def test_revalidation_failure_has_no_effect(self) -> None:
        linked, head, evidence = self.prepare_linked()
        plan, reasons = self.plan(evidence)
        self.assertFalse(reasons)
        closed = self.evidence(head, state="CLOSED", merged_at=None)
        result = self.execute(plan, closed)
        self.assertFalse(result.ok)
        self.assertFalse(result.effects_started)
        self.assertTrue(linked.exists())

    def test_failure_after_local_effect_reports_incomplete_state(self) -> None:
        linked, head = self.add_linked_topic(push=True)
        self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)
        evidence = self.evidence(head)
        plan, reasons = self.plan(evidence, delete_remote=True)
        self.assertFalse(reasons)
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ), patch.object(cleanup, "_remote_delete_with_lease", return_value=False):
            result = cleanup.execute_plan(plan, self.repo, self.reader(evidence))
        self.assertFalse(result.ok)
        self.assertTrue(result.effects_started)
        self.assertFalse(linked.exists())
        self.assertTrue(any("remote topic branch deletion failed" in reason for reason in result.failures))


    def test_linked_main_and_primary_topic_blocks_cleanup(self) -> None:
        run("git", "checkout", "-b", self.topic, cwd=self.repo)
        linked = self.temp / "linked-main"
        run("git", "worktree", "add", str(linked), "main", cwd=self.repo)

        head = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        remote_main = self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=linked)

        wts = cleanup._read_worktrees(self.repo)[0]
        topic_wt = next(w for w in wts if w.branch_ref == f"refs/heads/{self.topic}")
        self.assertTrue(topic_wt.is_primary)

        ev = self.evidence(head)
        plan, reasons = self.plan(ev)

        self.assertIsNone(plan)
        self.assertTrue(any("primary topic worktree with linked canonical worktree is not safely supported for removal" in r for r in reasons))


    def test_primary_topic_linked_main_with_unrelated_active_worktree_blocks_safely(self) -> None:
        run("git", "checkout", "-b", self.topic, cwd=self.repo)

        linked_main = self.temp / "linked-main"
        run("git", "worktree", "add", str(linked_main), "main", cwd=self.repo)

        unrelated = self.temp / "unrelated-worktree"
        run("git", "worktree", "add", "-b", "other-branch", str(unrelated), "main", cwd=self.repo)

        (unrelated / "dirty.txt").write_text("untouched\n", encoding="utf-8")

        head = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        remote_main = self.advance_remote_main()
        run("git", "pull", "--ff-only", "origin", "main", cwd=linked_main)

        ev = self.evidence(head)
        plan, reasons = self.plan(ev)

        self.assertIsNone(plan)
        self.assertTrue(any("primary topic worktree with linked canonical worktree is not safely supported for removal" in r for r in reasons))

        self.assertTrue(unrelated.exists())
        self.assertTrue((unrelated / "dirty.txt").exists())
        self.assertEqual((unrelated / "dirty.txt").read_text(encoding="utf-8"), "untouched\n")

    def test_unrelated_worktree_and_ref_survive_cleanup(self) -> None:
        linked, _, evidence = self.prepare_linked()
        other_branch = "codex/other-unfinished"
        other_worktree = self.temp / "other-worktree"
        run("git", "worktree", "add", "-b", other_branch, str(other_worktree), "main", cwd=self.repo)
        other_sha = run("git", "rev-parse", "HEAD", cwd=other_worktree).stdout.strip()
        plan, reasons = self.plan(evidence)
        self.assertFalse(reasons)
        result = self.execute(plan, evidence)
        self.assertTrue(result.ok, result.failures)
        self.assertFalse(linked.exists())
        self.assertTrue(other_worktree.exists())
        self.assertEqual(
            run("git", "rev-parse", f"refs/heads/{other_branch}", cwd=self.repo).stdout.strip(),
            other_sha,
        )


if __name__ == "__main__":
    unittest.main()
