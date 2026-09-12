# Agent Instructions

This repository uses the oimus AI Development Baseline.

`BASELINE.md` defines durable governance and safety policy. `PROJECT_PROFILE.toml` defines project-specific authority and risk context. `PROJECT_STATUS.md` records current project state.

## Start from repository evidence

Before changing tracked project state:

1. Read `BASELINE.md`, `PROJECT_STATUS.md`, `PROJECT_PROFILE.toml`, and the relevant Issue/PR and ADR/design documentation.
2. Resolve the intended work item, repository, implementation branch, and scope.
3. Identify the change-specific risk facets and derive the applicable risk level under `BASELINE.md`.

Do not treat chat history, agent summaries, or copied status text as authoritative when repository or platform evidence is available.

If the repository, work item, or writable branch cannot be established with sufficient confidence, inspect further but do not make tracked changes.

## Autonomy and approval

For requests to review, explain, diagnose, investigate, or plan:

- inspect the relevant repository and platform evidence;
- report findings and evidence;
- do not implement changes unless implementation is also requested.

For requests to change, build, fix, or remediate:

- make the requested in-scope changes on the resolved implementation branch;
- perform relevant non-destructive validation without asking for separate approval;
- continue through ordinary inspect -> change -> verify -> report steps while the work remains within scope.

Require explicit human authorization before:

- Ready transition;
- merge;
- deployment or release where designated human-final;
- destructive cleanup or irreversible mutation;
- external writes not already authorized by the task;
- credential-sensitive effects;
- material expansion of scope.

Ready and merge are always human-final house policy.

## Change discipline

- Do not use `main` as the normal implementation branch.
- Keep changes within the declared scope and preserve unrelated work.
- Do not weaken tests merely to obtain a passing result.
- Do not expose secrets, credentials, private data, or owner-local artifacts.
- Apply the escalation, uncertainty, protected-effect, and evidence rules in `BASELINE.md`.

## Evidence before claims

Treat agent completion statements as claims until verified.

Before reporting a tracked change as complete, establish the applicable evidence from the authority that owns each fact. Include, where relevant:

- branch and exact HEAD;
- material changed paths;
- tests and their results;
- authoritative CI/review state;
- required real-boundary validation;
- residual uncertainty or deferred work.

A successful implementation, test, or review does not by itself authorize or prove a protected effect.

When remediation changes the relevant revision, reassess which prior evidence was invalidated and rerun the evidence required by `BASELINE.md`.

If the same `MAJOR` safety invariant remains violated after two remediation attempts, stop patching and perform an architecture/scope review before another attempt.

## Handoff

At a meaningful handoff, explain concisely:

- what changed and why;
- what intentionally did not change;
- what evidence supports the current state;
- what remains uncertain, deferred, or blocked;
- which human decision or protected effect comes next.

Prefer simplification or documentation when complexity prevents the project owner from reaching the comprehension level required by `BASELINE.md`.

## Post-merge closeout

Merge status and local worktree closeout are separate facts.

After a tracked PR is human-merged, follow the post-merge closeout procedure defined in `BASELINE.md` and the repository-provided verification/cleanup tools.

When retiring an eligible merged topic worktree, use `python scripts/post_merge_cleanup.py --pr <PR_NUMBER>` as the plan-only first step. After the tool produces an eligible plan, present that specific plan to the human and obtain new, explicit authorization to execute it before running `--execute`. Do not infer execution authorization from an earlier or general request to clean up.

Do not use destructive cleanup merely to make a closeout check pass. Preserve intentional local work and report blocked or incomplete closeout state explicitly.

## Repository-wide branch audit

For repository-wide branch inventory/review, use `python scripts/branch_cleanup_audit.py --repository OWNER/REPO` and follow `docs/branch-cleanup-policy.md`.

The helper is audit-only. Its output is evidence for human review and never deletion authority; review-candidate entries explicitly carry `deletion_authority: false`. Any destructive executor is a separate authority boundary tracked in Issue #22.

For native `gh` commands, exit status is authoritative for command success; stderr is diagnostic output only and may contain normal success/progress text.
