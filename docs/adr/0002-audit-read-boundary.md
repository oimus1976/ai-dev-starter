# ADR-0002 — Separate branch audit interpretation from GitHub reads

- **Status:** Proposed; human-final acceptance remains separate
- **Date:** 2026-09-09
- **Related:** Issue #20, PR #21, Issue #22, branch-cleanup-policy.md

## Context

Repeated review found that Python source-pattern checks could accept equivalent process capabilities through aliases or indirection. Issue #20 / PR #21 now explicitly require a reviewable current audit-only implementation instead of an exhaustive proof about future Python source. This is the requested architecture reset under the baseline anti-loop rule.

## Decision

Separate pure interpretation and evidence serialization into `branch_cleanup_core.py`. Inputs are supplied GitHub data, canonical identity interpreted from repository metadata, retained branches, and a timestamp. The core performs no I/O.

Place authenticated github.com reads in `branch_cleanup_github.py`, with three public operations: repository metadata, branches, and pull requests. Endpoints and pagination are constructed inside this adapter; the sole process invocation is `gh api --hostname github.com <endpoint>`, with no method/body options or shell. Repository path segments are URL-encoded. Failed commands, invalid UTF-8, invalid JSON, and malformed list responses fail closed.

Keep `branch_cleanup_audit.py` as the CLI composition and local-output layer. It reads and interprets canonical repository identity before subsequent reads. Same-repository filtering, classification, and evidence generation remain in the pure core. All candidates require human review and grant no deletion authority.

Replace exhaustive source-shape policing with behavioral tests of the core, adapter, and real composition using mocked native responses. New process/network capability requires independent architecture review. Module separation is not a Python sandbox or a restriction on credential permissions.

## Consequences and verification

The current implementation has no remote mutation path. Local JSON output remains intentional. Canonical identity, fork exclusion, review-required states, UTF-8 decoding, and exit-code semantics remain unchanged. Errors stop inventory generation; there is no mutation or force-recovery path.

Tests and review establish the current implementation's behavior; they do not prove arbitrary future code safe. Stronger runtime capability separation and any destructive executor remain separate work. Issue #22 is not implemented here, and ADR-0001's one-PR local closeout boundary is unchanged.

Exact-head focused regressions, a bounded real-GitHub Windows smoke, and independent review of this revised guarantee are required. Unavailable exact-head Actions evidence must remain explicit rather than being replaced with historical CI. Ready and merge remain human-final.
