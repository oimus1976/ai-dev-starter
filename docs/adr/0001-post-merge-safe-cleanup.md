# ADR-0001 — Authorize post-merge cleanup from exact merged-PR identity

- **Status:** Proposed; accepted only by human merge of PR #13
- **Date recorded:** 2026-09-02; safety boundary amended 2026-09-03 after L2 review
- **Decision owners:** Repository owner (human-final Ready/merge)
- **Related:** Issue #12, PR #13, BASELINE.md §12/§13/§22

## Context

The non-destructive post-merge closeout verifier can establish that a completed task worktree has no unaccounted residue and that canonical `main` is ready for the next task. It intentionally does not retire merged topic worktrees or refs.

Repeated local Codex work leaves merged topic worktrees and branches behind. Manual cleanup is easy to forget, while unconditional cleanup can delete work that no longer corresponds to the merged PR. Squash merges also mean ordinary ancestry alone cannot prove that a topic ref is disposable.

The first implementation used expected-SHA `git update-ref -d` for local topic and stale remote-tracking refs. L2 adversarial review demonstrated two important limits: `update-ref -d` can delete a branch that became checked out in another worktree between occupancy inspection and deletion, and a remote branch can reappear between an `ls-remote` absence check and direct deletion of its local tracking ref. Those races make the original broader cleanup claim too strong.

Cleanup therefore keeps the authority model but narrows the v1 effect model to operations whose critical protection is enforced by Git itself or by an exact remote lease.

## Decision

1. Keep `verify_local_closeout.py` non-destructive. Cleanup is a separate protected effect implemented by `post_merge_cleanup.py`.
2. The cleanup tool obtains fresh PR evidence itself through authenticated GitHub CLI. Operator-supplied merge state or SHA alone is not cleanup authority.
3. v1 supports only same-repository merged PRs whose base is the configured canonical branch. Fork/cross-repository PRs fail closed.
4. The target cleanup identity is the PR's exact head branch plus exact head SHA. Local/remote refs that drift from that SHA are not cleanup targets.
5. Default invocation is plan-only. `--execute` reacquires GitHub and mutable Git state before effects rather than trusting an earlier plan.
6. Linked topic worktrees are removed only through normal `git worktree remove`; needing `--force` blocks cleanup. Single-checkout cleanup may switch a strictly clean exact-head topic checkout to canonical and fast-forward canonical only to the freshly fetched canonical ref.
7. Worktree registry reads used for authorization are parsed from one successful `git worktree list --porcelain` result. A read failure is an explicit failure, never an empty-registry interpretation.
8. Local topic branch auto-deletion is narrower than originally proposed. It is attempted only when the exact PR head is already an ancestor of the fresh canonical branch, and deletion uses `git branch -d` so Git itself refuses deletion of a branch currently checked out in any registered worktree. Squash/rebase-style local topic refs whose PR head is not in canonical ancestry are retained for manual/future cleanup rather than deleted with raw ref CAS or force.
9. v1 does not directly delete stale remote-tracking refs. If the remote branch is already absent, an existing exact tracking ref is retained. This avoids treating a concurrently recreated live remote branch as stale. Broad prune remains out of scope.
10. Remote topic deletion is a stronger optional effect and remains off by default. If requested, the current remote ref must still equal the expected PR head and deletion uses an explicit expected-SHA lease.
11. Broad prune, reset, stash, content discard, `git clean`, `git branch -D`, forced worktree removal, raw local branch deletion, and unconditional ref deletion are not cleanup recovery mechanisms.
12. Pre-effect uncertainty is reported as `SAFE CLEANUP: BLOCKED`. If an earlier authorized effect has already completed or a destructive command has begun and a later effect/postcondition fails, report `SAFE CLEANUP: INCOMPLETE` rather than claiming that no mutation occurred.
13. Canonical branch/worktree and unrelated worktrees/refs are outside cleanup scope. v1 only claims non-use within the same Git repository/worktree registry; it does not claim knowledge of other clones or machines.

## Alternatives considered

### Extend the existing verifier to delete residue

Rejected because it mixes observation with a destructive effect and makes a diagnostic command unsafe to run casually.

### Keep expected-SHA `update-ref -d` for local topic branches

Rejected after L2 review. Expected-SHA CAS protects ref identity but does not atomically protect worktree occupancy; Git allows `update-ref -d` to remove a branch that is checked out in another worktree.

### Use `git branch -D` for squash/rebase-style topic refs

Rejected because it bypasses Git's merged-content protection and would broaden the destructive effect merely to achieve branch hygiene.

### Add compensation/restore logic around raw ref deletion

Deferred. A delete-then-restore scheme still permits a window in which a newly occupied worktree has a broken symbolic HEAD and adds recovery complexity to a v1 whose purpose is routine safe closeout.

### Run `git fetch --prune` for stale tracking refs

Rejected for v1 because it can change refs unrelated to the target PR.

### Directly CAS-delete an exact stale tracking ref after observing the remote absent

Rejected after L2 review because the remote branch can be recreated between the absence read and local tracking-ref deletion. Remote data would remain, but the helper could still delete a tracking ref that is no longer semantically stale and incorrectly report success.

### Automatically delete remote branches

Rejected as the default because remote write has a larger blast radius than local closeout and GitHub may already remove the branch after merge.

## Consequences

### Positive

- Routine merged Codex worktree residue can be retired without weakening local-work preservation.
- Normal merge topic branches can be retired through Git's own checked-out-branch protection rather than raw ref deletion.
- Squash/rebase-style merged PRs are still supported for worktree retirement and canonical next-task readiness, while their local topic branch is retained when v1 cannot prove a deletion primitive with the desired safety property.
- A reused/drifted branch fails closed instead of being mistaken for old residue.
- Remote-tracking refs are not mutated based on a non-atomic remote absence observation.
- The verifier remains safe as a read/fetch-oriented diagnostic tool.

### Negative / tradeoffs

- `gh` authentication remains a runtime dependency for cleanup authorization.
- v1 does not fully solve local branch clutter for squash/rebase-style PRs; those local topic refs are retained deliberately.
- v1 does not prune an already-stale target remote-tracking ref.
- v1 does not clean fork/cross-repository PRs or residue across other clones/machines.
- Multi-effect cleanup cannot be atomic across worktree, local branch, and optional remote branch; partial success is therefore an explicit `INCOMPLETE` state.
- A future design that wants automatic squash-branch retirement needs a stronger repository-quiescence/locking or another deletion primitive that protects both exact identity and worktree occupancy without force.

## Authority / security / recovery effects

GitHub owns the merged PR state and exact PR head identity used to authorize a target. Local Git owns current worktree/ref occupancy and cleanliness. Git's normal `branch -d` command, not a prior occupancy snapshot, owns the final checked-out-branch refusal on the auto-delete path. The remote Git ref is re-read and protected by an exact lease when remote deletion is requested.

The change adds bounded destructive local authority and optional remote write authority. It does not change the house rule that Ready and merge are human-final.

There is no force-recovery path whose purpose is to make cleanup pass. `BLOCKED` preserves state. `INCOMPLETE` requires inspection of the reported post-state before another attempt.

## Evidence / validation required

Before recommending human Ready for the implementing PR:

- synthetic regressions derived from requirements/threats, including merge-commit and squash-like paths, unmerged/closed-unmerged, dirty/untracked/Git-operation states, head/ref drift, single and linked layouts, worktree-registry read failure, worktree reoccupation before branch deletion, stale tracking retention, remote lease behavior, remote reappearance, revalidation, and unrelated-work preservation;
- exact-head CI on Linux, Windows, and macOS;
- independent exact-head review at the level required for a `HIGH_IMPACT` destructive-I/O change;
- bounded Windows real-machine qualification on the final exact head;
- after human merge, first real-project adoption in `wacaf-room-watcher` before wider rollout.

The Windows qualification recorded for pre-remediation HEAD `a55d30d1b9e88858443b8d5d963adbdd08de4eb6` is historical evidence only; remediation changes require a final exact-head rerun before Ready.

## Supersession

If the authority model, supported repository topology, local squash-branch retirement policy, or remote-write policy changes materially, add/supersede this ADR rather than silently broadening cleanup behavior.
