# AI Development Starter v0.5

A project starter for AI-assisted development that keeps human ownership, evidence, and recoverability ahead of implementation speed.

This is a **house baseline**, not a universal software-development standard. It was distilled from recent active projects and is intentionally risk-based: small experiments stay light, while changes that touch authority, private data, destructive I/O, deployment, credentials, security boundaries, real platform behavior, or broad system behavior receive stronger gates.

## Core idea

AI output is a claim until verified by an authoritative source.

The starter therefore separates:

- **authority** — which system owns which fact;
- **risk** — which facets and named level apply to the change;
- **evidence** — what actually proves the change;
- **human comprehension** — whether the owner can still operate, diagnose, and govern the project;
- **protected effects** — which actions require separate human decisions.

## Start here

1. Copy this starter into a new repository.
2. Optionally initialize name/purpose with `python scripts/bootstrap.py --name "..." --purpose "..."`.
3. Complete `PROJECT_PROFILE.toml`.
4. Complete the summary block at the top of `PROJECT_STATUS.md`.
5. Read `BASELINE.md` and keep only the risk facets that actually apply.
6. Add a project-specific `.github/workflows/project-ci.yml`. The starter does **not** copy an active dummy project CI workflow. Until your project CI exists, `policy-check` fails closed instead of presenting an unexplained green state.
7. Run `python scripts/verify_repo.py`.

`policy-check` can establish that the required project CI workflow has been deliberately added; it cannot prove that the workflow's tests are sufficient. Acceptance still requires evidence from the actual project CI run.

## Risk language

Risk levels use names rather than `R1/R2/R3` codes:

- `ROUTINE` — ordinary bounded tracked change;
- `ELEVATED` — broader impact or a meaningful external/platform/privacy/agent/workflow boundary;
- `HIGH_IMPACT` — failure could authorize, expose, destroy, deploy, sign, corrupt critical state, or weaken a security boundary.

Review findings also use words rather than reverse-numbered `P0/P1/...` labels: `CRITICAL`, `MAJOR`, `MINOR`, `NOTE`.

## Default workflow

```text
exploration/spike
    |
    | keep it?
    v
tracked change
    |
    +--> durable intent record
    +--> branch
    +--> Draft PR
    +--> risk-based verification
    +--> review
    +--> comprehension gate
    +--> human Ready
    +--> human merge
    +--> post-merge local closeout
         +--> non-destructive verify
         +--> target-scoped cleanup when eligible
```

Exploration that is genuinely disposable does not need Issue/PR ceremony. Once work is intended to persist, it enters the tracked workflow.

Post-merge cleanup is intentionally separate from verification. `post_merge_cleanup.py` reads merged-PR authority independently through authenticated GitHub CLI, plans by default, and requires `--execute` before changing local state. Remote branch deletion is a further explicit opt-in.

## Files

- `BASELINE.md` — single normative source for authority, risk, review, evidence, and comprehension gates.
- `PROJECT_PROFILE.toml` — project-specific authority, risk, and governance choices.
- `PROJECT_STATUS.md` — concise current state first, detail second.
- `CHANGELOG.md` — meaningful changes, not a duplicate commit log.
- `AGENTS.md` — instructions for AI coding agents.
- `docs/adr/` — durable architecture decisions when warranted.
- `.github/pull_request_template.md` — review/evidence/comprehension checklist.
- `.github/workflows/policy-check.yml` — starter structural check; canonical starter regression tests run only in the template repository.
- `.github/workflows/project-ci.yml` — intentionally **absent** from the template; each generated project must add its own real CI.
- `scripts/bootstrap.py` — dependency-free identity initializer.
- `scripts/verify_repo.py` — dependency-free starter consistency check.
- `scripts/verify_local_closeout.py` — non-destructive local closeout verifier.
- `scripts/closeout_state.py` — shared dependency-free Git/worktree state helpers used by closeout tooling.
- `scripts/post_merge_cleanup.py` — fail-closed merged-PR cleanup planner/executor; dry-run by default.
- `starter_tests/` — regression tests for ai-dev-starter itself.
- `tests/` — reserved for generated projects' own tests.

## Baseline freshness

Baseline version: **0.5**  
Reviewed: **2026-09-02**  
Evidence window: **recent active projects only**

The baseline itself is subject to comprehension debt and policy drift. Re-review it after real adoption feedback, not merely on a calendar because a date elapsed.
