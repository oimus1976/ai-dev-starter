import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import branch_cleanup_audit as audit

ROOT = Path(__file__).resolve().parents[1]


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


class AuthorityTests(unittest.TestCase):
    def test_repository_must_be_explicit_owner_repo(self):
        self.assertEqual(audit.validate_repository("oimus/repo"), "oimus/repo")
        for invalid in ("repo", "owner/", "/repo", "owner/repo/extra", ""):
            with self.subTest(invalid=invalid), self.assertRaises(audit.AuditError):
                audit.validate_repository(invalid)

    def test_api_is_pinned_to_github_com_even_when_environment_might_select_other_host(self):
        native = audit.NativeResult((), 0, "[]", "")
        with mock.patch.object(audit, "run_native", return_value=native) as run_native:
            self.assertEqual(audit.api_json("repos/oimus/repo/branches"), [])
        run_native.assert_called_once_with(
            [
                "gh",
                "api",
                "--hostname",
                "github.com",
                "repos/oimus/repo/branches",
            ]
        )

    def test_fork_pr_with_same_ref_is_excluded_from_same_repo_evidence(self):
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


class ClassificationTests(unittest.TestCase):
    def test_default_and_github_protected_branches_are_protected(self):
        self.assertEqual(
            audit.classify_branch(
                "main", "abc", [], default_branch="main", retained=set()
            ),
            audit.CLASS_PROTECTED,
        )
        self.assertEqual(
            audit.classify_branch(
                "release/stable",
                "abc",
                [{"state": "closed", "merged_at": "2026-09-01", "head": {"sha": "abc"}}],
                default_branch="main",
                retained=set(),
                github_protected=True,
            ),
            audit.CLASS_PROTECTED,
        )

    def test_retained_branch_wins_before_no_pr(self):
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

    def test_no_pr_is_review_required(self):
        self.assertEqual(
            audit.classify_branch(
                "orchestration", "abc", [], default_branch="main", retained=set()
            ),
            audit.CLASS_NO_PR,
        )

    def test_open_pr_is_not_review_deletion_candidate(self):
        opened = [{"state": "open", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(
            audit.classify_branch(
                "topic", "abc", opened, default_branch="main", retained=set()
            ),
            audit.CLASS_OPEN,
        )

    def test_exact_merged_name_and_sha_is_review_evidence_not_delete_authority(self):
        merged = [
            {
                "state": "closed",
                "merged_at": "2026-09-01T00:00:00Z",
                "head": {"sha": "abc"},
            }
        ]
        self.assertEqual(
            audit.classify_branch(
                "topic", "abc", merged, default_branch="main", retained=set()
            ),
            audit.CLASS_MERGED,
        )
        self.assertEqual(audit.CLASS_MERGED, "MERGED_REVIEW_CANDIDATE")

    def test_historical_merged_name_with_moved_sha_requires_review(self):
        merged = [
            {
                "state": "closed",
                "merged_at": "2026-09-01T00:00:00Z",
                "head": {"sha": "old"},
            }
        ]
        self.assertEqual(
            audit.classify_branch(
                "topic", "new", merged, default_branch="main", retained=set()
            ),
            audit.CLASS_MERGED_MOVED,
        )

    def test_closed_unmerged_requires_review(self):
        closed = [{"state": "closed", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(
            audit.classify_branch(
                "topic", "abc", closed, default_branch="main", retained=set()
            ),
            audit.CLASS_CLOSED,
        )


class ReviewEvidenceTests(unittest.TestCase):
    def inventory(self):
        return {
            "branches": [
                {
                    "branch": "main",
                    "sha": "m",
                    "classification": audit.CLASS_PROTECTED,
                    "pull_requests": [],
                },
                {
                    "branch": "retained",
                    "sha": "r",
                    "classification": audit.CLASS_RETAINED,
                    "pull_requests": [],
                },
                {
                    "branch": "open",
                    "sha": "o",
                    "classification": audit.CLASS_OPEN,
                    "pull_requests": [{"number": 1}],
                },
                {
                    "branch": "merged",
                    "sha": "a",
                    "classification": audit.CLASS_MERGED,
                    "pull_requests": [{"number": 2}],
                },
                {
                    "branch": "moved",
                    "sha": "b",
                    "classification": audit.CLASS_MERGED_MOVED,
                    "pull_requests": [{"number": 3}],
                },
                {
                    "branch": "closed",
                    "sha": "c",
                    "classification": audit.CLASS_CLOSED,
                    "pull_requests": [{"number": 4}],
                },
                {
                    "branch": "no-pr",
                    "sha": "d",
                    "classification": audit.CLASS_NO_PR,
                    "pull_requests": [],
                },
            ]
        }

    def test_review_candidates_are_evidence_only(self):
        candidates = audit.review_candidates(self.inventory())
        self.assertEqual(
            [item["branch"] for item in candidates],
            ["merged", "moved", "closed", "no-pr"],
        )
        for item in candidates:
            self.assertTrue(item["human_review_required"])
            self.assertFalse(item["deletion_authority"])
            self.assertIn("expected_sha", item)

    def test_main_writes_inventory_and_review_candidates_only(self):
        inventory = self.inventory()
        inventory.update(
            {
                "repository": "oimus/repo",
                "source_host": "github.com",
                "mutation_capability": "NONE",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            audit, "build_inventory", return_value=inventory
        ):
            exit_code = audit.main(
                ["--repository", "oimus/repo", "--audit-dir", temp_dir]
            )
            self.assertEqual(exit_code, 0)
            root = Path(temp_dir)
            self.assertTrue((root / "inventory.json").is_file())
            self.assertTrue((root / "review-candidates.json").is_file())
            payload = json.loads((root / "review-candidates.json").read_text(encoding="utf-8"))
            self.assertTrue(all(item["deletion_authority"] is False for item in payload))


class NoMutationSurfaceTests(unittest.TestCase):
    def test_parser_has_no_destructive_options(self):
        for args in (
            ["--repository", "oimus/repo", "--execute"],
            ["--repository", "oimus/repo", "--delete-merged"],
            ["--repository", "oimus/repo", "--delete-reviewed", "review.json"],
        ):
            with self.subTest(args=args), self.assertRaises(SystemExit) as raised:
                audit.parse_args(args)
            self.assertEqual(raised.exception.code, 2)

    def test_source_contains_no_remote_delete_primitive(self):
        text = (ROOT / "scripts/branch_cleanup_audit.py").read_text(encoding="utf-8")
        self.assertNotIn('"git", "push"', text)
        self.assertNotIn("delete_branch_with_lease", text)
        self.assertNotIn("execute_deletion", text)
        self.assertNotIn("--execute", text)
        self.assertNotIn("--delete-merged", text)
        self.assertNotIn("--delete-reviewed", text)
        self.assertIn('"mutation_capability": "NONE"', text)


if __name__ == "__main__":
    unittest.main()
