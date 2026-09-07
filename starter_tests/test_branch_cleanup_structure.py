import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BranchCleanupStructureTests(unittest.TestCase):
    def test_baseline_declares_authoritative_remote_cleanup_gate(self):
        text = (ROOT / "BASELINE.md").read_text(encoding="utf-8")
        self.assertIn("Repository-wide branch cleanup is a separate destructive gate", text)
        self.assertIn("Current branch existence and PR state on GitHub are authoritative", text)
        self.assertIn("Closed-unmerged PR branches are never bulk-delete candidates", text)
        self.assertIn("process exit status is the command success authority", text)
        self.assertIn("require the exact target set to have zero residual members", text)

    def test_agent_instructions_reference_helper_and_policy(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("scripts/branch_cleanup_audit.py", text)
        self.assertIn("docs/branch-cleanup-policy.md", text)
        self.assertIn("Closed-unmerged branches require individual human review", text)
        self.assertIn("stderr is diagnostic output only", text)

    def test_policy_check_compiles_and_runs_branch_cleanup_regressions(self):
        text = (ROOT / ".github/workflows/policy-check.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/branch_cleanup_audit.py", text)
        self.assertIn('test_branch_cleanup_audit.py', text)

    def test_policy_document_keeps_cleanup_tools_separate(self):
        text = (ROOT / "docs/branch-cleanup-policy.md").read_text(encoding="utf-8")
        self.assertIn("verify_local_closeout.py", text)
        self.assertIn("post_merge_cleanup.py", text)
        self.assertIn("branch_cleanup_audit.py", text)
        self.assertIn("Do not substitute one tool's successful result", text)


if __name__ == "__main__":
    unittest.main()
