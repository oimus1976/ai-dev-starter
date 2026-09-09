import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import branch_cleanup_audit as audit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/branch_cleanup_audit.py"


def _parent_map(tree):
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _enclosing_function(node, parents):
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return None


def assert_audit_only_source(testcase, source):
    """Enforce the complete audit-only native/network capability boundary."""

    tree = ast.parse(source)
    parents = _parent_map(tree)

    actual_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                actual_imports.append(("import", alias.name, alias.asname))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                actual_imports.append(("from", node.module, alias.name, alias.asname))

    expected_imports = {
        ("from", "__future__", "annotations", None),
        ("import", "argparse", None),
        ("import", "json", None),
        ("import", "subprocess", None),
        ("import", "sys", None),
        ("import", "tempfile", None),
        ("from", "datetime", "datetime", None),
        ("from", "datetime", "timezone", None),
        ("from", "pathlib", "Path", None),
        ("from", "typing", "Any", None),
        ("from", "typing", "Iterable", None),
        ("from", "typing", "Sequence", None),
        ("from", "urllib.parse", "quote", None),
    }
    testcase.assertEqual(set(actual_imports), expected_imports)
    testcase.assertEqual(len(actual_imports), len(expected_imports))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            testcase.assertNotIn(node.func.id, {"__import__", "eval", "exec", "compile"})

    subprocess_attributes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "subprocess"
    ]
    testcase.assertTrue(subprocess_attributes)
    testcase.assertTrue(all(node.attr in {"run", "PIPE"} for node in subprocess_attributes))

    run_attributes = [node for node in subprocess_attributes if node.attr == "run"]
    testcase.assertEqual(len(run_attributes), 1)
    run_attr = run_attributes[0]
    run_call = parents.get(run_attr)
    testcase.assertIsInstance(run_call, ast.Call)
    testcase.assertIs(run_call.func, run_attr)
    testcase.assertEqual(_enclosing_function(run_call, parents), "github_api_get")

    testcase.assertEqual(len(run_call.args), 1)
    argv_list = run_call.args[0]
    testcase.assertIsInstance(argv_list, ast.List)
    testcase.assertEqual(len(argv_list.elts), 5)
    testcase.assertEqual(
        [argv_list.elts[index].value for index in range(3)],
        ["gh", "api", "--hostname"],
    )
    testcase.assertIsInstance(argv_list.elts[3], ast.Name)
    testcase.assertEqual(argv_list.elts[3].id, "GITHUB_HOST")
    testcase.assertIsInstance(argv_list.elts[4], ast.Name)
    testcase.assertEqual(argv_list.elts[4].id, "endpoint")

    keywords = {keyword.arg: keyword.value for keyword in run_call.keywords}
    testcase.assertEqual(set(keywords), {"stdout", "stderr", "check"})
    for name in ("stdout", "stderr"):
        value = keywords[name]
        testcase.assertIsInstance(value, ast.Attribute)
        testcase.assertIsInstance(value.value, ast.Name)
        testcase.assertEqual(value.value.id, "subprocess")
        testcase.assertEqual(value.attr, "PIPE")
    testcase.assertIsInstance(keywords["check"], ast.Constant)
    testcase.assertIs(keywords["check"].value, False)

    subprocess_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    testcase.assertEqual(subprocess_calls, [run_call])


class NativeBoundaryTests(unittest.TestCase):
    def test_api_is_pinned_get_only_and_stderr_is_diagnostic_on_success(self):
        completed = mock.Mock(returncode=0, stdout=b"[]", stderr=b"normal stderr\n")
        with mock.patch.object(audit.subprocess, "run", return_value=completed) as run:
            self.assertEqual(audit.github_api_get("repos/oimus/repo/branches"), [])
        run.assert_called_once_with(
            ["gh", "api", "--hostname", "github.com", "repos/oimus/repo/branches"],
            stdout=audit.subprocess.PIPE,
            stderr=audit.subprocess.PIPE,
            check=False,
        )

    def test_nonzero_api_exit_fails_closed(self):
        completed = mock.Mock(returncode=7, stdout=b"looks fine", stderr=b"")
        with mock.patch.object(audit.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(audit.AuditError, "failed with exit 7"):
                audit.github_api_get("repos/oimus/repo")


class AuthorityTests(unittest.TestCase):
    def test_repository_must_be_explicit_owner_repo(self):
        self.assertEqual(audit.validate_repository("oimus/repo"), "oimus/repo")
        for invalid in ("repo", "owner/", "/repo", "owner/repo/extra", ""):
            with self.subTest(invalid=invalid), self.assertRaises(audit.AuditError):
                audit.validate_repository(invalid)

    def test_repository_identity_uses_authoritative_canonical_full_name(self):
        with mock.patch.object(
            audit,
            "api_json",
            return_value={"full_name": "oimus1976/ai-dev-starter", "default_branch": "main"},
        ) as api_json:
            canonical, default_branch = audit.repository_identity("OIMUS1976/AI-DEV-STARTER")
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
            return_value={
                "main": {"sha": "m", "protected": False},
                "topic": {"sha": "abc", "protected": False},
            },
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

    def test_fork_pr_with_same_ref_is_excluded_from_same_repo_evidence(self):
        same_repo = {"number": 2, "head": {"ref": "topic", "sha": "same", "repo": {"full_name": "oimus/repo"}}}
        fork = {"number": 1, "head": {"ref": "topic", "sha": "fork", "repo": {"full_name": "someone/fork"}}}
        with mock.patch.object(audit, "paged_list", return_value=[fork, same_repo]):
            mapped = audit.pull_map("oimus/repo")
        self.assertEqual([pr["number"] for pr in mapped["topic"]], [2])


class ClassificationTests(unittest.TestCase):
    def test_classification_contract(self):
        self.assertEqual(audit.classify_branch("main", "abc", [], default_branch="main", retained=set()), audit.CLASS_PROTECTED)
        self.assertEqual(audit.classify_branch("keep", "abc", [], default_branch="main", retained={"keep"}), audit.CLASS_RETAINED)
        self.assertEqual(audit.classify_branch("none", "abc", [], default_branch="main", retained=set()), audit.CLASS_NO_PR)
        opened = [{"state": "open", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(audit.classify_branch("topic", "abc", opened, default_branch="main", retained=set()), audit.CLASS_OPEN)
        merged = [{"state": "closed", "merged_at": "2026-09-01T00:00:00Z", "head": {"sha": "abc"}}]
        self.assertEqual(audit.classify_branch("topic", "abc", merged, default_branch="main", retained=set()), audit.CLASS_MERGED)
        self.assertEqual(audit.classify_branch("topic", "new", merged, default_branch="main", retained=set()), audit.CLASS_MERGED_MOVED)
        closed = [{"state": "closed", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(audit.classify_branch("topic", "abc", closed, default_branch="main", retained=set()), audit.CLASS_CLOSED)


class ReviewEvidenceTests(unittest.TestCase):
    def test_review_candidates_are_evidence_only(self):
        inventory = {
            "branches": [
                {"branch": "merged", "sha": "a", "classification": audit.CLASS_MERGED, "pull_requests": [{"number": 2}]},
                {"branch": "open", "sha": "o", "classification": audit.CLASS_OPEN, "pull_requests": [{"number": 1}]},
            ]
        }
        candidates = audit.review_candidates(inventory)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["human_review_required"])
        self.assertFalse(candidates[0]["deletion_authority"])

    def test_main_writes_real_inventory_authority_fields(self):
        responses = {
            "repos/OIMUS/REPO": {"full_name": "oimus/repo", "default_branch": "main"},
            "repos/oimus/repo/branches?per_page=100&page=1": [
                {"name": "main", "commit": {"sha": "m"}, "protected": True},
                {"name": "topic", "commit": {"sha": "abc"}, "protected": False},
            ],
            "repos/oimus/repo/pulls?state=all&per_page=100&page=1": [
                {
                    "number": 1,
                    "state": "closed",
                    "merged_at": "2026-09-01T00:00:00Z",
                    "title": "merged",
                    "html_url": "https://github.com/oimus/repo/pull/1",
                    "head": {"ref": "topic", "sha": "abc", "repo": {"full_name": "oimus/repo"}},
                }
            ],
        }

        def api_side_effect(endpoint):
            self.assertIn(endpoint, responses)
            return responses[endpoint]

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(audit, "api_json", side_effect=api_side_effect):
            exit_code = audit.main(["--repository", "OIMUS/REPO", "--audit-dir", temp_dir])
            self.assertEqual(exit_code, 0)
            root = Path(temp_dir)
            inventory = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
            candidates = json.loads((root / "review-candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(inventory["source_host"], "github.com")
            self.assertEqual(inventory["mutation_capability"], "NONE")
            self.assertEqual(inventory["repository"], "oimus/repo")
            self.assertEqual(inventory["requested_repository"], "OIMUS/REPO")
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

    def test_production_source_satisfies_exact_capability_allowlist(self):
        assert_audit_only_source(self, SOURCE.read_text(encoding="utf-8"))

    def test_negative_fixture_rejects_subprocess_from_import_alias(self):
        mutated = SOURCE.read_text(encoding="utf-8") + "\nfrom subprocess import run as invoke\ninvoke(['git','push'])\n"
        with self.assertRaises(AssertionError):
            assert_audit_only_source(self, mutated)

    def test_negative_fixture_rejects_subprocess_run_assignment_alias(self):
        mutated = SOURCE.read_text(encoding="utf-8") + "\ninvoke = subprocess.run\ninvoke(['git','push'])\n"
        with self.assertRaises(AssertionError):
            assert_audit_only_source(self, mutated)

    def test_negative_fixture_rejects_urllib_request(self):
        mutated = SOURCE.read_text(encoding="utf-8") + "\nfrom urllib import request\nrequest.Request('https://api.github.com', method='DELETE')\n"
        with self.assertRaises(AssertionError):
            assert_audit_only_source(self, mutated)

    def test_negative_fixture_rejects_dynamic_import(self):
        mutated = SOURCE.read_text(encoding="utf-8") + "\nmod = __import__('subprocess')\nmod.run(['git','push'])\n"
        with self.assertRaises(AssertionError):
            assert_audit_only_source(self, mutated)

    def test_negative_fixture_rejects_second_process_helper(self):
        mutated = SOURCE.read_text(encoding="utf-8") + "\ndef mutate():\n    return subprocess.run(['git','push'])\n"
        with self.assertRaises(AssertionError):
            assert_audit_only_source(self, mutated)

    def test_end_to_end_inventory_calls_fixed_get_only_adapter(self):
        responses = {
            "repos/OIMUS/REPO": {"full_name": "oimus/repo", "default_branch": "main"},
            "repos/oimus/repo/branches?per_page=100&page=1": [{"name": "main", "commit": {"sha": "m"}, "protected": True}],
            "repos/oimus/repo/pulls?state=all&per_page=100&page=1": [],
        }

        def get_side_effect(endpoint):
            self.assertIn(endpoint, responses)
            return responses[endpoint]

        with mock.patch.object(audit, "github_api_get", side_effect=get_side_effect) as getter:
            inventory = audit.build_inventory("OIMUS/REPO", set())
        self.assertEqual(inventory["repository"], "oimus/repo")
        self.assertEqual(inventory["source_host"], "github.com")
        self.assertEqual(inventory["mutation_capability"], "NONE")
        self.assertEqual(getter.call_count, 3)


if __name__ == "__main__":
    unittest.main()
