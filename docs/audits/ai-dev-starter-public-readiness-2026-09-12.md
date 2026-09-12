# ai-dev-starter public-readiness audit — 2026-09-12

Issue: #33

## Terminal state

`BLOCKED`

This is a read-only publication audit. It does **not** authorize changing repository visibility.

## Audit target

- Repository: `oimus1976/ai-dev-starter`
- Visibility observed: `private`
- Default branch: `main`
- Main SHA observed at audit start: `794aa1528f0b55fa077364fc4f12397eee5276da`
- Repository role: reusable/template AI-assisted development baseline
- GitHub license metadata at audit start: no project license detected (`license: null`)

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

- `AUDIT_HEAD=794aa1528f0b55fa077364fc4f12397eee5276da`
- Gitleaks version: `8.30.1`
- scan mode: `gitleaks git`
- log opts: `--all --full-history`
- redaction: `--redact=100`
- result: `GITLEAKS_HISTORY=PASS`
- exit code: `0`

Assessment: B1 is cleared for the Gitleaks scanner/ruleset scope against current refs plus fetched PR-head refs. The generated JSON report remains local and was not uploaded or pasted into shared discussion.

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

Assessment: B5 is cleared for the defined repository-publication provenance/redistribution screening scope. This is not a general legal opinion.

### GitHub Actions publication surface — B3 cleared for retained surface

The retained GitHub Actions surface was inventoried and screened without creating a combined raw-log archive.

Observed:

- workflow runs currently retained: 174;
- retained artifacts: 0;
- logs available and scanned: 153 runs;
- Gitleaks stdin findings across those 153 logs: 0;
- runs with no retained log: 21;
- partial-log runs: 0;
- Gitleaks/tool errors: 0;
- API classification errors: 0.

The 21 no-log runs were individually checked through the workflow-jobs API. Every run had three jobs and **zero executed steps**. Their job conclusions are `failure`, but there is no executed-step log surface to review. This is consistent with the known GitHub-hosted Actions availability/quota condition and is not treated as code/test evidence.

Assessment: B3 is cleared for the currently retained Actions publication surface: all available logs were scanner-clean, the remaining no-log runs never started a step, and no artifact exists.

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

### Repository protection

The current private repository returned GitHub API `403` for repository rulesets under the current plan/visibility combination. Existing house policy must therefore not be described as server-enforced on current private `main`.

If publication occurs, ruleset/branch-protection creation and authoritative readback are mandatory post-publication steps. Availability must not be assumed before the visibility change.

## Current blockers

### B1 — Full-history secret scan — CLEARED for scanner scope

Gitleaks 8.30.1 completed with zero findings against the isolated audit clone, all current refs, and fetched GitHub PR-head refs at the audited baseline SHA.

### B2 — Project license decision unresolved

The repository is explicitly designed for reuse, but GitHub currently reports no project license.

Required close condition:

- human owner decides whether the repository is merely source-visible or intended to grant reusable/open-source rights;
- if OSS reuse is intended, choose and add the project license through a reviewed tracked change;
- review dependency/third-party notices separately.

No license is selected by this audit.

### B3 — Actions logs/artifacts — CLEARED for retained surface

Current inventory: 174 runs, zero artifacts. All 153 available logs passed Gitleaks stdin scanning with zero findings. The remaining 21 runs had no log and were confirmed through API readback to contain zero executed steps. Partial logs, tool errors, and API classification errors were zero.

### B4 — GitHub-hosted discussion/attachments — CLEARED for audited surface

All 89 inventoried textual items passed Gitleaks screening with zero findings. No attachment URLs were detected. The seven environment/private-data indicator sources were manually classified as the already accepted owner email plus six Windows developer-path findings, and the human owner explicitly accepted those paths for public disclosure.

### B5 — Historical redistribution review — CLEARED for audit scope

Historical object-name screening found 56 unique paths with zero risk-name hits. A follow-up text-indicator pass scanned 213 reachable commits and surfaced only the repository's own Issue #33 readiness/audit wording.

## Non-blocking observations

- The repository is already written as a reusable starter rather than a personal-data store.
- Current workflow permissions and checkout behavior are intentionally narrow.
- Historical author email `oimus1976@gmail.com` is explicitly accepted by the human owner for public disclosure.
- Windows developer paths surfaced in Issue/PR discussion are explicitly accepted by the human owner for public disclosure.
- There are no current GitHub Releases or retained Actions artifacts.
- Public visibility would remove private-repository GitHub-hosted Actions minute pressure for standard runners; that benefit remains secondary to the publication-safety gate.

## Why PROJECT_STATUS.md is not updated

`PROJECT_STATUS.md` and `PROJECT_PROFILE.toml` in the canonical starter are distributed template inputs containing deliberate `TODO` placeholders for generated/adopted projects. Writing canonical-repository maintenance state into those files would change generated-project initialization semantics.

For this repository, Issue #33 state is therefore recorded in this audit document plus `CHANGELOG.md`.

## Next evidence step

Resolve B2 with an explicit human license decision. If OSS reuse is intended, add the chosen license through the tracked Issue #33 branch, then refresh the audit against the exact PR head / intended publication SHA before any human Ready or visibility decision.

Until B2 is closed, terminal state remains `BLOCKED`.
