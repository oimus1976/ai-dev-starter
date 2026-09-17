# Declarative verification plan authority contract

This document defines the higher-assurance verification path introduced after Issue #39 showed that an arbitrary PowerShell `-Body` callback in the caller's runspace cannot also be treated as an exclusive terminal-authority boundary.

The authoritative invariant for this path is:

> plan data -> trusted controller validation/execution -> framed evidence -> exactly one final controller-owned RESULT

Use `Invoke-VerificationPlan` from `scripts/interactive_verification.ps1`. The implementation lives in `scripts/verification_plan.ps1` and is loaded by the canonical helper.

## Scope and threat model

This path is intended for `HIGH_IMPACT` gate-producing procedures that can be expressed using the supported declarative vocabulary.

It is designed to fail closed against:

- malformed or hostile plan data;
- unknown step types or fields;
- caller/native payloads that look like control records;
- PowerShell function/alias shadowing of safety-critical native resolution/serialization commands covered by regression tests;
- stale or missing native exit status;
- malformed durable logs containing zero, multiple, or non-final terminal markers.

It does **not** claim an OS security boundary against arbitrary hostile code already executing with the same Windows user authority. Such code can modify files, processes, or the helper itself and requires an external OS/app-control boundary. Do not describe this helper as protection against that stronger threat model.

## Plan schema

The top-level JSON object must contain exactly:

- `schema`: exactly `verification-plan-v1`;
- `project`: identifier matching `[A-Za-z0-9._-]+`;
- `purpose`: identifier matching `[A-Za-z0-9._-]+`;
- `steps`: a non-empty JSON array.

The entire plan is syntactically and semantically validated before the first `Native` step executes. An invalid later step therefore blocks earlier native mutation rather than being discovered only after side effects.

### `Native`

Required fields:

- `id`;
- `type`: `Native`;
- `command`: a simple application name matching `[A-Za-z0-9._-]+`;
- `arguments`: JSON array of strings;
- `accepted_exit_codes`: non-empty JSON array of Int32 values;
- `failure_outcome`: `FAIL` or `BLOCKED`.

The controller resolves only `Application` commands, requires a rooted resolved path, invokes that resolved path directly, clears the global `$LASTEXITCODE` immediately before launch, and requires a fresh exit status afterwards. Native stderr remains diagnostic when the exit code is accepted.

### `AssertOutputEmpty`

Required fields:

- `id`;
- `type`: `AssertOutputEmpty`;
- `step`: id of an earlier `Native` step;
- `failure_outcome`: `FAIL` or `BLOCKED`.

The assertion succeeds only when the referenced native step produced no captured output. A failed assertion stops later steps.

### `Record`

Required fields:

- `id`;
- `type`: `Record`;
- `name`: `[A-Z0-9_]+` and not a controller-reserved field name;
- `value`: string.

`Record` values are JSON-framed data. Text such as `RESULT=PASS`, including multiline text, cannot become a standalone terminal record. `RESULT` and other controller-owned evidence fields are reserved and cannot be emitted by a plan.

## Current v1 limitation

`verification-plan-v1` intentionally has a small vocabulary. It currently does **not** provide an output-equality, regex, or general scripting assertion.

Therefore, do not claim that this v1 plan by itself proves facts such as:

- observed `HEAD` equals an independently established expected SHA;
- observed branch equals an expected branch;
- repository identity equals an expected repository;

unless the required comparison is represented by a native command whose own exit code authoritatively establishes that condition.

Do not work around this limitation by adding an arbitrary PowerShell/script step or by treating the legacy `-Body` callback as equivalent HIGH_IMPACT authority. Extend the declarative vocabulary in a separately reviewed change when a new assertion primitive is required.

## Evidence and terminal authority

Each initialized plan attempt writes one UTF-8 log. The default location is:

```text
%TEMP%\ai-dev-starter-logs\verification-plan\attempt-<timestamp>-<pid>-<suffix>.log
```

Caller-controlled and native output payloads are JSON-framed. Native evidence includes requested command, structured arguments, resolved application path, output items, and exit status.

The controller owns terminal outcome. In a valid plan log:

- exactly one line matches `RESULT=PASS|FAIL|BLOCKED`;
- that line is the final record;
- `PASS` is written only after all plan steps succeed;
- expected unmet conditions may produce `BLOCKED` when the step declares that failure outcome;
- other validation/execution failures produce `FAIL`.

The controller self-validates its terminal evidence through a controller-local parser before reporting successful completion. This self-check does not depend on a caller-replaceable public consumer function.

For later consumption of a persisted log, use `Get-VerificationLogOutcome`. It rejects logs with zero, multiple, or non-final terminal records. This is a structural terminal-marker check, not cryptographic authentication of the file or its origin.

## Relationship to the legacy body API

`Invoke-VerificationAttempt -Body { ... }` remains available for compatibility with the Issue #29 bounded-execution/logging behavior and its regression suite.

However, post-merge adversarial review demonstrated that a body running in the same dot-sourced PowerShell session can reach the legacy raw writer. Attempts to turn same-runspace naming, module-private state, file locking, or manually assigned `ConstrainedLanguage` into a security boundary were rejected during Issue #39 work.

Accordingly:

- do not use the legacy arbitrary-body API as the sole terminal-authority evidence for a new `HIGH_IMPACT` gate;
- do not describe `Internal` naming or same-runspace module privacy as access control;
- when consuming any persisted result, require the structural consumer rule of exactly one final terminal marker;
- keep the legacy path only where its lower-assurance compatibility contract is explicitly acceptable.

Whether the legacy API should ultimately be removed, renamed, or retained as a documented lower-assurance compatibility surface remains a human architecture decision under Issue #39.

## Validation requirements

Changes to the declarative authority path require exact-head regression evidence covering, where applicable:

- complete-plan validation before native execution;
- unknown type/field fail-closed behavior;
- JSON array/type/range constraints;
- reserved-field rejection;
- output/control-record framing;
- native application resolution and direct resolved-path launch;
- executable/cmdlet shadowing resistance claimed by the implementation;
- fresh native exit status and accepted/rejected exit behavior;
- stderr-with-success behavior on Windows PowerShell 5.1 and PowerShell 7;
- assertion fail-stop behavior;
- exactly one final terminal result;
- malformed-log consumer rejection;
- preservation of relevant Issue #29 regressions;
- independent L2+ adversarial review for `HIGH_IMPACT` acceptance.

Ready and merge remain human-final.
