import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import branch_cleanup_audit as audit


class NativeResultTests(unittest.TestCase):
    def test_stderr_does_not_make_exit_zero_a_failure(self):
        result = audit.run_native(
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('normal native stderr\\n'); raise SystemExit(0)",
            ]
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.returncode, 0)
        self.assertIn("normal native stderr", result.stderr)

    def test_nonzero_exit_is_failure_even_with_normal_stdout(self):
        result = audit.run_native(
            [
                sys.executable,
                "-c",
                "import sys; print('looks fine'); raise SystemExit(7)",
            ]
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 7)
        with self.assertRaises(audit.AuditError):
            audit.require_ok(result, "fixture")

    def test_complex_argument_is_preserved_as_one_argv_entry(self):
        expression = ".[] | select(.merged_at != null) | .head.ref"
        result = audit.run_native(
            [
                sys.executable,
                "-c",
                "import sys; print(len(sys.argv)); print(sys.argv[1])",
                expression,
            ]
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout.splitlines(), ["2", expression])


class ClassificationTests(unittest.TestCase):
    def test_no_pr_empty_array_classifies_explicitly(self):
        self.assertEqual(
            audit.classify_branch(
                "orchestration", "abc", [], default_branch="main", retained=set()
            ),
            audit.CLASS_NO_PR,
        )

    def test_retained_wins_before_no_pr_classification(self):
        self.assertEqual(
            audit.classify_branch(
                "orchestration",
                "abc",
                [],
                default_branch="main",
                retained={"orchestration"},
            ),
            audit.CLASS_RETAINED,
        )

    def test_default_branch_is_protected(self):
        self.assertEqual(
            audit.classify_branch(
                "main", "abc", [], default_branch="main", retained=set()
            ),
            audit.CLASS_PROTECTED,
        )

    def test_github_protected_branch_is_protected_even_if_merged(self):
        prs = [
            {
                "state": "closed",
                "merged_at": "2026-09-01T00:00:00Z",
                "head": {"sha": "abc"},
            }
        ]
        self.assertEqual(
            audit.classify_branch(
                "release/stable",
                "abc",
                prs,
                default_branch="main",
                retained=set(),
                github_protected=True,
            ),
            audit.CLASS_PROTECTED,
        )

    def test_merged_open_and_closed_unmerged_are_distinct(self):
        merged = [
            {
                "state": "closed",
                "merged_at": "2026-09-01T00:00:00Z",
                "head": {"sha": "merged-sha"},
            }
        ]
        opened = [{"state": "open", "merged_at": None, "head": {"sha": "open-sha"}}]
        closed = [{"state": "closed", "merged_at": None, "head": {"sha": "closed-sha"}}]
        self.assertEqual(
            audit.classify_branch(
                "merged", "merged-sha", merged, default_branch="main", retained=set()
            ),
            audit.CLASS_MERGED,
        )
        self.assertEqual(
            audit.classify_branch(
                "open", "open-sha", opened, default_branch="main", retained=set()
            ),
            audit.CLASS_OPEN,
        )
        self.assertEqual(
            audit.classify_branch(
                "closed", "closed-sha", closed, default_branch="main", retained=set()
            ),
            audit.CLASS_CLOSED,
        )

    def test_historical_merged_name_with_moved_current_sha_requires_review(self):
        prs = [
            {
                "state": "closed",
                "merged_at": "2026-09-01T00:00:00Z",
                "head": {"sha": "old-merged-sha"},
            }
        ]
        self.assertEqual(
            audit.classify_branch(
                "reused-topic",
                "new-current-sha",
                prs,
                default_branch="main",
                retained=set(),
            ),
            audit.CLASS_MERGED_MOVED,
        )


class PullMappingTests(unittest.TestCase):
    def test_fork_pr_with_same_ref_does_not_authorize_same_repo_branch(self):
        same_repo = {
            "number": 2,
            "head": {
                "ref": "topic",
                "sha": "same-repo-sha",
                "repo": {"full_name": "oimus/repo"},
            },
        }
        fork = {
            "number": 1,
            "head": {
                "ref": "topic",
                "sha": "fork-sha",
                "repo": {"full_name": "someone/fork"},
            },
        }
        with mock.patch.object(audit, "paged_list", return_value=[fork, same_repo]):
            mapped = audit.pull_map("oimus/repo")
        self.assertEqual([pr["number"] for pr in mapped["topic"]], [2])


class ApiAndDeletionTests(unittest.TestCase):
    def test_partial_prior_deletion_only_targets_present_exact_merged_heads(self):
        inventory = {
            "branches": [
                {
                    "branch": "main",
                    "sha": "m",
                    "classification": audit.CLASS_PROTECTED,
                    "pull_requests": [],
                },
                {
                    "branch": "still-here",
                    "sha": "a",
                    "classification": audit.CLASS_MERGED,
                    "pull_requests": [{"number": 1}],
                },
                {
                    "branch": "same-name-but-moved",
                    "sha": "b",
                    "classification": audit.CLASS_MERGED_MOVED,
                    "pull_requests": [{"number": 2}],
                },
            ]
        }
        self.assertEqual(
            [row["branch"] for row in audit.merged_targets(inventory)],
            ["still-here"],
        )

    def test_reviewed_closed_branch_requires_exact_sha(self):
        inventory = {
            "branches": [
                {
                    "branch": "old-topic",
                    "sha": "new",
                    "classification": audit.CLASS_CLOSED,
                    "pull_requests": [{"number": 10}],
                }
            ]
        }
        with self.assertRaisesRegex(audit.AuditError, "moved"):
            audit.validate_reviewed_targets(
                inventory,
                [{"branch": "old-topic", "expected_sha": "old"}],
            )

    def test_https_origin_repository_is_parsed(self):
        result = audit.NativeResult(
            ("git", "remote", "get-url", "origin"),
            0,
            "https://github.com/oimus/repo.git\n",
            "",
        )
        with mock.patch.object(audit, "run_native", return_value=result):
            self.assertEqual(audit.origin_repository(), "oimus/repo")

    def test_scp_origin_repository_is_parsed(self):
        result = audit.NativeResult(
            ("git", "remote", "get-url", "origin"),
            0,
            "git@github.com:oimus/repo.git\n",
            "",
        )
        with mock.patch.object(audit, "run_native", return_value=result):
            self.assertEqual(audit.origin_repository(), "oimus/repo")

    def test_unrecognized_origin_blocks(self):
        result = audit.NativeResult(
            ("git", "remote", "get-url", "origin"),
            0,
            "https://example.invalid/oimus/repo.git\n",
            "",
        )
        with mock.patch.object(audit, "run_native", return_value=result):
            with self.assertRaisesRegex(audit.AuditError, "recognized github.com"):
                audit.origin_repository()

    def test_origin_mismatch_blocks(self):
        with mock.patch.object(audit, "origin_repository", return_value="other/repo"):
            with self.assertRaisesRegex(audit.AuditError, "origin repository mismatch"):
                audit.ensure_origin_matches("oimus/repo")

    def test_exact_lease_delete_preserves_slash_hash_and_accepts_success_stderr(self):
        native = audit.NativeResult(
            (), 0, "", "To https://github.com/oimus/repo.git\n - [deleted] topic\n"
        )
        with mock.patch.object(audit, "run_native", return_value=native) as run_native:
            result = audit.delete_branch_with_lease("codex/github-issue-#100", "abc123")
        self.assertEqual(result.returncode, 0)
        run_native.assert_called_once_with(
            [
                "git",
                "push",
                "--force-with-lease=refs/heads/codex/github-issue-#100:abc123",
                "origin",
                ":refs/heads/codex/github-issue-#100",
            ]
        )

    def test_exact_lease_delete_nonzero_blocks(self):
        native = audit.NativeResult((), 1, "", "stale info\n")
        with mock.patch.object(audit, "run_native", return_value=native):
            with self.assertRaisesRegex(audit.AuditError, "exit 1"):
                audit.delete_branch_with_lease("topic", "abc")

    def test_post_delete_residual_is_blocking(self):
        targets = [{"branch": "topic", "sha": "abc"}]
        success = audit.NativeResult((), 0, "", "normal success stderr")
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            audit, "ensure_origin_matches"
        ), mock.patch.object(
            audit, "branch_map", side_effect=[{"topic": "abc"}, {"topic": "abc"}]
        ), mock.patch.object(
            audit, "delete_branch_with_lease", return_value=success
        ):
            with self.assertRaisesRegex(audit.AuditError, "residual"):
                audit.execute_deletion(
                    "oimus/repo",
                    targets,
                    retained=set(),
                    audit_dir=Path(temp_dir),
                )

    def test_retained_branch_cannot_be_deleted_before_origin_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            audit, "ensure_origin_matches"
        ) as ensure_origin:
            with self.assertRaisesRegex(audit.AuditError, "retained"):
                audit.execute_deletion(
                    "oimus/repo",
                    [{"branch": "orchestration", "sha": "abc"}],
                    retained={"orchestration"},
                    audit_dir=Path(temp_dir),
                )
            ensure_origin.assert_not_called()

    def test_review_manifest_rejects_duplicate_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review.json"
            path.write_text(
                json.dumps(
                    [
                        {"branch": "topic", "expected_sha": "a"},
                        {"branch": "topic", "expected_sha": "a"},
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(audit.AuditError, "duplicate"):
                audit.load_reviewed_targets(path)


if __name__ == "__main__":
    unittest.main()
