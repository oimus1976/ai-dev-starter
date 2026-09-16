# GitHub Actions quota fallback

This document defines the operator procedure when GitHub-hosted Actions is unavailable because included Actions minutes, billing restrictions, or provider availability prevent the normal project checks from running.

This is an **availability fallback**, not a redefinition of CI success.

## 1. Classify the failure before retrying

Keep these states distinct:

- **CODE/TEST FAILURE** — the hosted job ran the relevant project command and that command failed.
- **HOSTED CI UNAVAILABLE** — the hosted environment did not provide project-test evidence because quota, billing, or provider availability blocked execution.
- **UNKNOWN** — evidence is insufficient to classify the condition.

Do not infer code failure merely from a red GitHub run when the underlying project command never ran. When an explicit quota or billing condition is established, record hosted CI as unavailable and stop blind reruns until the condition changes.

## 2. Exact-head local fallback

When progress should continue while hosted CI is unavailable, verify the same exact revision intended for acceptance. Establish the expected full commit SHA from authoritative PR/branch state before running local checks; do not let the local checkout define its own acceptance target.

Minimum evidence:

1. repository identity;
2. branch name;
3. authoritative expected full HEAD and observed local full HEAD;
4. clean working-tree status before checks;
5. project unit/regression commands and native exit codes;
6. syntax/compile/static commands where applicable and native exit codes;
7. local baseline/policy verifier and native exit code;
8. material environment facts;
9. unchanged HEAD and clean worktree after checks;
10. one durable attempt log.

A successful exact-head fallback requires the observed local HEAD to equal the independently established expected SHA, a clean worktree before the checks, and still-clean, unchanged HEAD afterwards. A dirty worktree may be diagnostic evidence, but it is not exact-head verification.

### Interactive PowerShell

Use the canonical contract in `docs/INTERACTIVE_POWERSHELL_VERIFICATION.md` and the paired helper files `scripts/interactive_verification.ps1` + `scripts/interactive_verification.psm1`.

The required shape is:

```powershell
. .\scripts\interactive_verification.ps1

$expectedHead = "<authoritative-full-sha>"

Invoke-VerificationAttempt `
    -ProjectName "<project>" `
    -Purpose "actions-quota-fallback" `
    -Body {
        param($ctx)

        # Record repository, branch, expected/observed HEAD, and pre-status.
        # Use Invoke-VerificationNative for every native command whose success matters.
        # Call Stop-VerificationBlocked for unmet acceptance preconditions.
        # Run the repository's real CI-equivalent local checks.
        # Re-read HEAD and status after the checks.
        # Do not write RESULT=PASS here; the wrapper owns the terminal marker.
    }
```

The body must contain all gate-producing work for the attempt. Do not paste later mutation or success statements after the bounded invocation.

For every initialized attempt the helper provides:

- a dedicated log under `%TEMP%\<project>-logs\actions-quota-fallback\...` by default;
- explicit UTF-8 log writing;
- framed native-command evidence including JSON-framed `COMMAND=...`, `COMMAND_EXECUTABLE=...`, resolved application path `COMMAND_RESOLVED=...`, structured `COMMAND_ARGUMENTS_JSON=...`, JSON-framed `NATIVE_OUTPUT=...`, and `EXIT_CODE=...`; caller-provided `DISPLAY_COMMAND=...` is explanatory only and payload text cannot create standalone control records;
- application-only resolution followed by direct invocation of the resolved executable path, preventing PowerShell function/alias shadowing;
- fresh native-exit capture: the global `$LASTEXITCODE` is cleared before launch and a missing fresh status fails closed instead of reusing stale success; native stderr remains diagnostic when the exit code is accepted;
- a module-private raw-record writer that is not exported to the guarded caller session;
- an opaque guarded context that does not expose `LogPath`;
- an active durable log opened by the module with read-only sharing so guarded body code cannot reopen, replace, or delete the log for writing on the supported Windows boundary;
- exactly one persisted terminal result in the normal evidence path: `RESULT=PASS`, `RESULT=BLOCKED`, or `RESULT=FAIL`;
- canonical fail-closed consumption via `Get-VerificationLogOutcome`, which rejects zero, multiple, or non-final terminal records;
- `LOG=<path>` on the console when the helper reaches its terminal reporting path;
- no routine use of `exit`, so a failed bounded attempt does not intentionally terminate the interactive shell.

A fallback consumer must never treat the mere presence of `RESULT=PASS` as sufficient. The log is acceptable only when exactly one terminal result exists and it is the final log record.

Before acceptance, the local fallback body for a specific repository must actually record the minimum evidence listed above. The generic helper cannot infer project-specific test commands or acceptance preconditions.

Do not mechanically copy Python commands to a non-Python project. The project-specific CI workflow remains the best reference for which local commands are equivalent.

Repositories created before this helper existed do not inherit it automatically. Adopt the `.ps1` entrypoint and `.psm1` implementation together before relying on this exact interactive pattern.

## 3. Evidence language

Use wording that keeps authorities distinct:

> GitHub-hosted CI unavailable due to account/provider availability. Exact-head local verification completed at `<full-sha>` with `<commands/results>`. This is local verification evidence and is not reported as GitHub Actions SUCCESS.

Do not say:

- `CI passed` when only local checks passed;
- `GitHub Actions SUCCESS` for a local run;
- `tests failed` when the provider condition prevented the test command from running.

## 4. HIGH_IMPACT changes

For `HIGH_IMPACT`, local fallback does not remove the other gates. Keep separate:

- exact-head local verification;
- required L2+ independent review;
- real-boundary smoke where required;
- C2 owner comprehension;
- human-final Ready;
- human-final merge;
- deployment/release authority where applicable.

If correctness specifically depends on the GitHub-hosted runner environment, a local run cannot establish that runner-specific fact. That claim remains blocked until an appropriate runner boundary is available.

## 5. Self-hosted runner as a mitigation

A self-hosted runner can reduce dependence on GitHub-hosted minute quotas, but adding one changes trust and workflow boundaries.

Treat introducing a self-hosted runner as a separate tracked change. Review at least:

- which repositories/workflows may target it;
- what secrets can reach it;
- whether untrusted PR code can execute on it;
- host patching and account isolation;
- persistence between jobs;
- workspace/artifact cleanup;
- network reachability;
- physical/remote access;
- runner labels and routing rules;
- recovery/re-registration procedure.

Do not silently change `runs-on` merely to bypass quota.

## 6. When hosted minutes return

Return to the normal hosted verification path when quota, billing, or provider availability is restored.

The fallback does not permanently weaken the repository's declared CI authority. For a still-open `HIGH_IMPACT` PR, rerun the normal hosted exact-head checks when they become available if acceptance materially relies on hosted-runner evidence.

## 7. Existing-repository adoption

For each active repository that needs this fallback:

1. add or link this policy in the repository's operating instructions;
2. adopt both interactive PowerShell helper files/contract if interactive gate-producing PowerShell is used;
3. identify the exact local commands equivalent to project CI;
4. keep temp/ignored verification logs outside Git unless the repository explicitly requires tracked evidence;
5. document quota/provider-blocked hosted runs as `UNAVAILABLE`, not PASS or code FAIL;
6. retain Ready/merge human-final rules;
7. decide separately whether a self-hosted runner is warranted.

Backport only the policy needed by the repository; do not copy unrelated starter changes merely for consistency.
