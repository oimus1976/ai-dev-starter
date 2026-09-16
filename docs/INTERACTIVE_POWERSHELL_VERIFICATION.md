# Interactive PowerShell verification contract

This document defines the reusable operator pattern for state-changing or gate-producing PowerShell procedures pasted or invoked from an interactive PowerShell session.

The invariant is:

> one attempt = one bounded execution unit = one log file = one terminal outcome

Use `scripts/interactive_verification.ps1` as the canonical helper entrypoint in this repository. The entrypoint imports the implementation module and exposes only the supported caller surface; the raw record writer remains module-private. Adopt or copy both helper files deliberately into downstream repositories that need the same contract; do not reconstruct the pattern from chat history.

## Required operator shape

Load the helper, then put **all gate checks, mutations, and success-producing work inside one `Invoke-VerificationAttempt` body**. Do not append attempt steps after the invocation as separate top-level pasted statements.

```powershell
. .\scripts\interactive_verification.ps1

Invoke-VerificationAttempt `
    -ProjectName "ai-dev-starter" `
    -Purpose "example-verification" `
    -Body {
        param($ctx)

        $repo = Invoke-VerificationNative `
            -Context $ctx `
            -Command "git" `
            -Arguments @("remote", "get-url", "origin") `
            -DisplayCommand "git remote get-url origin"

        $branch = Invoke-VerificationNative `
            -Context $ctx `
            -Command "git" `
            -Arguments @("branch", "--show-current") `
            -DisplayCommand "git branch --show-current"

        $head = Invoke-VerificationNative `
            -Context $ctx `
            -Command "git" `
            -Arguments @("rev-parse", "HEAD") `
            -DisplayCommand "git rev-parse HEAD"

        $status = Invoke-VerificationNative `
            -Context $ctx `
            -Command "git" `
            -Arguments @("status", "--porcelain=v1", "--untracked-files=all") `
            -DisplayCommand "git status --porcelain=v1 --untracked-files=all"

        if ($status.Output.Count -ne 0) {
            Stop-VerificationBlocked "working tree is not clean"
        }

        Write-VerificationField -Context $ctx -Name "REPOSITORY" -Value (($repo.Output | Out-String).Trim())
        Write-VerificationField -Context $ctx -Name "BRANCH" -Value (($branch.Output | Out-String).Trim())
        Write-VerificationField -Context $ctx -Name "HEAD" -Value (($head.Output | Out-String).Trim())

        # Put any permitted mutation only after all required gates.
        # Do not emit RESULT=PASS here; the wrapper owns the terminal marker.
    }
```

The helper creates and opens the durable log before the guarded body starts. The module retains the write handle with read-only sharing while the body runs, so guarded code is not given the log path and cannot replace or reopen the active log for writing through ordinary caller-visible APIs. In the normal evidence path, an initialized attempt persists exactly one terminal marker and prints `LOG=<path>`.

## Terminal outcomes

- `RESULT=PASS` — the guarded body completed without an exception.
- `RESULT=BLOCKED` — an expected unmet precondition called `Stop-VerificationBlocked`.
- `RESULT=FAIL` — any other exception or rejected native exit code.

The body must not write its own terminal marker. PASS is owned by the wrapper and can only be produced at the successful end.

`Write-VerificationInternalRecord` is module-private and is not exported into the caller session. The guarded body receives an opaque attempt capability rather than `LogPath`. Caller-visible diagnostic APIs can only write framed data records. Naming a function `Internal` is not treated as the boundary; module export state, opaque context, and the held log handle form the boundary together.

## Native commands

Use `Invoke-VerificationNative` for native commands whose success matters. It logs:

- `COMMAND=...` as a JSON-framed human-readable rendering of the requested invocation;
- `COMMAND_EXECUTABLE=...` as a JSON-framed requested executable name;
- `COMMAND_ARGUMENTS_JSON=...` so argument boundaries remain independently inspectable;
- `COMMAND_RESOLVED=...` as the JSON-framed resolved application path that is actually invoked;
- optional `DISPLAY_COMMAND=...` as JSON-framed caller-supplied explanatory text when it differs from the requested invocation;
- each stdout/stderr item as a JSON-framed `NATIVE_OUTPUT=...` record;
- `EXIT_CODE=...`.

Caller-controlled text and native output are encoded so embedded newlines or text such as `RESULT=PASS` cannot become standalone control records. `DISPLAY_COMMAND` is never authoritative evidence of what executed. `COMMAND_RESOLVED` records the application path actually invoked.

The helper resolves native commands as applications first and invokes that resolved path directly so a PowerShell function or alias with the same name cannot shadow the executable between resolution and launch. Immediately before launch it clears the global `$LASTEXITCODE`; immediately after launch it captures the fresh value. If no fresh native exit status is produced, the attempt fails with `EXIT_CODE=UNAVAILABLE` rather than reusing a stale value.

Exit status is authoritative. Windows PowerShell 5.1 may otherwise surface redirected native stderr as an `ErrorRecord`, so the helper temporarily permits native stderr while the process runs, restores fail-stop PowerShell error behavior before writing evidence, and then decides native success from the captured exit code. Stderr content is diagnostic only and does not itself make the native command fail.

The default accepted native exit code is `0`. If a command intentionally uses another exit code as a non-error state, pass the explicit accepted set and interpret the command result before continuing.

If an expected state means the attempt cannot continue safely, call `Stop-VerificationBlocked` rather than manufacturing a successful exit.

## Logging contract

Default logs live under:

```text
%TEMP%\<project>-logs\<purpose>\attempt-<timestamp>-<pid>-<suffix>.log
```

For this repository that becomes `%TEMP%\ai-dev-starter-logs\<purpose>\...`.

A repository may provide `-LogRoot` only when it has an explicit alternative evidence location. Do not scatter gate logs directly in `%TEMP%` or reconstruct them later from terminal scrollback.

The helper writes log files with explicit UTF-8 encoding. Windows PowerShell 5.1 and PowerShell 7 must both preserve readable UTF-8 evidence.

`Write-VerificationLog` is the caller-facing diagnostic writer and always records payload text as a JSON-framed `DETAIL=...` field. Use `Write-VerificationField` for named caller evidence such as repository, branch, or HEAD values. `RESULT` is reserved and cannot be emitted through the public field writer.

The guarded context intentionally does **not** expose `LogPath`. The active durable log is held open by the module with `FileShare.Read`, so a guarded body cannot reopen, replace, or delete it for writing on the supported Windows boundary while the attempt is active.

Do not write secrets, credentials, private data, or unrelated environment dumps merely to make the log comprehensive.

## Consuming verification logs

Do not treat the presence of any `RESULT=PASS` line as sufficient evidence.

Use `Get-VerificationLogOutcome -LiteralPath <path>` or an equivalent fail-closed parser. A valid log must contain:

- exactly one terminal `RESULT=PASS|FAIL|BLOCKED` record; and
- that terminal record must be the final log record.

Logs with zero terminal records, multiple terminal records, or a non-final terminal record are malformed and must be rejected rather than interpreted as PASS.

## Repository evidence

A generic helper cannot know which facts are material for every workflow. Gate-producing procedures should normally record, where relevant:

- repository identity;
- branch;
- expected and observed full HEAD;
- pre-operation status;
- commands and native exit codes;
- post-operation HEAD/status;
- any platform fact needed for the claim;
- exactly one terminal result.

A PASS marker does not elevate the authority of the underlying checks. For example, local exact-head verification is still local evidence and must not be reported as GitHub Actions success.

## Failure containment

The helper deliberately rethrows after recording FAIL or BLOCKED. In an interactive PowerShell session this aborts the current bounded invocation but does not use `exit` and therefore does not intentionally terminate the parent shell.

If an error occurs while recording diagnostic error text, the original verification exception remains authoritative and the helper reports `LOG_WRITE_ERROR=...` on the console. If persistence or validation of terminal `RESULT=PASS` evidence fails, the attempt fails rather than returning a success with incomplete durable evidence.

Do not defeat this property by pasting later mutation or success statements after `Invoke-VerificationAttempt`. If follow-up work is part of the same attempt, it belongs inside the `-Body` block.

## Adoption and validation

Downstream repositories should adopt the `.ps1` entrypoint and `.psm1` implementation together when they actually use interactive PowerShell gate procedures. Tailor repository-specific commands and evidence fields; do not copy Python or starter-specific checks mechanically.

Changes to this contract require regression evidence for:

- early PowerShell exception fail-stop;
- native non-zero fail-stop;
- native stderr with exit code `0` remaining diagnostic rather than becoming a false failure;
- caller-provided display text, native output, and public diagnostic logging being unable to inject standalone control records;
- caller-provided display text being unable to replace executable/argument evidence;
- resolved application execution being immune to PowerShell function/alias shadowing;
- stale native exit status being unable to authorize later success;
- guarded-body inability to discover or call the raw record writer;
- guarded-body inability to replace or reopen the active log for writing;
- BLOCKED / FAIL / PASS exclusivity;
- exactly one final terminal record;
- malformed-log consumer rejection for zero, multiple, or non-final terminal markers;
- one log per initialized attempt;
- `LOG=<path>` surfacing;
- UTF-8 readability;
- terminal-log persistence/validation failure being unable to surface a false PASS;
- parent-session survival;
- Windows PowerShell 5.1 / PowerShell 7 behavior claimed by the repository.
