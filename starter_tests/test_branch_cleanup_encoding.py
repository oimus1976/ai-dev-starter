import json
import unittest
from unittest import mock

from scripts import branch_cleanup_audit as audit


class BranchCleanupEncodingTests(unittest.TestCase):
    def test_native_utf8_output_does_not_use_windows_legacy_code_page(self):
        expected = {"message": "日本語—✓"}
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(expected, ensure_ascii=False).encode("utf-8"),
            stderr=b"",
        )
        with mock.patch.object(audit.subprocess, "run", return_value=completed):
            self.assertEqual(audit.github_api_get("fixture"), expected)

    def test_non_utf8_native_output_fails_closed(self):
        completed = mock.Mock(returncode=0, stdout=bytes([0xFF]), stderr=b"")
        with mock.patch.object(audit.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(audit.AuditError, "non-UTF-8 output"):
                audit.github_api_get("fixture")


if __name__ == "__main__":
    unittest.main()
