# Authoritative branch audit policy

This policy extends the post-merge local closeout rules in `BASELINE.md` and `AGENTS.md`. It does not replace `scripts/verify_local_closeout.py` or `scripts/post_merge_cleanup.py`.

`branch_cleanup_audit.py` answers a repository-wide **audit** question: what branches currently exist on github.com, what same-repository PR evidence is associated with them, and which branches require human review before any later cleanup decision.

It deliberately does **not** delete remote branches.

## Authority and scope

Current branch existence, current branch SHA, current GitHub-protected state, repository default branch, canonical repository identity, and PR state are read from authenticated `github.com` APIs. Conversation history, prior agent summaries, stale local `origin/*` refs, and prior cleanup output are not authority for current remote state.

The helper pins GitHub CLI API reads to `github.com`; `GH_HOST` must not silently redirect audit authority to another host.

The operator supplies `OWNER/REPO`, but that spelling is not itself the same-repository comparison authority. The helper first reads repository metadata from github.com, obtains GitHub's canonical `full_name`, and then uses that canonical identity for branch reads, PR reads, same-repository PR filtering, and the inventory `repository` field. The original operator spelling is retained separately as `requested_repository` for diagnosis. This prevents valid case variants, redirects, or renamed-repository resolution from silently discarding same-repository PR evidence.

The helper has no remote mutation capability:

- no `git push`;
- no GitHub ref DELETE;
- no `--execute`;
- no `--delete-merged`;
- no `--delete-reviewed`.

Its output is evidence for human review only.

## Audit/read architecture boundary

PR #21 separates three responsibilities (see ADR-0002):

- `scripts/branch_cleanup_core.py` interprets supplied repository metadata, branches, and PRs; classifies branches; and generates review candidates and JSON. It has no process, network, filesystem, or clock I/O. The caller supplies the timestamp.
- `scripts/branch_cleanup_github.py` exposes only repository metadata, branch-list, and pull-request-list reads. It builds the endpoints internally and performs authenticated `gh api --hostname github.com <endpoint>` reads without method overrides, request bodies, or shell execution. Native exit status and UTF-8 decoding remain authoritative.
- `scripts/branch_cleanup_audit.py` composes those reads with the pure core and writes local evidence. It resolves GitHub's canonical identity before requesting branches and PRs.

The guarantee is about the current reviewed production implementation: it contains no remote mutation path and emits no deletion authority. AST/source-shape tests are not a complete security boundary and cannot prove all future Python forms mutation-free. The former exhaustive capability validator and its alias/import fixtures are replaced by tests of the pure core, the narrow read operations, failure handling, and the composed inventory path down to mocked native calls.

Any new process/network capability is an architecture-boundary change requiring independent review. This module separation does not restrict the permissions of the operator's GitHub credentials. Stronger runtime capability enforcement requires separate design; destructive execution remains scoped to Issue #22.

## Why deletion was scoped out

Independent review of PR #21 exposed a structural limitation: GitHub branch name + SHA + PR history does not provide a stable branch-incarnation identity. A branch may be deleted and later recreated at the same name and same SHA for a different purpose. Historical merged-PR evidence cannot distinguish those incarnations.

The same review also exposed host-binding, mutable push-destination, PR/protection TOCTOU, and post-effect failure-classification gaps in the earlier executor design.

Per the baseline anti-loop rule, the destructive executor was removed instead of receiving another sequence of local safety patches. Any future destructive executor is tracked separately in Issue #22 and must define explicit human authorization and its accepted residual-race model before implementation.

## Authoritative sets

For a repository, the audit models at least:

- `R`: current `(branch name, SHA)` pairs that exist on github.com;
- `M`: `(head ref, head SHA)` pairs from merged PRs whose `head.repo.full_name` equals the canonical repository `full_name` returned by github.com.

An exact `(name, SHA)` match between `R` and `M` is useful review evidence. It is **not deletion authority**, because it cannot prove branch incarnation.

Fork PRs never contribute same-repository branch evidence merely because they use the same `head.ref`.

## Classification

Use explicit states:

- `PROTECTED` — default branch or any branch GitHub currently reports as protected;
- `RETAINED_LONG_LIVED` — explicitly retained operational/long-lived branch;
- `MERGED_REVIEW_CANDIDATE` — current name+SHA exactly matches a same-repository merged PR head; human review still required;
- `MERGED_HEAD_MOVED_REVIEW_REQUIRED` — branch name has merged PR history but current SHA differs from all merged head SHAs;
- `OPEN_PR` — associated with an open same-repository PR;
- `CLOSED_UNMERGED_REVIEW_REQUIRED` — closed same-repository PR evidence without a merged PR;
- `NO_PR_REVIEW_REQUIRED` — no same-repository PR evidence.

`MERGED_REVIEW_CANDIDATE` replaces the earlier `MERGED_DELETE_CANDIDATE` concept. Exact name+SHA correlation is evidence, not proof that a later delete is safe.

### Closed-unmerged branches

A closed-unmerged branch requires individual human review. At minimum inspect:

- PR title/body and close/superseded rationale;
- whether a replacement PR exists and is merged;
- current main-vs-branch comparison;
- unique implementation, evidence, PoC results, or operational material;
- whether the PR discussion is sufficient durable historical evidence.

### No-PR branches

No PR does not mean orphaned. Compare the branch to main and inspect its purpose/content. Long-lived operational branches should be explicitly retained.

### Moved/reused merged-name branches

A current branch whose name appears in merged PR history but whose current SHA differs is review-required. Even an exact SHA match remains human-review evidence only because branch incarnation is not observable.

## Native command semantics

For native tools such as `gh`, process exit status is the command success authority. stderr is diagnostic evidence only.

A successful native operation may write normal progress/status to stderr, and Windows PowerShell may render native stderr as `NativeCommandError`. stderr output alone does not prove failure.

Native stdout/stderr used by the helper are decoded explicitly as UTF-8 so GitHub CLI JSON is not decoded through a Windows legacy code page such as cp932.

When complex arguments matter, preserve argv directly rather than relying on shell or Windows PowerShell re-parsing.

## Audit output

The helper writes two UTF-8 JSON files to an explicit or OS-temp audit directory:

- `inventory.json` — complete authoritative branch classifications and compact PR evidence;
- `review-candidates.json` — exact branch/SHA/classification/PR evidence for branches requiring later human review.

Every entry in `review-candidates.json` records:

- `human_review_required: true`;
- `deletion_authority: false`.

The inventory records `source_host: github.com`, canonical `repository`, diagnostic `requested_repository`, and `mutation_capability: NONE`.

Large inventories belong in the audit directory; interactive output should normally show counts, classifications, host, mutation capability, and the audit path.

## Helper

Use an explicit repository identity:

```text
python scripts/branch_cleanup_audit.py --repository OWNER/REPO
```

Optionally classify intentional long-lived branches:

```text
python scripts/branch_cleanup_audit.py --repository OWNER/REPO --retain orchestration
```

The command performs inventory/classification only. There is no destructive mode.

## Relationship to other closeout tooling

- `verify_local_closeout.py`: non-destructive check for local/canonical readiness after one PR.
- `post_merge_cleanup.py`: narrowly scoped post-merge local/worktree cleanup with its own authority boundary.
- `branch_cleanup_audit.py`: repository-wide authoritative github.com branch inventory/classification and human-review evidence generation, with **no remote mutation capability**.

Do not substitute one tool's successful result for another tool's authority boundary.

## Future destructive execution

Issue #22 is the only current follow-up for a repository-wide remote deletion executor. It must not infer automatic deletion authority solely from a `MERGED_REVIEW_CANDIDATE` classification or from name+SHA correlation.

Any future executor must separately define and review:

- explicit human authorization artifact;
- repository host and destination binding;
- branch-incarnation ambiguity;
- unavoidable review-to-effect and precondition-to-effect races;
- effect-phase `BLOCKED` versus `INCOMPLETE` semantics;
- authoritative post-delete verification;
- disposable-repository destructive real-boundary tests before production use.

## Origin

This policy was added after a real `life-dashboard` branch cleanup exposed partial prior deletion, misleading native stderr rendering on Windows PowerShell, a branch believed deleted but still present on GitHub, closed-unmerged branches containing meaningful superseded work, and a no-PR long-lived `orchestration` branch that had to be retained. See Issue #20 and the architecture-reset record on PR #21.
