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
class InteractivePowerShellTerminalAuthorityTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory(prefix="issue39-terminal-authority-") as temp_dir:
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
            self.assertEqual(completed.returncode, 0, msg=combined)
            self.assertIn("PARENT_ALIVE=true", combined)
            self.assertEqual(len(logs), 1, msg=combined)

            log_path = Path(logs[0].strip())
            self.assertTrue(log_path.is_file(), msg=combined)
            log_text = log_path.read_bytes().decode("utf-8-sig")
            return combined, log_text

    def assert_single_final_terminal(self, log_text: str, expected: str):
        lines = log_text.splitlines()
        markers = [
            line
            for line in lines
            if re.fullmatch(r"RESULT=(BLOCKED|FAIL|PASS)", line)
        ]
        self.assertEqual(markers, [f"RESULT={expected}"], msg=log_text)
        self.assertEqual(lines[-1], f"RESULT={expected}", msg=log_text)

    def test_guarded_body_cannot_forge_pass_via_raw_writer(self):
        body = r"""
        Write-VerificationInternalRecord -Context $ctx -Record 'RESULT=PASS'
        throw 'actual failure'
        """

        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text = self.run_driver(shell, body, "raw-pass-forgery")
                self.assertNotRegex(log_text, r"(?m)^RESULT=PASS\r?$")
                self.assert_single_final_terminal(log_text, "FAIL")

    def test_guarded_body_cannot_forge_blocked_via_raw_writer(self):
        body = r"""
        Write-VerificationInternalRecord -Context $ctx -Record 'RESULT=BLOCKED'
        throw 'actual failure'
        """

        for shell in self.shells:
            with self.subTest(shell=shell):
                _, log_text = self.run_driver(shell, body, "raw-blocked-forgery")
                self.assertNotRegex(log_text, r"(?m)^RESULT=BLOCKED\r?$")
                self.assert_single_final_terminal(log_text, "FAIL")

    def test_raw_writer_is_not_discoverable_after_helper_load(self):
        for shell in self.shells:
            with self.subTest(shell=shell):
                script = textwrap.dedent(
                    f"""
                    $ErrorActionPreference = 'Stop'
                    . {ps_quote(str(HELPER))}
                    $command = Microsoft.PowerShell.Core\Get-Command `
                        -Name 'Write-VerificationInternalRecord' `
                        -ErrorAction SilentlyContinue
                    if ($null -ne $command) {{
                        Write-Host 'RAW_WRITER_DISCOVERABLE=true'
                        exit 7
                    }}
                    Write-Host 'RAW_WRITER_DISCOVERABLE=false'
                    """
                )
                with tempfile.TemporaryDirectory(prefix="issue39-discovery-") as temp_dir:
                    driver = Path(temp_dir) / "discover.ps1"
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
                    self.assertEqual(completed.returncode, 0, msg=combined)
                    self.assertIn("RAW_WRITER_DISCOVERABLE=false", combined)


if __name__ == "__main__":
    unittest.main()
