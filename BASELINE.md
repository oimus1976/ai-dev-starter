# oimus AI Development Baseline v0.5

## 1. Scope

This baseline governs AI-assisted development in repositories that adopt it. It is intentionally a **house policy**: project-specific needs may tighten it, but weakening a safety or authority boundary must be explicit and justified.

The baseline optimizes four outcomes together:

1. correctness;
2. security;
3. operability;
4. comprehensibility.

Fast implementation that leaves the owner unable to understand or recover the project is not considered a successful outcome.

## 2. Authority is per fact, not per project

Do not declare one system the source of truth for everything.

For each material fact or state, identify exactly one authority where practical. Typical domains include:

- planning and priority;
- execution scope and progress;
- source code;
- private/actual data;
- CI result;
- review result;
- deployed production state;
- credentials;
- release artifacts.

A local chat, agent summary, or copied status message is never authoritative merely because it is convenient.

`PROJECT_PROFILE.toml` records the project authority map.

## 3. AI output is a claim until verified

Statements such as:

- "done";
- "tests pass";
- "pushed";
- "reviewed";
- "deployed";

are claims.

Evidence should come from the authority that owns the fact: Git commit/SHA, diff, CI run, test output, deployed target observation, artifact hash, or another explicit authoritative source.

Do not manufacture missing evidence from agent prose.

## 4. Exploration is lighter than tracked implementation

Disposable exploration/spikes may remain outside the full Issue/PR workflow if all of the following hold:

- the work is not intended to be merged or shipped;
- it does not touch actual/private data, credentials, production, destructive I/O, or another protected effect;
- its output is treated as experimental evidence, not adopted behavior.

Once work is intended to persist, it becomes a tracked change.

For tracked changes:

- use an explicit implementation branch;
- do not use direct `main` write as the normal path;
- use a Draft PR while implementation/review is in progress;
- keep a durable intent record. R2/R3 changes require an Issue or equivalent durable work item; small R1 changes may use a sufficiently complete PR body.

## 5. Risk facets are composable

A project/change may have multiple facets:

- `PRIVATE_DATA`
- `EXTERNAL_WRITE`
- `DESTRUCTIVE_IO`
- `AI_AGENT` — the product/runtime grants an agent observation or mutation authority; merely using AI to write code does not set this facet.
- `SECURITY_BOUNDARY`
- `HIGH_AUTHORITY`
- `PLATFORM_DEPENDENT`
- `CREDENTIALS`
- `DEPLOYMENT`
- `CRYPTOGRAPHY`
- `WORKFLOW_PERMISSION`

Facets are not mutually exclusive.

The project records persistent facets in `PROJECT_PROFILE.toml`. Each PR declares change-specific facets.

## 6. Risk tier and automatic escalation

### R0 — disposable exploration

No persistent adoption, no protected effect, no actual/private data.

### R1 — routine tracked change

Ordinary application code/docs/tests with bounded local impact.

### R2 — boundary-sensitive change

At least one meaningful external/platform/privacy/agent/dependency/workflow boundary is involved, but the change does not directly control a high-impact authorization or destructive effect.

### R3 — high-impact change

A failure could authorize, expose, destroy, irreversibly mutate, deploy, sign, or materially weaken a security boundary.

Automatic minimum escalation:

- `PRIVATE_DATA` -> R2
- `EXTERNAL_WRITE` -> R2
- `AI_AGENT` with mutation capability -> R2
- `PLATFORM_DEPENDENT` where correctness depends on real OS/tool behavior -> R2
- `WORKFLOW_PERMISSION` -> R2
- `DESTRUCTIVE_IO` -> R3
- `CREDENTIALS` -> R3
- `DEPLOYMENT` -> R3
- `SECURITY_BOUNDARY` -> R3
- `HIGH_AUTHORITY` -> R3
- `CRYPTOGRAPHY` used as a security control -> R3

AI may recommend escalation. AI must not silently downgrade below these minima.

## 7. Uncertainty policy

Fail closed when uncertainty concerns:

- authorization;
- security boundary;
- private/actual data exposure;
- destructive mutation;
- deployment/release authority;
- credentials;
- acceptance of an irreversible output.

For informational or non-safety state, preserve uncertainty explicitly (`UNKNOWN`, `UNCERTAIN`, `NOT_APPLICABLE`) rather than blocking the entire project or guessing.

## 8. Evidence invalidation

A new commit does not automatically invalidate every prior fact, and prior evidence is not automatically reusable.

Determine which evidence the change invalidates.

Minimum defaults:

- executable code change -> rerun relevant tests/CI;
- workflow/dependency/toolchain change -> rerun CI and review the supply-chain/permission effect;
- security/authority logic change -> exact-head CI and exact-head independent review;
- test-only change -> check that tests were not weakened to make failures disappear;
- ordinary docs-only change -> lightweight structural check may be sufficient;
- typo-only change -> no heavyweight re-review unless it changes meaning.

R3 uses exact-head evidence by default.

## 9. Review independence

Review is not a boolean.

- `L0` — same agent/self-review;
- `L1` — fresh context/adversarial review;
- `L2` — separate agent/model or independently configured reviewer;
- `L3` — materially different provider/toolchain plus human final judgment.

R1: L1 recommended.  
R2: L1 required; L2 preferred for material boundary changes.  
R3: L2 minimum before human final action.

Repeated prompts to the same reviewer under unchanged evidence do not count as increasing independence.

## 10. Test from requirements, threats, known bugs, and boundaries

Do not let the implementation generate its own definition of success.

Tests should derive from at least the relevant subset of:

- requirements/acceptance criteria;
- threats and abuse cases;
- known bugs/regressions;
- external boundaries;
- invariants.

A material bug found during review should normally receive a regression test unless the test would be misleading or impractical; in that case record why.

## 11. Real-boundary validation

Unit/synthetic tests cannot establish facts owned by a real external boundary.

If correctness materially depends on an OS, SDK, filesystem behavior, external API, deployment target, package manager, document format, device class, or similar boundary, perform a bounded positive and/or negative smoke against that real boundary before making the corresponding claim.

Record the environment/toolchain used. "Works on my machine" is not sufficient without identifying which machine/runtime facts matter.

## 12. Protected effects remain separate

Success at one step does not authorize the next.

At minimum, treat these as separate effects when applicable:

- actual/private source read;
- canonical/private write;
- production deployment/write;
- backup activation;
- destructive cleanup/prune/delete;
- restore/overwrite;
- recurring automation;
- credential handling;
- Ready transition;
- merge;
- release/signing.

A rehearsal or capability proof establishes possibility, not authority.

House policy: **Ready and merge are human-final actions.** Projects may also designate deployment/release as human-final.

## 13. Pre-effect freshness and postconditions

For R3 protected mutations, and R2 where TOCTOU matters:

```text
plan
-> fresh authoritative read
-> precondition validation
-> effect
-> postcondition validation
```

Do not rely solely on evidence gathered earlier in the workflow when target state may have changed.

## 14. Enforcement state must be explicit

Policy text, platform enforcement, and verified enforcement are different facts.

Use these states:

- `DECLARED` — written policy exists;
- `ENFORCED` — a mechanism is configured to enforce it;
- `VERIFIED` — enforcement has been independently observed/tested;
- `UNKNOWN` — enforcement state cannot currently be established.

Never report a policy as enforced merely because the intended setting is documented.

## 15. Documentation has non-overlapping jobs

- `PROJECT_STATUS.md` — what is true now; start with a 30-second summary.
- `CHANGELOG.md` — meaningful semantic changes; not a duplicate commit log.
- ADR — why a durable architecture/governance decision was made.
- Issue/PR — implementation scope, discussion, and change history.

Create an ADR when the decision has durable architectural/governance consequences, especially authority, trust boundaries, component separation, major technology commitment, or security/recovery implications.

Do not create ADRs for ordinary implementation choices.

When a decision changes, supersede history rather than silently rewriting it.

## 16. Human comprehension is a gate

Documentation availability does not prove owner understanding.

The owner should be able to explain, at the level required by the risk tier:

1. what the project/change does;
2. which authority owns the important facts;
3. where important/private data lives;
4. what AI/automation may change;
5. what remains human-decided;
6. major failure modes;
7. first diagnostic location when something breaks;
8. recovery/rollback entry point;
9. major unresolved risks;
10. what changed in the current PR and why.

Comprehension levels:

- `C0 Operate` — normal start/stop/use;
- `C1 Diagnose` — architecture outline, authority, main failures, logs/CI, rollback entry;
- `C2 Govern` — can judge architecture/security/authority tradeoffs and decide whether the change should be accepted.

Minimum persistent-change target:

- R1 -> C1
- R2 -> C1
- R3 -> C2

If the owner cannot meet the required level, stop feature growth and pay down comprehension debt before accepting more complexity.

## 17. Review severity

- `P0` — catastrophic/high-impact: data loss, secret exposure, authority bypass, equivalent;
- `P1` — intended-use correctness/safety defect;
- `P2` — edge case, maintainability, coverage, bounded weakness;
- `P3` — polish/preference/future improvement.

P0/P1 must be fixed, scoped out, or explicitly block acceptance.

P2 may be fixed or deliberately deferred with residual risk recorded.

P3 normally does not block.

## 18. Review stop conditions

Stop adversarial review for a change when all applicable conditions hold:

1. P0 = 0;
2. P1 = 0;
3. acceptance criteria are satisfied;
4. required tests/CI pass on the final relevant revision;
5. R3 has final relevant exact-head independent review at required level;
6. unresolved P2 items are recorded or intentionally accepted;
7. required real-boundary smoke is complete;
8. documentation does not materially contradict implementation;
9. the human has enough evidence to judge residual risk;
10. the required comprehension level is met.

Anti-loop rules:

- If the same safety invariant produces P1 after two remediation attempts, perform an architecture/scope review before a third patch.
- After five material review/fix cycles, perform an architecture/scope reset review before another patch.
- Once the final relevant revision receives a clean required-level adversarial review, do not ask the same reviewer the same question again without new evidence, code, threat, or scope.

## 19. Dependency/action pinning is lifecycle management

Pinning improves reproducibility but can freeze vulnerable versions.

When dependencies/actions are pinned, also record enough version context to update them and define a maintenance path. Pinning without an update mechanism is incomplete supply-chain hygiene.

## 20. Baseline changes

Changes to this baseline itself are governed like architecture changes:

- record rationale;
- review for reduced safeguards and increased ceremony;
- prefer evidence from recent real projects;
- do not accumulate rules solely because one project once needed them;
- remove or demote rules that repeatedly create ceremony without reducing observed risk.
