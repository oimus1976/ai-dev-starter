# AI Development Starter v0.5

A project starter for AI-assisted development that keeps human ownership, evidence, and recoverability ahead of implementation speed.

This is a **house baseline**, not a universal software-development standard. It was distilled from recent active projects and is intentionally risk-based: small experiments stay light, while changes that touch authority, private data, destructive I/O, deployment, credentials, security boundaries, or real platform behavior receive stronger gates.

## Core idea

AI output is a claim until verified by an authoritative source.

The starter therefore separates:

- **authority** — which system owns which fact;
- **risk** — which facets and tier apply to the change;
- **evidence** — what actually proves the change;
- **human comprehension** — whether the owner can still operate, diagnose, and govern the project;
- **protected effects** — which actions require separate human decisions.

## Start here

1. Copy this starter into a new repository.
2. Optionally initialize name/purpose with `python scripts/bootstrap.py --name "..." --purpose "..."`.
3. Complete `PROJECT_PROFILE.toml`.
4. Complete the summary block at the top of `PROJECT_STATUS.md`.
5. Read `BASELINE.md` and keep only the risk facets that actually apply.
6. Replace the copied placeholder CI in `.github/workflows/ci.yml` with project-specific checks. The canonical `oimus1976/ai-dev-starter` repository self-checks itself; copies intentionally fail until this step is done.
7. Run `python scripts/verify_repo.py`.

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
```

Exploration that is genuinely disposable does not need Issue/PR ceremony. Once work is intended to persist, it enters the tracked workflow.

## Files

- `BASELINE.md` — single normative source for authority, risk, review, evidence, and comprehension gates.
- `PROJECT_PROFILE.toml` — project-specific authority, risk, and governance choices.
- `PROJECT_STATUS.md` — concise current state first, detail second.
- `CHANGELOG.md` — meaningful changes, not a duplicate commit log.
- `AGENTS.md` — instructions for AI coding agents.
- `docs/adr/` — durable architecture decisions when warranted.
- `.github/pull_request_template.md` — review/evidence/comprehension checklist.
- `.github/workflows/policy-check.yml` — starter structural policy check.
- `.github/workflows/ci.yml` — intentionally failing placeholder until project CI is defined.
- `scripts/bootstrap.py` — dependency-free identity initializer.
- `scripts/verify_repo.py` — dependency-free starter consistency check.

## Baseline freshness

Baseline version: **0.5**  
Reviewed: **2026-08-30**  
Evidence window: **recent active projects only**

The baseline itself is subject to comprehension debt and policy drift. Re-review it after real adoption feedback, not merely on a calendar because a date elapsed.
