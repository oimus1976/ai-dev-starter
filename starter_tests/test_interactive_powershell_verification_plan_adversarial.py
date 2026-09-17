import json
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
class InteractivePowerShellVerificationPlanAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = []
        for candidate in ("powershell.exe", "pwsh.exe"):
            resolved = shutil.which(candidate)
            if resolved and resolved not in cls.shells:
                cls.shells.append(resolved)
        if not cls.shells:
            raise unittest.SkipTest("no Windows PowerShell or PowerShell executable found")

    @staticmethod
    def base_plan(purpose: str, steps):
        return {
            "schema": "verification-plan-v1",
            "project": "ai-dev-starter",
            "purpose": purpose,
            "steps": steps,
        }

    def run_plan(self, shell: str, plan: dict, prelude: str = ""):
        with tempfile.TemporaryDirectory(prefix="issue39-plan-adversarial-") as temp_dir:
            temp_path = Path(temp_dir)
            plan_path = temp_path / "plan.json"
            log_root = temp_path / "logs"
            driver = temp_path / "driver.ps1"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            driver.write_text(
                textwrap.dedent(
                    f"""
                    $ErrorActionPreference = 'Stop'
                    . {ps_quote(str(HELPER))}
                    {textwrap.dedent(prelude).strip()}
                    try {{
                        Invoke-VerificationPlan `
                            -PlanPath {ps_quote(str(plan_path))} `
                            -LogRoot {ps_quote(str(log_root))}
                    }}
                    catch {{
                        Microsoft.PowerShell.Utility\\Write-Host ('CAUGHT=' + $_.Exception.Message)
                    }}
                    Microsoft.PowerShell.Utility\\Write-Host 'PARENT_ALIVE=true'
                    """
                ),
                encoding="utf-8-sig",
            )

            command = [shell, "-NoProfile"]
            if Path(shell).name.lower() == "powershell.exe":
                command.extend(["-ExecutionPolicy", "Bypass"])
            command.extend(["-File", str(driver)])
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=30,
                check=False,
            )
            combined = completed.stdout + completed.stderr
            logs = list(log_root.glob("attempt-*.log")) if log_root.exists() else []
            log_text = None
            if len(logs) == 1:
                log_text = logs[0].read_bytes().decode("utf-8-sig")
            return completed, combined, log_text

    def assert_terminal(self, log_text: str, expected: str):
        self.assertIsNotNone(log_text)
        lines = log_text.splitlines()
        markers = [line for line in lines if re.fullmatch(r"RESULT=(PASS|FAIL|BLOCKED)", line)]
        self.assertEqual(markers, [f"RESULT={expected}"], msg=log_text)
        self.assertEqual(lines[-1], f"RESULT={expected}", msg=log_text)

    def test_steps_must_be_json_array(self):
        plan = self.base_plan(
            "steps-shape",
            {
                "id": "would-run",
                "type": "Native",
                "command": "cmd.exe",
                "arguments": ["/d", "/c", "echo SHOULD-NOT-RUN"],
                "accepted_exit_codes": [0],
                "failure_outcome": "FAIL",
            },
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan)
                self.assertNotIn("SHOULD-NOT-RUN", log_text or combined)
                self.assert_terminal(log_text, "FAIL")

    def test_native_arguments_must_be_json_array(self):
        plan = self.base_plan(
            "arguments-shape",
            [
                {
                    "id": "bad",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": "/d",
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, _, log_text = self.run_plan(shell, plan)
                self.assert_terminal(log_text, "FAIL")

    def test_accepted_exit_codes_must_be_json_array(self):
        plan = self.base_plan(
            "exit-codes-shape",
            [
                {
                    "id": "bad",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo SHOULD-NOT-RUN"],
                    "accepted_exit_codes": 0,
                    "failure_outcome": "FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan)
                self.assertNotIn("SHOULD-NOT-RUN", log_text or combined)
                self.assert_terminal(log_text, "FAIL")

    def test_out_of_range_later_exit_code_blocks_all_native_execution(self):
        plan = self.base_plan(
            "exit-code-range",
            [
                {
                    "id": "early",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo EARLY-RAN"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
                {
                    "id": "bad",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo LATE-RAN"],
                    "accepted_exit_codes": [2147483648],
                    "failure_outcome": "FAIL",
                },
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan)
                evidence = log_text or combined
                self.assertNotIn("EARLY-RAN", evidence)
                self.assertNotIn("LATE-RAN", evidence)
                self.assert_terminal(log_text, "FAIL")

    def test_record_value_object_is_rejected_before_native_execution(self):
        plan = self.base_plan(
            "record-value-type",
            [
                {
                    "id": "early",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo EARLY-RAN"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
                {
                    "id": "bad-record",
                    "type": "Record",
                    "name": "CUSTOM_NOTE",
                    "value": {"nested": "ambiguous"},
                },
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan)
                self.assertNotIn("EARLY-RAN", log_text or combined)
                self.assert_terminal(log_text, "FAIL")

    def test_native_stderr_with_zero_exit_is_diagnostic_success(self):
        plan = self.base_plan(
            "stderr-zero",
            [
                {
                    "id": "probe",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo diagnostic 1>&2 & exit /b 0"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan)
                self.assertIsNotNone(log_text, msg=combined)
                self.assertIn("EXIT_CODE=0", log_text)
                self.assertIn("diagnostic", log_text)
                self.assert_terminal(log_text, "PASS")

    def test_explicit_nonzero_exit_code_can_be_accepted(self):
        plan = self.base_plan(
            "accepted-seven",
            [
                {
                    "id": "probe",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "exit /b 7"],
                    "accepted_exit_codes": [7],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, _, log_text = self.run_plan(shell, plan)
                self.assertIn("EXIT_CODE=7", log_text)
                self.assert_terminal(log_text, "PASS")

    def test_rejected_nonzero_exit_stops_later_native_step(self):
        plan = self.base_plan(
            "rejected-seven",
            [
                {
                    "id": "fail",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "exit /b 7"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
                {
                    "id": "later",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo LATER-RAN"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan)
                self.assertIn("EXIT_CODE=7", log_text)
                self.assertNotIn("LATER-RAN", log_text or combined)
                self.assert_terminal(log_text, "FAIL")

    def test_function_named_like_executable_cannot_redirect_native_launch(self):
        plan = self.base_plan(
            "executable-shadow",
            [
                {
                    "id": "probe",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo resolved-native-ok"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        prelude = r"""
        function global:cmd.exe {
            throw 'shadow cmd.exe invoked'
        }
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan, prelude)
                self.assertNotIn("shadow cmd.exe invoked", combined)
                self.assertIn('NATIVE_OUTPUT="resolved-native-ok"', log_text)
                self.assert_terminal(log_text, "PASS")

    def test_wildcard_command_name_is_rejected_before_execution(self):
        plan = self.base_plan(
            "wildcard-command",
            [
                {
                    "id": "bad",
                    "type": "Native",
                    "command": "cmd*.exe",
                    "arguments": ["/d", "/c", "echo SHOULD-NOT-RUN"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text = self.run_plan(shell, plan)
                self.assertNotIn("SHOULD-NOT-RUN", log_text or combined)
                self.assert_terminal(log_text, "FAIL")


if __name__ == "__main__":
    unittest.main()
