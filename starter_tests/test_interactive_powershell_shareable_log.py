import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "shareable_command_log.ps1"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt", "real PowerShell boundary coverage is Windows-only")
class ShareablePowerShellCommandLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = []
        for candidate in ("powershell.exe", "pwsh.exe"):
            resolved = shutil.which(candidate)
            if resolved and resolved not in cls.shells:
                cls.shells.append(resolved)
        if not cls.shells:
            raise unittest.SkipTest("no Windows PowerShell or PowerShell executable found")

    def run_driver(self, shell: str, invocation: str):
        with tempfile.TemporaryDirectory(prefix="issue43-shareable-log-") as temp_dir:
            temp_path = Path(temp_dir)
            driver = temp_path / "driver.ps1"
            env = os.environ.copy()
            env["TEMP"] = str(temp_path)
            env["TMP"] = str(temp_path)

            script = textwrap.dedent(
                f"""
                $ErrorActionPreference = 'Stop'
                . {ps_quote(str(HELPER))}
                {textwrap.dedent(invocation).strip()}
                """
            )
            driver.write_text(script, encoding="utf-8-sig")

            command = [shell, "-NoProfile"]
            if Path(shell).name.lower() == "powershell.exe":
                command.extend(["-ExecutionPolicy", "Bypass"])
            command.extend(["-File", str(driver)])

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
            return completed, combined, logs, temp_path

    def assert_log_path(self, log_value: str, temp_path: Path) -> tuple[Path, str]:
        log_path = Path(log_value.strip())
        self.assertTrue(log_path.is_file())
        self.assertEqual(log_path.parent, temp_path / "ai-dev-starter" / "issue43")
        self.assertFalse(str(log_path).startswith(str(ROOT)))
        return log_path, log_path.read_bytes().decode("utf-8-sig")

    def test_scriptblock_output_is_shown_and_logged_as_utf8(self):
        invocation = r"""
        $result = Invoke-ShareableCommandLog `
            -Name 'script-output' `
            -WorkItem 'issue43' `
            -ScriptBlock {
                Write-Output 'plain-output'
                Write-Output '日本語-✓'
            }
        Write-Host ('RETURN_LOG=' + $result.LogPath)
        """

        for shell in self.shells:
            with self.subTest(shell=shell):
                completed, combined, logs, temp_path = self.run_driver(shell, invocation)
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=f"shell={shell}\nstdout={completed.stdout}\nstderr={completed.stderr}",
                )
                self.assertEqual(len(logs), 1, msg=combined)
                log_path, log_text = self.assert_log_path(logs[0], temp_path)
                self.assertIn("plain-output", combined)
                self.assertIn("日本語-✓", combined)
                self.assertIn("plain-output", log_text)
                self.assertIn("日本語-✓", log_text)
                self.assertIn(f"RETURN_LOG={log_path}", combined)

    def test_native_nonzero_stdout_stderr_and_exit_code_are_shareable(self):
        invocation = r"""
        $result = Invoke-ShareableCommandLog `
            -Name 'native-nonzero' `
            -WorkItem 'issue43' `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'echo native-out & echo native-err 1>&2 & exit /b 7')
        Write-Host ('RETURN_EXIT_CODE=' + $result.ExitCode)
        """

        for shell in self.shells:
            with self.subTest(shell=shell):
                completed, combined, logs, temp_path = self.run_driver(shell, invocation)
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=f"shell={shell}\nstdout={completed.stdout}\nstderr={completed.stderr}",
                )
                self.assertEqual(len(logs), 1, msg=combined)
                _, log_text = self.assert_log_path(logs[0], temp_path)
                self.assertIn("native-out", combined)
                self.assertIn("native-err", combined)
                self.assertIn("native-out", log_text)
                self.assertIn("native-err", log_text)
                self.assertIn("EXIT_CODE=7", log_text)
                self.assertIn("RETURN_EXIT_CODE=7", combined)

    def test_repeated_name_generates_distinct_log_files(self):
        invocation = r"""
        Invoke-ShareableCommandLog `
            -Name 'repeat' `
            -WorkItem 'issue43' `
            -ScriptBlock { Write-Output 'first' } | Out-Null
        Invoke-ShareableCommandLog `
            -Name 'repeat' `
            -WorkItem 'issue43' `
            -ScriptBlock { Write-Output 'second' } | Out-Null
        """

        for shell in self.shells:
            with self.subTest(shell=shell):
                completed, combined, logs, temp_path = self.run_driver(shell, invocation)
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=f"shell={shell}\nstdout={completed.stdout}\nstderr={completed.stderr}",
                )
                self.assertEqual(len(logs), 2, msg=combined)
                self.assertNotEqual(logs[0], logs[1])
                for log_value in logs:
                    self.assert_log_path(log_value, temp_path)


if __name__ == "__main__":
    unittest.main()
