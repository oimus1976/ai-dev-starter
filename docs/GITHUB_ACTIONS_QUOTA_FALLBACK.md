# GitHub Actions quota fallback

This document defines the operator procedure when GitHub-hosted Actions is unavailable because the account has exhausted included Actions minutes or an equivalent account/billing/provider availability condition.

This is an **availability fallback**, not a redefinition of CI success.

## 1. Classify the failure before retrying

First distinguish these cases:

- **CODE/TEST FAILURE** — the hosted job started the relevant project command and that command failed.
- **HOSTED CI UNAVAILABLE** — the job could not provide project-test evidence because account quota, billing restriction, or provider availability blocked execution.
- **UNKNOWN** — evidence is insufficient to classify the condition.

Do not infer CODE/TEST FAILURE merely from a red GitHub run when the underlying job never reached the project check.

When the owner has an explicit GitHub quota/billing notification and the runs stop for that reason, record `HOSTED CI UNAVAILABLE: ACTIONS_QUOTA` and stop blind reruns until the condition changes.

## 2. Exact-head local fallback

When project progress should continue while hosted CI is unavailable, use the same exact revision intended for acceptance. Establish that intended full commit SHA from the authoritative PR/branch state before running the local fallback; do not let the local checkout define its own acceptance target.

Minimum evidence:

1. repository identity;
2. branch name;
3. authoritative expected full HEAD SHA and observed local full HEAD SHA;
4. dirty/clean working-tree status;
5. project unit/regression command(s) and native exit code;
6. syntax/compile/static command(s) applicable to the project and native exit code;
7. local baseline/policy verifier command and native exit code;
8. environment facts that materially affect the checks;
9. one durable local log containing commands/results, or a small set of numbered logs.

Use a dedicated ignored/temp log directory rather than scattering verification files in the temp-directory root. A suitable Windows convention is `%TEMP%\<project>-logs\<workstream-or-purpose>\...`. If a project requires durable tracked verification evidence, follow that repository's documented evidence location instead. Never put secrets/private data into the log merely to satisfy this procedure.

A successful exact-head fallback requires the observed local HEAD to equal the independently established expected SHA, a clean worktree before the checks, and still-clean, unchanged HEAD afterwards. A dirty worktree may be useful diagnostic evidence, but it is not exact-head verification because local modifications can change the behavior being tested.

### PowerShell pattern

For a copy/paste procedure in an interactive PowerShell session, run the whole attempt inside one explicit script block. Before running it, replace `<full-sha-intended-for-acceptance>` with the full SHA obtained from the authoritative PR/branch state. Check `$LASTEXITCODE` immediately after every native command whose success matters. Record the command, output, and native exit code in the log. Do not use `exit` merely to stop the procedure, because that terminates the interactive shell. Emit the success marker only once, at the successful end of the guarded block.

```powershell
& {
    $ErrorActionPreference = "Stop"

    $expectedHead = "<full-sha-intended-for-acceptance>"
    if ($expectedHead -eq "<full-sha-intended-for-acceptance>") {
        throw "replace the expected HEAD placeholder with the authoritative full SHA before running"
    }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $logDir = Join-Path $env:TEMP "<project>-logs\actions-quota-fallback"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $log = Join-Path $logDir "local-ci-$stamp.log"

    "EXPECTED_HEAD=$expectedHead" | Tee-Object -FilePath $log

    "COMMAND=git remote get-url origin" | Tee-Object -FilePath $log -Append
    $repo = git remote get-url origin 2>&1
    $code = $LASTEXITCODE
    $repo | Tee-Object -FilePath $log -Append
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "git remote get-url origin failed; see $log" }
    "REPOSITORY=$(($repo | Out-String).Trim())" | Tee-Object -FilePath $log -Append

    "COMMAND=git branch --show-current" | Tee-Object -FilePath $log -Append
    $branch = git branch --show-current 2>&1
    $code = $LASTEXITCODE
    $branch | Tee-Object -FilePath $log -Append
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "git branch --show-current failed; see $log" }
    $branchText = ($branch | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($branchText)) { throw "detached HEAD is not accepted for this fallback; see $log" }
    "BRANCH=$branchText" | Tee-Object -FilePath $log -Append

    "COMMAND=git rev-parse HEAD" | Tee-Object -FilePath $log -Append
    $head = git rev-parse HEAD 2>&1
    $code = $LASTEXITCODE
    $head | Tee-Object -FilePath $log -Append
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "git rev-parse HEAD failed; see $log" }
    $headText = ($head | Out-String).Trim()
    "HEAD=$headText" | Tee-Object -FilePath $log -Append
    if ($headText -ne $expectedHead) { throw "local HEAD does not match authoritative expected HEAD; see $log" }

    "COMMAND=git status --porcelain=v1 --untracked-files=all" | Tee-Object -FilePath $log -Append
    $status = git status --porcelain=v1 --untracked-files=all 2>&1
    $code = $LASTEXITCODE
    $status | Tee-Object -FilePath $log -Append
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "git status failed; see $log" }
    if ($status) { throw "working tree is not clean; exact-head verification blocked; see $log" }
    "WORKTREE_CLEAN=true" | Tee-Object -FilePath $log -Append

    # Replace these with the repository's real CI-equivalent checks.
    "COMMAND=python -m unittest discover -s tests -v" | Tee-Object -FilePath $log -Append
    python -m unittest discover -s tests -v *>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "unit tests failed; see $log" }

    "COMMAND=python -m compileall -q ." | Tee-Object -FilePath $log -Append
    python -m compileall -q . *>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "compile check failed; see $log" }

    "COMMAND=python scripts/verify_repo.py --repository <owner/repo>" | Tee-Object -FilePath $log -Append
    python scripts/verify_repo.py --repository "<owner/repo>" *>&1 |
        Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "baseline policy check failed; see $log" }

    "COMMAND=git rev-parse HEAD" | Tee-Object -FilePath $log -Append
    $postHead = git rev-parse HEAD 2>&1
    $code = $LASTEXITCODE
    $postHead | Tee-Object -FilePath $log -Append
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "post-check HEAD read failed; see $log" }
    $postHeadText = ($postHead | Out-String).Trim()
    if ($postHeadText -ne $expectedHead) { throw "HEAD no longer matches authoritative expected HEAD; see $log" }

    "COMMAND=git status --porcelain=v1 --untracked-files=all" | Tee-Object -FilePath $log -Append
    $postStatus = git status --porcelain=v1 --untracked-files=all 2>&1
    $code = $LASTEXITCODE
    $postStatus | Tee-Object -FilePath $log -Append
    "EXIT_CODE=$code" | Tee-Object -FilePath $log -Append
    if ($code -ne 0) { throw "post-check git status failed; see $log" }
    if ($postStatus) { throw "working tree changed during verification; see $log" }

    "POST_HEAD=$postHeadText" | Tee-Object -FilePath $log -Append
    "POST_WORKTREE_CLEAN=true" | Tee-Object -FilePath $log -Append
    "LOCAL_EXACT_HEAD_VERIFICATION=PASS" | Tee-Object -FilePath $log -Append
    "log=$log"
}
```

The outer script block is deliberate. An exception inside it prevents later check/success statements in this pasted procedure from running. This PR applies that safety property to this example only; the reusable cross-repository interactive PowerShell contract is tracked separately in Issue #29.

Do not mechanically copy Python commands to a non-Python project. The project-specific CI workflow remains the best reference for which local commands are equivalent. Add project-specific environment facts to the log when they materially affect the checks.

## 3. Evidence language

Use wording that keeps authorities distinct:

> GitHub-hosted CI unavailable due to account Actions-minute quota. Exact-head local verification completed at `<full-sha>` with `<commands/results>`. This is local verification evidence and is not reported as GitHub Actions SUCCESS.

Do not say:

- `CI passed` when only local checks passed;
- `GitHub Actions SUCCESS` for a local run;
- `tests failed` when the provider quota prevented the test command from running.

## 4. HIGH_IMPACT changes

For `HIGH_IMPACT`, local fallback does not remove the other gates. Keep separate:

- exact-head local verification;
- required L2+ independent review;
- real-boundary smoke where required;
- C2 owner comprehension;
- human-final Ready;
- human-final merge;
- deployment/release authority where applicable.

If correctness specifically depends on the GitHub-hosted runner environment, a local run cannot establish that runner-specific fact. That claim stays blocked until an appropriate runner boundary is available.

## 5. Self-hosted runner as a mitigation

A self-hosted runner can reduce dependence on GitHub-hosted minute quotas, but adding one changes trust and workflow boundaries.

Treat introducing a self-hosted runner as a separate tracked change with at least `WORKFLOW_PERMISSION`, `PLATFORM_DEPENDENT`, and normally `SECURITY_BOUNDARY` considerations. Review:

- which repositories/workflows may target it;
- what secrets can reach it;
- whether untrusted PR code can execute on it;
- host patching and account isolation;
- persistence between jobs;
- cleanup of workspaces/artifacts;
- network reachability from the runner;
- physical/remote access to the machine;
- runner labels and routing rules;
- recovery/re-registration procedure.

Do not silently change `runs-on` to a self-hosted label across repositories just to bypass quota.

## 6. When hosted minutes return

Return to the normal hosted verification path when the quota resets or billing/provider availability is restored.

The fallback does not permanently weaken the repository's declared CI authority. For a still-open `HIGH_IMPACT` PR, rerun the normal hosted exact-head checks when they become available if the acceptance decision materially relies on hosted-runner evidence.

## 7. Existing-repository adoption

Repositories created before this starter policy was added do not inherit it automatically.

For each active repository:

1. add or link this policy in the repository's operating instructions;
2. identify the exact local commands equivalent to its project CI;
3. keep temp/ignored verification logs outside Git unless the repository explicitly requires durable tracked evidence;
4. document that quota-blocked hosted runs are `UNAVAILABLE`, not PASS or code FAIL;
5. retain Ready/merge human-final rules;
6. decide separately whether a self-hosted runner is warranted.

Backport only the policy needed by the repository; do not copy unrelated starter changes merely for consistency.
