# Interactive PowerShell verification contract

This document defines the repository's PowerShell verification surfaces and their authority boundaries.

The common evidence invariant is:

> one initialized attempt = one bounded execution unit = one log file = one terminal outcome

Use `scripts/interactive_verification.ps1` as the canonical entry point. It loads both the legacy bounded-body helper and the declarative verification-plan controller.

## Authority split

For a new `HIGH_IMPACT` gate, prefer the declarative controller documented in `docs/DECLARATIVE_VERIFICATION_PLAN.md` when the required checks can be expressed by `verification-plan-v1`.

The declarative path does not accept an arbitrary authoritative PowerShell callback. It validates the entire data-only plan before native execution, executes only supported primitives, frames caller/native evidence, owns the terminal result, and structurally validates that result.

`Invoke-VerificationAttempt -Body { ... }` remains a compatibility surface for the Issue #29 fail-stop/logging behavior. It is **not** the sole terminal-authority surface for a new `HIGH_IMPACT` gate. Issue #39 adversarial review proved that arbitrary body code in the same dot-sourced runspace can reach the legacy raw writer. Same-runspace naming, module privacy, file locking, and manually assigned `ConstrainedLanguage` were not accepted as a security boundary.

Do not silently substitute the legacy body API when a declarative plan cannot express a required HIGH_IMPACT assertion. Either add a reviewed declarative primitive or report that the higher-assurance path does not yet express the gate.

Issue #42 records the legacy API's current lifecycle state as `compatibility-only`. Runtime deprecation warnings, renaming, and removal are deferred; later lifecycle transitions require explicit migration evidence and review. See `docs/history/issue-42-legacy-verification-api-migration.md`.

## Declarative verification plan

Load the canonical helper and invoke a JSON plan:

```powershell
. .\scripts\interactive_verification.ps1

Invoke-VerificationPlan `
    -PlanPath .\verification-plan.json `
    -LogRoot "$env:TEMP\ai-dev-starter-logs\verification-plan"
```

See `docs/DECLARATIVE_VERIFICATION_PLAN.md` for the schema, supported `Native`, `AssertOutputEmpty`, and `Record` steps, current v1 limitations, threat model, and validation requirements.

For persisted-plan log consumption, use `Get-VerificationLogOutcome`. A valid consumed log must contain exactly one `RESULT=PASS|FAIL|BLOCKED` record and it must be the final record. The consumer rejects zero, multiple, or non-final terminal markers.

This structural consumer check is fail-closed terminal-marker validation. It is not cryptographic authentication of a file against arbitrary code running with the same OS-user authority.

## Legacy bounded-body compatibility contract

The legacy API still provides a useful fail-stop unit for lower-assurance interactive procedures:

```powershell
. .\scripts\interactive_verification.ps1

Invoke-VerificationAttempt `
    -ProjectName "ai-dev-starter" `
    -Purpose "example-verification" `
    -Body {
        param($ctx)

        $head = Invoke-VerificationNative `
            -Context $ctx `
            -Command "git" `
            -Arguments @("rev-parse", "HEAD") `
            -DisplayCommand "git rev-parse HEAD"

        Write-VerificationField -Context $ctx -Name "HEAD" -Value (($head.Output | Out-String).Trim())

        # Keep all checks/mutations belonging to this bounded attempt here.
        # Do not append attempt work as later top-level pasted statements.
    }
```

Its operational invariant remains: a PowerShell/native failure inside the bounded invocation prevents later statements in that body from running and therefore prevents ordinary fall-through to a wrapper PASS.

The legacy body must not write its own terminal marker. However, because the body executes in the caller's runspace, this is now documented as a compatibility rule rather than an access-control guarantee. Do not claim that the raw writer is unreachable from arbitrary body code.

## Native-command behavior

`Invoke-VerificationNative` and the declarative `Native` step preserve the relevant Issue #29 native-command guarantees:

- native command resolution is restricted to applications;
- a rooted resolved application path is recorded and invoked directly;
- function/alias shadowing of the requested executable does not redirect the actual launch;
- the global `$LASTEXITCODE` is cleared immediately before launch and a fresh value is required afterwards;
- missing or stale native exit status fails closed;
- native stderr is diagnostic when the captured exit code is accepted;
- rejected exit codes stop later work;
- caller/native text is JSON-framed so embedded newlines or text such as `RESULT=PASS` cannot become standalone control records through the public framed APIs.

For the legacy helper, `Invoke-VerificationNative` records JSON-framed `COMMAND`, `COMMAND_EXECUTABLE`, `COMMAND_RESOLVED`, optional `DISPLAY_COMMAND`, `NATIVE_OUTPUT`, structured `COMMAND_ARGUMENTS_JSON`, and `EXIT_CODE` evidence.

For the declarative controller, see its dedicated contract for the narrower schema and pre-execution validation rules.

## Logging and terminal outcomes

Legacy default logs live under:

```text
%TEMP%\<project>-logs\<purpose>\attempt-<timestamp>-<pid>-<suffix>.log
```

Declarative-plan default logs live under:

```text
%TEMP%\ai-dev-starter-logs\verification-plan\attempt-<timestamp>-<pid>-<suffix>.log
```

Logs are written as UTF-8. Windows PowerShell 5.1 may include a UTF-8 BOM; the contract is UTF-8 readability, not a specific BOM form.

The normal terminal states are:

- `RESULT=PASS` — the bounded operation/controller completed its required work;
- `RESULT=BLOCKED` — an expected unmet precondition stopped the operation;
- `RESULT=FAIL` — validation, PowerShell, native, or evidence failure prevented success.

For authoritative consumption, never accept a log merely because it contains a `RESULT=PASS` line somewhere. Require exactly one terminal marker and require that marker to be the final record. `Get-VerificationLogOutcome` implements that structural rule.

Do not reconstruct durable gate evidence later from terminal history when the reusable helper can record it during execution.

Do not write secrets, credentials, private data, or unrelated environment dumps merely to make a log comprehensive.

## Repository evidence

A generic helper cannot know which facts are material for every workflow. Gate-producing procedures should normally record, where relevant:

- repository identity;
- branch;
- authoritative expected full HEAD and observed full HEAD;
- pre-operation status;
- commands and native exit codes;
- post-operation HEAD/status;
- any platform fact needed for the claim;
- exactly one structurally valid terminal result.

A PASS marker does not elevate the authority of the underlying checks. Local exact-head verification is still local evidence and must not be reported as GitHub Actions success.

`verification-plan-v1` currently lacks a general output-equality assertion. Therefore it must not be described as proving expected-vs-observed HEAD/branch/repository equality unless that comparison is represented by a supported primitive or an authoritative native exit-code check. See the dedicated plan contract for this limitation.

## Failure containment

The legacy bounded helper rethrows after recording FAIL or BLOCKED. It does not use `exit` merely to stop a routine interactive procedure, so the parent shell is not intentionally terminated.

The declarative controller likewise reports `LOG=<path>` and throws when plan validation/execution or terminal evidence cannot establish success.

Failure to persist or structurally validate terminal evidence must never be converted into PASS.

## Adoption and validation

Downstream repositories should adopt the helper only when they actually need this contract, and should preserve the authority split instead of copying only the convenient API surface.

Changes to these contracts require regression evidence appropriate to the changed surface, including:

- fail-stop behavior;
- native exit-code handling;
- control-record framing;
- executable/cmdlet shadowing resistance claimed by the implementation;
- stale native exit rejection;
- BLOCKED / FAIL / PASS behavior;
- one log per initialized attempt;
- UTF-8 readability;
- parent-session survival where claimed;
- malformed-log consumer rejection;
- declarative complete-plan validation before native execution;
- Windows PowerShell 5.1 / PowerShell 7 behavior claimed by the repository;
- independent L2+ adversarial review for HIGH_IMPACT acceptance.

Ready and merge remain human-final.
