import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import branch_cleanup_audit as audit
from scripts import branch_cleanup_core as core
from scripts import branch_cleanup_github as github


def responses():
    return {
        "repos/OIMUS/REPO": {"full_name": "oimus/repo", "default_branch": "main"},
        "repos/oimus/repo/branches?per_page=100&page=1": [
            {"name": "main", "commit": {"sha": "m"}, "protected": True},
            {"name": "topic", "commit": {"sha": "abc"}, "protected": False},
            {"name": "closed", "commit": {"sha": "c"}, "protected": False},
            {"name": "no-pr", "commit": {"sha": "n"}, "protected": False},
        ],
        "repos/oimus/repo/pulls?state=all&per_page=100&page=1": [
            {"number": 1, "state": "closed", "merged_at": "2026-09-01T00:00:00Z",
             "head": {"ref": "topic", "sha": "abc", "repo": {"full_name": "oimus/repo"}}},
            {"number": 2, "state": "open", "merged_at": None,
             "head": {"ref": "topic", "sha": "abc", "repo": {"full_name": "someone/fork"}}},
            {"number": 3, "state": "closed", "merged_at": None,
             "head": {"ref": "closed", "sha": "c", "repo": {"full_name": "oimus/repo"}}},
        ],
    }


def native_response(argv, **kwargs):
    return mock.Mock(returncode=0, stdout=json.dumps(responses()[argv[4]]).encode("utf-8"), stderr=b"normal diagnostic")


class NativeBoundaryTests(unittest.TestCase):
    def test_public_reads_use_fixed_get_argv_and_stderr_is_diagnostic(self):
        cases = [
            (github.repository_metadata, "repos/oimus/repo", {}),
            (github.branches, "repos/oimus/repo/branches?per_page=100&page=1", []),
            (github.pulls, "repos/oimus/repo/pulls?state=all&per_page=100&page=1", []),
        ]
        for read, endpoint, payload in cases:
            with self.subTest(read=read.__name__):
                completed = mock.Mock(returncode=0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"normal stderr\n")
                with mock.patch.object(github.subprocess, "run", return_value=completed) as run:
                    self.assertEqual(read("oimus/repo"), payload)
                run.assert_called_once_with(
                    ["gh", "api", "--hostname", "github.com", endpoint],
                    stdout=github.subprocess.PIPE, stderr=github.subprocess.PIPE, check=False,
                )

    def test_nonzero_exit_fails_closed_even_with_valid_stdout(self):
        for stderr in (b"", b"denied"):
            with self.subTest(stderr=stderr):
                completed = mock.Mock(returncode=7, stdout=b"{}", stderr=stderr)
                with mock.patch.object(github.subprocess, "run", return_value=completed):
                    with self.assertRaisesRegex(core.AuditError, "failed with exit 7"):
                        github.repository_metadata("oimus/repo")

    def test_invalid_json_fails_closed(self):
        completed = mock.Mock(returncode=0, stdout=b"not json", stderr=b"")
        with mock.patch.object(github.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(core.AuditError, "invalid JSON"):
                github.repository_metadata("oimus/repo")

    def test_pagination_preserves_fixed_reads(self):
        for read, resource, query in ((github.branches, "branches", ""), (github.pulls, "pulls", "state=all&")):
            with self.subTest(resource=resource):
                pages = [[{"name": str(n)} for n in range(100)], [{"name": "last"}]]
                completed = [mock.Mock(returncode=0, stdout=json.dumps(page).encode("utf-8"), stderr=b"") for page in pages]
                with mock.patch.object(github.subprocess, "run", side_effect=completed) as run:
                    self.assertEqual(len(read("oimus/repo")), 101)
                self.assertEqual(run.call_args_list, [
                    mock.call(["gh", "api", "--hostname", "github.com", f"repos/oimus/repo/{resource}?{query}per_page=100&page={page}"],
                              stdout=github.subprocess.PIPE, stderr=github.subprocess.PIPE, check=False)
                    for page in (1, 2)
                ])

    def test_malformed_pages_fail_closed(self):
        for payload in (None, {}, [1]):
            with self.subTest(payload=payload):
                completed = mock.Mock(returncode=0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")
                with mock.patch.object(github.subprocess, "run", return_value=completed):
                    with self.assertRaises(core.AuditError):
                        github.branches("oimus/repo")

    def test_repository_segments_cannot_inject_query_or_options(self):
        completed = mock.Mock(returncode=0, stdout=b"{}", stderr=b"")
        with mock.patch.object(github.subprocess, "run", return_value=completed) as run:
            github.repository_metadata("owner/repo?--method=DELETE")
        self.assertEqual(run.call_args.args[0], ["gh", "api", "--hostname", "github.com", "repos/owner/repo%3F--method%3DDELETE"])

    def test_invalid_repository_or_resource_does_not_start_process(self):
        with mock.patch.object(github.subprocess, "run") as run:
            for invalid in ("repo", "owner/", "/repo", "owner/repo/extra", ""):
                with self.subTest(invalid=invalid), self.assertRaises(core.AuditError):
                    github.repository_metadata(invalid)
            with self.assertRaises(core.AuditError):
                github._paged_list("oimus/repo", "git/refs")
        run.assert_not_called()


class AuthorityTests(unittest.TestCase):
    def test_canonical_repository_identity_is_interpreted_from_metadata(self):
        self.assertEqual(core.repository_identity({"full_name": "oimus/repo", "default_branch": "main"}), ("oimus/repo", "main"))
        for invalid in (None, {}, {"full_name": "/repo", "default_branch": "main"}, {"full_name": "oimus/repo", "default_branch": ""}):
            with self.subTest(invalid=invalid), self.assertRaises(core.AuditError):
                core.repository_identity(invalid)

    def test_malformed_branch_authority_fails_closed(self):
        for item in ({}, {"name": "topic", "commit": {"sha": "abc"}, "protected": None}):
            with self.subTest(item=item), self.assertRaises(core.AuditError):
                core.branch_records([item])

    def test_pure_inventory_preserves_authority_and_review_states(self):
        data = responses()
        kwargs = dict(
            identity=core.repository_identity(data["repos/OIMUS/REPO"]),
            branch_items=data["repos/oimus/repo/branches?per_page=100&page=1"],
            pull_items=data["repos/oimus/repo/pulls?state=all&per_page=100&page=1"],
            generated_at="2026-09-09T00:00:00+00:00",
        )
        inventory = core.build_inventory("OIMUS/REPO", set(), **kwargs)
        self.assertEqual(inventory, core.build_inventory("OIMUS/REPO", set(), **kwargs))
        assert_inventory(self, inventory)
        self.assertEqual(inventory["generated_at"], kwargs["generated_at"])
        self.assertEqual(json.loads(core.evidence_json(inventory)), inventory)
        self.assertIn("日本語", core.evidence_json({"title": "日本語"}))


def assert_inventory(testcase, inventory):
    testcase.assertEqual(inventory["repository"], "oimus/repo")
    testcase.assertEqual(inventory["requested_repository"], "OIMUS/REPO")
    testcase.assertEqual(inventory["source_host"], "github.com")
    testcase.assertEqual(inventory["mutation_capability"], "NONE")
    rows = {row["branch"]: row for row in inventory["branches"]}
    testcase.assertEqual(rows["main"]["classification"], core.CLASS_PROTECTED)
    testcase.assertEqual(rows["topic"]["classification"], core.CLASS_MERGED)
    testcase.assertEqual([pr["number"] for pr in rows["topic"]["pull_requests"]], [1])
    testcase.assertEqual(rows["closed"]["classification"], core.CLASS_CLOSED)
    testcase.assertEqual(rows["no-pr"]["classification"], core.CLASS_NO_PR)
    candidates = core.review_candidates(inventory)
    testcase.assertEqual({row["branch"] for row in candidates}, {"topic", "closed", "no-pr"})
    for candidate in candidates:
        testcase.assertIs(candidate["human_review_required"], True)
        testcase.assertIs(candidate["deletion_authority"], False)


class ClassificationTests(unittest.TestCase):
    def test_classification_contract(self):
        self.assertEqual(core.classify_branch("main", "abc", [], default_branch="main", retained=set()), core.CLASS_PROTECTED)
        self.assertEqual(core.classify_branch("keep", "abc", [], default_branch="main", retained={"keep"}), core.CLASS_RETAINED)
        self.assertEqual(core.classify_branch("none", "abc", [], default_branch="main", retained=set()), core.CLASS_NO_PR)
        opened = [{"state": "open", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(core.classify_branch("topic", "abc", opened, default_branch="main", retained=set()), core.CLASS_OPEN)
        merged = [{"state": "closed", "merged_at": "2026-09-01T00:00:00Z", "head": {"sha": "abc"}}]
        self.assertEqual(core.classify_branch("topic", "abc", merged, default_branch="main", retained=set()), core.CLASS_MERGED)
        self.assertEqual(core.classify_branch("topic", "new", merged, default_branch="main", retained=set()), core.CLASS_MERGED_MOVED)
        closed = [{"state": "closed", "merged_at": None, "head": {"sha": "abc"}}]
        self.assertEqual(core.classify_branch("topic", "abc", closed, default_branch="main", retained=set()), core.CLASS_CLOSED)


class CompositionTests(unittest.TestCase):
    def test_real_inventory_path_reaches_fixed_native_reads(self):
        with mock.patch.object(github.subprocess, "run", side_effect=native_response) as run:
            inventory = audit.collect_inventory("OIMUS/REPO", set())
        assert_inventory(self, inventory)
        self.assertEqual(run.call_args_list, [
            mock.call(["gh", "api", "--hostname", "github.com", endpoint],
                      stdout=github.subprocess.PIPE, stderr=github.subprocess.PIPE, check=False)
            for endpoint in responses()
        ])

    def test_main_writes_evidence_from_real_read_composition(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(github.subprocess, "run", side_effect=native_response):
            self.assertEqual(audit.main(["--repository", "OIMUS/REPO", "--audit-dir", temp_dir]), 0)
            root = Path(temp_dir)
            inventory = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
            candidates = json.loads((root / "review-candidates.json").read_text(encoding="utf-8"))
            assert_inventory(self, inventory)
            self.assertEqual(candidates, core.review_candidates(inventory))

    def test_failed_identity_stops_before_other_reads_or_output(self):
        completed = mock.Mock(returncode=0, stdout=b"{}", stderr=b"")
        with mock.patch.object(github.subprocess, "run", return_value=completed) as run, mock.patch.object(audit, "audit_directory") as directory:
            self.assertEqual(audit.main(["--repository", "OIMUS/REPO"]), 2)
        run.assert_called_once()
        directory.assert_not_called()

    def test_failed_branch_or_pull_read_prevents_evidence_output(self):
        for failed_endpoint in list(responses())[1:]:
            with self.subTest(endpoint=failed_endpoint):
                def read(argv, **kwargs):
                    if argv[4] == failed_endpoint:
                        return mock.Mock(returncode=1, stdout=b"[]", stderr=b"read failed")
                    return native_response(argv, **kwargs)

                with mock.patch.object(github.subprocess, "run", side_effect=read), mock.patch.object(audit, "audit_directory") as directory:
                    self.assertEqual(audit.main(["--repository", "OIMUS/REPO"]), 2)
                directory.assert_not_called()


class NoMutationOptionsTests(unittest.TestCase):
    def test_parser_has_no_destructive_options(self):
        for args in (
            ["--repository", "oimus/repo", "--execute"],
            ["--repository", "oimus/repo", "--delete-merged"],
            ["--repository", "oimus/repo", "--delete-reviewed", "review.json"],
        ):
            with self.subTest(args=args), self.assertRaises(SystemExit) as raised:
                audit.parse_args(args)
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
