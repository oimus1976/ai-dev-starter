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
FIXTURE_REMOTE = "https://example.invalid/oimus1976/evidence-fixture.git"
FIXTURE_BRANCH = "evidence-branch"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed with {completed.returncode}: {completed.stderr}"
        )
    return completed.stdout.strip()


@unittest.skipUnless(os.name == "nt", "real PowerShell boundary coverage is Windows-only")
class InteractivePowerShellRepositoryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = []
        for candidate in ("powershell.exe", "pwsh.exe"):
            resolved = shutil.which(candidate)
            if resolved and resolved not in cls.shells:
                cls.shells.append(resolved)
        if not cls.shells:
            raise unittest.SkipTest("no Windows PowerShell or PowerShell executable found")

    def make_repo_fixture(self, root: Path) -> tuple[Path, str]:
        repo = root / "repo"
        repo.mkdir()
        run_git(repo, "init")
        run_git(repo, "config", "user.name", "Issue 29 Regression")
        run_git(repo, "config", "user.email", "issue29@example.invalid")
        (repo / "tracked.txt").write_text("fixture\n", encoding="utf-8")
        run_git(repo, "add", "tracked.txt")
        run_git(repo, "commit", "-m", "fixture")
        run_git(repo, "branch", "-M", FIXTURE_BRANCH)
        run_git(repo, "remote", "add", "origin", FIXTURE_REMOTE)
        expected_head = run_git(repo, "rev-parse", "HEAD")
        self.assertRegex(expected_head, r"^[0-9a-f]{40}$")
        self.assertEqual(run_git(repo, "status", "--porcelain=v1", "--untracked-files=all"), "")
        return repo, expected_head

    def run_evidence_attempt(self, shell: str, repo: Path, expected_head: str, temp_path: Path):
        driver = temp_path / f"driver-{Path(shell).stem}.ps1"
        env = os.environ.copy()
        env["TEMP"] = str(temp_path)
        env["TMP"] = str(temp_path)

        script = textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . {ps_quote(str(HELPER))}
            $expectedHead = {ps_quote(expected_head)}

            try {{
                Invoke-VerificationAttempt `
                    -ProjectName 'ai-dev-starter' `
                    -Purpose 'repository-evidence' `
                    -Body {{
                        param($ctx)

                        $repo = Invoke-VerificationNative -Context $ctx -Command 'git' -Arguments @('remote', 'get-url', 'origin') -DisplayCommand 'git remote get-url origin'
                        $branch = Invoke-VerificationNative -Context $ctx -Command 'git' -Arguments @('rev-parse', '--abbrev-ref', 'HEAD') -DisplayCommand 'git rev-parse --abbrev-ref HEAD'
                        $head = Invoke-VerificationNative -Context $ctx -Command 'git' -Arguments @('rev-parse', 'HEAD') -DisplayCommand 'git rev-parse HEAD'
                        $preStatus = Invoke-VerificationNative -Context $ctx -Command 'git' -Arguments @('status', '--porcelain=v1', '--untracked-files=all') -DisplayCommand 'git status --porcelain=v1 --untracked-files=all'

                        $headText = (($head.Output | Out-String).Trim())
                        if ($headText -ne $expectedHead) {{ Stop-VerificationBlocked 'HEAD mismatch' }}
                        if ($preStatus.Output.Count -ne 0) {{ Stop-VerificationBlocked 'pre-status is dirty' }}

                        Write-VerificationField -Context $ctx -Name 'REPOSITORY' -Value (($repo.Output | Out-String).Trim())
                        Write-VerificationField -Context $ctx -Name 'BRANCH' -Value (($branch.Output | Out-String).Trim())
                        Write-VerificationField -Context $ctx -Name 'EXPECTED_HEAD' -Value $expectedHead
                        Write-VerificationField -Context $ctx -Name 'HEAD' -Value $headText
                        Write-VerificationField -Context $ctx -Name 'PRE_STATUS_CLEAN' -Value 'true'

                        $postHead = Invoke-VerificationNative -Context $ctx -Command 'git' -Arguments @('rev-parse', 'HEAD') -DisplayCommand 'git rev-parse HEAD (post)'
                        $postStatus = Invoke-VerificationNative -Context $ctx -Command 'git' -Arguments @('status', '--porcelain=v1', '--untracked-files=all') -DisplayCommand 'git status --porcelain=v1 --untracked-files=all (post)'
                        $postHeadText = (($postHead.Output | Out-String).Trim())
                        if ($postHeadText -ne $expectedHead) {{ Stop-VerificationBlocked 'post HEAD mismatch' }}
                        if ($postStatus.Output.Count -ne 0) {{ Stop-VerificationBlocked 'post-status is dirty' }}

                        Write-VerificationField -Context $ctx -Name 'POST_HEAD' -Value $postHeadText
                        Write-VerificationField -Context $ctx -Name 'POST_STATUS_CLEAN' -Value 'true'
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
            cwd=repo,
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
        logs = re.findall(r"(?m)^LOG=(.+)$", combined)
        self.assertEqual(len(logs), 1, msg=combined)
        log_path = Path(logs[0].strip())
        self.assertTrue(log_path.is_file(), msg=combined)
        return log_path.read_bytes().decode("utf-8-sig")

    def test_repository_branch_exact_head_and_pre_post_status_are_recorded(self):
        with tempfile.TemporaryDirectory(prefix="issue29-repo-evidence-") as temp_dir:
            temp_path = Path(temp_dir)
            repo, expected_head = self.make_repo_fixture(temp_path)

            for shell in self.shells:
                with self.subTest(shell=shell):
                    log_text = self.run_evidence_attempt(shell, repo, expected_head, temp_path)
                    self.assertIn(f'REPOSITORY="{FIXTURE_REMOTE}"', log_text)
                    self.assertIn(f'BRANCH="{FIXTURE_BRANCH}"', log_text)
                    self.assertIn(f'EXPECTED_HEAD="{expected_head}"', log_text)
                    self.assertIn(f'HEAD="{expected_head}"', log_text)
                    self.assertIn('PRE_STATUS_CLEAN="true"', log_text)
                    self.assertIn(f'POST_HEAD="{expected_head}"', log_text)
                    self.assertIn('POST_STATUS_CLEAN="true"', log_text)
                    self.assertRegex(log_text, r"(?m)^RESULT=PASS\r?$")
                    self.assertNotIn("RESULT=FAIL", log_text)
                    self.assertNotIn("RESULT=BLOCKED", log_text)

            self.assertEqual(run_git(repo, "rev-parse", "HEAD"), expected_head)
            self.assertEqual(run_git(repo, "status", "--porcelain=v1", "--untracked-files=all"), "")


if __name__ == "__main__":
    unittest.main()
