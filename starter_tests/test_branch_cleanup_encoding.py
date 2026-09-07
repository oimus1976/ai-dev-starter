import sys
import unittest

from scripts import branch_cleanup_audit as audit


class BranchCleanupEncodingTests(unittest.TestCase):
    def test_native_utf8_output_does_not_use_windows_legacy_code_page(self):
        expected = "日本語—✓"
        payload_hex = expected.encode("utf-8").hex()
        result = audit.run_native(
            [
                sys.executable,
                "-c",
                f"import sys; sys.stdout.buffer.write(bytes.fromhex('{payload_hex}'))",
            ]
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, expected)

    def test_non_utf8_native_output_fails_closed(self):
        with self.assertRaisesRegex(audit.AuditError, "non-UTF-8 output"):
            audit.run_native(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.buffer.write(bytes([0xff]))",
                ]
            )


if __name__ == "__main__":
    unittest.main()
