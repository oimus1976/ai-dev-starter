import json
import os
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
class InteractivePowerShellVerificationPlanCasingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = []
        for candidate in ("powershell.exe", "pwsh.exe"):
            resolved = shutil.which(candidate)
            if resolved and resolved not in cls.shells:
                cls.shells.append(resolved)
        if not cls.shells:
            raise unittest.SkipTest("no Windows PowerShell or PowerShell executable found")

    def run_plan(self, shell: str, plan: dict):
        with tempfile.TemporaryDirectory(prefix="issue39-casing-plan-") as temp_dir:
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
            logs = list(log_root.glob("attempt-*.log")) if log_root.exists() else []
            log_text = logs[0].read_bytes().decode("utf-8-sig") if len(logs) == 1 else None
            return completed, completed.stdout + completed.stderr, log_text, sentinel

    def run_consumer(self, shell: str, log_text: str):
        with tempfile.TemporaryDirectory(prefix="issue39-casing-consumer-") as temp_dir:
            temp_path = Path(temp_dir)
            log_path = temp_path / "attempt.log"
            driver = temp_path / "consumer.ps1"
            log_path.write_text(log_text, encoding="utf-8")

            script = textwrap.dedent(
                f"""
                $ErrorActionPreference = 'Stop'
                . {ps_quote(str(HELPER))}
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

    @staticmethod
    def base_plan(steps: list[dict]) -> dict:
        return {
            "schema": "verification-plan-v1",
            "project": "ai-dev-starter",
            "purpose": "casing-regression",
            "steps": steps,
        }

    def assert_plan_rejected_before_sentinel(self, plan: dict):
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, sentinel = self.run_plan(shell, plan)
                self.assertIn("PARENT_ALIVE=true", combined)
                self.assertFalse(sentinel.exists(), msg=combined)
                self.assertIsNotNone(log_text, msg=combined)
                self.assertTrue(log_text.rstrip().endswith("RESULT=FAIL"), msg=log_text)

    def test_consumer_rejects_lowercase_and_mixed_case_terminal_markers(self):
        malformed = (
            "FORMAT=interactive-verification-plan-v1\nresult=pass\n",
            "FORMAT=interactive-verification-plan-v1\nResult=Pass\n",
        )
        for shell in self.shells:
            for log_text in malformed:
                with self.subTest(shell=shell, log_text=log_text):
                    completed = self.run_consumer(shell, log_text)
                    combined = completed.stdout + completed.stderr
                    self.assertEqual(completed.returncode, 7, msg=combined)
                    self.assertIn("REJECTED=", combined)
                    self.assertNotIn("OUTCOME=", combined)

    def test_schema_token_is_case_sensitive(self):
        plan = self.base_plan([
            {
                "id": "note",
                "type": "Record",
                "name": "CUSTOM_NOTE",
                "value": "safe",
            }
        ])
        plan["schema"] = "Verification-Plan-V1"
        self.assert_plan_rejected_before_sentinel(plan)

    def test_step_type_is_case_sensitive(self):
        plan = self.base_plan([
            {
                "id": "note",
                "type": "record",
                "name": "CUSTOM_NOTE",
                "value": "safe",
            }
        ])
        self.assert_plan_rejected_before_sentinel(plan)

    def test_failure_outcome_is_case_sensitive_and_prevalidated(self):
        plan = self.base_plan([
            {
                "id": "would-run",
                "type": "Native",
                "command": "cmd.exe",
                "arguments": ["/d", "/c", "echo SHOULD-NOT-RUN"],
                "accepted_exit_codes": [0],
                "failure_outcome": "blocked",
            }
        ])
        for shell in self.shells:
            with self.subTest(shell=shell):
                _, combined, log_text, _ = self.run_plan(shell, plan)
                self.assertIsNotNone(log_text, msg=combined)
                self.assertNotIn("SHOULD-NOT-RUN", log_text)
                self.assertTrue(log_text.rstrip().endswith("RESULT=FAIL"), msg=log_text)

    def test_record_name_requires_canonical_uppercase(self):
        plan = self.base_plan([
            {
                "id": "note",
                "type": "Record",
                "name": "custom_note",
                "value": "safe",
            }
        ])
        self.assert_plan_rejected_before_sentinel(plan)


if __name__ == "__main__":
    unittest.main()
