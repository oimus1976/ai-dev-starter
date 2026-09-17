# Issue #42 legacy verification API migration

Issue #42 defines the migration and deprecation lifecycle for the legacy
`Invoke-VerificationAttempt -Body` verification API after the declarative
verification-plan authority path was merged by PR #41.

Baseline inspected:

`99c0fb6fbedbdaad589a15975b42d0988f41cc45`

## Inventory result

The exact-baseline repository inventory covered:

- `Invoke-VerificationAttempt`
- `Write-VerificationLog`
- `Write-VerificationField`
- `Invoke-VerificationNative`
- `Stop-VerificationBlocked`
- `Write-VerificationInternalRecord`

The references classify as follows.

### Legacy implementation

`scripts/interactive_verification.ps1` continues to define the legacy
arbitrary-body compatibility surface and its helper functions.

The declarative controller in `scripts/verification_plan.ps1` does not depend
on those legacy helper functions for its terminal-result authority.

### Lower-assurance compatibility/operator use

`docs/INTERACTIVE_POWERSHELL_VERIFICATION.md` documents the legacy API as a
lower-assurance compatibility mechanism.

This documentation does not make the legacy arbitrary-body API valid as the
sole terminal authority for a new HIGH_IMPACT gate.

### Test-only compatibility coverage

`starter_tests/test_interactive_powershell_verification.py` exercises the
Issue #29 fail-stop, logging, native-command, framing, and compatibility
contract.

These tests remain compatibility coverage while the legacy API remains
supported and are not migration targets merely because they reference the
legacy API.

`starter_tests/test_interactive_powershell_repository_evidence.py` also uses
the legacy helpers as test coverage for repository evidence behavior.

### Policy and history references

`AGENTS.md`, `CHANGELOG.md`, `docs/DECLARATIVE_VERIFICATION_PLAN.md`, and
`docs/GITHUB_ACTIONS_QUOTA_FALLBACK.md` contain policy/history references that
explain the authority split or prohibit HIGH_IMPACT fallback to the legacy
arbitrary-body API.

These references are not active legacy callers.

### HIGH_IMPACT callers

No non-test HIGH_IMPACT caller of the legacy arbitrary-body API was found in
the exact-baseline repository inventory.

This finding is limited to repository content at the baseline commit and does
not by itself prove that no downstream consumer exists.

## verification-plan-v1 expressibility

The current declarative vocabulary can:

- execute reviewed native commands;
- treat the resolved native exit status as authoritative;
- assert that captured native output is empty;
- record framed evidence.

It cannot directly compare arbitrary captured output against an independently
supplied expected value.

Therefore checks such as:

- observed HEAD equals an expected commit SHA;
- observed branch equals an expected branch;
- observed repository identity equals an expected repository;

are not generally expressible as declarative output comparisons in
`verification-plan-v1`.

A future narrowly scoped primitive such as `AssertOutputEquals` may be useful,
but Issue #42 does not add it speculatively when no current HIGH_IMPACT
migration requires it.

A reviewed native command or application may instead perform a particular
comparison and communicate the result through its exit status when that is
appropriate for the gate.

## Lifecycle

The legacy API lifecycle is defined as:

1. `compatibility-only`
   - current state;
   - existing Issue #29 compatibility behavior remains supported;
   - new HIGH_IMPACT verification must not use the arbitrary `-Body` API as
     sole terminal authority.

2. `deprecated-for-new-use`
   - no new callers should be introduced, including lower-assurance callers;
   - existing callers and compatibility tests may remain during migration.

3. `migration-complete`
   - non-test operational callers have been migrated or retired;
   - operator documentation no longer teaches the legacy API for new use;
   - remaining references are compatibility tests, history, and migration
     documentation.

4. `removal-candidate`
   - downstream/public-starter impact has been reviewed;
   - a compatibility-test retirement or replacement plan exists;
   - removal can be evaluated as a separate breaking change.

Transition between these states requires explicit evidence. A state name must
not be advanced merely because no new caller was observed in one repository
inventory.

## Current decision

Issue #42 keeps the legacy API in `compatibility-only` state.

At this stage:

- do not remove it;
- do not rename it;
- do not add runtime warning behavior;
- do not weaken the declarative authority policy;
- do not silently fall back to arbitrary `-Body` for an unsupported
  HIGH_IMPACT assertion;
- preserve the Issue #29 bounded fail-stop/logging behavior.

Runtime deprecation warnings are deferred until a deliberate transition to
`deprecated-for-new-use`, because warnings would change observable behavior
while compatibility is intentionally retained.

Any removal or behavior-breaking deprecation remains a separate reviewed
change and a human-final decision.
