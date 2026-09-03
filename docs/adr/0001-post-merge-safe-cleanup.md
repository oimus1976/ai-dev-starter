# ADR-0001 — Authorize post-merge cleanup from exact merged-PR identity

- **Status:** Proposed; accepted only by human merge of PR #13
- **Date recorded:** 2026-09-02; safety boundary amended 2026-09-03 after L2 review
- **Decision owners:** Repository owner (human-final Ready/merge)
- **Related:** Issue #12, PR #13, BASELINE.md §12/§13/§22

## Context

The non-destructive post-merge closeout verifier can establish that a completed task worktree has no unaccounted residue and that canonical `main` is ready for the next task. It intentionally does not retire merged topic worktrees or refs.

Repeated local Codex work leaves merged topic worktrees and branches behind. Manual cleanup is easy to forget, while unconditional cleanup can delete work that no longer corresponds to the merged PR.

The first implementation used expected-SHA `git update-ref -d` for local topic and stale remote-tracking refs. L2 adversarial review demonstrated that expected-SHA CAS protects ref identity but not worktree occupancy atomically. A second design used normal `git branch -d` only when the PR head was already in canonical history, but a later L2 review demonstrated another race: the topic ref can move after the exact-head check and before `branch -d`, allowing a different canonical-contained ref value to be deleted. Therefore v1 no longer performs automatic local topic-branch deletion at all.

The same review also found that ref postcondition snapshots treated `git for-each-ref` failure as an empty set, which could convert unverifiable post-state into a false PASS. Ref snapshots are now explicit success/error evidence.

Cleanup therefore keeps the merged-PR authority model but narrows v1 destructive local authority to worktree retirement and single-checkout return-to-canonical. Local topic refs and remote-tracking refs are retained. Optional remote topic deletion remains separately protected by an exact remote lease.

## Decision

1. Keep `verify_local_closeout.py` non-destructive. Cleanup is a separate protected effect implemented by `post_merge_cleanup.py`.
2. The cleanup tool obtains fresh PR evidence itself through authenticated GitHub CLI. Operator-supplied merge state or SHA alone is not cleanup authority.
3. v1 supports only same-repository merged PRs whose base is the configured canonical branch. Fork/cross-repository PRs fail closed.
4. The target cleanup identity is the PR's exact head branch plus exact head SHA. Identity drift blocks planning/execution.
5. Default invocation is plan-only. `--execute` reacquires GitHub and mutable Git state before effects rather than trusting an earlier plan.
6. Linked topic worktrees are removed only through normal `git worktree remove`; needing `--force` blocks cleanup. Single-checkout cleanup may switch a strictly clean exact-head topic checkout to canonical and fast-forward canonical only to the freshly fetched canonical ref.
7. Worktree registry reads used for authorization are parsed from one successful `git worktree list --porcelain` result. A read failure is an explicit failure, never an empty-registry interpretation.
8. v1 does not automatically delete local topic branches, regardless of merge style or ancestry. A local topic ref that existed at plan time must still equal the exact PR head after cleanup; drift/disappearance makes the result fail rather than treating that mutation as allowed.
9. v1 does not directly delete stale remote-tracking refs. Existing tracking refs are retained rather than pruned from a non-atomic remote-absence observation.
10. Remote topic deletion is a stronger optional effect and remains off by default. If requested, the current remote ref must still equal the expected PR head and deletion uses an explicit expected-SHA lease.
11. Ref snapshots used to prove unrelated/ref-retention postconditions are fail-closed. Planning cannot proceed if the baseline heads/remotes snapshot is unreadable or malformed. If the post-effect snapshot cannot be established, execution is not a PASS; after effects have begun it is `SAFE CLEANUP: INCOMPLETE`.
12. Broad prune, reset, stash, content discard, `git clean`, `git branch -D`, forced worktree removal, raw local-branch `update-ref -d`, and unconditional ref deletion are not cleanup recovery mechanisms.
13. Pre-effect uncertainty is reported as `SAFE CLEANUP: BLOCKED`. If an earlier authorized effect has already completed or a destructive command has begun and a later effect/postcondition fails, report `SAFE CLEANUP: INCOMPLETE` rather than claiming that no mutation occurred.
14. Canonical branch/worktree and unrelated worktrees/refs are outside cleanup scope. v1 only claims non-use within the same Git repository/worktree registry; it does not claim knowledge of other clones or machines.

## Alternatives considered

### Extend the existing verifier to delete residue

Rejected because it mixes observation with a destructive effect and makes a diagnostic command unsafe to run casually.

### Keep expected-SHA `update-ref -d` for local topic branches

Rejected after L2 review. Expected-SHA CAS protects ref identity but does not atomically protect worktree occupancy; Git permits a raw ref deletion independently of the worktree's symbolic HEAD.

### Use normal `git branch -d` after exact-head and ancestry checks

Rejected for v1 after a second L2 review. The exact-head check and `branch -d` are separate operations; a concurrent ref update can replace the branch with another canonical-contained commit before deletion. Git's merged/occupancy checks do not preserve the earlier exact PR identity atomically.

### Add repository-wide locking or compensation around local branch deletion

Deferred. A correct design would need to protect both exact ref identity and worktree occupancy across the effect. That is more complex than the v1 goal of routine worktree closeout and should be a separate design issue.

### Run `git fetch --prune` for stale tracking refs

Rejected for v1 because it can change refs unrelated to the target PR.

### Directly CAS-delete an exact stale tracking ref after observing the remote absent

Rejected after L2 review because the remote branch can be recreated between the absence read and local tracking-ref deletion.

### Automatically delete remote branches

Rejected as the default because remote write has a larger blast radius than local closeout and GitHub may already remove the branch after merge.

## Consequences

### Positive

- Routine merged Codex worktree residue can be retired without granting automatic local branch-deletion authority.
- Linked and single-checkout layouts still converge on a canonical next-task entry point.
- Both normal-merge and squash/rebase-style PRs use the same simple local-ref policy: retain the local topic branch in v1.
- Remote-tracking refs are not mutated based on a non-atomic remote absence observation.
- Ref-snapshot uncertainty cannot be mistaken for an empty ref set or successful postcondition.
- The verifier remains safe as a read/fetch-oriented diagnostic tool.

### Negative / tradeoffs

- `gh` authentication remains a runtime dependency for cleanup authorization.
- v1 deliberately leaves local topic branches behind; branch-list hygiene is not fully automated.
- v1 does not prune an already-stale target remote-tracking ref.
- v1 does not clean fork/cross-repository PRs or residue across other clones/machines.
- Multi-effect cleanup cannot be atomic across worktree/switch state and optional remote deletion; partial success is therefore an explicit `INCOMPLETE` state.
- Automatic local branch retirement is deferred until a design can atomically protect both exact PR identity and worktree occupancy.

## Authority / security / recovery effects

GitHub owns the merged PR state and exact PR head identity used to authorize a target. Local Git owns current worktree/ref occupancy and cleanliness. Local topic refs remain outside v1's destructive authority. The remote Git ref is re-read and protected by an exact lease when remote deletion is explicitly requested.

The change adds bounded destructive local worktree authority and optional remote write authority. It does not change the house rule that Ready and merge are human-final.

There is no force-recovery path whose purpose is to make cleanup pass. `BLOCKED` preserves state. `INCOMPLETE` requires inspection of the reported post-state before another attempt.

## Evidence / validation required

Before recommending human Ready for the implementing PR:

- synthetic regressions derived from requirements/threats, including merge-commit and squash-like paths, unmerged/closed-unmerged, dirty/untracked/Git-operation states, head/ref drift, single and linked layouts, worktree-registry read failure, retained-local-ref drift, stale tracking retention, remote lease behavior, remote reappearance, baseline ref-snapshot failure, post-effect ref-snapshot failure, revalidation, self-removing invocation, and unrelated-work preservation;
- exact-head CI on Linux, Windows, and macOS;
- independent exact-head review at the level required for a `HIGH_IMPACT` destructive-I/O change;
- bounded Windows real-machine qualification on the final exact head;
- after human merge, first real-project adoption in `wacaf-room-watcher` before wider rollout.

Evidence from any earlier HEAD is historical only after remediation changes the exact head.

## Supersession

If the authority model, supported repository topology, local branch-retirement policy, or remote-write policy changes materially, add/supersede this ADR rather than silently broadening cleanup behavior.
