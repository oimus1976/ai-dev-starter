# Changelog

Record meaningful semantic changes. This is not a duplicate commit log.

For each entry, prefer:

- what goal or behavior changed;
- why it changed;
- what safety/authority boundary changed or stayed the same;
- the related Issue/PR/ADR;
- validation status when material.

Do not copy long implementation chronology that already exists in Git/PR history.

## Unreleased

### Baseline

- Initial project scaffold from oimus AI Development Starter v0.5.
- Hardened the template policy workflow after the first real template-generation smoke: checkout credentials are no longer persisted, PR policy checks validate the actual proposed head instead of GitHub's synthetic merge commit, generated-repo setup failures now give state-aware next steps, and observed GitHub branch-protection/ruleset limits are recorded. See Issue #3.
- Separated starter regressions into `starter_tests/` after the first `wacaf-room-watcher` adoption exposed a namespace collision with generated-project tests. Generated projects can now use `tests/` without discovering canonical-template regression assumptions; baseline policy and regression coverage are unchanged. See Issue #5.
- Added a distinct post-merge local closeout gate after the first real Starter project exposed that GitHub merge state does not establish local checkout readiness. A non-destructive verifier now refreshes the canonical remote and requires canonical branch + clean worktree + no in-progress Git operation + exact local/remote HEAD match before local closeout is claimed. Destructive cleanup remains a separate decision. See Issue #8.
- Corrected the closeout gate after the first horizontal rollout exposed a common linked-worktree blind spot: a PR may run in a topic worktree while canonical `main` remains checked out elsewhere. Topic-worktree closeout now verifies the exact GitHub-confirmed PR head and the task worktree's cleanliness while separately proving the canonical worktree is clean and synchronized; topic worktrees need not be forced onto `main` or deleted. See Issue #10.
- Added fail-closed post-merge safe cleanup as a separate protected effect after verification. The cleanup planner performs its own authenticated GitHub PR read, defaults to dry-run, revalidates before `--execute`, uses normal worktree removal and exact-lease optional remote deletion, supports linked and single-checkout layouts, leaves remote deletion off by default, and distinguishes pre-effect `BLOCKED` from post-effect `INCOMPLETE`. L2 adversarial review successively exposed non-atomic local-ref deletion and remote-tracking cleanup races, so v1 was deliberately narrowed: local topic branches are never auto-deleted, stale remote-tracking refs are retained, and unreadable/malformed ref snapshots fail closed rather than becoming empty sets. The existing verifier remains non-destructive. See Issue #12 and ADR-0001.
- Corrected the first real post-merge qualification defect where the documented cleanup command generated `scripts/__pycache__/` while importing its sibling helper and then blocked on its own ignored residue. The cleanup entry point now disables bytecode writes before local imports; pre-existing ignored files remain blocking and no cleanup authority is broadened. See Issue #14.
- Added authoritative repository-wide branch **audit** after a real `life-dashboard` cleanup exposed partial prior deletion, misleading native stderr rendering, stale deletion assumptions, closed-unmerged branches requiring successor review, and a no-PR long-lived branch that had to be retained. Independent review of the first executor design exposed unresolved host-binding, branch-incarnation, push-destination, TOCTOU, and post-effect-state gaps; per the anti-loop rule the destructive path was removed rather than patched again. The helper now pins authenticated reads to `github.com`, emits inventory plus human-review evidence, and has no remote mutation capability. A separately authorized destructive executor, if still needed, is isolated to Issue #22. Existing one-PR local closeout/worktree cleanup authority remains unchanged. See Issue #20 and PR #21.
