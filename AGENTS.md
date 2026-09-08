# Agent Instructions

This repository uses the oimus AI Development Baseline.

## Before editing

1. Read `PROJECT_STATUS.md`, `PROJECT_PROFILE.toml`, and relevant ADR/design docs.
2. Identify the intended work item/PR and target branch.
3. State the change-specific risk facets and derived risk level: `ROUTINE`, `ELEVATED`, or `HIGH_IMPACT`.
4. Escalate automatically when the change touches credentials, deployment, destructive I/O, security/authority logic, private data, external writes, workflow permissions, or real platform behavior.
5. If you cannot establish the target repository/branch/work item, stop before writing.

## Editing rules

- Never treat chat history as authoritative project state when repository evidence is available.
- Do not write to a branch that was not explicitly resolved for the task.
- Do not use `main` as the normal implementation branch.
- Keep changes within the declared scope.
- Preserve unrelated files and existing history.
- Do not weaken tests merely to make CI pass.
- Do not expose secrets, credentials, private data, or owner-local artifacts in code, logs, Issues, PRs, or summaries.
- Treat unsupported/uncertain safety conditions conservatively according to `BASELINE.md`.

## Claims and evidence

Your completion statement is a claim, not authority.

Report evidence separately, including as applicable:

- branch and exact HEAD;
- changed paths;
- test command and result;
- CI status if independently available;
- real-boundary smoke environment/result;
- residual uncertainty.

Do not claim Ready, merge, deploy, release, or another protected effect merely because implementation/tests/review succeeded.

## After review findings

A remediation creates a new change that may invalidate prior evidence.

Re-run the evidence required by the change type/risk level. `HIGH_IMPACT` security/authority changes require exact-head revalidation and independent review.

If the same `MAJOR` safety invariant survives two remediation attempts, stop patching and request an architecture/scope review.

## Human comprehension

Do not optimize only for passing tests.

At meaningful handoff points explain concisely:

- what changed;
- why;
- what did not change;
- what evidence supports it;
- what remains uncertain/deferred;
- what the human must decide next;
- how the change affects authority, failure/recovery, or operational understanding.

If the project owner cannot reasonably explain the required C1/C2 concepts after the change, prefer simplification/documentation over more feature work.

## Human-final house policy

Ready and merge are human-final. Do not perform or infer them from another approval.

## Post-merge local closeout

Human merge completion and local closeout are separate facts.

When a tracked PR used a local checkout/worktree, do not report the work item as locally closed out until GitHub independently confirms the merge and the applicable local closeout path passes.

### Non-destructive verification

`scripts/verify_local_closeout.py` remains the non-destructive diagnostic/verifier.

If the PR checkout itself is the canonical checkout used for the next task, run:

`python scripts/verify_local_closeout.py`

The verifier requires fresh canonical remote state, canonical `main` (unless project-specific override), a clean tracked+untracked worktree, no merge/rebase/cherry-pick/revert/bisect in progress, and exact local/canonical-remote HEAD match.

If the PR used a linked topic worktree while canonical `main` remains checked out in another worktree:

1. independently read the merged PR's exact head SHA from GitHub;
2. in the topic worktree run `python scripts/verify_local_closeout.py --expected-pr-head <FULL_PR_HEAD_SHA>`;
3. require the topic worktree to be clean, have no Git operation in progress, and still be at that confirmed PR head;
4. require the separately checked-out canonical worktree to be clean and exactly synchronized to fresh `origin/main`.

A successful topic-worktree verification means the task worktree has no unaccounted local residue and the canonical worktree is the next-work entry point. It does **not** mean the topic worktree itself became `main`.

The verifier may `git fetch` to establish freshness, but it must not reset, stash, discard files, delete branches/worktrees, or perform other destructive cleanup merely to make the gate pass.

### Fail-closed safe cleanup

When the merged task's closeout procedure includes retirement of its topic worktree, use the separate cleanup tool. The normal first command is plan-only:

`python scripts/post_merge_cleanup.py --pr <PR_NUMBER>`

The cleanup tool must perform its own fresh GitHub PR read through authenticated `gh`; operator-supplied merge claims are not sufficient. Its cleanup identity is the same-repository merged PR's exact head branch and head SHA.

Only an eligible plan may proceed to:

`python scripts/post_merge_cleanup.py --pr <PR_NUMBER> --execute`

Local execution is limited to the exact merged PR worktree/switch state. It may normally remove an eligible linked topic worktree and safely return a single clean topic checkout to canonical `main`. **v1 never auto-deletes the local topic branch**, regardless of merge style or ancestry. The local topic ref is retained and must remain at the exact PR head if it existed at plan time. v1 also retains remote-tracking refs rather than deleting them from a non-atomic remote-absence observation.

The helper must not use reset, stash, content discard, `git clean`, forced worktree removal, `git branch -D`, raw local-branch `update-ref -d`, normal `git branch -d` for automatic topic retirement, unconditional ref deletion, or broad prune to make cleanup succeed.

Before a worktree-changing cleanup effect, v1 also fails closed on local state that ordinary `git status` can hide or classify as disposable: ignored files/directories, `assume-unchanged` or `skip-worktree` index flags, and submodule gitlinks. Resolve or deliberately preserve those states outside the cleanup helper rather than teaching the helper to guess which local data is expendable.

Remote topic deletion is a stronger optional effect and is off by default. Use `--delete-remote` only when that remote write is explicitly part of the closeout procedure; the tool must re-check the remote ref and use an exact expected-SHA lease.

`--execute` re-reads authority and mutable Git state rather than trusting a prior plan. Worktree-registry authorization and local-ref postconditions must come from successful reads; read failure is never equivalent to an empty registry/ref set. A pre-effect failure is `SAFE CLEANUP: BLOCKED` and performs no cleanup. A failure after an authorized effect has already completed or an effect command has begun is `SAFE CLEANUP: INCOMPLETE`; report the partial/ambiguous state and stop rather than attempting force recovery.

If either verifier or cleanup blocks, preserve intentional local work and report the unresolved state. Canonical branch/worktree and unrelated worktrees/refs are never cleanup targets.

## Repository-wide branch audit

Repository-wide branch audit is separate from one-PR local closeout. Use current authenticated `github.com` branch existence, SHA, protection, default-branch state, and same-repository PR evidence as the authority; do not infer remote existence from chat history, stale `origin/*` refs, or prior cleanup output.

Use `scripts/branch_cleanup_audit.py --repository OWNER/REPO` and follow `docs/branch-cleanup-policy.md`.

The helper is **audit-only**. It must not push, delete refs, or expose `--execute`, `--delete-merged`, or `--delete-reviewed`. It writes `inventory.json` plus `review-candidates.json`; review-candidate entries are evidence only and explicitly carry `deletion_authority: false`.

Exact current name+SHA correlation with a same-repository merged PR is classified `MERGED_REVIEW_CANDIDATE`, not automatic deletion authority. GitHub does not provide a stable branch-incarnation identity that proves a deleted/recreated ref at the same name+SHA is the historical merged branch.

Closed-unmerged and no-PR branches require individual human review. Open-PR, protected/default, and explicitly retained long-lived branches are not review-deletion candidates. Fork PRs do not supply same-repository branch authority.

For native `gh` commands, exit status is authoritative for command success. stderr is diagnostic output only and may contain normal success/progress text. GitHub CLI output is decoded as UTF-8 rather than through a Windows legacy console code page.

Any repository-wide destructive executor is outside this helper's authority and must be designed separately. Issue #22 tracks that work. Do not infer permission to delete from `MERGED_REVIEW_CANDIDATE`, `review-candidates.json`, or a successful audit run.
