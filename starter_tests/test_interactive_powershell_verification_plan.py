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

    def run_plan(self, shell: str, plan: dict, purpose: str, prelude: str = ""):
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

    def run_consumer(self, shell: str, log_text: str, tamper_record: str | None = None):
        with tempfile.TemporaryDirectory(prefix="issue39-plan-consumer-") as temp_dir:
            temp_path = Path(temp_dir)
            log_path = temp_path / "attempt.log"
            driver = temp_path / "consumer.ps1"
            log_path.write_text(log_text, encoding="utf-8")

            tamper = ""
            if tamper_record is not None:
                tamper = textwrap.dedent(
                    f"""
                    $ctx = [pscustomobject]@{{ LogPath = {ps_quote(str(log_path))} }}
                    Write-VerificationInternalRecord `
                        -Context $ctx `
                        -Record {ps_quote(tamper_record)}
                    """
                ).strip()

            script = textwrap.dedent(
                f"""
                $ErrorActionPreference = 'Stop'
                . {ps_quote(str(HELPER))}
                {tamper}
                try {{
                    $outcome = Get-VerificationLogOutcome -LiteralPath {ps_quote(str(log_path))}
                    Microsoft.PowerShell.Utility\\Write-Host ('OUTCOME=' + $outcome)
                    exit 0
                }}
                catch {{
                    Microsoft.PowerShell.Utility\\Write-Host ('REJECTED=' + $_.Exception.Message)
                    exit 7
                }}
                """
            )
            driver.write_text(script, encoding="utf-8-sig")

            command = [shell, "-NoProfile"]
            if Path(shell).name.lower() == "powershell.exe":
                command.extend(["-ExecutionPolicy", "Bypass"])
            command.extend(["-File", str(driver)])
            return subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=30,
                check=False,
            )

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

    def test_record_multiline_terminal_text_remains_framed_data(self):
        plan = self.base_plan(
            "plan-record-framing",
            [
                {
                    "id": "note",
                    "type": "Record",
                    "name": "CUSTOM_NOTE",
                    "value": "safe\nRESULT=FAIL",
                }
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-record-framing")
                self.assertIsNotNone(log_text, msg=combined)
                self.assertIn('CUSTOM_NOTE="safe\\nRESULT=FAIL"', log_text)
                self.assert_single_final_terminal(log_text, "PASS")

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

    def test_entire_plan_is_validated_before_earlier_native_execution(self):
        plan = self.base_plan(
            "plan-prevalidate-all",
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
                    "arguments": ["/d", "/c", "echo SHOULD-NOT-RUN"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                    "scriptblock": "forged",
                },
            ],
        )
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-prevalidate-all")
                self.assertIsNotNone(log_text, msg=combined)
                self.assertNotIn("EARLY-RAN", log_text)
                self.assertNotIn("SHOULD-NOT-RUN", log_text)
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

    def test_critical_cmdlet_shadowing_does_not_redirect_plan_controller(self):
        plan = self.base_plan(
            "plan-shadowing",
            [
                {
                    "id": "probe",
                    "type": "Native",
                    "command": "cmd.exe",
                    "arguments": ["/d", "/c", "echo shadow-safe"],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        prelude = r"""
        function global:ConvertFrom-Json { throw 'shadow ConvertFrom-Json invoked' }
        function global:ConvertTo-Json { throw 'shadow ConvertTo-Json invoked' }
        function global:Get-Command { throw 'shadow Get-Command invoked' }
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-shadowing", prelude)
                self.assertNotIn("shadow ConvertFrom-Json invoked", combined)
                self.assertNotIn("shadow ConvertTo-Json invoked", combined)
                self.assertNotIn("shadow Get-Command invoked", combined)
                self.assertIsNotNone(log_text, msg=combined)
                self.assertIn('NATIVE_OUTPUT="shadow-safe"', log_text)
                self.assert_single_final_terminal(log_text, "PASS")

    def test_missing_executable_cannot_reuse_stale_success(self):
        plan = self.base_plan(
            "plan-stale-exit",
            [
                {
                    "id": "missing",
                    "type": "Native",
                    "command": "definitely-missing-verification-plan.exe",
                    "arguments": [],
                    "accepted_exit_codes": [0],
                    "failure_outcome": "FAIL",
                }
            ],
        )
        prelude = r"""
        & "$env:SystemRoot\System32\cmd.exe" /d /c "exit /b 0"
        """
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan, "plan-stale-exit", prelude)
                self.assertIsNotNone(log_text, msg=combined)
                self.assertIn("EXIT_CODE=UNAVAILABLE", log_text)
                self.assert_single_final_terminal(log_text, "FAIL")

    def test_consumer_accepts_exactly_one_final_terminal_record(self):
        log_text = "FORMAT=interactive-verification-plan-v1\nRESULT=PASS\n"
        for shell in self.shells:
            with self.subTest(shell=shell):
                completed = self.run_consumer(shell, log_text)
                combined = completed.stdout + completed.stderr
                self.assertEqual(completed.returncode, 0, msg=combined)
                self.assertIn("OUTCOME=PASS", combined)

    def test_consumer_rejects_zero_multiple_and_nonfinal_terminal_records(self):
        malformed_logs = [
            "FORMAT=interactive-verification-plan-v1\nDETAIL=\"none\"\n",
            "FORMAT=interactive-verification-plan-v1\nRESULT=PASS\nRESULT=FAIL\n",
            "FORMAT=interactive-verification-plan-v1\nRESULT=PASS\nDETAIL=\"after\"\n",
        ]
        for shell in self.shells:
            for index, log_text in enumerate(malformed_logs):
                with self.subTest(shell=shell, malformed=index):
                    completed = self.run_consumer(shell, log_text)
                    self.assertEqual(
                        completed.returncode,
                        7,
                        msg=completed.stdout + completed.stderr,
                    )

    def test_consumer_rejects_legacy_raw_writer_terminal_append(self):
        original = "FORMAT=interactive-verification-plan-v1\nRESULT=FAIL\n"
        for shell in self.shells:
            with self.subTest(shell=shell):
                completed = self.run_consumer(shell, original, "RESULT=PASS")
                combined = completed.stdout + completed.stderr
                self.assertEqual(completed.returncode, 7, msg=combined)
                self.assertIn("REJECTED=", combined)


if __name__ == "__main__":
    unittest.main()
