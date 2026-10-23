# [W5] Establish regression coverage for original PyTuflow functionality

## Initial status

Draft scaffolding only: this PR currently adds a scoped work plan. Runtime changes and acceptance tests have not been implemented on this branch. Earlier review reproductions were isolated component checks, not full Windows/GIS integration validation.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `test/original-library-regression-ci`.
- PR base: `master`.
- Starting state: **Can start now**.
- This is an independent branch from master; it does not depend on the deferred optimisation PRs.
- Dependent work: W7 on `refactor/package-api-quality`.
- This work package owns shared regression and installed-wheel acceptance infrastructure for W1-W8; it does not implement their production fixes.

## Purpose

Documentation-only draft scaffold for a separate regression-infrastructure workstream. Establish an honest, reproducible baseline for the existing results, TMF, project and FM functionality, then add Windows and installed-wheel checks without changing the existing deferred acceptance gates. Base: master. This is the infrastructure parent of W7.

## Scope

- Inventory existing results, Python-mesh, QGIS, TMF, project and FM tests and their actual dependency/fixture requirements. Identify collection failures, missing backends, existing product failures and harness defects separately. The earlier static inventory found 1,771 test functions; this is not an executed test count or an acceptance target.
- Capture canonical upstream cf908cc922ca8448ed6002834877b0b377329eae and the current fork base in the same Windows environment. Preserve exact commit IDs, Python/package versions, collected/pass/fail/error/skip counts and JUnit reports. Record known baseline failures explicitly and gate unexpected regressions without treating an incomplete run as success.
- Add separate Windows Python 3.12 and 3.14 jobs for supported non-QGIS functionality, including results, project creation and FM conversion. Establish an explicit QGIS integration job or documented runnable job boundary using its real Python runtime. Missing QGIS may be an explained skip in non-QGIS jobs; a job designated to validate QGIS must fail if QGIS is unavailable.
- Make test collection independent of unavailable optional backends. Use narrow, named capability markers/collection boundaries and report skipped groups; do not blanket-skip a results suite or silence warnings to produce green CI.
- Build wheel/sdist and validate the installed wheel outside the source checkout: import origin, public imports, project CLI --help and representative packaged JSON/template/schema access. Smoke tests should use temporary generated model files and committed public fixtures only.
- Use a documented dependency baseline plus a current supported dependency job. Introduce lowest-supported dependency checks where the declared lower bounds are coherent. Production compatibility corrections belong to W7 or the responsible functionality workstream, not to hidden test workarounds.
- Own new general CI workflows, shared test helpers, fixture isolation and regression-baseline records. Preserve all existing deferred/graph workflow triggers, pins, gates and comparison semantics. Coordinate with W7 before editing README, pyproject.toml, dependency metadata or runtime imports; W7 owns those files.
- Keep generated test outputs in temporary directories, including FM conversion fixtures that currently use repository-relative outputs_tmp. Do not delete or overwrite public reference fixtures.

## Acceptance criteria

- [ ] A fresh agent can reproduce collection and the baseline using documented commands in the declared Windows environments; original upstream and current fork results are reported independently.
- [ ] Every required group is collected and executed, or has an explicit capability-bound skip with a recorded reason. An unavailable required backend, collection error, missing JUnit report or unexpectedly empty suite fails the relevant job.
- [ ] No new regression relative to the recorded current-fork baseline is accepted. Existing failures remain visible with exact test IDs and evidence; no broad xfail/skip or warning suppression hides them.
- [ ] Results, project and FM-only changes trigger the new relevant checks. Existing deferred gates continue to work unchanged.
- [ ] Wheel smoke tests run with a working directory outside the checkout and prove pytuflow.__file__ points to the installed package. Public CLI help and representative packaged resource loading pass.
- [ ] Reports give exact head/base SHAs, dependency versions, commands, test counts, skips and limitations. Do not report static test-function counts as executed tests or claim native Windows/QGIS validation from a Linux-only run.

## Exclusions

- No deferred/compiled-graph optimisation, acceptance redesign or edits to the existing deferred workflows.
- No mass production-code clean-up, numerical algorithm changes, blanket lint/type enforcement or cross-platform expansion.
- No TUFLOW or other proprietary solver execution, private SMB access, private datasets, release, merge, tag, publication or production dependency repin.
- No claim that all existing tests pass until the actual suites run in the stated environments.

## Source pointers

- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/tests/test_time_series.py
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/tests/test_map_output_pymesh.py
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/tests/test_map_output.py#L1-L7
- https://github.com/TUFLOW-Support/PyTuflow/tree/cf908cc922ca8448ed6002834877b0b377329eae/tests/project
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/tests/fm_lib/integration_tests/test_conversion.py#L15-L58
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pyproject.toml#L44-L61
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/README.md#L78-L124

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Continue implementation of this draft W5 PR after reading its latest body, comments, review threads, exact head/base SHAs and repository guidance. The initial PR contains planning documentation only; implement the bounded scope, do not stop after updating the plan. Work on this PR's branch using an isolated checkout/worktree if other agents are active. The parent is master. W7 is a child of W5 and owns package metadata, README and runtime import changes.

Start by recording the current remote head/base. The review reference is canonical upstream cf908cc922ca8448ed6002834877b0b377329eae and fork review head e162c04330d24c37bee3ade94479cc4602651060; these are historical references, not permission to reset a newer branch. Compare original upstream and the current fork in equivalent environments so pre-existing failures are separated from regressions.

Milestone 1 — Baseline and collection: inspect tests/test_time_series.py, tests/test_map_output_pymesh.py, tests/test_map_output.py, tests/tmf, tests/project and tests/fm_lib. The QGIS module currently imports qgis.core at collection time. Inventory dependencies and fixture side effects before execution. Collect and run each capability group independently and capture JUnit, versions, counts and exact failures. Do not conceal existing failures by broad skips, xfails, warning filters or weaker assertions.

Milestone 2 — General regression jobs: add independent Windows Python 3.12/3.14 coverage for the supported original-library groups. Separate QGIS integration and require its backend when that job is selected. Make outputs/project/FM paths trigger their jobs. Add a trustworthy baseline comparison where required, with missing/empty reports and unexpected skipped groups failing. Keep all existing deferred workflows unchanged. W5 owns shared test helpers, fixtures and these new workflows; discuss any pyproject/README changes with W7 first.

Milestone 3 — Distribution smoke tests: build wheel/sdist and use a fresh environment outside the checkout to verify the installed wheel, exported API, packaged JSON/templates/schema and project CLI --help. Ensure the import path cannot accidentally use repository sources. Use temporary directories and only committed public fixtures; FM conversion tests must not overwrite their reference outputs.

Initial Windows command patterns, after confirming files/dependencies and backend groups:
  py -3.12 -m pip install -e . pytest build
  py -3.12 -m pytest --collect-only -q tests/test_time_series.py tests/test_map_output_pymesh.py tests/project tests/tmf tests/fm_lib
  py -3.12 -m pytest -q tests/test_time_series.py tests/test_map_output_pymesh.py tests/project tests/tmf tests/fm_lib --junitxml=<temporary-report-path>
  py -3.14 -m pip install -e . pytest build
  py -3.14 -m pytest -q <same-reviewed-capability-groups> --junitxml=<temporary-report-path>
  py -3.14 -m build
Use separate commands for QGIS under the verified QGIS interpreter; do not assume py -3.14 provides it. Treat the command patterns as a starting point: fix collection grouping in the harness, not by silently omitting failed groups. Inspect subprocess tests first; only Python CLI/help/conversion operations are allowed, never a solver launch. Use normal PowerShell statements and exit-code checks so a failed pytest/build command cannot be hidden by a later successful command.

Coordinate with W7 on public dependency support and with the other workstreams on shared fixtures. Any production failure discovered here must be recorded with a minimal reproduction and assigned to its owning workstream. Do not make unrelated algorithm fixes merely to turn the baseline green.

Before reporting completion, run the new exact-head jobs, the relevant original regressions and git diff --check. Report changes, exact source/environment, counts, remaining baseline failures, backend skips, wheel origin/resource evidence and CI URLs. Leave the PR draft if any required implementation or validation remains. Do not merge, publish, tag, run a solver, access private SMB models or repin production consumers.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
