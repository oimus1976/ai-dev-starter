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

### PowerShell authority path

Use `scripts/interactive_verification.ps1` together with the authority split documented in `docs/INTERACTIVE_POWERSHELL_VERIFICATION.md`.

For a new `HIGH_IMPACT` fallback gate, use `Invoke-VerificationPlan` only when `verification-plan-v1` can express every acceptance condition whose success will be claimed. See `docs/DECLARATIVE_VERIFICATION_PLAN.md`.

Current v1 supports data-only `Native`, `AssertOutputEmpty`, and `Record` steps. It validates the complete plan before native execution, frames payloads, uses fresh native exit status, and owns the terminal result. Persisted logs must be consumed with the rule implemented by `Get-VerificationLogOutcome`: exactly one terminal marker, and that marker must be the final record.

Current v1 does **not** provide a general output-equality assertion. Therefore it cannot, by itself, prove expected-vs-observed HEAD/branch/repository equality unless that comparison is expressed through a native command whose exit status authoritatively establishes the condition.

Do not work around that limitation by using `Invoke-VerificationAttempt -Body { ... }` as equivalent HIGH_IMPACT terminal authority. The legacy arbitrary-body API remains for Issue #29 compatibility, but Issue #39 adversarial review proved that same-runspace body code can reach its raw writer. If the local fallback requires an assertion the declarative vocabulary cannot express, record the fallback as not yet fully expressible or extend the vocabulary in a separately reviewed change.

A minimal plan invocation is:

```powershell
. .\scripts\interactive_verification.ps1

Invoke-VerificationPlan `
    -PlanPath .\verification-plan.json `
    -LogRoot "$env:TEMP\ai-dev-starter-logs\verification-plan"
```

For every authoritative initialized plan attempt, require:

- one dedicated UTF-8 log;
- complete-plan validation before the first native step;
- recorded command, structured arguments, resolved executable, output, and exit status where relevant;
- controller-owned `RESULT=PASS|BLOCKED|FAIL`;
- exactly one terminal result and final-record placement for persisted-log consumption;
- `LOG=<path>` surfaced on the console;
- no relabeling of local evidence as hosted CI success.

The helper does not claim an OS security boundary against arbitrary hostile code already executing with the same Windows user authority.

Before acceptance, the project-specific fallback must actually establish every item in the minimum-evidence list above. The generic helper cannot infer project-specific CI-equivalent commands or acceptance preconditions.

Do not mechanically copy Python commands to a non-Python project. The project-specific CI workflow remains the best reference for which local commands are equivalent.

Repositories created before this helper existed do not inherit it automatically. Adopt the helper/contract explicitly before relying on this pattern.

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
2. adopt the interactive PowerShell authority contract if PowerShell gate procedures are used;
3. identify the exact local commands equivalent to project CI;
4. verify that the declarative vocabulary can express every claimed acceptance condition before treating it as HIGH_IMPACT terminal authority;
5. keep temp/ignored verification logs outside Git unless the repository explicitly requires tracked evidence;
6. document quota/provider-blocked hosted runs as `UNAVAILABLE`, not PASS or code FAIL;
7. retain Ready/merge human-final rules;
8. decide separately whether a self-hosted runner is warranted.

Backport only the policy needed by the repository; do not copy unrelated starter changes merely for consistency.
