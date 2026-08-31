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

When a tracked PR used a local checkout/worktree, do not report the work item as locally closed out and do not start the next tracked implementation in that checkout until all of the following are established:

1. GitHub independently confirms the PR was merged;
2. remote-tracking refs are refreshed;
3. the checkout is on canonical `main` unless the project explicitly names another canonical branch;
4. the working tree, including untracked files, is clean;
5. no merge/rebase/cherry-pick/revert/bisect operation is in progress;
6. local `HEAD` exactly matches fresh `origin/main` (or the project-specific canonical remote/branch).

Run `python scripts/verify_local_closeout.py` for the local-state checks. The verifier may `git fetch` to establish freshness, but it must not reset, stash, discard files, delete branches/worktrees, or perform other destructive cleanup merely to make the gate pass.

If the gate fails, preserve intentional local work first and report the unresolved local state instead of claiming closeout. Topic-branch/worktree deletion is a separate cleanup decision and is not required merely to prove that the canonical checkout is ready for the next task.
