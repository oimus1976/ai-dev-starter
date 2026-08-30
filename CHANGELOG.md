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
