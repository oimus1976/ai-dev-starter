# Public Repository Readiness

Use this runbook before changing a repository from private to public. Publication is a security/privacy/reuse boundary, not a billing optimization.

A clean working tree, a clean current `main`, or a search over current files alone is **not** enough evidence. Publication can expose Git history, commit metadata, Issues/PRs, Actions history and logs, artifacts, releases, and other GitHub-hosted metadata.

## Authority and states

This procedure separates four states:

1. `AUDIT` — read-only evidence gathering.
2. `REMEDIATION` — tracked fixes or separately approved cleanup.
3. `READY_FOR_HUMAN_GATE` — no known blocker remains, but visibility is still private.
4. `PUBLISHED_VERIFIED` — a human changed visibility and post-publication verification passed.

Any uncertainty, incomplete scan, unresolved secret/private-data finding, redistribution uncertainty, unsafe workflow boundary, or unresolved license decision means `BLOCKED`.

`READY_FOR_HUMAN_GATE` is evidence, not authority to publish. The private -> public visibility change remains a separate human action.

## 1. Pin the audit target and create an isolated audit clone

Audit an exact GitHub state in a disposable clone rather than relying on whichever refs happen to exist in a development checkout. The audit clone is read-only with respect to GitHub; do not push from it.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repoSlug = 'OWNER/REPO'
    $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
    $auditRoot = Join-Path $env:TEMP "ai-dev-starter-logs\public-readiness\$ts"
    $auditRepo = Join-Path $auditRoot 'repo'
    $logDir = Join-Path $auditRoot 'evidence'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    gh repo clone $repoSlug $auditRepo -- --no-checkout
    if ($LASTEXITCODE -ne 0) { throw 'audit clone failed' }

    # A normal clone gets current branch refs. PR heads are a separate GitHub ref
    # namespace and are fetched into audit-only remote-tracking refs so --all
    # includes them without changing the development checkout.
    git -C $auditRepo fetch origin '+refs/pull/*/head:refs/remotes/audit-pr/*'
    if ($LASTEXITCODE -ne 0) { throw 'PR-head ref fetch failed' }

    $head = (git -C $auditRepo rev-parse origin/main).Trim()
    $defaultBranch = (gh repo view $repoSlug --json defaultBranchRef --jq '.defaultBranchRef.name').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'default-branch read failed' }
    $head = (git -C $auditRepo rev-parse "origin/$defaultBranch").Trim()

    @(
        "AUDIT_REPOSITORY=$repoSlug"
        "AUDIT_DEFAULT_BRANCH=$defaultBranch"
        "AUDIT_HEAD=$head"
        "AUDIT_REPO=$auditRepo"
    ) | Set-Content -Encoding utf8 (Join-Path $logDir 'audit-target.txt')

    "AUDIT_ROOT=$auditRoot"
    "AUDIT_REPO=$auditRepo"
    "EVIDENCE_DIR=$logDir"
}
```

Record the exact SHA in the repository-specific audit record. If the intended publication SHA changes, evidence from the old SHA does not automatically cover the new one.

The audit clone deliberately remains under `%TEMP%` after the procedure so cleanup is not silently coupled to evidence generation. Remove it later only after the evidence has been reviewed and any needed local records have been retained.

## 2. Scan branches, tags, and GitHub PR-head refs for secrets

Use a dedicated secret scanner that scans Git history. The canonical example is Gitleaks. Record the exact scanner version before interpreting the result.

Gitleaks `git` mode uses Git history and accepts `git log` options through `--log-opts`; `--all` therefore scans the current refs present in the isolated audit clone, including the fetched `audit-pr/*` refs.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $auditRepo = '<AUDIT_REPO from step 1>'
    $logDir = '<EVIDENCE_DIR from step 1>'

    gitleaks version | Set-Content -Encoding utf8 (Join-Path $logDir 'gitleaks-version.txt')
    if ($LASTEXITCODE -ne 0) { throw 'gitleaks version failed' }

    $report = Join-Path $logDir 'gitleaks-history.json'
    gitleaks git --redact=100 --report-format json --report-path $report --exit-code 42 --log-opts='--all --full-history' $auditRepo
    $code = $LASTEXITCODE

    if ($code -eq 0) {
        'GITLEAKS_HISTORY=PASS' | Set-Content -Encoding utf8 (Join-Path $logDir 'gitleaks-result.txt')
    } elseif ($code -eq 42) {
        'GITLEAKS_HISTORY=FINDINGS_REVIEW_REQUIRED' | Set-Content -Encoding utf8 (Join-Path $logDir 'gitleaks-result.txt')
        throw 'Gitleaks found reviewable history findings; publication remains BLOCKED'
    } else {
        "GITLEAKS_HISTORY=TOOL_ERROR exit=$code" | Set-Content -Encoding utf8 (Join-Path $logDir 'gitleaks-result.txt')
        throw "Gitleaks failed with exit $code"
    }
}
```

Do not paste detected secret values into Issues, PRs, chat, or durable shared logs. Keep the redacted report local. A finding is not cleared merely because the current file no longer contains the value.

A zero-finding Gitleaks result clears only the scanner/ruleset scope. It does **not** prove that Issues, PR comments/attachments, Actions logs, unusual credentials, personal data, or redistribution-sensitive material are safe.

If a real secret was ever committed, revoke/rotate it first. History rewriting, if still desired, is a separate consequential human decision; do not rewrite shared history automatically.

## 3. Review commit metadata and historical object names

Commit author identity and email addresses become publication metadata. Review them intentionally. Use the same isolated audit clone so PR-head commits are included.

```powershell
$auditRepo = '<AUDIT_REPO from step 1>'
$logDir = '<EVIDENCE_DIR from step 1>'

git -C $auditRepo log --all --date=iso-strict --format='%H`t%an`t%ae`t%ad`t%s' |
    Set-Content -Encoding utf8 (Join-Path $logDir 'commit-metadata.tsv')
if ($LASTEXITCODE -ne 0) { throw 'git log failed' }

git -C $auditRepo rev-list --objects --all |
    Sort-Object -Unique |
    Set-Content -Encoding utf8 (Join-Path $logDir 'historical-object-names.txt')
if ($LASTEXITCODE -ne 0) { throw 'git rev-list failed' }
```

Review at least:

- author names and email addresses;
- commit subjects for private case/project names;
- deleted/renamed path names for personal, organization-internal, host, share, or case identifiers;
- unexpected binary/vendor assets.

A privacy-sensitive filename can remain visible in history even when its contents were later removed.

PR-head fetching materially broadens the reachable audit set, but it still does not prove absence from every GitHub-retained unreachable object or platform database. Issues/PR discussion, attachments, and Actions are reviewed separately below.

## 4. Review redistribution and license state

Before publication, classify the repository as one of:

- source-visible only, with no permission granted beyond applicable copyright law; or
- reusable/open source, with an explicit project license.

If reuse is intended, absence of a project license is a publication blocker until the human owner selects one. Do not confuse a project license with dependency or third-party notices.

Review third-party source, copied snippets, vendored binaries, fonts, images, fixtures, model/data files, and generated bundles separately. If redistribution rights are unclear, keep the repository private or remove/replace the material through a reviewed change.

## 5. Review GitHub-hosted metadata while the repository is private

Inspect all publication surfaces, not only Git:

- repository description, topics, homepage, default branch;
- Issues, comments, attachments, and edited descriptions;
- PR descriptions, reviews, review comments, attachments, and patches;
- Actions run history and logs;
- retained Actions artifacts;
- releases and release assets;
- Discussions/Wiki/Pages if enabled.

For large repositories, inventory first and record what was reviewed. Search high-risk terms, but do not treat keyword search as proof of absence.

Useful inventories with GitHub CLI:

```powershell
$repo = 'OWNER/REPO'
$logDir = '<EVIDENCE_DIR from step 1>'

gh repo view $repo --json nameWithOwner,visibility,isPrivate,defaultBranchRef,description,homepageUrl,licenseInfo |
    Set-Content -Encoding utf8 (Join-Path $logDir 'github-repository.json')

gh issue list --repo $repo --state all --limit 1000 --json number,title,state,url |
    Set-Content -Encoding utf8 (Join-Path $logDir 'github-issues.json')

gh pr list --repo $repo --state all --limit 1000 --json number,title,state,isDraft,url,headRefName,baseRefName |
    Set-Content -Encoding utf8 (Join-Path $logDir 'github-prs.json')

gh run list --repo $repo --limit 1000 --json databaseId,name,event,status,conclusion,headSha,createdAt,url |
    Set-Content -Encoding utf8 (Join-Path $logDir 'github-actions-runs.json')

gh release list --repo $repo --limit 1000 |
    Set-Content -Encoding utf8 (Join-Path $logDir 'github-releases.txt')

gh api --paginate "repos/$repo/actions/artifacts?per_page=100" --jq '.artifacts[] | [.id,.name,.expired,.workflow_run.id] | @tsv' |
    Set-Content -Encoding utf8 (Join-Path $logDir 'github-actions-artifacts.tsv')
```

The inventory files may themselves contain publication-sensitive metadata. Keep them local unless deliberately sanitized.

### Actions logs

Private -> public conversion exposes Actions history and logs. Therefore old run logs are part of the publication surface.

Review all retained run logs. Prefer scanners that report only run ID + finding category; do not create a new giant plaintext archive of logs containing possible secrets. If a run log contains sensitive data, publication remains blocked until the owner decides whether the run/log can be removed and whether any credential must be revoked.

### Issues and PRs

Real local paths, device names, internal URLs, email addresses, pasted logs, screenshots, and attachments may exist in Issues/PRs even when the Git tree is clean. Classify each finding as:

- acceptable/public by design;
- redact/remove before publication;
- blocking because removal cannot reliably eliminate the exposure.

Do not silently rewrite historical discussion merely to make the audit pass.

## 6. Review public-fork workflow safety

Before publication, inspect every workflow and reusable action for the trust-boundary change introduced by untrusted forks.

At minimum verify:

- explicit minimal `permissions:`;
- checkout credentials are not persisted unless required;
- no secret-bearing job executes untrusted PR code;
- `pull_request_target` is absent or has a separately reviewed safe design;
- no untrusted artifact/cache content crosses into privileged jobs without validation;
- environment/deployment/write credentials are not reachable from ordinary fork PR execution;
- self-hosted runners are not exposed to arbitrary fork code;
- third-party Actions are pinned according to project policy.

A workflow that is safe for a private owner-only repository may be unsafe after publication.

## 7. Record pre-publication repository protection state

Read current protection/ruleset state from authoritative GitHub. Feature availability may differ between private and public visibility or by plan.

Do not write `ENFORCED` or `VERIFIED` merely because a policy document says direct main writes are forbidden.

If the current plan cannot enforce the desired protection while private, record that as a pre-publication limitation. Prepare the desired public-state rule, but do not claim it exists before authoritative post-change verification.

## 8. Human publication gate

Publication is allowed only when the repository-specific audit record says `READY_FOR_HUMAN_GATE` and identifies the exact audited SHA.

The human owner reviews at least:

- unresolved/redacted secret scan findings: none;
- private-data/platform-metadata findings: accepted or remediated;
- license/reuse decision: explicit;
- third-party redistribution: acceptable;
- fork/workflow boundary: acceptable;
- post-publication protection plan: prepared;
- exact SHA still equals the audited SHA or the audit has been refreshed.

Only then may the owner change visibility. Automation, CI success, review success, or this runbook alone never changes repository visibility.

## 9. Post-publication verification

Immediately after the human changes visibility, verify authoritative GitHub state:

- repository is `public` and the intended default branch is unchanged;
- expected Issues/PRs/Actions history are visible as intended;
- branch protection/rulesets are created or enabled as planned and read back from GitHub;
- required status checks refer to unique current job names;
- Actions permissions and fork-PR settings match the reviewed model;
- no unexpected Pages/package/release surface became public;
- a read-only unauthenticated/public smoke can fetch only content intended to be public.

If post-publication protection cannot be established as planned, record the deviation explicitly and decide whether to return the repository to private visibility. Returning to private does not prove that already published/forked/cloned information disappeared.

## Evidence language

Use one terminal state in the repository-specific audit record:

- `BLOCKED` — a blocker or incomplete required audit remains.
- `READY_FOR_HUMAN_GATE` — audit complete for an exact SHA; publication is still private and requires a human action.
- `PUBLISHED_VERIFIED` — human publication occurred and post-publication verification passed.

Never use `PASS` alone for a pre-publication audit because it can be mistaken for publication authority.
