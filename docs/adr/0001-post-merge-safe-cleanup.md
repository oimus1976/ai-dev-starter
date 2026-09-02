# ADR-0001 — Authorize post-merge cleanup from exact merged-PR identity

- **Status:** Proposed; accepted only by human merge of PR #13
- **Date recorded:** 2026-09-02
- **Decision owners:** Repository owner (human-final Ready/merge)
- **Related:** Issue #12, PR #13, BASELINE.md §12/§13/§22

## Context

The non-destructive post-merge closeout verifier can establish that a completed task worktree has no unaccounted residue and that canonical `main` is ready for the next task. It intentionally does not retire merged topic worktrees or refs.

Repeated local Codex work leaves merged topic worktrees and branches behind. Manual cleanup is easy to forget, while unconditional cleanup can delete work that no longer corresponds to the merged PR. Squash merges also mean ordinary ancestor-based `git branch -d` is not a sufficient authorization rule.

Cleanup therefore needs an authority model that is narrower than "the branch looks merged" and an effect model that does not weaken the existing verifier.

## Decision

1. Keep `verify_local_closeout.py` non-destructive. Cleanup is a separate protected effect implemented by `post_merge_cleanup.py`.
2. The cleanup tool obtains fresh PR evidence itself through authenticated GitHub CLI. Operator-supplied merge state or SHA alone is not cleanup authority.
3. v1 supports only same-repository merged PRs whose base is the configured canonical branch. Fork/cross-repository PRs fail closed.
4. The target cleanup identity is the PR's exact head branch plus exact head SHA. Local/remote refs that drift from that SHA are not deleted.
5. Default invocation is plan-only. `--execute` reacquires GitHub and mutable Git state before effects rather than trusting an earlier plan.
6. Linked topic worktrees are removed only through normal `git worktree remove`; needing `--force` blocks cleanup.
7. Local topic and target stale remote-tracking refs are deleted only through expected-SHA compare-and-swap (`git update-ref -d <ref> <expected>`). This permits safe cleanup after squash merges without unconditional force deletion.
8. Remote topic deletion is a stronger optional effect and remains off by default. If requested, the current remote ref must still equal the expected PR head and deletion uses an explicit expected-SHA lease.
9. Broad prune, reset, stash, content discard, `git clean`, `git branch -D`, forced worktree removal, and unconditional ref deletion are not cleanup recovery mechanisms.
10. Pre-effect uncertainty is reported as `SAFE CLEANUP: BLOCKED`. If an earlier authorized effect has already completed and a later effect/postcondition fails, report `SAFE CLEANUP: INCOMPLETE` rather than claiming that no mutation occurred.
11. Canonical branch/worktree and unrelated worktrees/refs are outside cleanup scope. v1 only claims non-use within the same Git repository/worktree registry; it does not claim knowledge of other clones or machines.

## Alternatives considered

### Extend the existing verifier to delete residue

Rejected because it mixes observation with a destructive effect and makes a diagnostic command unsafe to run casually.

### Use `git branch -d` as the sole deletion rule

Rejected because a correctly merged squash PR leaves its topic head outside canonical ancestry.

### Use `git branch -D` or unconditional `update-ref -d`

Rejected because branch identity could have moved or been reused after the PR merged.

### Run `git fetch --prune` for stale tracking refs

Rejected for v1 because it changes refs unrelated to the target PR.

### Automatically delete remote branches

Rejected as the default because remote write has a larger blast radius than local closeout and GitHub may already remove the branch after merge.

## Consequences

### Positive

- Routine merged Codex residue can be retired without weakening local-work preservation.
- Squash merge is handled using exact identity rather than ancestry heuristics.
- A reused/drifted branch fails closed instead of being mistaken for old residue.
- The verifier remains safe as a read/fetch-oriented diagnostic tool.
- The planner can be integrated into later orchestration without granting broad prune/delete authority.

### Negative / tradeoffs

- `gh` authentication becomes a runtime dependency for cleanup authorization.
- v1 does not clean fork/cross-repository PRs or residue across other clones/machines.
- Multi-effect cleanup cannot be atomic across worktree, local refs, and remote refs; partial success is therefore an explicit `INCOMPLETE` state.
- Conservative remote-ref drift checks can block local cleanup when a branch name has been reused; this is intentional and requires human resolution.

## Authority / security / recovery effects

GitHub owns the merged PR state and exact PR head identity used to authorize a target. Local Git owns current worktree/ref occupancy and cleanliness. The remote Git ref is re-read separately when remote deletion is requested.

The change adds bounded destructive local authority and optional remote write authority. It does not change the house rule that Ready and merge are human-final.

There is no force-recovery path whose purpose is to make cleanup pass. `BLOCKED` preserves state. `INCOMPLETE` requires inspection of the reported post-state before another attempt.

## Evidence / validation required

Before recommending human Ready for the implementing PR:

- synthetic regressions derived from requirements/threats, including merge-commit and squash-merge paths, unmerged/closed-unmerged, dirty/untracked/Git-operation states, head/ref drift, single and linked layouts, target-only stale tracking cleanup, remote lease behavior, revalidation, and unrelated-work preservation;
- exact-head CI on Linux, Windows, and macOS;
- independent review at the level required for a `HIGH_IMPACT` destructive-I/O change;
- bounded Windows real-machine qualification;
- after human merge, first real-project adoption in `wacaf-room-watcher` before wider rollout.

## Supersession

If the authority model, supported repository topology, or remote-write policy changes materially, add/supersede this ADR rather than silently broadening cleanup behavior.
