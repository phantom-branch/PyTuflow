# Integrated acceptance and single-upstream-PR preparation

> **Work-package status:** Draft planning and audit tooling. **Not** the upstream
> submission. The consolidated production acceptance and curated upstream
> branch remain to be executed after prerequisite merges.

## Objective

Produce **one** final, reviewable contribution from the finished fork to
[`TUFLOW-Support/PyTuflow`](https://github.com/TUFLOW-Support/PyTuflow).
First prove consolidated regression parity on a frozen, assembled fork
revision; then audit the full canonical-upstream-to-fork delta, curate the
changes, prepare one upstream-targeted branch and submit **one** upstream PR
when its scope and evidence are accepted.

This fork PR is an **integration gate and handoff**, not an alternate release,
a place to merge unfinished production branches, or an automatic upstream
submission. Keep its diff limited to read-only audit/report tooling, test
checks, documentation and evidence. Leave it **draft** until the work is
completed. Do not rename, rebase, cherry-pick or merge another agent's branches.

## Live prerequisites (inspect again before any acceptance)

- [#34: pandas 3.1 materials parser](https://github.com/phantom-branch/PyTuflow/pull/34)
  must be merged and CI/review accepted.
- [#20: bounded raster cache/NetCDF recovery](https://github.com/phantom-branch/PyTuflow/pull/20)
  must be merged and exact-head CI, native MDAL parity and benchmark evidence
  accepted. Its prior QGIS/SMB results are revision-specific; verify code
  identity across any base integrations.
- Source fork `master` when this package was created:
  `0aba6b79db0ecc4922b910867f2c96905acb8d3a`.
  Source official upstream `master` then:
  `cf908cc922ca8448ed6002834877b0b377329eae`.
  **These are reference checkpoints, not final-candidate identities.**
  Re-fetch and freeze both exact SHAs at execution time.
- Upstream audit [#29](https://github.com/phantom-branch/PyTuflow/pull/29)
  remains diagnostic only. Python 3.10 syntax is the intended *typing syntax*
  floor if independently supported; QGIS/Python 3.12 and standalone 3.14
  must remain working. Do not lower runtime metadata just to match original
  upstream's incorrect 3.9 claim.
- Optional, not prerequisite by default: Linux deferred follow-up #4,
  diagnostic profiling PRs #24/#25/#28, experimental benchmark branches.
  Escalate a diagnostic finding into a scoped fix only if a regression warrants it.

## Milestone A — Freeze and run the complete consolidated acceptance

1. Verify #34 and #20 merged; obtain a clean **normal** fork checkout at the
   resulting exact `master` SHA, plus a separate clean checkout of official
   upstream at its newly verified `master` SHA. Do not use virtualenvs or
   new Git worktrees. Confirm no test run changes tracked source or fixtures.
2. Run all applicable hosted workflows against the frozen candidate:
   original-library regression (Windows Python 3.12/3.14 pinned and Python
   3.14 current dependencies), independently built **installed wheels**
   (3.12/3.14) and external typing consumer, package/API (3.12/3.13/3.14),
   TMF materials/legacy tests, result-time/numerical and raster-cache
   coverage, pandas 3.1 output checks, deferred references, batch compiler /
   activation, tutorial example parity and safe-save/input checks.
   **Record every job's actual conclusion.** A workflow missed due to
   path filters is **not** a pass. Trigger a frozen-commit `workflow_dispatch`
   or approved manual equivalent and record the exact SHA.
3. Use the existing, unchanged W5 runner `ci/run_regression.py` and
   strict `ci/compare_regression.py`, with source identities from actual
   checkouts. Require the complete standalone groups
   `time_series python_mesh tmf project fm` and independently verify
   canonical-upstream completeness. **Do not redefine the fixed fork
   baseline** or assume historical raw failures remain after merged fixes;
   record current raw failure IDs and source/output signatures.
4. Native Windows OSGeo4W QGIS (real QGIS/MDAL) must run the **complete**
   `--group qgis` module (`tests/test_map_output.py`, historically 239),
   with strict baseline/candidate comparisons and public provider controls.
   Reuse the known-good QGIS environment and no stubs. If QGIS 3 LTR is
   available, record that separately; **do not silently assert it passed**.
5. A single authorised Windows SMB agent alone handles any **required**
   latest-head native performance checks, especially W4 caching or P4 batch
   performance. Older matched measurements may be reused only if compared
   implementation hashes are unchanged. Keep model/host/path details and
   raw NAS reports local; publish sanitised aggregate evidence only.
6. Collect JSON/JUnit/logs/source hashes, interpreter/dependency/QGIS/MDAL
   versions, exact command lines and comparator output. Label inherited
   failures versus newly introduced failures. Zero new regressions,
   complete required groups, no suppressed warnings/changed fixtures or
   unknown skips are necessary. Any failed gate blocks readiness.
7. Publish one traceable acceptance matrix on this PR, referencing the
   actual workflow runs and authorised local QGIS and SMB comment URLs.

## Milestone B — Curate the official-upstream delta

1. Verify official upstream `master` before diffing; pin it by SHA, not by
   URL or assumption. Compare the full fork head to the exact upstream
   SHA, including `pytuflow/**`, tests, packaging, workflows, docs, typing
   exports, deferred APIs and third-party helper changes.
2. Use the read-only `ci/upstream_delta.py` inventory (see below) to
   document each changed file. It categorises *locations*, not approval.
   For each functional change make a human-reviewed **keep / revise /
   exclude** decision with an upstream-facing rationale and the originating
   fork PR/commit. Do not mistake file counts for behavioural parity.
3. Audit default installation, all public imports and class identity, QGIS
   3/4/Python support, PEP 561 typing, CLI/cache semantics, file ordering,
   save/undo fidelity, numerical outputs and references. Compare against
   the **official upstream**, not just fork's earlier fixed baseline.
4. Explicitly flag scope risk: optional deferred/context/batch-graph API
   changes, shared-cache performance optimisations, package metadata
   support changes, generated project artifacts and diagnostic-only tools.
   Do not expand upstream surface without evidence and a clear explanation.
5. Prepare **one** upstream branch in this fork based on the refreshed
   official upstream `master`, using a clean normal checkout and preserving
   all history on fork `master`. Curate reviewable commits by topic on that
   branch; do not submit separate upstream PRs. Check the final diff contains
   only approved files, no private reports or internal-only diagnostics.
6. Re-run the relevant consolidated acceptance on the actual curated
   upstream branch (it is a **different candidate** from fork master).
   If something was excluded, confirm its absence is deliberate and does not
   silently break dependencies.
7. Submit **one** upstream-targeted PR only after an explicit readiness
   record accepts its scope, test results, upstream head and review. Do not
   merge the upstream contribution on the user's behalf.

## Executable upstream-delta inventory

After fetching canonical upstream into the chosen *normal* fork checkout (or
ensuring the upstream commit is already available), run:

```powershell
python ci/upstream_delta.py --repository . `
    --upstream-ref <EXACT_CANONICAL_SHA> `
    --candidate-ref <EXACT_FORK_SHA> `
    --output "F:/Temp/PyTuflowUpstreamReview/upstream-delta.json"
```

- The inventory is **read-only** and refuses dirty sources, missing revisions
  and report paths within the checkout.
- Output includes exact commit identities, ancestry, renamed/deleted files and
  grouped path counts; it does not invent per-file semantic decisions or test
  acceptance.
- Before publishing, inspect path labels for private content. Do **not**
  upload model names, private SMB paths, profiles, hostnames or command rows.
- Use `git diff --find-renames` and direct code review for the detailed
  provenance/keep-exclude decisions. The tool is not a replacement for
  human judgement.

## Final acceptance and ownership

- All required gates accepted against *exact* frozen SHAs.
- Every changed source file has provenance and an explicit upstream
  keep/revise/exclude disposition.
- No duplicate source, cherry-pick or feature-drift debris.
- Final upstream branch's test evidence is its own, not merely the fork's.
- Codex review has no unresolved actionable findings.
- **One** official upstream PR is the deliverable, not one PR per fork
  workstream. Leave this integration PR draft until evidence is complete.
- No local solver execution, package release, publishing, private model upload,
  or automatic Linux acceptance. Australian English in all reporting.

## Agent work division

- **Integration agent:** frozen SHA matrix, hosted workflows, file audit and
  new read-only `ci/upstream_delta.py` checks; owns this PR's docs/CI.
- **QGIS/SMB agent:** real native QGIS/MDAL and, if justified, network
  benchmarking; publishes sanitised outcomes only.
- **Upstream-review agent:** read official upstream baseline, curate
  behavioural/API diff and design a single branch; avoid touching other
  agent branches. Do not start external PR before approval.

The ownership boundary prevents test/tool changes from being mixed into
functional PRs #20/#34 or unmerged diagnostics.

## Preliminary GitHub source-delta triage (not final readiness)

A read-only comparison at PR creation used official upstream
`cf908cc922ca8448ed6002834877b0b377329eae` against fork
`0aba6b79db0ecc4922b910867f2c96905acb8d3a`. GitHub reported the
fork **64 commits ahead**, **zero behind**, and **214 changed file paths**.
Location-only provisional buckets: **55** `pytuflow/` production,
**47** `tests/`, **20** `ci/` or `.github/workflows/`, **84**
`docs/` or `agent_workstreams/`, and **8** other paths. In this snapshot
the latter eight include `README.md`, project/deferred design notes and
`pyproject.toml`. These counts have not been checked by the new local
inventory script yet and **must not be treated as an approved file list**.

This already demonstrates why directly submitting fork `master` upstream
is inappropriate: the comparison contains internal benchmark and validation
reports, local planning handoffs, feature-specific acceptance workflows and
substantial deferred/batch additions alongside substantive bug fixes. The
upstream review needs explicit **keep / revise / exclude** decisions.

The final comparison must be rerun after #34/#20 merge and after any new
official upstream commits. If the upstream SHA changes, freeze a new pair
and do not silently reuse these historical numbers.
