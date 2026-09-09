import json
import unittest
from unittest import mock

from scripts import branch_cleanup_core as core
from scripts import branch_cleanup_github as github


class BranchCleanupEncodingTests(unittest.TestCase):
    def test_native_utf8_output_does_not_use_windows_legacy_code_page(self):
        expected = {"message": "日本語—✓"}
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(expected, ensure_ascii=False).encode("utf-8"),
            stderr=b"",
        )
        with mock.patch.object(github.subprocess, "run", return_value=completed):
            self.assertEqual(github.repository_metadata("oimus/repo"), expected)

    def test_non_utf8_native_output_fails_closed(self):
        completed = mock.Mock(returncode=0, stdout=bytes([0xFF]), stderr=b"")
        with mock.patch.object(github.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(core.AuditError, "non-UTF-8 output"):
                github.repository_metadata("oimus/repo")


if __name__ == "__main__":
    unittest.main()
