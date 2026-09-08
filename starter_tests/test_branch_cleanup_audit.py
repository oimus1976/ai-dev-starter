import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import branch_cleanup_audit as audit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/branch_cleanup_audit.py"


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
            ["gh", "api", "--hostname", "github.com", "repos/oimus/repo/branches"]
        )

    def test_repository_identity_uses_authoritative_canonical_full_name(self):
        with mock.patch.object(
            audit,
            "api_json",
            return_value={
                "full_name": "oimus1976/ai-dev-starter",
                "default_branch": "main",
            },
        ) as api_json:
            canonical, default_branch = audit.repository_identity(
                "OIMUS1976/AI-DEV-STARTER"
            )
        self.assertEqual(canonical, "oimus1976/ai-dev-starter")
        self.assertEqual(default_branch, "main")
        api_json.assert_called_once_with("repos/OIMUS1976/AI-DEV-STARTER")

    def test_build_inventory_uses_canonical_identity_for_branch_and_pr_reads(self):
        same_repo_pr = {
            "number": 9,
            "state": "open",
            "merged_at": None,
            "head": {
                "ref": "topic",
                "sha": "abc",
                "repo": {"full_name": "oimus1976/ai-dev-starter"},
            },
        }
        with mock.patch.object(
            audit,
            "repository_identity",
            return_value=("oimus1976/ai-dev-starter", "main"),
        ), mock.patch.object(
            audit,
            "branch_records",
            return_value={"main": {"sha": "m", "protected": False}, "topic": {"sha": "abc", "protected": False}},
        ) as branches, mock.patch.object(
            audit, "pull_map", return_value={"topic": [same_repo_pr]}
        ) as pulls:
            inventory = audit.build_inventory("OIMUS1976/AI-DEV-STARTER", set())
        branches.assert_called_once_with("oimus1976/ai-dev-starter")
        pulls.assert_called_once_with("oimus1976/ai-dev-starter")
        self.assertEqual(inventory["repository"], "oimus1976/ai-dev-starter")
        self.assertEqual(inventory["requested_repository"], "OIMUS1976/AI-DEV-STARTER")
        topic = next(row for row in inventory["branches"] if row["branch"] == "topic")
        self.assertEqual(topic["classification"], audit.CLASS_OPEN)
        self.assertEqual(topic["pull_requests"][0]["number"], 9)

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
            audit.classify_branch("main", "abc", [], default_branch="main", retained=set()),
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
            audit.classify_branch("orchestration", "abc", [], default_branch="main", retained={"orchestration"}),
            audit.CLASS_RETAINED,
        )

    def test_no_pr_is_review_required(self):
        self.assertEqual(
            audit.classify_branch("orchestration", "abc", [], default_branch="main", retained=set()),
            audit.CLASS_NO_PR,
        )

    def test_open_pr_is_not_review_deletion_candidate(self):
        opened = [{"state": "open", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(
            audit.classify_branch("topic", "abc", opened, default_branch="main", retained=set()),
            audit.CLASS_OPEN,
        )

    def test_exact_merged_name_and_sha_is_review_evidence_not_delete_authority(self):
        merged = [{"state": "closed", "merged_at": "2026-09-01T00:00:00Z", "head": {"sha": "abc"}}]
        self.assertEqual(
            audit.classify_branch("topic", "abc", merged, default_branch="main", retained=set()),
            audit.CLASS_MERGED,
        )
        self.assertEqual(audit.CLASS_MERGED, "MERGED_REVIEW_CANDIDATE")

    def test_historical_merged_name_with_moved_sha_requires_review(self):
        merged = [{"state": "closed", "merged_at": "2026-09-01T00:00:00Z", "head": {"sha": "old"}}]
        self.assertEqual(
            audit.classify_branch("topic", "new", merged, default_branch="main", retained=set()),
            audit.CLASS_MERGED_MOVED,
        )

    def test_closed_unmerged_requires_review(self):
        closed = [{"state": "closed", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(
            audit.classify_branch("topic", "abc", closed, default_branch="main", retained=set()),
            audit.CLASS_CLOSED,
        )


class ReviewEvidenceTests(unittest.TestCase):
    def inventory(self):
        return {
            "source_host": "github.com",
            "repository": "oimus/repo",
            "requested_repository": "oimus/repo",
            "default_branch": "main",
            "mutation_capability": "NONE",
            "branches": [
                {"branch": "main", "sha": "m", "classification": audit.CLASS_PROTECTED, "pull_requests": []},
                {"branch": "retained", "sha": "r", "classification": audit.CLASS_RETAINED, "pull_requests": []},
                {"branch": "open", "sha": "o", "classification": audit.CLASS_OPEN, "pull_requests": [{"number": 1}]},
                {"branch": "merged", "sha": "a", "classification": audit.CLASS_MERGED, "pull_requests": [{"number": 2}]},
                {"branch": "moved", "sha": "b", "classification": audit.CLASS_MERGED_MOVED, "pull_requests": [{"number": 3}]},
                {"branch": "closed", "sha": "c", "classification": audit.CLASS_CLOSED, "pull_requests": [{"number": 4}]},
                {"branch": "no-pr", "sha": "d", "classification": audit.CLASS_NO_PR, "pull_requests": []},
            ],
        }

    def test_review_candidates_are_evidence_only(self):
        candidates = audit.review_candidates(self.inventory())
        self.assertEqual([item["branch"] for item in candidates], ["merged", "moved", "closed", "no-pr"])
        for item in candidates:
            self.assertTrue(item["human_review_required"])
            self.assertFalse(item["deletion_authority"])
            self.assertIn("expected_sha", item)

    def test_main_writes_real_inventory_authority_fields(self):
        branch_payload = [
            {"name": "main", "commit": {"sha": "m"}, "protected": True},
            {"name": "topic", "commit": {"sha": "abc"}, "protected": False},
        ]
        pr_payload = [
            {
                "number": 1,
                "state": "closed",
                "merged_at": "2026-09-01T00:00:00Z",
                "title": "merged",
                "html_url": "https://github.com/oimus/repo/pull/1",
                "head": {
                    "ref": "topic",
                    "sha": "abc",
                    "repo": {"full_name": "oimus/repo"},
                },
            }
        ]

        def api_side_effect(endpoint):
            if endpoint == "repos/OIMUS/REPO":
                return {"full_name": "oimus/repo", "default_branch": "main"}
            if endpoint.startswith("repos/oimus/repo/branches?"):
                return branch_payload
            if endpoint.startswith("repos/oimus/repo/pulls?"):
                return pr_payload
            self.fail(f"unexpected endpoint: {endpoint}")

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            audit, "api_json", side_effect=api_side_effect
        ):
            exit_code = audit.main(["--repository", "OIMUS/REPO", "--audit-dir", temp_dir])
            self.assertEqual(exit_code, 0)
            root = Path(temp_dir)
            inventory = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
            candidates = json.loads((root / "review-candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(inventory["source_host"], "github.com")
            self.assertEqual(inventory["mutation_capability"], "NONE")
            self.assertEqual(inventory["repository"], "oimus/repo")
            self.assertEqual(inventory["requested_repository"], "OIMUS/REPO")
            self.assertEqual(candidates[0]["classification"], audit.CLASS_MERGED)
            self.assertTrue(candidates[0]["human_review_required"])
            self.assertFalse(candidates[0]["deletion_authority"])


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

    def test_ast_restricts_imports_and_native_process_surface(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        self.assertEqual(
            imported_roots,
            {"__future__", "argparse", "json", "subprocess", "sys", "tempfile", "dataclasses", "datetime", "pathlib", "typing", "urllib"},
        )

        run_native_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run_native"
        ]
        self.assertEqual(len(run_native_calls), 1)
        call = run_native_calls[0]
        self.assertIsInstance(call.args[0], ast.List)
        argv = call.args[0].elts
        self.assertGreaterEqual(len(argv), 5)
        self.assertEqual([elt.value for elt in argv[:3] if isinstance(elt, ast.Constant)], ["gh", "api", "--hostname"])
        self.assertIsInstance(argv[3], ast.Name)
        self.assertEqual(argv[3].id, "GITHUB_HOST")
        self.assertIsInstance(argv[4], ast.Name)
        self.assertEqual(argv[4].id, "endpoint")

        subprocess_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        self.assertEqual(len(subprocess_calls), 1)
        self.assertEqual(subprocess_calls[0].func.attr, "run")

    def test_end_to_end_inventory_native_calls_are_get_only_github_com_api(self):
        responses = {
            "repos/OIMUS/REPO": {"full_name": "oimus/repo", "default_branch": "main"},
            "repos/oimus/repo/branches?per_page=100&page=1": [
                {"name": "main", "commit": {"sha": "m"}, "protected": True}
            ],
            "repos/oimus/repo/pulls?state=all&per_page=100&page=1": [],
        }

        def native_side_effect(args, *, cwd=None):
            self.assertIsNone(cwd)
            self.assertEqual(args[:4], ["gh", "api", "--hostname", "github.com"])
            self.assertEqual(len(args), 5)
            endpoint = args[4]
            self.assertIn(endpoint, responses)
            return audit.NativeResult(tuple(args), 0, json.dumps(responses[endpoint]), "")

        with mock.patch.object(audit, "run_native", side_effect=native_side_effect) as run_native:
            inventory = audit.build_inventory("OIMUS/REPO", set())
        self.assertEqual(inventory["repository"], "oimus/repo")
        self.assertEqual(inventory["source_host"], "github.com")
        self.assertEqual(inventory["mutation_capability"], "NONE")
        self.assertEqual(run_native.call_count, 3)


if __name__ == "__main__":
    unittest.main()
