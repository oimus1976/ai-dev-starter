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

### Full-history secret scan

An isolated audit clone was created under `%TEMP%` from `oimus1976/ai-dev-starter`, and GitHub `refs/pull/*/head` were fetched into audit-only refs before scanning. The clone resolved the intended publication baseline as:

- `AUDIT_HEAD=794aa1528f0b55fa077364fc4f12397eee5276da`
- Gitleaks version: `8.30.1`
- scan mode: `gitleaks git`
- log opts: `--all --full-history`
- redaction: `--redact=100`
- result: `GITLEAKS_HISTORY=PASS`
- exit code: `0`

Assessment: B1 is cleared for the scanner/ruleset scope against the audited all-ref + fetched PR-head set. This does not prove safety of GitHub-hosted Issues/PR comments/attachments, Actions logs/artifacts, unusual credentials outside Gitleaks rules, personal metadata, or redistribution-sensitive historical material; those surfaces remain separate blockers below.

The generated `gitleaks-history.json` remains local and was not uploaded to GitHub or shared discussion.

### GitHub Actions publication surface

GitHub API inventory reported 167 workflow runs at the time of the audit. The latest runs are currently failing because hosted Actions execution is unavailable; this audit does not reinterpret those failures as code evidence.

Draft PR #34 run #155 (`34679706627`) reported all three jobs as failed, but the `baseline-policy` job contained zero executed steps. That is consistent with the existing hosted-runner availability/quota condition rather than an executed documentation/test failure.

GitHub documents that Actions history and logs become visible when a private repository is converted to public. Therefore retained historical run logs are a required publication surface, not an optional cleanup task.

Assessment: `BLOCKED` until all retained run logs and any non-expired artifacts are screened for publication-sensitive data.

### Issues / PR discussion evidence

Targeted GitHub search found no Issue/PR hits for obvious GitHub token prefixes (`github_pat_`, `ghp_`), `BEGIN PRIVATE KEY`, or `@gmail.com`. This is a limited screening result, not proof of absence in attachments, logs, edits, or arbitrary historical text.

Real absolute Windows paths are definitely present in GitHub-hosted discussion:

- Issue #17 records `C:\Users\oimus\...` worktree topology;
- PR #13 contains a qualification comment naming local clone `C:\Users\oimus\ai-dev-starter`;
- PR #15 contains a qualification comment naming `C:\Users\oimus\ai-dev-starter-issue14` and command lines using that path.

These are not credential findings, but they prove that publication-sensitive environment metadata exists outside the Git tree.

Assessment: each such finding must be classified as intentionally public, redacted/removed, or blocking. Current targeted search is not yet a complete Issue/PR/review/attachment audit.

### Current branches / all-ref surface

GitHub reported 17 current branches at audit time, including merged/older topic branches, current workstreams, and two Jules branches. None is protected while the repository remains private under the current plan.

Assessment: publication review must cover **all refs**, not only `main`. The isolated audit clone plus fetched PR-head refs and `--all --full-history` scan cover the intended reachable Git history without requiring branch deletion. Branch deletion remains a separate protected/destructive effect.

### Current tree / redistribution screening

The recursive tree for audited `main` consists of Markdown/TOML/YAML/Python source and tests; no obvious current vendored binary, media, font, model/data bundle, or third-party asset directory was identified in the root/tree inventory.

Assessment: this reduces the current-tree redistribution concern but does not by itself clear copied third-party text. B5 remains open until the historical text/license/vendor indicator scan is reviewed.

### Historical metadata / object-name inventory

The same isolated audit clone was used to inventory Git metadata and historical object names across all refs.

Observed:

- commit records inspected: 211;
- unique author identities: 3;
- unique historical paths: 56;
- paths matching the current credential/secret/high-risk-binary filename pattern: 0;
- authors were `google-labs-jules[bot]`, `oimus1976`, and `Sumio Nishioka`;
- the bot uses a GitHub noreply address;
- commits attributed to `oimus1976` and `Sumio Nishioka` use `oimus1976@gmail.com`.

Human owner decision: the historical `oimus1976@gmail.com` author address is **accepted for public disclosure** for this repository. No history rewrite is required or authorized on account of that address.

Assessment: Git-history privacy concern for the author email is closed by explicit human classification. The zero-risk-path result substantially reduces B5, but does not prove absence of copied third-party/license-restricted text; one historical text indicator pass remains required.

### Releases

GitHub API returned no releases.

Assessment: no current release assets to audit, subject to refresh immediately before the human publication gate.

### Repository protection

The current private repository returned GitHub API `403` for repository rulesets with the message that GitHub Pro is required or the repository must be public. Existing house policy therefore must not be described as server-enforced on current private `main`.

GitHub documentation states that rulesets/protected branches are available for public repositories on GitHub Free. If publication occurs, protection creation and authoritative readback are mandatory post-publication steps; availability must not be assumed in advance.

## Current blockers

### B1 — Full-history secret scan — CLEARED for scanner scope

Gitleaks 8.30.1 completed successfully with zero findings against the isolated audit clone, all current refs, and fetched GitHub PR-head refs at the audited baseline SHA.

This clears the required scanner gate only. GitHub-hosted metadata and redistribution review remain separate.

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

Known environment-specific path findings now include Issue #17 and PR qualification comments in #13 and #15. Targeted token/private-key/email-pattern searches returned no hits, but arbitrary comments, reviews, edits, images, and attachments have not yet received complete publication classification.

Required close condition:

- review all Issues/PRs/comments and relevant attachments;
- classify each environment/private-data finding;
- do not claim deletion from the Git tree removes platform-hosted copies.

### B5 — Historical redistribution review incomplete

Current `main` tree inventory contains no obvious vendored binary/media asset class. The all-ref object-name inventory found 56 unique historical paths and zero paths matching the current secret/high-risk-binary filename pattern.

Required close condition:

- run a historical text indicator pass for copyright/license/vendor/third-party markers across all reachable commits;
- manually classify any matched paths/content provenance;
- resolve redistribution uncertainty before publication.

## Non-blocking observations

- The repository is already written as a reusable starter rather than a personal-data store.
- Current workflow permissions and checkout behavior are intentionally narrow.
- Gitleaks full-history scan passed for the audited all-ref + PR-head set.
- Historical author email `oimus1976@gmail.com` is explicitly accepted by the human owner for public disclosure.
- Historical object-name screening found 56 unique paths and zero filename-pattern hits for the current risk set.
- There are no GitHub Releases at audit time.
- Current `main` tree does not show an obvious third-party binary/media bundle.
- Public visibility would make GitHub Free ruleset/branch-protection features available, subject to post-change authoritative verification.
- Public visibility would also remove private-repository GitHub-hosted Actions minute pressure for standard runners; that benefit is secondary to the publication-safety gate.

## Why PROJECT_STATUS.md is not updated

`PROJECT_STATUS.md` and `PROJECT_PROFILE.toml` in the canonical starter are distributed template inputs containing deliberate `TODO` placeholders for generated/adopted projects. Writing canonical-repository maintenance state into those files would leak starter-maintenance details into every future generated project and change their initialization contract.

For this repository, Issue #33 state is therefore recorded in this audit document plus `CHANGELOG.md`. Generated repositories should continue to replace their own `PROJECT_STATUS.md` / `PROJECT_PROFILE.toml` placeholders as normal.

## Next evidence step

Run the historical text indicator pass from the same isolated audit clone and classify any copyright/license/vendor/third-party matches. If that produces no unresolved provenance concern, close B5 and move to the GitHub-hosted Actions surface (B3).

Until B2–B5 are closed, terminal state remains `BLOCKED`.
