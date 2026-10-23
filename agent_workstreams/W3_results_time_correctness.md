# [W3] Correct result timestep selection and NetCDF time units

## Initial status

Draft scaffolding only: this PR currently adds a scoped work plan. Runtime changes and acceptance tests have not been implemented on this branch. Earlier review reproductions were isolated component checks, not full Windows/GIS integration validation.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `fix/results-time-correctness`.
- PR base: `master`.
- Starting state: **Can start now**.
- This is an independent branch from master; it does not depend on the deferred optimisation PRs.
- Dependent work: W4 on `fix/raster-cache-reader-recovery`.
- Common regression/integration coordination: **W5**, `test/original-library-regression-ci`. Existing acceptance workflows must remain intact.

## Purpose

Documentation-only implementation scaffold. Correct inherited result-time defects, preserving public extraction interfaces and proving equivalent physical times across supported NetCDF units. No implementation or full integration validation has been completed by this scaffold.

## Scope

- Base: master. This is the parent of W4; W8 is independent. W5 supplies common CI gates without creating a branch dependency.
- Correct the reversed previous/next branches in Output._closest_time_index and document boundary and tolerance behaviour without gratuitous API changes.
- Normalise supported NetCDF time units at the NCGrid reader boundary before deriving metadata or absolute datetimes; preserve the original units/reference metadata.
- Cover exact, in-between, nonuniform and single-timestep cases, distinguishing a genuine temporal sample from the existing static-result convention.
- Review the Output.times metadata-column guard and time-step derivation for empty or singleton inputs as part of the same time contract.

## Acceptance criteria

- [ ] For available times [0, 1, 2] and request 0.6, previous selects 0 and next selects 1; exact hits and documented endpoint behaviour remain stable.
- [ ] Tiny equivalent NetCDF fixtures using seconds, minutes and hours return the same relative hours, absolute datetimes and extracted samples. Other claimed supported units are either converted correctly or rejected explicitly.
- [ ] Numeric and datetime requests select the same physical sample; nonuniform axes, empty metadata and a legitimate single temporal sample receive explicit tested handling.
- [ ] Meaningful regression tests fail on the inherited baseline, pass on the candidate, and run on Windows Python 3.12 and 3.14 under the common acceptance contract.
- [ ] Run relevant existing tests from tests/test_map_output.py, tests/test_map_output_pymesh.py and tests/test_time_series.py; report unavailable optional-provider cases separately. QGIS integration is a separate validation lane.

## Exclusions

- Deferred, batch or compiled dependency evaluation; solver execution; private models or SMB benchmarks.
- Raster-cache redesign or NetCDF handle-lifecycle repairs owned by W4; FV depth averaging and vector minima owned by W8.
- An arbitrary new public time API, unsupported calendar expansion, unrelated packaging changes, merge or release.

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Implement W3 in phantom-branch/PyTuflow on this draft PR's existing branch. The PR currently contains only planning documentation: it does not implement the fixes or establish full integration validation. Work autonomously through implementation, meaningful regression tests, documentation and an updated PR handoff. Request review only after the implementation is complete and the relevant available gates have passed.

Branch relationships: W3 targets master. W4 branches from and targets W3 because it edits the same grid/NetCDF area and relies on the corrected time contract. W8 is independent on master. W5 defines common CI acceptance but is not a code or branch dependency. Inspect current PR metadata and repository guidance before editing; preserve unrelated work, and do not force-push or rewrite another contributor's history. Record the actual starting and final commit SHAs. The reviewed original upstream baseline is cf908cc922ca8448ed6002834877b0b377329eae, inherited unchanged in these result files at fork master e162c04330d24c37bee3ade94479cc4602651060. Reconfirm the relevant source at the current branch before applying repairs.

Verified defects and scope:
1. pytuflow/_outputs/output.py, Output._closest_time_index, computes timestep minus requested time, then uses positive differences for previous and negative differences for next. Executing the original function with times [0.0, 1.0, 2.0] and request 0.6 returns index 1 for previous and index 0 for next. Correct this while preserving public call signatures and documented exact-match behaviour. Establish endpoint, empty-axis and tolerance behaviour from existing documentation/tests; do not introduce arbitrary API breaks.
2. pytuflow/_outputs/nc_grid.py, NCGrid._reference_time, records time_units, but _load_info treats NCGridVar.times as hours. pytuflow/_outputs/helpers/nc_grid_var.py exposes raw numeric NetCDF time values. A seconds axis [0,3600,7200] is consequently returned as [0,3600,7200] relative hours and generates dates months apart. Convert at an appropriate reader boundary into the established internal unit, retaining original metadata. Coordinate with the existing _parse_time_units_string and pytuflow/_outputs/map_output.py::_calculate_time_step rather than duplicating inconsistent conversions. Handle the formats actually claimed by this reader; explicitly diagnose unsupported units/calendars instead of silently guessing.
3. Review Output.times metadata validation and empty/singleton axes. Its present intersect1d(...).all() check does not prove that all required columns exist. A temporal singleton must be distinguished from static-result conventions before changing generated times.

Use small, analytical fixtures and on-disk NetCDF tests generated under tmp_path. Prove that seconds/minutes/hours encoding the same samples gives identical relative hours, absolute datetimes and extracted data. Cover exact hits, between-time requests, irregular spacing, endpoints, numeric/datetime equivalence, timezone/reference handling and realistic single-timestep behaviour. Tests must exercise the installed/imported implementation, not copied function bodies or assertions that merely mirror code. The original review used isolated source-level reproductions; upgrade that evidence to real reader integration where dependencies are available.

Inspect existing tests/test_map_output.py, tests/test_map_output_pymesh.py and tests/test_time_series.py and the public tests/nc_grid fixtures. Add focused regression tests where they can run without QGIS, then run the affected existing result tests. Windows Python 3.12 and 3.14 are the common acceptance platforms; report QGIS-dependent validation separately and do not claim it ran if unavailable. Use W5's shared gates when available, keeping dependency/provider failures distinct from regressions. A short baseline-versus-candidate comparison should identify newly fixed cases and any existing failures without weakening expected results.

Update the PR description and handoff with implemented behaviour, test commands/counts, exact source revision, compatibility decisions and remaining optional-provider limitations. Keep the PR draft until its acceptance evidence is complete. Preserve Windows lexical paths; do not replace them with Path.resolve(). Do not change deferred execution, implement W4/W8, launch TUFLOW, access private SMB data, merge, publish or change production dependency pins.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
