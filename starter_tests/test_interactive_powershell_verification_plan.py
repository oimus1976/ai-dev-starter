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
class InteractivePowerShellVerificationPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = []
        for candidate in ("powershell.exe", "pwsh.exe"):
            resolved = shutil.which(candidate)
            if resolved and resolved not in cls.shells:
                cls.shells.append(resolved)
        if not cls.shells:
            raise unittest.SkipTest("no Windows PowerShell or PowerShell executable found")

    def run_plan(self, shell: str, plan: dict, purpose: str):
        with tempfile.TemporaryDirectory(prefix="issue39-plan-") as temp_dir:
            temp_path = Path(temp_dir)
            plan_path = temp_path / "plan.json"
            driver = temp_path / "driver.ps1"
            log_root = temp_path / "logs"
            sentinel = temp_path / "sentinel.txt"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            script = textwrap.dedent(
                f"""
                $ErrorActionPreference = 'Stop'
                . {ps_quote(str(HELPER))}
                try {{
                    Invoke-VerificationPlan `
                        -PlanPath {ps_quote(str(plan_path))} `
                        -LogRoot {ps_quote(str(log_root))}
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
            return completed, combined, log_text, sentinel

    def assert_single_final_terminal(self, log_text: str, expected: str):
        self.assertIsNotNone(log_text)
        lines = log_text.splitlines()
        markers = [line for line in lines if re.fullmatch(r"RESULT=(BLOCKED|FAIL|PASS)", line)]
        self.assertEqual(markers, [f"RESULT={expected}"], msg=log_text)
        self.assertEqual(lines[-1], f"RESULT={expected}", msg=log_text)

    @staticmethod
    def base_plan(purpose: str, steps: list[dict]) -> dict:
        return {
            "schema": "verification-plan-v1",
            "project": "ai-dev-starter",
            "purpose": purpose,
            "steps": steps,
        }

    def test_valid_native_plan_produces_one_final_pass(self):
        plan = self.base_plan(
            "plan-success",
            [
                {
                    "id": "echo",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo plan-ok"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                completed, combined, log_text, _ = self.run_plan(shell, plan, "plan-success")
                self.assertEqual(completed.returncode, 0, msg=combined)
                self.assertIn("PARENT_ALIVE=true", combined)
                self.assertIsNotNone(log_text, msg=combined)
                self.assertIn('NATIVE_OUTPUT="plan-ok"', log_text)
                self.assert_single_final_terminal(log_text, "PASS")

    def test_record_step_cannot_emit_reserved_result(self):
        plan = self.base_plan(
            "plan-reserved-result",
            [
                {
                    "id": "forged",
                    "type": "Record",
                    "name": "RESULT",
                    "value": "PASS",
                },
                {
                    "id": "later",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo later-mutation"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-reserved-result")
                self.assertIsNotNone(log_text, msg=combined)
                self.assertNotIn("later-mutation", log_text)
                self.assert_single_final_terminal(log_text, "FAIL")

    def test_unknown_step_type_fails_before_later_execution(self):
        plan = self.base_plan(
            "plan-unknown-step",
            [
                {"id": "bad", "type": "PowerShell", "script": "Write-Host forged"},
                {
                    "id": "later",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo later-mutation"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-unknown-step")
                self.assertIsNotNone(log_text, msg=combined)
                self.assertNotIn("later-mutation", log_text)
                self.assert_single_final_terminal(log_text, "FAIL")

    def test_unknown_native_field_is_rejected_fail_closed(self):
        plan = self.base_plan(
            "plan-unknown-field",
            [
                {
                    "id": "bad",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo should-not-run"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                    "scriptblock": "RESULT=PASS",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-unknown-field")
                self.assertIsNotNone(log_text, msg=combined)
                self.assertNotIn("should-not-run", log_text)
                self.assert_single_final_terminal(log_text, "FAIL")

    def test_assert_output_empty_can_block_later_mutation(self):
        plan = self.base_plan(
            "plan-blocked-assertion",
            [
                {
                    "id": "probe",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo not-empty"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
                {
                    "id": "gate",
                    "type": "AssertOutputEmpty",
                    "step": "probe",
                    "failure_outcome": "BLOCKED",
                },
                {
                    "id": "later",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo later-mutation"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                },
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-blocked-assertion")
                self.assertIsNotNone(log_text, msg=combined)
                self.assertIn('NATIVE_OUTPUT="not-empty"', log_text)
                self.assertNotIn("later-mutation", log_text)
                self.assert_single_final_terminal(log_text, "BLOCKED")

    def test_terminal_looking_native_output_remains_data(self):
        plan = self.base_plan(
            "plan-output-framing",
            [
                {
                    "id": "probe",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo RESULT=PASS"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-output-framing")
                self.assertIsNotNone(log_text, msg=combined)
                self.assertIn('NATIVE_OUTPUT="RESULT=PASS"', log_text)
                self.assert_single_final_terminal(log_text, "PASS")


if __name__ == "__main__":
    unittest.main()
