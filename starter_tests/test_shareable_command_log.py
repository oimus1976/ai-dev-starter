import os
import locale
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "shareable_command_log.py"


class ShareableCommandLogTests(unittest.TestCase):
    def run_logger_command(self, name: str, child_command: list[str]):
        temp_path = Path(tempfile.mkdtemp(prefix="issue43-shareable-log-"))
        self.addCleanup(shutil.rmtree, temp_path, ignore_errors=True)

        env = os.environ.copy()
        env["TEMP"] = str(temp_path)
        env["TMP"] = str(temp_path)
        env["PYTHONIOENCODING"] = "utf-8"

        command = [
            sys.executable,
            str(HELPER),
            "--work-item",
            "issue43",
            "--name",
            name,
            "--",
            *child_command,
        ]

        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )
        combined = completed.stdout + completed.stderr
        logs = re.findall(r"(?m)^LOG=(.+)\r?$", combined)

        log_path = None
        log_text = None
        if logs:
            log_path = Path(logs[-1].strip())
            if log_path.is_file():
                log_text = log_path.read_text(encoding="utf-8-sig")

        return completed, combined, logs, log_path, log_text, temp_path

    def run_logger(self, name: str, child_code: str):
        return self.run_logger_command(
            name,
            [sys.executable, "-c", child_code],
        )

    def assert_log_location(self, log_path: Path, temp_path: Path):
        self.assertIsNotNone(log_path)
        self.assertTrue(log_path.is_file())
        self.assertEqual(log_path.parent, temp_path / "ai-dev-starter" / "issue43")
        self.assertFalse(str(log_path).startswith(str(ROOT)))

    def test_stdout_and_utf8_text_are_shown_and_logged(self):
        completed, combined, logs, log_path, log_text, temp_path = self.run_logger(
            "stdout-utf8",
            "print('plain-output'); print('日本語-✓')",
        )

        self.assertEqual(completed.returncode, 0, msg=combined)
        self.assertEqual(len(logs), 1, msg=combined)
        self.assert_log_location(log_path, temp_path)
        self.assertIn("plain-output", combined)
        self.assertIn("日本語-✓", combined)
        self.assertIn("plain-output", log_text)
        self.assertIn("日本語-✓", log_text)
        self.assertIn("EXIT_CODE=0", log_text)

    def test_stderr_and_nonzero_exit_are_shown_logged_and_returned(self):
        completed, combined, logs, log_path, log_text, temp_path = self.run_logger(
            "stderr-nonzero",
            "import sys; print('child-out'); print('child-err', file=sys.stderr); sys.exit(7)",
        )

        self.assertEqual(completed.returncode, 7, msg=combined)
        self.assertEqual(len(logs), 1, msg=combined)
        self.assert_log_location(log_path, temp_path)
        self.assertIn("child-out", combined)
        self.assertIn("child-err", combined)
        self.assertIn("child-out", log_text)
        self.assertIn("child-err", log_text)
        self.assertIn("EXIT_CODE=7", log_text)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell boundary is Windows-only")
    def test_windows_powershell_51_japanese_stdout_stderr_remain_readable(self):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell 5.1 executable not found")

        legacy_encoding = locale.getpreferredencoding(False) or "utf-8"
        try:
            "日本語".encode(legacy_encoding)
        except UnicodeEncodeError:
            self.skipTest(
                f"active Windows code page cannot represent Japanese: {legacy_encoding}"
            )

        completed, combined, logs, log_path, log_text, temp_path = (
            self.run_logger_command(
                "powershell51-japanese",
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    (
                        "Write-Output 'PS_STDOUT=日本語'; "
                        "[Console]::Error.WriteLine('PS_STDERR=日本語')"
                    ),
                ],
            )
        )

        self.assertEqual(completed.returncode, 0, msg=combined)
        self.assertEqual(len(logs), 1, msg=combined)
        self.assert_log_location(log_path, temp_path)
        for marker in ("PS_STDOUT=日本語", "PS_STDERR=日本語"):
            self.assertIn(marker, combined)
            self.assertIn(marker, log_text)
        self.assertIn("EXIT_CODE=0", log_text)

    def test_repeated_name_generates_distinct_log_files(self):
        first = self.run_logger("repeat", "print('first')")
        second = self.run_logger("repeat", "print('second')")

        self.assertEqual(first[0].returncode, 0, msg=first[1])
        self.assertEqual(second[0].returncode, 0, msg=second[1])
        self.assertEqual(len(first[2]), 1, msg=first[1])
        self.assertEqual(len(second[2]), 1, msg=second[1])
        self.assertNotEqual(first[3].name, second[3].name)


if __name__ == "__main__":
    unittest.main()
