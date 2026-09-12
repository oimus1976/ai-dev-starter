# ai-dev-starter public-readiness audit — 2026-09-12

Issue: #33

## Terminal state

`READY_FOR_HUMAN_GATE`

All repository-specific publication blockers B1–B5 are cleared for their defined audit scopes. This state does **not** authorize changing repository visibility, marking PR #34 Ready, or merging it.

This document is the final tracked audit-state change on the Issue #33 branch. Before any human Ready or visibility action, perform one **read-only exact-head verification of this state commit itself**. If that verification fails or the branch moves afterward, treat the repository as `BLOCKED` again until refreshed.

## Audit target

- Repository: `oimus1976/ai-dev-starter`
- Visibility observed throughout audit: `private`
- Default branch: `main`
- Main SHA observed at audit start: `794aa1528f0b55fa077364fc4f12397eee5276da`
- Repository role: reusable/template AI-assisted development baseline
- Human license decision: MIT License
- Root `LICENSE`: present on the Issue #33 branch with `Copyright (c) 2026 Sumio Nishioka`

## Publication-surface evidence

### B1 — Full-history secret scan — CLEARED for scanner scope

An isolated audit clone under `%TEMP%` fetched current heads plus GitHub `refs/pull/*/head` into audit-only refs. Gitleaks `8.30.1` was run with `gitleaks git`, `--all --full-history`, and `--redact=100`.

Completed evidence:

- initial full-history scan: PASS / exit `0`;
- final pre-state refresh at PR head `a96aeb6607c1df5922fb6142e0c87a0aff69d5ea`: `HEAD_EXACT=True`;
- branch diff check at that head: `DIFF_EXACT=True`;
- final pre-state Gitleaks full-history refresh: exit `0`.

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

The repository is explicitly designed for reuse. The human owner selected the **MIT License** and a standard root `LICENSE` was added on the Issue #33 branch.

Assessment: reusable/open-source rights are explicit. License choice is complete; visibility remains a separate human-final gate.

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

The `failure` conclusions on these zero-step runs are consistent with the known hosted-runner/quota availability condition and are not treated as code/test evidence.

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

### Releases

The final local helper reported `RELEASE_COUNT=1`, but authoritative GitHub Releases API readback returned an empty collection `[]`.

Assessment: current Releases count is **0**. The local value was a PowerShell array-wrapping/counting artifact, not a real GitHub Release.

### Current branch scope

At final pre-state head `a96aeb6607c1df5922fb6142e0c87a0aff69d5ea`, the branch diff from `main` was exactly these five files:

- `CHANGELOG.md`
- `LICENSE`
- `README.md`
- `docs/PUBLIC_REPOSITORY_READINESS.md`
- `docs/audits/ai-dev-starter-public-readiness-2026-09-12.md`

No executable source file or workflow file was changed by PR #34.

## Workflow / public-fork boundary

The current `.github/workflows/policy-check.yml` baseline uses:

- `pull_request` and `push` to `main`;
- explicit `contents: read` permission;
- `actions/checkout` with `persist-credentials: false`;
- commit-pinned third-party Actions;
- no `pull_request_target`;
- no current secret-bearing deployment/write step.

Assessment: current workflow shape is suitable as the public/fork baseline. Any future introduction of privileged fork-PR execution, `pull_request_target`, secrets, write permissions, deployment authority, or trusted self-hosted runners must receive a fresh trust-boundary review.

## Repository protection

While the repository remains private under the current plan, GitHub ruleset readback returned the plan/visibility limitation rather than an enforceable ruleset.

If publication occurs, ruleset/branch-protection creation and authoritative readback are mandatory **post-publication** steps. Protection availability must not be treated as already enforced before the visibility change.

## Why PROJECT_STATUS.md is not updated

`PROJECT_STATUS.md` and `PROJECT_PROFILE.toml` are distributed starter inputs with deliberate `TODO` placeholders. Writing canonical repository-maintenance state into them would change generated-project initialization semantics.

Issue #33 state is therefore recorded in this audit document plus `CHANGELOG.md`.

## Human gate

Subject to a clean read-only verification of this final audit-state commit itself, the repository is ready for a human decision on PR #34 Ready/merge and the later private-to-public visibility change.

The following remain human-final and are **not** authorized by this audit record:

- marking PR #34 Ready;
- merging PR #34;
- changing repository visibility;
- rewriting history;
- deleting branches;
- deleting or redacting historical GitHub-hosted evidence.

After any visibility change, perform authoritative post-publication verification of visibility, default branch, branch/ruleset protection, Actions/fork settings, Releases/packages/Pages exposure, and unauthenticated public access.