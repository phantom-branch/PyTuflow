# Master protection and opt-in squash auto-merge

The intended sequence is Draft → Develop → Review → explicitly authorize
auto-merge → required CI green → squash merge. Repository-wide availability of
auto-merge never arms it for an individual PR. A ready PR stays open until its
owner merges it manually or explicitly requests auto-merge.

```powershell
gh pr merge NUMBER --auto --squash --repo phantom-branch/PyTuflow
gh pr merge NUMBER --disable-auto --repo phantom-branch/PyTuflow
```

The first command can merge immediately if all requirements already pass.
The second cancels pending auto-merge without closing the PR. Drafts cannot
merge. No workflow in this change arms auto-merge or merges a PR.

## Active repository configuration

Audit on 25 October 2026 found squash-only merging, auto-merge availability and
merged-branch deletion already enabled. There were no rulesets or legacy master
protection and no open PR had auto-merge armed. Repository merge settings and
permissions were preserved.

Ruleset **master PR protection**, ID **25816190**, matches only
`refs/heads/master`: PR required, zero approving reviews, no code-owner or
last-push approval, conversation resolution required, no force pushes or branch
deletion, linear history and squash-only merging. No bypass actors or merge queue.
Administrators retain repository administration permissions.

## Required checks after this workflow change is merged

Do **not** activate dependent check requirements before this PR is merged and
its checks have been verified. Then update this same ruleset (not an overlapping
rule) to require these GitHub Actions checks, integration ID **15368**:

- `Fast contracts gate`: both Windows Python 3.12/3.14 fast-contract jobs must
  succeed when the path classifier requires them.
- `Original library acceptance`: all three existing W5 regression lanes and
  both Python 3.12/3.14 installed-wheel jobs must succeed when applicable.

Both workflows run on every PR without workflow-level path filtering. Their
small classification/final-gate jobs always report. Documentation-only changes
explicitly classify substantive work as not required; the final gate verifies
the expensive jobs were skipped and reports that scope decision. A code/build/
fixture change requires successful execution, so a skipped, cancelled, failed or
missing substantive job cannot satisfy the gate. Git diff uses all files and
both sides of renames, without GitHub's 300-file path-filter limit. Explicit
workflow dispatch continues to run the substantive jobs.

Classification and final-gate control code use GitHub's merged PR checkout, so
an older documentation branch does not need to copy the new helper first.
Substantive Windows tests retain their exact PR-head checkouts. Existing code
branches still need to incorporate any CI infrastructure their own substantive
commands require; this change does not rewrite those branches automatically.

Existing regression, baseline integrity and wheel-smoke commands are unchanged.
Specialized QGIS, numerical, deferred and other workflows retain their existing
triggers and acceptance roles; these two repository-wide gates do not replace
their feature-specific acceptance evidence or native QGIS validation.

No strict-up-to-date requirement is added: results remain tied to the PR head
without forcing unrelated master updates to rerun costly checks. Failed or
pending required gates block merge; green gates make a non-draft PR eligible
subject to resolved conversations and mergeability. They do not request a merge.

## Verification and activation boundary

Validate classifier and fail-closed outcomes with `python -m pytest -q tests/ci`;
Actionlint validates both modified workflows. Hosted runs of this CI-only PR
validate the actual check names and GitHub Actions provider. No artificial PR
or merge is needed to exercise the docs classifier in tests. Actual docs-only
hosted execution and auto-merge completion cannot be demonstrated here without
creating/merging additional PRs, which are intentionally not done.

After the owner authorizes this CI PR's merge, read back the same ruleset and
add `required_status_checks` with those two contexts, `integration_id: 15368`,
`strict_required_status_checks_policy: false`, and
`do_not_enforce_on_create: false`. Re-read effective master rules, a development
branch (no rules expected), repository merge settings and all open PRs' per-PR
auto-merge fields. Do not arm any PR as part of configuration.
