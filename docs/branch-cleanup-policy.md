# Authoritative branch cleanup policy

This policy extends the post-merge local closeout rules in `BASELINE.md` and `AGENTS.md`. It does not replace `scripts/verify_local_closeout.py` or `scripts/post_merge_cleanup.py`.

The local post-merge helper answers whether one merged PR's worktree can be retired safely. This policy answers a different question: how to audit and clean accumulated GitHub branches across a repository without treating stale local refs, chat history, or PR closure alone as deletion authority.

## Authority and phases

Remote cleanup is a protected destructive effect. Keep these phases separate:

1. **inventory** — read current GitHub branches and PR state; no mutation;
2. **classify** — distinguish protected, retained, merged-present, moved/reused merged-name, open, closed-unmerged, and no-PR branches;
3. **plan** — construct an exact deletion target set;
4. **execute** — re-read mutable state and delete only the authorized exact targets;
5. **verify remote** — refetch GitHub branches and require zero residual targets;
6. **verify local** — only after remote verification, prune local remote-tracking refs and inspect/delete stale local branches separately.

Do not combine classification and destructive mutation into one opaque step.

## Authoritative sets

For a repository, model at least:

- `R`: `(branch name, current SHA)` pairs that currently exist on GitHub;
- `M`: `(head ref, head SHA)` pairs of merged PRs;
- `C = R ∩ M`: current branch identities whose exact current SHA is the head SHA of a merged PR.

Only `C` is eligible for automatic merged-branch deletion. Matching a historical merged PR by branch name alone is insufficient: the branch may have been reused or moved after the merge. A historical merged PR head that is already absent is not a deletion target.

Conversation history, agent summaries, prior script output, or stale `origin/*` refs are not authority for whether a remote branch currently exists.

## Classification

Use explicit states rather than a generic stale/clean boolean:

- `PROTECTED` — default/canonical branch or another explicit protected branch;
- `RETAINED_LONG_LIVED` — intentionally retained operational/long-lived branch;
- `MERGED_DELETE_CANDIDATE` — current GitHub branch whose exact current SHA matches a merged PR head SHA for the same ref;
- `MERGED_HEAD_MOVED_REVIEW_REQUIRED` — branch name has merged PR history but current SHA no longer matches any merged head SHA;
- `OPEN_PR` — branch associated with an open PR;
- `CLOSED_UNMERGED_REVIEW_REQUIRED` — closed PR branch with no merged PR;
- `NO_PR_REVIEW_REQUIRED` — current branch with no PR evidence.

### Closed-unmerged branches

Never bulk-delete a closed-unmerged branch merely because its PR is closed. Review it individually. At minimum inspect:

- PR title/body and close/superseded rationale;
- whether a replacement PR exists and is merged;
- current main-vs-branch ahead/behind state;
- unique implementation, evidence, PoC results, or operational material;
- whether the PR discussion itself is sufficient durable historical evidence.

Only after human review may such a branch become an explicit deletion target.

### No-PR branches

No PR does not mean orphaned. Compare the branch to main and inspect its purpose/content. Long-lived operational branches must be explicitly retained.

### Moved or reused merged-name branches

A current branch whose name appears in merged PR history but whose current SHA differs from every merged PR head SHA is never an automatic merged-delete target. Treat it as review-required because it may contain post-merge or reused-branch work.

## Native command semantics

For `git`, `gh`, and other native tools, process exit status is the success/failure authority. stderr is diagnostic evidence only.

A successful Git operation may write normal progress/status to stderr, and Windows PowerShell may render native stderr as `NativeCommandError`. stderr output alone does not prove failure.

When complex arguments matter, avoid shell re-parsing. In particular, Windows PowerShell 5.1 `Start-Process -ArgumentList` must not be assumed to preserve a complex `gh --jq` expression containing spaces/pipes as one argument. Prefer an argv-preserving invocation or parse GitHub JSON in the helper itself.

## Deletion requirements

A deletion plan must contain exact current branch identities. Automatic merged deletion requires the current branch SHA to equal the merged PR's head SHA. Human-reviewed closed-unmerged deletion requires an explicit expected SHA in the reviewed manifest.

Immediately before a destructive effect, re-read the branch and require the exact expected identity. A moved or missing reviewed branch blocks rather than silently changing the target set.

`MERGED_DELETE_CANDIDATE` may be selected automatically from the current authoritative inventory. `CLOSED_UNMERGED_REVIEW_REQUIRED` requires a human-reviewed exact target manifest. `MERGED_HEAD_MOVED_REVIEW_REQUIRED`, `OPEN_PR`, `NO_PR_REVIEW_REQUIRED`, `PROTECTED`, and `RETAINED_LONG_LIVED` are never automatic delete targets.

## Post-delete verification

A zero exit code from a delete command is necessary but not sufficient to report cleanup complete.

After the selected deletion set is processed:

1. refetch current GitHub branches;
2. intersect the exact target names with the fresh current set;
3. require `remaining_target_count == 0`;
4. confirm intended protected/retained branches still exist where relevant.

If any target remains, report cleanup as blocked/incomplete and stop. Do not use force recovery to make the report green.

## Local cleanup after remote verification

Only after remote cleanup is verified:

1. `git fetch --prune`;
2. verify the canonical checkout is clean and on the intended canonical branch;
3. list remaining local branches;
4. review/delete stale local branches separately;
5. verify final `git status --short --branch`, `git branch`, and `git branch -r`.

Remote cleanup success is not authority to discard dirty worktrees or unknown local content.

## Audit output

Large inventories, PR mappings, and native stdout/stderr belong in a temporary audit directory by default. Interactive output should normally contain counts, classifications, failures, and the audit path.

A project may promote a concise summary into durable project history when branch cleanup itself is operationally significant.

## Helper

Use:

```text
python scripts/branch_cleanup_audit.py
```

for inventory only. Explicit long-lived branches can be retained in the classification:

```text
python scripts/branch_cleanup_audit.py --retain orchestration
```

Plan deletion of current merged PR heads whose exact identity still matches the merged PR head:

```text
python scripts/branch_cleanup_audit.py --delete-merged
```

Execution is explicit:

```text
python scripts/branch_cleanup_audit.py --delete-merged --execute
```

Closed-unmerged deletion requires a human-reviewed JSON manifest containing exact branch and expected SHA pairs:

```json
[
  {
    "branch": "topic/example",
    "expected_sha": "0123456789abcdef0123456789abcdef01234567"
  }
]
```

Then plan first:

```text
python scripts/branch_cleanup_audit.py --delete-reviewed reviewed.json
```

and execute only after the plan is accepted:

```text
python scripts/branch_cleanup_audit.py --delete-reviewed reviewed.json --execute
```

The helper uses authenticated `gh` reads/writes, Python JSON parsing, argv-preserving native invocation, exact merged-head identity classification, exact-SHA pre-effect checks for reviewed targets, and authoritative post-delete residual verification.

## Relationship to other closeout tooling

- `verify_local_closeout.py`: non-destructive check for local/canonical readiness after one PR.
- `post_merge_cleanup.py`: fail-closed retirement of one merged PR's local worktree/switch state, with narrowly authorized optional remote topic deletion.
- `branch_cleanup_audit.py`: repository-wide authoritative remote branch inventory/classification and separately authorized cleanup.

Do not substitute one tool's successful result for another tool's authority boundary.

## Origin

This policy was added after a real `life-dashboard` branch cleanup exposed partial prior deletion, misleading native stderr rendering on Windows PowerShell, a branch believed deleted but still present on GitHub, closed-unmerged branches containing meaningful superseded work, and a no-PR long-lived `orchestration` branch that had to be retained. See ai-dev-starter Issue #20.
