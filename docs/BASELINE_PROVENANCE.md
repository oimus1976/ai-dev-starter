# Baseline Provenance and Limits

## Evidence window

This v0.5 baseline was distilled on 2026-08-30 from recent active development, intentionally excluding older projects whose practices may reflect older model/tool behavior.

Primary recent evidence sources:

- `oimus1976/agent-controller`
- `oimus1976/life-dashboard`
- `oimus1976/pdf-size-fit`

## Reusable lessons extracted

- agent/provider completion is not objective artifact verification;
- exact-head evidence matters when authority/security state can drift;
- a remediation may invalidate earlier CI/review evidence;
- real platform smoke can falsify claims that synthetic/unit tests miss;
- private/raw data authority may legitimately remain outside GitHub;
- planning authority and execution authority can be different systems;
- durable ADRs, current status, semantic changelog, and PR history have different jobs;
- human comprehension must not lag indefinitely behind AI implementation throughput.

## First template-generation smoke

On 2026-08-30, `oimus1976/ai-dev-starter-adoption-smoke` was created from this repository using GitHub's template mechanism.

Observed evidence:

- the generated repository records `oimus1976/ai-dev-starter` as its template source;
- the generated initial commit tree and the template main tree were identical: `f10a0a8e1b05c9f59dc02dc5b29d8a328dfad8b7`;
- only `.github/workflows/policy-check.yml` was copied; no project CI workflow was present;
- the initial generated-repo policy check failed closed on unresolved project/profile/status values and missing project CI;
- canonical starter regression tests were skipped in the generated repository as intended;
- the real Actions log exposed that `actions/checkout` defaulted to `persist-credentials: true`, prompting an explicit `false` hardening change;
- the initial failure was accurate but cognitively noisy, prompting a concise initialization/next-step summary ahead of detailed diagnostics.

GitHub enforcement observation on the starter repository:

- `main` reported `protected: false`;
- the repository rulesets API returned `403` indicating GitHub Pro or a public repository is required for that feature under the current repository/account state.

Therefore the house rule against normal direct `main` writes is currently **DECLARED policy**, not GitHub platform enforcement. Do not describe it as `ENFORCED` or `VERIFIED` unless the platform state changes and is re-observed.

## First real project adoption: wacaf-room-watcher

On 2026-08-31, `oimus1976/wacaf-room-watcher` became the first real project to adopt and evolve from the Starter baseline.

Early adoption produced concrete corrections rather than merely confirming the template:

- the initial adoption exposed a namespace collision between canonical Starter regressions and generated-project `tests/`, leading Starter regressions to move into `starter_tests/` while project `tests/` became project-owned;
- subsequent tracked Phase 3/4 changes showed that Ready/merge human-final gates worked, but also exposed a lifecycle gap: GitHub merge completion did not establish that the developer's local checkout had returned to clean, synchronized canonical `main`;
- that gap motivated the post-merge local closeout gate and `scripts/verify_local_closeout.py` in Issue #8;
- the first horizontal rollout then exposed a second-order worktree gap: the original linked-worktree regression moved the primary checkout off `main`, so it missed the common arrangement where the primary worktree keeps `main` and a separate linked worktree carries the PR topic branch;
- Issue #10 therefore split task-worktree closeout from canonical-worktree readiness: a linked topic worktree can close out while remaining on its topic branch when its exact GitHub-confirmed PR head is preserved and a separate canonical worktree is clean and synchronized.

This evidence supports keeping merge authority, task-worktree residue, and canonical next-work readiness as separate facts. It also reinforces the rule that baseline changes should come from observed friction in real work, not from speculative ceremony.

## Known limits of the baseline

1. The evidence comes from a small number of projects by the same owner in the same time period.
2. These projects are unusually security/evidence conscious; copying their strongest controls into every small project would create ceremony without proportional benefit.
3. GitHub branch protection/ruleset enforcement is not active for the starter under the observed current repository/account state; human/process discipline still carries the direct-main-write boundary.
4. The first real project is now active and has already generated useful corrections, but the baseline has not yet accumulated evidence across multiple independently shaped new projects. Long-term adoption friction and which rules should be demoted remain empirical questions.
5. A clean AI review does not prove the baseline itself is optimal; new evidence should trigger revision.

## Promotion criterion

Do not call this an established standard yet.

Promote beyond Draft/Baseline status only after real-project adoption evidence confirms across more than one project shape that:

- the owner can maintain required C1/C2 comprehension;
- the workflow does not create repeated low-value ceremony;
- risk escalation catches meaningful boundaries without classifying ordinary work as high risk;
- recovery/evidence paths are actually usable;
- baseline rules that were not useful are removed or demoted rather than preserved for tradition.
