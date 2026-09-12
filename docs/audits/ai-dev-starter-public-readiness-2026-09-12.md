# ai-dev-starter public-readiness audit — 2026-09-12

Issue: #33

## Terminal state

`PUBLISHED_VERIFIED`

The repository was audited while private, passed the human publication gate, was changed to public visibility, and completed post-publication verification. The public repository now has an active `protect-main` repository ruleset protecting `refs/heads/main`.

## Audit target

- Repository: `oimus1976/ai-dev-starter`
- Visibility during pre-publication audit: `private`
- Visibility after human publication gate: `public`
- Default branch: `main`
- Main SHA observed at audit start: `794aa1528f0b55fa077364fc4f12397eee5276da`
- Published/verified main SHA: `84607eda92be319e7aacd10ba11a209771d5abef`
- Published/verified main tree SHA: `48f0a237dfc8df8a7ee24e90c1aee00478f16499`
- Repository role: reusable/template AI-assisted development baseline
- Human license decision: MIT License
- Root `LICENSE`: present with `Copyright (c) 2026 Sumio Nishioka`

## Publication-surface evidence

### B1 — Full-history secret scan — CLEARED for scanner scope

An isolated audit clone under `%TEMP%` fetched current heads plus GitHub `refs/pull/*/head` into audit-only refs. Gitleaks `8.30.1` was run with `gitleaks git`, `--all --full-history`, and `--redact=100`.

Completed evidence:

- initial full-history scan: PASS / exit `0`;
- final pre-state refresh at PR head `a96aeb6607c1df5922fb6142e0c87a0aff69d5ea`: `HEAD_EXACT=True`;
- branch diff check at that head: `DIFF_EXACT=True`;
- final pre-state Gitleaks full-history refresh: exit `0`;
- final human-gate refresh at PR head `2fbd960062524d611c66079dcd493cc81f288f17`: `HEAD_EXACT=True`, `DIFF_EXACT=True`, Gitleaks exit `0`, artifacts `0`, Releases `0`.

The generated Gitleaks JSON reports remained local and were not uploaded or pasted into shared discussion.

### Git metadata / object-name privacy review

Observed during the all-ref audit:

- commit records inspected at the initial inventory: 211;
- unique author identities: 3;
- unique historical paths: 56;
- filename-pattern hits for credentials/secrets/high-risk binaries: 0;
- authors: `google-labs-jules[bot]`, `oimus1976`, and `Sumio Nishioka`;
- owner-authored commits use `oimus1976@gmail.com`.

Human owner decision: `oimus1976@gmail.com` author metadata is **accepted for public disclosure** for this repository. No history rewrite is required or authorized on account of that address.

### B2 — Project license — CLEARED

The repository is explicitly designed for reuse. The human owner selected the **MIT License** and a standard root `LICENSE` was added before publication.

Assessment: reusable/open-source rights are explicit and GitHub recognizes the repository license as MIT.

### B3 — GitHub Actions logs/artifacts — CLEARED for retained surface

Primary inventory and scan:

- workflow runs retained at the completed bulk scan: 174;
- retained artifacts: 0;
- available logs scanned with Gitleaks stdin: 153;
- Gitleaks findings in those logs: 0;
- no-log runs: 21;
- partial-log runs: 0;
- Gitleaks/tool errors: 0;
- API classification errors: 0.

Each of the 21 no-log runs had three jobs and zero executed steps.

Final refresh after Issue #33 branch updates:

- repository run count increased to 180;
- artifacts remained 0;
- six newly retained runs were inspected through the workflow-jobs API;
- every one of those six runs had three jobs with `steps=null` / zero executed steps;
- therefore no new executed log surface was introduced after the bulk log scan.

The pre-publication `failure` conclusions on these zero-step runs were consistent with the hosted-runner/quota availability condition and were not treated as code/test evidence.

Post-publication Actions verification:

- the final pre-publication failed run `34690218786` was re-run after visibility changed to public;
- all three jobs executed normally and completed `success`:
  - `baseline-policy`;
  - `canonical-closeout-platform (windows-latest)`;
  - `canonical-closeout-platform (macos-latest)`.

Assessment: the private-repository hosted-runner/quota start failure was no longer present after publication, and the canonical public CI baseline executed successfully.

### B4 — GitHub-hosted discussion / attachment references — CLEARED for audited surface

The GitHub-hosted textual discussion surface was inventoried without creating a raw combined archive.

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

Manual classification of the seven indicators:

- PR #34 contains the already accepted owner email;
- Issue #17 and five GitHub-hosted comments contain Windows developer paths under `C:\Users\oimus\...` for personal OSS repositories/worktrees and Windows qualification evidence;
- no host name, UNC path, private IP, credential, organization-internal URL, municipal/business-system path, or attachment URL was present in those hits.

Human owner decision: the six Windows developer-path findings are **accepted for public disclosure**. No redaction/edit is required or authorized on account of those paths.

### B5 — Historical redistribution / provenance review — CLEARED for audit scope

Historical object-name screening found 56 unique paths with zero risk-name hits. A separate text-indicator pass scanned 213 reachable commits for copyright/license/vendor/third-party/redistribution indicators.

The only matched paths were:

- `CHANGELOG.md`;
- `docs/PUBLIC_REPOSITORY_READINESS.md`;
- `docs/audits/ai-dev-starter-public-readiness-2026-09-12.md`.

Those hits were the repository's own Issue #33 readiness/audit wording. No unresolved third-party source/test/config/vendor path was identified. The subsequently added MIT `LICENSE` is intentional first-party project licensing metadata.

### Releases / Pages / package surface

- authoritative GitHub Releases API readback after publication returned `[]` / zero Releases;
- repository metadata reports `has_pages=false`;
- no package-publishing workflow, deployment credential, package manifest publication step, or package-release automation was identified in the audited repository/workflow surface.

This record does not make claims about unrelated packages owned by the account outside this repository.

### Current branch scope

PR #34 changed exactly these five files before publication:

- `CHANGELOG.md`
- `LICENSE`
- `README.md`
- `docs/PUBLIC_REPOSITORY_READINESS.md`
- `docs/audits/ai-dev-starter-public-readiness-2026-09-12.md`

No executable source file or workflow file was changed by PR #34.

PR #34 was squash-merged to `main` as `84607eda92be319e7aacd10ba11a209771d5abef`. Its tree SHA `48f0a237dfc8df8a7ee24e90c1aee00478f16499` matched the audited publication content.

## Workflow / public-fork boundary

The current `.github/workflows/policy-check.yml` baseline uses:

- `pull_request` and `push` to `main`;
- explicit `contents: read` permission;
- `actions/checkout` with `persist-credentials: false`;
- commit-pinned third-party Actions;
- no `pull_request_target`;
- no current secret-bearing deployment/write step.

Assessment: current workflow shape is suitable as the public/fork baseline. Any future introduction of privileged fork-PR execution, `pull_request_target`, secrets, write permissions, deployment authority, or trusted self-hosted runners must receive a fresh trust-boundary review.

## Repository protection — VERIFIED

After publication, repository ruleset `protect-main` was created and authoritatively read back as ruleset ID `23040722`.

Verified state:

- target: branch;
- enforcement: `active`;
- include: `refs/heads/main`;
- bypass actors: none;
- current user bypass: `never`;
- deletion: prohibited;
- non-fast-forward / force push: prohibited;
- pull request required;
- required approving review count: `0`;
- review-thread resolution required;
- allowed merge methods: merge, squash, rebase;
- strict up-to-date policy: disabled;
- required status checks:
  - `baseline-policy`;
  - `canonical-closeout-platform (windows-latest)`;
  - `canonical-closeout-platform (macos-latest)`.

The authoritative branch endpoint now reports `main` as `protected=true` while preserving main SHA `84607eda92be319e7aacd10ba11a209771d5abef`.

## Why PROJECT_STATUS.md is not updated

`PROJECT_STATUS.md` and `PROJECT_PROFILE.toml` are distributed starter inputs with deliberate `TODO` placeholders. Writing canonical repository-maintenance state into them would change generated-project initialization semantics.

Issue #33 state is therefore recorded in this audit document plus `CHANGELOG.md`.

## Publication verification

Human-final actions were performed explicitly and separately:

1. PR #34 was marked Ready by the human owner.
2. PR #34 was merged by the human owner.
3. The repository visibility change from private to public was explicitly authorized and performed by the human owner.
4. Post-publication repository state was authoritatively read back as `visibility=public`, default branch `main`, with main SHA unchanged from the post-merge SHA.
5. Public hosted Actions were re-run and all three canonical jobs succeeded.
6. `protect-main` was created and authoritatively read back as active; the branch endpoint reports `main` protected.
7. Releases remained zero and Pages remained disabled.

Terminal assessment: **`PUBLISHED_VERIFIED`**.

The publication audit is complete. Future changes that materially broaden the public trust boundary—especially secrets/write permissions, privileged fork execution, `pull_request_target`, deployment/package publication, trusted self-hosted runners, or redistribution-sensitive assets—require a fresh targeted review.