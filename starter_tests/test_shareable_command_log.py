import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "shareable_command_log.py"


class ShareableCommandLogTests(unittest.TestCase):
    def run_logger(self, name: str, child_code: str):
        with tempfile.TemporaryDirectory(prefix="issue43-shareable-log-") as temp_dir:
            temp_path = Path(temp_dir)
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
                sys.executable,
                "-c",
                child_code,
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
