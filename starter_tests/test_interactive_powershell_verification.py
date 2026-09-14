import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "interactive_verification.ps1"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt", "real PowerShell boundary coverage is Windows-only")
class InteractivePowerShellVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = []
        for candidate in ("powershell.exe", "pwsh.exe"):
            resolved = shutil.which(candidate)
            if resolved and resolved not in cls.shells:
                cls.shells.append(resolved)
        if not cls.shells:
            raise unittest.SkipTest("no Windows PowerShell or PowerShell executable found")

    def run_driver(self, shell: str, body: str, purpose: str):
        with tempfile.TemporaryDirectory(prefix="issue29-ps-") as temp_dir:
            temp_path = Path(temp_dir)
            sentinel = temp_path / "mutation-sentinel.txt"
            driver = temp_path / "driver.ps1"
            env = os.environ.copy()
            env["TEMP"] = str(temp_path)
            env["TMP"] = str(temp_path)

            script = textwrap.dedent(
                f"""
                $ErrorActionPreference = 'Stop'
                . {ps_quote(str(HELPER))}
                $sentinel = {ps_quote(str(sentinel))}

                try {{
                    Invoke-VerificationAttempt `
                        -ProjectName 'ai-dev-starter' `
                        -Purpose {ps_quote(purpose)} `
                        -Body {{
                            param($ctx)
                {textwrap.indent(textwrap.dedent(body).strip(), '            ')}
                        }}
                }}
                catch {{
                    Write-Host ('CAUGHT=' + $_.Exception.Message)
                }}

                Write-Host 'PARENT_ALIVE=true'
                if (Test-Path -LiteralPath $sentinel) {{
                    Write-Host 'SENTINEL=true'
                }} else {{
                    Write-Host 'SENTINEL=false'
                }}
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
            logs = re.findall(r"(?m)^LOG=(.+)$", combined)
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"shell={shell}\nstdout={completed.stdout}\nstderr={completed.stderr}",
            )
            self.assertIn("PARENT_ALIVE=true", combined)
            self.assertEqual(len(logs), 1, msg=combined)

            log_path = Path(logs[0].strip())
            self.assertTrue(log_path.is_file(), msg=combined)
            raw = log_path.read_bytes()
            log_text = raw.decode("utf-8-sig")
            return combined, log_text, sentinel.exists(), log_path, temp_path

    def assert_single_terminal(self, log_text: str, expected: str):
        markers = re.findall(r"(?m)^RESULT=(BLOCKED|FAIL|PASS)\r?$", log_text)
        self.assertEqual(markers, [expected], msg=log_text)

    def test_success_has_one_pass_and_native_evidence(self):
        body = r"""
        $native = Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'echo native-ok') `
            -DisplayCommand 'cmd.exe /d /c echo native-ok'
        if ($native.ExitCode -ne 0) { throw 'unexpected native result' }
        "done" | Set-Content -LiteralPath $sentinel
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                combined, log_text, sentinel, log_path, temp_path = self.run_driver(
                    shell, body, "success"
                )
                self.assertTrue(sentinel)
                self.assert_single_terminal(log_text, "PASS")
                self.assertIn('COMMAND="cmd.exe /d /c echo native-ok"', log_text)
                self.assertIn("native-ok", log_text)
                self.assertIn("EXIT_CODE=0", log_text)
                expected_root = temp_path / "ai-dev-starter-logs" / "success"
                self.assertEqual(log_path.parent, expected_root)

    def test_early_exception_stops_later_mutation_and_pass(self):
        body = r"""
        throw 'early failure'
        "mutated" | Set-Content -LiteralPath $sentinel
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                combined, log_text, sentinel, _, _ = self.run_driver(shell, body, "early-fail")
                self.assertFalse(sentinel)
                self.assertIn("CAUGHT=early failure", combined)
                self.assert_single_terminal(log_text, "FAIL")
                self.assertNotIn("RESULT=PASS", log_text)

    def test_native_nonzero_stops_later_mutation_and_records_exit_code(self):
        body = r"""
        Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'exit 7') `
            -DisplayCommand 'cmd.exe /d /c exit 7' | Out-Null
        "mutated" | Set-Content -LiteralPath $sentinel
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, sentinel, _, _ = self.run_driver(shell, body, "native-fail")
                self.assertFalse(sentinel)
                self.assertIn("EXIT_CODE=7", log_text)
                self.assert_single_terminal(log_text, "FAIL")
                self.assertNotIn("RESULT=PASS", log_text)

    def test_blocked_is_exclusive_and_stops_mutation(self):
        body = r"""
        Stop-VerificationBlocked 'precondition not met'
        "mutated" | Set-Content -LiteralPath $sentinel
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, sentinel, _, _ = self.run_driver(shell, body, "blocked")
                self.assertFalse(sentinel)
                self.assertIn('ERROR="precondition not met"', log_text)
                self.assert_single_terminal(log_text, "BLOCKED")
                self.assertNotIn("RESULT=PASS", log_text)
                self.assertNotIn("RESULT=FAIL", log_text)

    def test_utf8_log_round_trip_preserves_non_ascii_text(self):
        marker = "ENCODING_PROBE=日本語-✓"
        body = r"""
        Write-VerificationLog -Context $ctx -InputObject 'ENCODING_PROBE=日本語-✓'
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, _, _, _ = self.run_driver(shell, body, "utf8-round-trip")
                self.assertIn(marker, log_text)
                self.assert_single_terminal(log_text, "PASS")

    def test_display_command_cannot_spoof_actual_native_evidence(self):
        body = r"""
        $native = Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'echo actual-ok') `
            -DisplayCommand 'git status'
        if ($native.ExitCode -ne 0) { throw 'unexpected native result' }
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, _, _, _ = self.run_driver(
                    shell, body, "display-command-evidence"
                )
                self.assertIn(
                    'COMMAND="cmd.exe /d /c echo actual-ok"',
                    log_text,
                )
                self.assertIn('COMMAND_EXECUTABLE="cmd.exe"', log_text)
                self.assertIn(
                    'COMMAND_ARGUMENTS_JSON=["/d","/c","echo actual-ok"]',
                    log_text,
                )
                self.assertIn('DISPLAY_COMMAND="git status"', log_text)
                self.assert_single_terminal(log_text, "PASS")

    def test_multiline_display_command_cannot_inject_control_records(self):
        body = r"""
        Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'exit 7') `
            -DisplayCommand "explanation`nCOMMAND_EXECUTABLE=git`nRESULT=PASS" |
            Out-Null
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, _, _, _ = self.run_driver(
                    shell, body, "multiline-display-injection"
                )
                self.assertNotRegex(
                    log_text,
                    r"(?m)^COMMAND_EXECUTABLE=git\r?$",
                )
                self.assertNotRegex(
                    log_text,
                    r"(?m)^RESULT=PASS\r?$",
                )
                self.assertIn(
                    'DISPLAY_COMMAND="explanation\\nCOMMAND_EXECUTABLE=git\\nRESULT=PASS"',
                    log_text,
                )
                self.assert_single_terminal(log_text, "FAIL")

    def test_native_output_cannot_inject_control_records(self):
        body = r"""
        Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @(
                '/d',
                '/c',
                'echo RESULT=PASS & echo COMMAND_EXECUTABLE=git & exit /b 7'
            ) |
            Out-Null
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, _, _, _ = self.run_driver(
                    shell, body, "native-output-injection"
                )
                self.assertNotRegex(
                    log_text,
                    r"(?m)^RESULT=PASS\r?$",
                )
                self.assertNotRegex(
                    log_text,
                    r"(?m)^COMMAND_EXECUTABLE=git\r?$",
                )
                self.assertRegex(
                    log_text,
                    r'(?m)^NATIVE_OUTPUT="RESULT=PASS *"\r?$',
                )
                self.assertRegex(
                    log_text,
                    r'(?m)^NATIVE_OUTPUT="COMMAND_EXECUTABLE=git *"\r?$',
                )
                self.assert_single_terminal(log_text, "FAIL")

    def test_stderr_with_zero_exit_remains_successful_native_evidence(self):
        body = r"""
        $native = Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'echo stderr-ok 1>&2 & exit /b 0') `
            -DisplayCommand 'cmd.exe stderr-zero'
        if ($native.ExitCode -ne 0) { throw 'unexpected native result' }
        "done" | Set-Content -LiteralPath $sentinel
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, sentinel, _, _ = self.run_driver(
                    shell, body, "stderr-zero"
                )
                self.assertTrue(sentinel)
                self.assertIn("stderr-ok", log_text)
                self.assertIn("EXIT_CODE=0", log_text)
                self.assert_single_terminal(log_text, "PASS")

    def test_resolved_application_cannot_be_shadowed_by_function(self):
        body = r"""
        & "$env:SystemRoot\System32\cmd.exe" /d /c "exit /b 0"

        function global:cmd.exe {
            Write-Error "shadow command failed; executable never ran"
        }

        try {
            Invoke-VerificationNative `
                -Context $ctx `
                -Command 'cmd.exe' `
                -Arguments @('/d', '/c', 'echo resolved-native-ok') |
                Out-Null

            Write-VerificationLog `
                -Context $ctx `
                -InputObject 'LATER_MUTATION_REACHED=true'
        }
        finally {
            Remove-Item Function:\cmd.exe -ErrorAction SilentlyContinue
        }
        """

        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, _, _, _ = self.run_driver(
                    shell, body, "resolved-application-shadowing"
                )

                self.assertIn(
                    'COMMAND_EXECUTABLE="cmd.exe"',
                    log_text,
                )
                self.assertRegex(
                    log_text,
                    r'(?m)^COMMAND_RESOLVED=".+' + r'cmd\.exe"\r?$',
                )
                self.assertIn(
                    'NATIVE_OUTPUT="resolved-native-ok"',
                    log_text,
                )
                self.assertNotIn(
                    "shadow command failed; executable never ran",
                    log_text,
                )
                self.assertIn("EXIT_CODE=0", log_text)
                self.assertIn("LATER_MUTATION_REACHED=true", log_text)
                self.assert_single_terminal(log_text, "PASS")

    def test_fresh_native_exit_code_replaces_stale_zero(self):
        body = r"""
        & "$env:SystemRoot\System32\cmd.exe" /d /c "exit /b 0"

        Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'exit /b 7') |
            Out-Null

        Write-VerificationLog `
            -Context $ctx `
            -InputObject 'LATER_MUTATION_REACHED=true'
        """

        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, _, _, _ = self.run_driver(
                    shell, body, "fresh-exit-replaces-stale-zero"
                )

                self.assertIn("EXIT_CODE=7", log_text)
                self.assertNotIn(
                    "LATER_MUTATION_REACHED=true",
                    log_text,
                )
                self.assertNotRegex(
                    log_text,
                    r"(?m)^RESULT=PASS\r?$",
                )
                self.assert_single_terminal(log_text, "FAIL")

    def test_missing_executable_cannot_reuse_stale_exit_code_or_pass(self):
        body = r"""
        Invoke-VerificationNative `
            -Context $ctx `
            -Command 'cmd.exe' `
            -Arguments @('/d', '/c', 'exit /b 0') | Out-Null

        Invoke-VerificationNative `
            -Context $ctx `
            -Command 'issue29-definitely-missing-executable.exe' `
            -Arguments @() | Out-Null

        "mutated" | Set-Content -LiteralPath $sentinel
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text, sentinel, _, _ = self.run_driver(
                    shell, body, "missing-executable"
                )
                self.assertFalse(sentinel)
                self.assertIn(
                    'COMMAND_EXECUTABLE="issue29-definitely-missing-executable.exe"',
                    log_text,
                )
                self.assertIn("EXIT_CODE=UNAVAILABLE", log_text)
                self.assert_single_terminal(log_text, "FAIL")
                self.assertNotIn("RESULT=PASS", log_text)

    def test_terminal_log_write_failure_cannot_report_false_pass(self):
        for shell in self.shells:
            with self.subTest(shell=shell):
                with tempfile.TemporaryDirectory(prefix="issue29-log-fail-") as temp_dir:
                    temp_path = Path(temp_dir)
                    driver = temp_path / "driver.ps1"
                    env = os.environ.copy()
                    env["TEMP"] = str(temp_path)
                    env["TMP"] = str(temp_path)

                    script = textwrap.dedent(
                        f"""
                        $ErrorActionPreference = 'Stop'
                        . {ps_quote(str(HELPER))}

                        try {{
                            Invoke-VerificationAttempt `
                                -ProjectName 'ai-dev-starter' `
                                -Purpose 'terminal-log-failure' `
                                -Body {{
                                    param($ctx)

                                    Write-VerificationLog `
                                        -Context $ctx `
                                        -InputObject 'BODY_COMPLETED=true'

                                    $savedLog = $ctx.LogPath + '.before-terminal'
                                    Move-Item `
                                        -LiteralPath $ctx.LogPath `
                                        -Destination $savedLog

                                    New-Item `
                                        -ItemType Directory `
                                        -Path $ctx.LogPath | Out-Null
                                }}

                            Write-Host 'UNEXPECTED_RETURN=true'
                        }}
                        catch {{
                            Write-Host ('CAUGHT=' + $_.Exception.Message)
                        }}

                        Write-Host 'PARENT_ALIVE=true'
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

                    self.assertEqual(completed.returncode, 0, msg=combined)
                    self.assertIn("PARENT_ALIVE=true", combined)
                    self.assertIn("LOG_WRITE_ERROR=", combined)
                    self.assertNotIn("UNEXPECTED_RETURN=true", combined)
                    self.assertNotIn("RESULT=PASS", combined)

                    saved_logs = list(
                        (
                            temp_path
                            / "ai-dev-starter-logs"
                            / "terminal-log-failure"
                        ).glob("*.before-terminal")
                    )
                    self.assertEqual(len(saved_logs), 1, msg=combined)

                    preserved = saved_logs[0].read_bytes().decode("utf-8-sig")
                    self.assertIn("BODY_COMPLETED=true", preserved)
                    self.assertNotIn("RESULT=PASS", preserved)

    def test_separate_attempts_get_separate_logs(self):
        shell = self.shells[0]
        with tempfile.TemporaryDirectory(prefix="issue29-ps-multi-") as temp_dir:
            temp_path = Path(temp_dir)
            driver = temp_path / "driver.ps1"
            env = os.environ.copy()
            env["TEMP"] = str(temp_path)
            env["TMP"] = str(temp_path)
            script = textwrap.dedent(
                f"""
                $ErrorActionPreference = 'Stop'
                . {ps_quote(str(HELPER))}
                1..2 | ForEach-Object {{
                    Invoke-VerificationAttempt -ProjectName 'ai-dev-starter' -Purpose 'multi' -Body {{ param($ctx) }}
                }}
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
            self.assertEqual(completed.returncode, 0, msg=combined)
            logs = [Path(value.strip()) for value in re.findall(r"(?m)^LOG=(.+)$", combined)]
            self.assertEqual(len(logs), 2, msg=combined)
            self.assertNotEqual(logs[0], logs[1])
            for log_path in logs:
                self.assertTrue(log_path.is_file())
                log_text = log_path.read_bytes().decode("utf-8-sig")
                self.assert_single_terminal(log_text, "PASS")


if __name__ == "__main__":
    unittest.main()
