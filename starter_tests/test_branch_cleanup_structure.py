import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BranchCleanupStructureTests(unittest.TestCase):
    def test_baseline_does_not_claim_repository_wide_auto_delete_authority(self):
        text = (ROOT / "BASELINE.md").read_text(encoding="utf-8")
        self.assertNotIn("MERGED_DELETE_CANDIDATE", text)
        self.assertNotIn("automatic merged-branch deletion", text)
        self.assertIn("If the same safety invariant produces a `MAJOR` finding after two remediation attempts", text)

    def test_agent_instructions_define_audit_only_scope(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("scripts/branch_cleanup_audit.py --repository OWNER/REPO", text)
        self.assertIn("docs/branch-cleanup-policy.md", text)
        self.assertIn("audit-only", text)
        self.assertIn("deletion_authority: false", text)
        self.assertIn("Issue #22", text)
        self.assertIn("stderr is diagnostic output only", text)

    def test_policy_check_compiles_and_runs_branch_cleanup_regressions(self):
        text = (ROOT / ".github/workflows/policy-check.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/branch_cleanup_audit.py", text)
        self.assertIn('test_branch_cleanup*.py', text)
        self.assertTrue((ROOT / "starter_tests/test_branch_cleanup_encoding.py").is_file())

    def test_policy_document_states_no_mutation_authority(self):
        text = (ROOT / "docs/branch-cleanup-policy.md").read_text(encoding="utf-8")
        self.assertIn("verify_local_closeout.py", text)
        self.assertIn("post_merge_cleanup.py", text)
        self.assertIn("branch_cleanup_audit.py", text)
        self.assertIn("pins GitHub CLI API reads to `github.com`", text)
        self.assertIn("MERGED_REVIEW_CANDIDATE", text)
        self.assertIn("mutation_capability: NONE", text)
        self.assertIn("deletion_authority: false", text)
        self.assertIn("no remote mutation capability", text)
        self.assertIn("Issue #22", text)
        self.assertIn("`MERGED_REVIEW_CANDIDATE` replaces the earlier `MERGED_DELETE_CANDIDATE` concept", text)
        self.assertEqual(text.count("MERGED_DELETE_CANDIDATE"), 1)
        self.assertNotIn("--force-with-lease=refs/heads/<branch>:<expected_sha>", text)

    def test_policy_records_revised_guarantee_and_module_responsibilities(self):
        text = (ROOT / "docs/branch-cleanup-policy.md").read_text(encoding="utf-8")
        self.assertIn("AST/source-shape tests are not a complete security boundary", text)
        self.assertIn("Any new process/network capability", text)
        self.assertIn("branch_cleanup_core.py", text)
        self.assertIn("branch_cleanup_github.py", text)
        self.assertTrue((ROOT / "docs/adr/0002-audit-read-boundary.md").is_file())


if __name__ == "__main__":
    unittest.main()
