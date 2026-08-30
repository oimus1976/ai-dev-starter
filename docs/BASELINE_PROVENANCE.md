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

## Known limits of the baseline

1. The evidence comes from a small number of projects by the same owner in the same time period.
2. These projects are unusually security/evidence conscious; copying their strongest controls into every small project would create ceremony without proportional benefit.
3. GitHub ruleset/branch-protection enforcement was not independently observable through the available integration during baseline review. The starter therefore records enforcement state separately from declared policy.
4. v0.5 has not yet been used to bootstrap a fresh real project. Adoption friction and missing defaults remain empirical questions.
5. A clean AI review does not prove the baseline itself is optimal; new evidence should trigger revision.

## Promotion criterion

Do not call this an established standard yet.

Promote beyond Draft/Baseline status only after at least one fresh project is created from it and post-adoption review confirms:

- the owner can maintain required C1/C2 comprehension;
- the workflow does not create repeated low-value ceremony;
- risk escalation catches meaningful boundaries without classifying ordinary work as high risk;
- recovery/evidence paths are actually usable;
- baseline rules that were not useful are removed or demoted rather than preserved for tradition.
