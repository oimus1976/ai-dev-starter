# ai-dev-starter public-readiness audit — 2026-09-12

Issue: #33

## Terminal state

`BLOCKED — final exact-head refresh pending`

All repository-specific publication blockers B1–B5 are cleared for their defined audit scopes. This document still does **not** authorize changing repository visibility. Before a human Ready or visibility decision, the audit must be refreshed against the exact PR head / intended publication SHA because the Issue #33 branch moved while recording the MIT license decision and final audit state.

## Audit target

- Repository: `oimus1976/ai-dev-starter`
- Visibility observed: `private`
- Default branch: `main`
- Main SHA observed at audit start: `794aa1528f0b55fa077364fc4f12397eee5276da`
- Repository role: reusable/template AI-assisted development baseline
- GitHub license metadata at audit start: no project license detected (`license: null`)
- Human license decision: MIT License
- Root `LICENSE`: added on the Issue #33 branch with `Copyright (c) 2026 Sumio Nishioka`

The implementation branch for Issue #33 was created from the exact main SHA above. Publication must be re-checked against the exact intended publication SHA immediately before the human visibility gate.

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

Assessment: current workflow shape is a good public/fork baseline.

### Full-history secret scan — B1 cleared for scanner scope

An isolated audit clone was created under `%TEMP%` from `oimus1976/ai-dev-starter`, and GitHub `refs/pull/*/head` were fetched into audit-only refs before scanning.

Observed:

- initial `AUDIT_HEAD=794aa1528f0b55fa077364fc4f12397eee5276da`
- Gitleaks version: `8.30.1`
- scan mode: `gitleaks git`
- log opts: `--all --full-history`
- redaction: `--redact=100`
- result: `GITLEAKS_HISTORY=PASS`
- exit code: `0`

Assessment: B1 is cleared for the Gitleaks scanner/ruleset scope against current refs plus fetched PR-head refs as of the completed scan. The generated JSON report remains local and was not uploaded or pasted into shared discussion. A final exact-head refresh is still required after all Issue #33 branch changes are complete.

### Git metadata / object-name inventory

The same isolated audit clone was used to inventory Git metadata and historical object names.

Observed:

- commit records inspected: 211;
- unique author identities: 3;
- unique historical paths: 56;
- filename-pattern hits for credentials/secrets/high-risk binaries: 0;
- authors: `google-labs-jules[bot]`, `oimus1976`, and `Sumio Nishioka`;
- the bot uses a GitHub noreply address;
- owner-authored commits use `oimus1976@gmail.com`.

Human owner decision: historical `oimus1976@gmail.com` author metadata is **accepted for public disclosure** for this repository. No history rewrite is required or authorized on account of that address.

### Historical redistribution/provenance indicator pass — B5 cleared for audit scope

After refreshing fetched PR-head refs, all reachable commits were scanned for copyright, license, third-party, vendoring, and redistribution indicators.

Observed:

- reachable commits scanned: 213;
- unique matched paths: 3;
- matched paths: `CHANGELOG.md`, `docs/audits/ai-dev-starter-public-readiness-2026-09-12.md`, and `docs/PUBLIC_REPOSITORY_READINESS.md`;
- all matches were Issue #33 public-readiness/audit wording introduced by this work;
- no historical source/test/config/vendor path surfaced from the indicator pattern;
- current `main` tree contains no obvious vendored binary/media/font/model/data bundle or third-party asset directory;
- GitHub currently has no Releases for this repository.

Assessment: B5 is cleared for the defined repository-publication provenance/redistribution screening scope. The subsequently added MIT `LICENSE` is intentional first-party licensing metadata, not an unresolved third-party provenance finding. This is not a general legal opinion.

### GitHub Actions publication surface — B3 cleared for retained surface

The retained GitHub Actions surface was inventoried and screened without creating a combined raw-log archive.

Observed:

- workflow runs currently retained at the completed inventory: 174;
- retained artifacts: 0;
- logs available and scanned: 153 runs;
- Gitleaks stdin findings across those 153 logs: 0;
- runs with no retained log: 21;
- partial-log runs: 0;
- Gitleaks/tool errors: 0;
- API classification errors: 0.

The 21 no-log runs were individually checked through the workflow-jobs API. Every run had three jobs and **zero executed steps**. Their job conclusions are `failure`, but there is no executed-step log surface to review. This is consistent with the known GitHub-hosted Actions availability/quota condition and is not treated as code/test evidence.

Assessment: B3 is cleared for the retained Actions publication surface observed during the audit. Final publication refresh must confirm no new retained artifact or relevant executed log has appeared since that inventory.

### Issues / PR discussion evidence — B4 cleared for audited surface

The GitHub-hosted discussion surface was inventoried without creating a raw combined text archive.

Observed:

- total text items screened: 89;
- Issue bodies: 18;
- PR bodies: 16;
- conversation comments: 47;
- inline review comments: 0;
- review bodies: 8;
- Gitleaks finding sources: 0;
- attachment sources: 0;
- attachment URLs detected: 0;
- tool errors: 0;
- environment/private-data indicator sources: 7.

The seven indicator sources were manually classified:

- PR #34 contains the already accepted historical owner email `oimus1976@gmail.com`;
- Issue #17 and five GitHub-hosted comments contain Windows developer paths under `C:\Users\oimus\...`, including personal OSS repository/worktree names used for exact-head and Windows real-machine qualification evidence;
- no host name, UNC path, private IP, credential, organization-internal URL, municipal/business-system path, or attachment URL was present in those hits.

Human owner decision: the six Windows developer-path findings are **accepted for public disclosure** for this repository. Their value as reproducible qualification evidence is retained; no redaction/edit is required or authorized on account of those paths.

Assessment: B4 is cleared for the audited GitHub-hosted textual/attachment-reference surface.

### Project licensing — B2 cleared by human decision

The repository is explicitly designed for reuse. The human owner selected the **MIT License** for public OSS reuse, and a standard MIT `LICENSE` file was added at the repository root on the Issue #33 branch.

Assessment: B2 is cleared. The license grants broad reuse, modification, redistribution, sublicensing, and sale rights subject to preservation of the copyright and license notice. This license choice does not itself authorize publication; visibility remains a separate human-final gate.

### Repository protection

The current private repository returned GitHub API `403` for repository rulesets under the current plan/visibility combination. Existing house policy must therefore not be described as server-enforced on current private `main`.

If publication occurs, ruleset/branch-protection creation and authoritative readback are mandatory post-publication steps. Availability must not be assumed before the visibility change.

## Blocker status

### B1 — Full-history secret scan — CLEARED for scanner scope

Gitleaks 8.30.1 completed with zero findings against the isolated audit clone, all current refs, and fetched GitHub PR-head refs at the completed scan point. Final exact-head refresh remains required because the Issue #33 branch moved afterward.

### B2 — Project license — CLEARED

Human owner selected MIT and a root `LICENSE` was added on the Issue #33 branch.

### B3 — Actions logs/artifacts — CLEARED for retained surface

Inventory observed 174 runs, zero artifacts. All 153 available logs passed Gitleaks stdin scanning with zero findings. The remaining 21 runs had no log and were confirmed through API readback to contain zero executed steps. Partial logs, tool errors, and API classification errors were zero.

### B4 — GitHub-hosted discussion/attachments — CLEARED for audited surface

All 89 inventoried textual items passed Gitleaks screening with zero findings. No attachment URLs were detected. The seven environment/private-data indicator sources were manually classified as the already accepted owner email plus six Windows developer-path findings, and the human owner explicitly accepted those paths for public disclosure.

### B5 — Historical redistribution review — CLEARED for audit scope

Historical object-name screening found 56 unique paths with zero risk-name hits. A follow-up text-indicator pass scanned 213 reachable commits and surfaced only the repository's own Issue #33 readiness/audit wording. The added MIT license is an intentional first-party project license.

## Non-blocking observations

- The repository is already written as a reusable starter rather than a personal-data store.
- Current workflow permissions and checkout behavior are intentionally narrow.
- Historical author email `oimus1976@gmail.com` is explicitly accepted by the human owner for public disclosure.
- Windows developer paths surfaced in Issue/PR discussion are explicitly accepted by the human owner for public disclosure.
- There are no current GitHub Releases or retained Actions artifacts at the completed inventory point.
- MIT was selected specifically to make reuse rights explicit for the reusable starter.
- Public visibility would remove private-repository GitHub-hosted Actions minute pressure for standard runners; that benefit remains secondary to the publication-safety gate.

## Why PROJECT_STATUS.md is not updated

`PROJECT_STATUS.md` and `PROJECT_PROFILE.toml` in the canonical starter are distributed template inputs containing deliberate `TODO` placeholders for generated/adopted projects. Writing canonical-repository maintenance state into those files would change generated-project initialization semantics.

For this repository, Issue #33 state is therefore recorded in this audit document plus `CHANGELOG.md`.

## Next evidence step

All repository-specific blockers B1–B5 are cleared. Refresh the isolated audit clone against the exact current PR #34 head / intended publication SHA, rerun the full-history secret scan, confirm the branch diff remains bounded to the public-readiness documentation plus `LICENSE`, and refresh GitHub-hosted Actions/releases/artifact counts. If that exact-head refresh is clean, advance the audit state to `READY_FOR_HUMAN_GATE` without changing visibility or marking the PR Ready automatically.
