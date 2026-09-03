## Goal / scope

- Goal:
- Durable work item (Issue/equivalent, required for `ELEVATED` / `HIGH_IMPACT`):
- Intended changed paths/components:

## Risk classification

- Level: `ROUTINE` / `ELEVATED` / `HIGH_IMPACT`
- Facets:
- Automatic escalation checked: yes / no

## Authority impact

- Authority domains touched:
- Authority changed? yes / no
- Protected effects involved:

## What changed

-

## What intentionally did not change

-

## Evidence

- Exact HEAD:
- Tests/local validation:
- CI:
- Real-boundary smoke (if applicable):
- Review independence level: L0 / L1 / L2 / L3

## Evidence invalidation

Which prior evidence became invalid because of this change?

-

## Residual findings / risk

Use `CRITICAL`, `MAJOR`, `MINOR`, or `NOTE` rather than reverse-numbered priority codes.

-

## Comprehension gate

Required level: C0 / C1 / C2

Owner should be able to explain:

- [ ] what changed and why;
- [ ] which authority owns the affected fact/state;
- [ ] major new/changed failure mode;
- [ ] first diagnostic location;
- [ ] rollback/recovery entry point;
- [ ] what the evidence does **not** prove;
- [ ] what remains human-decided.

## Human-final gates

- [ ] Ready has not been inferred from implementation/test/review completion.
- [ ] Merge has not been inferred from Ready or another approval.

## Post-merge local closeout

This is intentionally **not** a pre-merge acceptance checkbox. After the human merge, independently confirm the merged PR and close out local state before reporting the task locally closed.

- `python scripts/verify_local_closeout.py` remains the non-destructive verifier. For a linked topic worktree, supply the independently confirmed full PR head with `--expected-pr-head`.
- To retire only the merged PR's eligible topic residue, first run the separate dry-run planner: `python scripts/post_merge_cleanup.py --pr <PR_NUMBER>`.
- An explicit `--execute` performs cleanup only after fresh GitHub/local revalidation. Remote topic deletion remains off unless `--delete-remote` is explicitly requested and its exact expected-SHA lease passes.
- `SAFE CLEANUP: BLOCKED` means no cleanup effect was authorized. `SAFE CLEANUP: INCOMPLETE` means an earlier authorized effect may already have completed; stop and inspect rather than forcing recovery.
