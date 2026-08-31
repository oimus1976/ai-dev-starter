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

A local chat, agent summary, or copied status message is never authoritative merely because it is convenient. A local worktree may temporarily be the only place containing an uncommitted edit, while GitHub may be authoritative for the PR head and Actions for CI results. Authority is determined by the fact being established, not by whichever location is newest overall.

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

Exploration is a lifecycle state, not a persistent risk level.

Once work is intended to persist, it becomes a tracked change.

For tracked changes:

- use an explicit implementation branch;
- do not use direct `main` write as the normal path;
- use a Draft PR while implementation/review is in progress;
- keep a durable intent record. `ELEVATED` and `HIGH_IMPACT` changes require an Issue or equivalent durable work item; small `ROUTINE` changes may use a sufficiently complete PR body.

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

## 6. Risk levels and automatic escalation

Risk level is **not merely a count of how many components a change touches**. It combines the consequence of failure with the sensitivity of the behavior being changed: blast radius, authority, privacy, external mutation, destructive behavior, deployment, credentials, security controls, and real platform dependencies.

Use names rather than numeric `R1/R2/R3` codes so the meaning remains visible at the point of use.

### `ROUTINE` — ordinary bounded tracked change

Ordinary application code/docs/tests with bounded local impact and no reason for stronger verification.

### `ELEVATED` — increased impact or boundary sensitivity

Use when a change has broader operational/correctness impact or involves a meaningful external/platform/privacy/agent/dependency/workflow boundary, while not directly controlling a high-impact authorization or destructive effect.

### `HIGH_IMPACT` — high-impact change

Use when failure could authorize, expose, destroy, irreversibly mutate, deploy, sign, corrupt critical state, cause a comparable critical outage, or materially weaken a security boundary.

Automatic minimum escalation:

- `PRIVATE_DATA` -> `ELEVATED`
- `EXTERNAL_WRITE` -> `ELEVATED`
- `AI_AGENT` with mutation capability -> `ELEVATED`
- `PLATFORM_DEPENDENT` where correctness depends on real OS/tool behavior -> `ELEVATED`
- `WORKFLOW_PERMISSION` -> `ELEVATED`
- `DESTRUCTIVE_IO` -> `HIGH_IMPACT`
- `CREDENTIALS` -> `HIGH_IMPACT`
- `DEPLOYMENT` -> `HIGH_IMPACT`
- `SECURITY_BOUNDARY` -> `HIGH_IMPACT`
- `HIGH_AUTHORITY` -> `HIGH_IMPACT`
- `CRYPTOGRAPHY` used as a security control -> `HIGH_IMPACT`

AI may recommend escalation. AI must not silently downgrade below these minima. A change may also be escalated because its blast radius or failure consequence is larger than its facets alone suggest.

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

`HIGH_IMPACT` uses exact-head evidence by default.

## 9. Review independence

Review is not a boolean.

- `L0` — same agent/self-review;
- `L1` — fresh context/adversarial review;
- `L2` — separate agent/model or independently configured reviewer;
- `L3` — materially different provider/toolchain plus human final judgment.

`ROUTINE`: L1 recommended.  
`ELEVATED`: L1 required; L2 preferred for material boundary changes.  
`HIGH_IMPACT`: L2 minimum before human final action.

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

For `HIGH_IMPACT` protected mutations, and `ELEVATED` changes where TOCTOU matters:

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

The owner should be able to explain, at the level required by the risk level:

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

- `ROUTINE` -> C1
- `ELEVATED` -> C1
- `HIGH_IMPACT` -> C2

If the owner cannot meet the required level, stop feature growth and pay down comprehension debt before accepting more complexity.

## 17. Review finding severity

Use words rather than reverse-numbered `P0/P1/...` labels. The purpose is to make severity understandable without memorizing whether a larger or smaller number is worse.

- `CRITICAL` — catastrophic/high-impact: data loss, secret exposure, authority bypass, equivalent;
- `MAJOR` — intended-use correctness/safety defect;
- `MINOR` — edge case, maintainability, coverage, bounded weakness;
- `NOTE` — polish/preference/future improvement.

`CRITICAL` and `MAJOR` must be fixed, scoped out, or explicitly block acceptance.

`MINOR` may be fixed or deliberately deferred with residual risk recorded.

`NOTE` normally does not block.

## 18. Review stop conditions

Stop adversarial review for a change when all applicable conditions hold:

1. `CRITICAL` findings = 0;
2. `MAJOR` findings = 0;
3. acceptance criteria are satisfied;
4. required tests/CI pass on the final relevant revision;
5. `HIGH_IMPACT` has final relevant exact-head independent review at required level;
6. unresolved `MINOR` findings are recorded or intentionally accepted;
7. required real-boundary smoke is complete;
8. documentation does not materially contradict implementation;
9. the human has enough evidence to judge residual risk;
10. the required comprehension level is met.

Anti-loop rules:

- If the same safety invariant produces a `MAJOR` finding after two remediation attempts, perform an architecture/scope review before a third patch.
- After five material review/fix cycles, perform an architecture/scope reset review before another patch.
- Once the final relevant revision receives a clean required-level adversarial review, do not ask the same reviewer the same question again without new evidence, code, threat, or scope.

## 19. Project CI starts absent, not falsely green

The template ships `policy-check.yml`, but **does not ship an active project-specific CI workflow**.

A generated repository must add `.github/workflows/project-ci.yml` for its actual language/runtime/tests. Until that file exists, policy-check fails.

This avoids two bad states:

- a copied dummy CI that looks like real project validation;
- no signal at all that project CI is still missing.

The canonical template verifier also rejects accidentally adding `project-ci.yml` back into the template, so this absence is an intentional invariant rather than a convention.

`policy-check` can establish that the required workflow file has been deliberately added; it cannot determine whether arbitrary project tests are sufficient. Acceptance still requires evidence from the actual project CI run. A green policy-check alone must not be reported as successful project validation.

## 20. Dependency/action pinning is lifecycle management

Pinning improves reproducibility but can freeze vulnerable versions.

When dependencies/actions are pinned, also record enough version context to update them and define a maintenance path. Pinning without an update mechanism is incomplete supply-chain hygiene.

## 21. Baseline changes

Changes to this baseline itself are governed like architecture changes:

- record rationale;
- review for reduced safeguards and increased ceremony;
- prefer evidence from recent real projects;
- do not accumulate rules solely because one project once needed them;
- remove or demote rules that repeatedly create ceremony without reducing observed risk.

## 22. Post-merge local closeout is a separate gate

Human merge completion establishes the canonical GitHub effect. It does not establish the state of developer worktrees.

When a tracked PR used a local checkout/worktree, treat **post-merge local closeout** as a separate gate. Keep two facts distinct:

1. whether the worktree used for the PR has any unaccounted local residue;
2. whether the canonical checkout that will seed the next tracked task is clean and synchronized.

Common postconditions:

1. GitHub independently confirms that the intended PR was merged;
2. the canonical remote branch is freshly fetched;
3. the worktree used for the PR is clean, including untracked files;
4. no merge, rebase, cherry-pick, revert, or bisect operation is in progress in the worktree being closed out.

If the PR worktree is itself the canonical checkout, it must also be on canonical `main` (unless the project defines another canonical branch) and its `HEAD` must exactly match the freshly observed canonical remote branch (`origin/main` by default).

If the PR used a separate linked topic worktree while canonical `main` remains checked out elsewhere, do **not** require the topic worktree to become `main`. Instead:

1. independently read the merged PR's exact head SHA from GitHub;
2. require the topic worktree `HEAD` to still equal that confirmed PR head, so additional local commits are not silently ignored;
3. require the separately checked-out canonical worktree to be clean, have no Git operation in progress, remain on canonical `main`, and exactly match fresh `origin/main`.

Use `scripts/verify_local_closeout.py` where available. From a linked topic worktree, pass the confirmed head as `--expected-pr-head <FULL_PR_HEAD_SHA>`. A successful linked-worktree closeout means the task worktree has no unaccounted local residue **and** the canonical worktree is ready as the next-work entry point. It does not mean the topic worktree itself is ready for the next task.

Topic branch/worktree deletion is not required merely because a PR merged. The verifier may perform `git fetch` to establish freshness, but it must not reset, stash, discard files, delete branches/worktrees, or perform other destructive cleanup merely to make the gate pass.

If local closeout fails, preserve intentional local work first. Report the unresolved local state and remediate it explicitly; do not convert a failed closeout check into permission for destructive cleanup.

A task may be **merged but locally not closed out**. Keep those facts distinct in completion summaries.
