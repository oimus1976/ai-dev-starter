# ai-dev-starter public-readiness audit — 2026-09-12

Issue: #33

## Terminal state

`BLOCKED`

This is an initial read-only publication audit. It does **not** authorize changing repository visibility.

## Audit target

- Repository: `oimus1976/ai-dev-starter`
- Visibility observed: `private`
- Default branch: `main`
- Main SHA observed at audit start: `794aa1528f0b55fa077364fc4f12397eee5276da`
- Repository role: reusable/template AI-assisted development baseline
- GitHub license metadata: no project license detected (`license: null`)

The implementation branch for Issue #33 was created from the exact main SHA above. Evidence below that refers to repository content is bounded to that state unless explicitly refreshed.

## Evidence already checked

### Current workflow boundary

Current `.github/workflows/policy-check.yml` was inspected at the audit target SHA.

Observed:

- triggers are `pull_request` and `push` to `main`;
- explicit workflow permission is `contents: read`;
- `actions/checkout` uses `persist-credentials: false`;
- no `pull_request_target` trigger is present;
- no secret-bearing step or deployment/write step is present in the current workflow;
- current third-party Actions are pinned by commit SHA.

Assessment: current workflow shape is a good public/fork baseline, but historical workflows and all retained Actions logs still require review before publication.

### GitHub Actions publication surface

GitHub API inventory reported 167 workflow runs at the time of the audit. The latest runs are currently failing because hosted Actions execution is unavailable; this audit does not reinterpret those failures as code evidence.

GitHub documents that Actions history and logs become visible when a private repository is converted to public. Therefore retained historical run logs are a required publication surface, not an optional cleanup task.

Assessment: `BLOCKED` until all retained run logs and any non-expired artifacts are screened for publication-sensitive data.

### Issues / local-path evidence

Issue search found real absolute Windows paths in existing issue discussion, including `C:\Users\oimus\...` topology evidence in Issue #17. This is not a credential finding, but it proves that GitHub-hosted discussion contains environment-specific data outside the Git tree.

Assessment: each such finding must be classified as intentionally public, redacted/removed, or blocking. Current search is not yet a complete Issue/PR/attachment audit.

### Releases

GitHub API returned no releases.

Assessment: no current release assets to audit, subject to refresh immediately before the human publication gate.

### Repository protection

The current private repository returned GitHub API `403` for repository rulesets with the message that GitHub Pro is required or the repository must be public. Existing house policy therefore must not be described as server-enforced on current private `main`.

GitHub documentation states that rulesets/protected branches are available for public repositories on GitHub Free. If publication occurs, protection creation and authoritative readback are mandatory post-publication steps; availability must not be assumed in advance.

### Commit metadata

GitHub commit metadata currently exposes the owner author identity/email to repository readers. That metadata will become public if repository visibility changes.

Assessment: full `git log --all` author/email/message review is still required locally. If historical metadata is unacceptable, any history rewrite is a separate consequential human decision.

## Current blockers

### B1 — Full-history secret scan not yet executed locally

The GitHub-side current-tree screening performed before this Issue did not find obvious GitHub-token/private-key/client-secret/current-user-path patterns in current `main`, but that is not sufficient evidence.

Required close condition:

- run the version-recorded, redacted full-history scan from `docs/PUBLIC_REPOSITORY_READINESS.md` against all refs;
- review all findings without copying secret values into shared records;
- rotate/revoke any real credential before any history decision.

### B2 — Project license decision unresolved

The repository is explicitly designed for reuse, but GitHub currently reports no project license.

Required close condition:

- human owner decides whether the repository is merely source-visible or is intended to grant reusable/open-source rights;
- if OSS reuse is intended, choose and add the project license through a reviewed tracked change;
- review dependency/third-party notices separately.

No license is selected by this audit.

### B3 — Actions logs/artifacts not comprehensively screened

167 Actions runs exist. Current workflow code does not upload artifacts, but historical run/log/artifact state has not yet been exhaustively reviewed.

Required close condition:

- inventory all runs and artifacts;
- scan retained logs without producing a new raw shared archive of possible secret values;
- inspect every non-expired artifact before publication;
- delete/revoke only through separately reviewed actions when needed.

### B4 — GitHub-hosted discussion/attachments audit incomplete

Issue #17 proves environment-specific paths exist in discussion. PR bodies/reviews/comments and attachments have not yet received a complete publication classification.

Required close condition:

- review all Issues/PRs/comments and relevant attachments;
- classify each environment/private-data finding;
- do not claim deletion from the Git tree removes platform-hosted copies.

### B5 — Historical redistribution review incomplete

No obvious third-party binary/vendor payload was identified in the current root inspection, but deleted historical paths and historical copied material are not yet cleared.

Required close condition:

- review `git rev-list --objects --all` inventory and any binary/vendor findings;
- resolve redistribution uncertainty before publication.

## Non-blocking observations

- The repository is already written as a reusable starter rather than a personal-data store.
- Current workflow permissions and checkout behavior are intentionally narrow.
- There are no GitHub Releases at audit time.
- Public visibility would make GitHub Free ruleset/branch-protection features available, subject to post-change authoritative verification.
- Public visibility would also remove private-repository GitHub-hosted Actions minute pressure for standard runners; that benefit is secondary to the publication-safety gate.

## Why PROJECT_STATUS.md is not updated

`PROJECT_STATUS.md` and `PROJECT_PROFILE.toml` in the canonical starter are distributed template inputs containing deliberate `TODO` placeholders for generated/adopted projects. Writing canonical-repository maintenance state into those files would leak starter-maintenance details into every future generated project and change their initialization contract.

For this repository, Issue #33 state is therefore recorded in this audit document plus `CHANGELOG.md`. Generated repositories should continue to replace their own `PROJECT_STATUS.md` / `PROJECT_PROFILE.toml` placeholders as normal.

## Next evidence step

Run the local exact-SHA history/metadata scan in `docs/PUBLIC_REPOSITORY_READINESS.md` against a checkout of `794aa1528f0b55fa077364fc4f12397eee5276da`, retain the redacted logs locally, and update this record only with categories/results rather than secret values.

Until B1–B5 are closed, terminal state remains `BLOCKED`.
