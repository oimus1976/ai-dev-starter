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

### Issues / PR discussion evidence — B4 still open

Earlier targeted GitHub search found no Issue/PR hits for obvious GitHub token prefixes (`github_pat_`, `ghp_`), `BEGIN PRIVATE KEY`, or `@gmail.com`. This was only limited screening.

Known environment-specific content already exists in GitHub-hosted discussion:

- Issue #17 records `C:\Users\oimus\...` worktree topology;
- PR #13 contains a qualification comment naming local clone `C:\Users\oimus\ai-dev-starter`;
- PR #15 contains a qualification comment naming `C:\Users\oimus\ai-dev-starter-issue14` and command lines using that path.

These are not credential findings. They require explicit human classification as acceptable public developer-environment metadata, redaction/removal candidate, or blocker.

B4 remains open until all current Issue/PR bodies, conversation comments, review comments/review bodies, and attachment URLs are inventoried and screened, with any hits manually classified.

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

### B4 — GitHub-hosted discussion/attachments audit incomplete

Required close condition:

- inventory Issue and PR bodies;
- inventory conversation comments, review comments, and review bodies;
- identify attachment/user-content URLs;
- scanner-screen the textual surface without publishing a raw combined archive;
- manually classify environment/private-data findings;
- do not assume Git-tree cleanup affects GitHub-hosted discussion content.

### B5 — Historical redistribution review — CLEARED for audit scope

Historical object-name screening found 56 unique paths with zero risk-name hits. A follow-up text-indicator pass scanned 213 reachable commits and surfaced only the repository's own Issue #33 readiness/audit wording.

## Non-blocking observations

- The repository is already written as a reusable starter rather than a personal-data store.
- Current workflow permissions and checkout behavior are intentionally narrow.
- Historical author email `oimus1976@gmail.com` is explicitly accepted by the human owner for public disclosure.
- There are no current GitHub Releases or retained Actions artifacts.
- Public visibility would remove private-repository GitHub-hosted Actions minute pressure for standard runners; that benefit remains secondary to the publication-safety gate.

## Why PROJECT_STATUS.md is not updated

`PROJECT_STATUS.md` and `PROJECT_PROFILE.toml` in the canonical starter are distributed template inputs containing deliberate `TODO` placeholders for generated/adopted projects. Writing canonical-repository maintenance state into those files would change generated-project initialization semantics.

For this repository, Issue #33 state is therefore recorded in this audit document plus `CHANGELOG.md`.

## Next evidence step

Complete B4 by inventorying and scanner-screening GitHub-hosted Issue/PR discussion and attachment references, then manually classify only the surfaced hits.

Until B2 and B4 are closed, terminal state remains `BLOCKED`.