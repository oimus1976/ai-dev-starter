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


class OpaqueCleanupStateTests(unittest.TestCase):
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

    def linked_topic(self) -> tuple[Path, str]:
        linked = self.temp / "topic-worktree"
        run("git", "worktree", "add", "-b", self.topic, str(linked), "main", cwd=self.repo)
        self.configure(linked)
        (linked / "topic.txt").write_text("topic\n", encoding="utf-8")
        run("git", "add", "topic.txt", cwd=linked)
        run("git", "commit", "-m", "topic", cwd=linked)
        return linked, run("git", "rev-parse", "HEAD", cwd=linked).stdout.strip()

    def merge_result(self) -> None:
        other = self.temp / "other"
        run("git", "clone", str(self.remote), str(other), cwd=self.temp)
        self.configure(other)
        (other / "merged.txt").write_text("squash-like result\n", encoding="utf-8")
        run("git", "add", "merged.txt", cwd=other)
        run("git", "commit", "-m", "merged result", cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        run("git", "pull", "--ff-only", "origin", "main", cwd=self.repo)

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
                lambda pr, repository: evidence,
            )

    def test_ignored_file_blocks_destructive_cleanup(self) -> None:
        linked, head = self.linked_topic()
        self.merge_result()
        exclude = Path(run("git", "rev-parse", "--git-path", "info/exclude", cwd=linked).stdout.strip())
        if not exclude.is_absolute():
            exclude = (linked / exclude).resolve()
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write("ignored.tmp\n")
        (linked / "ignored.tmp").write_text("local-only data\n", encoding="utf-8")
        self.assertEqual(run("git", "status", "--porcelain=v1", cwd=linked).stdout.strip(), "")

        plan, reasons = self.plan(self.evidence(head))
        self.assertIsNone(plan)
        self.assertTrue(any("contains ignored files/directories" in reason for reason in reasons))
        self.assertTrue((linked / "ignored.tmp").exists())

    def test_assume_unchanged_modified_file_blocks_cleanup(self) -> None:
        linked, head = self.linked_topic()
        self.merge_result()
        run("git", "update-index", "--assume-unchanged", "topic.txt", cwd=linked)
        (linked / "topic.txt").write_text("hidden local edit\n", encoding="utf-8")
        self.assertEqual(run("git", "status", "--porcelain=v1", cwd=linked).stdout.strip(), "")

        plan, reasons = self.plan(self.evidence(head))
        self.assertIsNone(plan)
        self.assertTrue(any("assume-unchanged" in reason for reason in reasons))
        self.assertEqual((linked / "topic.txt").read_text(encoding="utf-8"), "hidden local edit\n")

    def test_skip_worktree_flag_blocks_cleanup(self) -> None:
        linked, head = self.linked_topic()
        self.merge_result()
        run("git", "update-index", "--skip-worktree", "topic.txt", cwd=linked)

        plan, reasons = self.plan(self.evidence(head))
        self.assertIsNone(plan)
        self.assertTrue(any("skip-worktree" in reason for reason in reasons))

    def test_missing_gh_is_reported_as_generic_blocking_evidence_failure(self) -> None:
        with patch.object(cleanup.subprocess, "run", side_effect=FileNotFoundError("gh missing")):
            with self.assertRaisesRegex(
                RuntimeError, "GitHub PR evidence could not be read with authenticated gh"
            ) as raised:
                cleanup.read_github_pr(self.pr_number, "oimus1976/ai-dev-starter")
        self.assertNotIn("gh missing", str(raised.exception))

    def test_failed_worktree_remove_is_incomplete_not_blocked(self) -> None:
        linked, head = self.linked_topic()
        self.merge_result()
        evidence = self.evidence(head)
        plan, reasons = self.plan(evidence)
        self.assertFalse(reasons)
        real_git = cleanup.git

        def fail_remove(*args: str, cwd: Path, check: bool = True):
            if args[:2] == ("worktree", "remove"):
                return subprocess.CompletedProcess(["git", *args], 1, "simulated failure")
            return real_git(*args, cwd=cwd, check=check)

        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ), patch.object(cleanup, "git", side_effect=fail_remove):
            result = cleanup.execute_plan(
                plan, self.repo, lambda pr, repository: evidence
            )

        self.assertFalse(result.ok)
        self.assertTrue(result.effects_started)
        self.assertTrue(linked.exists())
        self.assertTrue(any("normal topic worktree removal failed" in reason for reason in result.failures))







    def test_topology_determination_failure_blocks_cleanup(self) -> None:
        linked, head = self.linked_topic()
        self.merge_result()
        evidence = self.evidence(head)
        real_git = cleanup.git

        def fail_topology(*args: str, cwd: Path, check: bool = True):
            if args[:2] == ("rev-parse", "--path-format=absolute"):
                return subprocess.CompletedProcess(["git", *args], 1, "fatal: not a git directory\n")
            return real_git(*args, cwd=cwd, check=check)

        import closeout_state
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ), patch.object(closeout_state, "git", side_effect=fail_topology):
            plan, reasons = self.plan(evidence)

        self.assertIsNone(plan)
        self.assertTrue(any("could not determine primary vs linked topology for worktree" in r for r in reasons))


    def test_topology_determination_partial_failure_blocks_cleanup(self) -> None:
        linked, head = self.linked_topic()
        self.merge_result()
        evidence = self.evidence(head)
        real_git = cleanup.git

        def fail_topology(*args: str, cwd: Path, check: bool = True):
            if args[:2] == ("rev-parse", "--path-format=absolute"):
                if "--git-common-dir" in args:
                    return subprocess.CompletedProcess(["git", *args], 1, "fatal: not a git directory\n")
            return real_git(*args, cwd=cwd, check=check)

        import closeout_state
        with patch.object(
            cleanup,
            "remote_repository_identity",
            return_value=("oimus1976/ai-dev-starter", None),
        ), patch.object(closeout_state, "git", side_effect=fail_topology):
            plan, reasons = self.plan(evidence)

        self.assertIsNone(plan)
        self.assertTrue(any("could not determine primary vs linked topology for worktree" in r for r in reasons))
if __name__ == "__main__":
    unittest.main()