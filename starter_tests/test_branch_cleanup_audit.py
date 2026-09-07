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
                "orchestration",
                [],
                default_branch="main",
                retained=set(),
            ),
            audit.CLASS_NO_PR,
        )

    def test_retained_wins_before_no_pr_classification(self):
        self.assertEqual(
            audit.classify_branch(
                "orchestration",
                [],
                default_branch="main",
                retained={"orchestration"},
            ),
            audit.CLASS_RETAINED,
        )

    def test_default_branch_is_protected(self):
        self.assertEqual(
            audit.classify_branch(
                "main",
                [],
                default_branch="main",
                retained=set(),
            ),
            audit.CLASS_PROTECTED,
        )

    def test_merged_open_and_closed_unmerged_are_distinct(self):
        merged = [{"state": "closed", "merged_at": "2026-09-01T00:00:00Z"}]
        opened = [{"state": "open", "merged_at": None}]
        closed = [{"state": "closed", "merged_at": None}]
        self.assertEqual(
            audit.classify_branch("merged", merged, default_branch="main", retained=set()),
            audit.CLASS_MERGED,
        )
        self.assertEqual(
            audit.classify_branch("open", opened, default_branch="main", retained=set()),
            audit.CLASS_OPEN,
        )
        self.assertEqual(
            audit.classify_branch("closed", closed, default_branch="main", retained=set()),
            audit.CLASS_CLOSED,
        )


class ApiAndDeletionTests(unittest.TestCase):
    def test_branch_names_with_slash_and_hash_are_url_encoded(self):
        with mock.patch.object(audit, "api_json") as api_json:
            audit.delete_branch("oimus/repo", "codex/github-issue-#100")
        api_json.assert_called_once_with(
            "repos/oimus/repo/git/refs/heads/codex%2Fgithub-issue-%23100",
            method="DELETE",
        )

    def test_partial_prior_deletion_only_targets_present_merged_branches(self):
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

    def test_post_delete_residual_is_blocking(self):
        targets = [{"branch": "topic", "sha": "abc"}]
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            audit, "branch_map", side_effect=[{"topic": "abc"}, {"topic": "abc"}]
        ), mock.patch.object(audit, "delete_branch"):
            with self.assertRaisesRegex(audit.AuditError, "residual"):
                audit.execute_deletion(
                    "oimus/repo",
                    targets,
                    retained=set(),
                    audit_dir=Path(temp_dir),
                )

    def test_retained_branch_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(audit.AuditError, "retained"):
                audit.execute_deletion(
                    "oimus/repo",
                    [{"branch": "orchestration", "sha": "abc"}],
                    retained={"orchestration"},
                    audit_dir=Path(temp_dir),
                )

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
