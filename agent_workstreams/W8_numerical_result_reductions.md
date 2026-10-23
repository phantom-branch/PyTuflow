# [W8] Correct FV depth averaging and vector minimum reductions

## Initial status

Draft scaffolding only: this PR currently adds a scoped work plan. Runtime changes and acceptance tests have not been implemented on this branch. Earlier review reproductions were isolated component checks, not full Windows/GIS integration validation.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `fix/numerical-result-reductions`.
- PR base: `master`.
- Starting state: **Can start now**.
- This is an independent branch from master; it does not depend on the deferred optimisation PRs.
- Common regression/integration coordination: **W5**, `test/original-library-regression-ci`. Existing acceptance workflows must remain intact.

## Purpose

Documentation-only implementation scaffold. Repair proven partial-layer averaging and vector-minimum defects, then define and verify missing-value handling against the existing physical/public contracts. No implementation or full integration validation has been completed by this scaffold.

## Scope

- Base: master, independent of W3/W4. W5 supplies common CI gates without a branch dependency.
- Correct first-layer partial-depth weighting in depth_averaging.depth using physical interval overlap and preserve the documented top/bottom, elevation and sigma meanings.
- Investigate and explicitly document missing-value treatment across multi_level, depth and elevation using existing documentation/provider behaviour and analytical evidence; do not silently interpret missing values as zero.
- Repair PyMesh.minimum fallback when vector magnitudes are requested without split components, and verify agreement with the maximum and precomputed-minimum paths.
- Add analytical tests independent of QGIS plus relevant public-fixture integration coverage; avoid unrelated hydraulic algorithms.

## Acceptance criteria

- [ ] For layer boundaries [0, -1, -2] and values [10, 20], top depth intervals [0, 0.5], [0.2, 0.8] and [0, 1] return 10; [0, 1.5] returns 13.3333333333 within stated tolerance.
- [ ] Partial first/interior/last layers, top/bottom direction, out-of-domain ranges, dry columns and single-layer cases agree with independent analytical overlap calculations.
- [ ] Missing and all-missing data have an explicit evidenced contract applied consistently to numerators, denominators, masks and returned values; tests distinguish absent data from physical zero.
- [ ] Fallback vector minimum for [3,4] and [6,8] returns magnitude 5 when split_vector_components=False, and returns the documented component result when True; scalar/min/max and precomputed/fallback paths remain coherent.
- [ ] Focused tests and affected existing PyMesh/FV result tests pass on Windows Python 3.12 and 3.14. QGIS-provider comparison is a separate recorded validation lane.

## Exclusions

- A new hydraulic model, inferred physical meaning for missing data without supporting evidence, or arbitrary public return-type/policy changes.
- W3 time selection/units, W4 raster caching/reader lifecycle, deferred dependency work, unrelated FM conversion or solver algorithms.
- Private data, SMB performance claims, solver execution, merge, release or production dependency repinning.

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Implement W8 in phantom-branch/PyTuflow on this draft PR's existing branch. It currently contains documentation only: no implementation or full integration validation has been completed. Work autonomously through the corrections, meaningful analytical/integration tests and an updated PR handoff. Request review only after implementation is complete and relevant available acceptance gates have passed.

This PR targets master independently of W3 (time correctness) and W4 (raster caching/reader recovery). W5 defines common CI gates without creating a code or branch dependency. Inspect current PR metadata and repository guidance, preserve unrelated work and avoid rewriting another contributor's history. Record the exact starting/final commit SHAs. The affected original result files were unchanged between upstream cf908cc922ca8448ed6002834877b0b377329eae and reviewed fork master e162c04330d24c37bee3ade94479cc4602651060. Reconfirm current code before editing.

Verified defect one: pytuflow/_outputs/pymesh/depth_averaging/depth_averaging.py::depth incorrectly calculates the last partial thickness when an interval ends within the first layer. Using layer boundaries [[0,-1,-2]], values [[10,20]] and from_top=True, intervals [0,0.5], [0.2,0.8] and [0,1] currently return NaN although each lies entirely in the layer whose value is 10. The interval [0,1.5] correctly returns 13.3333333333. Repair boundary overlap calculations so each weight is the actual intersected layer thickness. Verify from_top=False, intervals within one interior layer, intervals crossing several layers, clipping and valid-domain handling. Review sigma/elevation paths for consistency where the same contract applies; avoid a wholesale algorithm rewrite without evidence.

There is also an explicit numerical-policy question. The existing multi_level, depth and elevation routines replace NaN values with zero in the weighted numerator while retaining their layer thickness in the denominator. Equal-thickness [10,NaN] can therefore produce 5. Inspect documentation, masks, callers and provider semantics before selecting a correction: a missing value is not automatically a physically dry or zero-valued layer. State whether invalid data invalidate the requested average or are excluded from both weighted sum and valid thickness, and justify that choice with existing contracts and reproducible evidence. Preserve existing valid-data behaviour. Do not invent an unsupported physical convention, silently turn missing data into zero, or change a public numerical policy without documenting its evidence and compatibility implications. If genuine ambiguity remains after investigation, implement independently proven repairs and clearly isolate that unresolved decision rather than claiming all numerical semantics validated.

Verified defect two: pytuflow/_outputs/pymesh/pymesh.py::PyMesh.minimum converts vectors to magnitudes when split_vector_components=False, then still takes the vector-component branch. In the fallback used when an extractor raises NotImplementedError for stored minima, vectors [3,4] and [6,8] produce magnitudes [5,10] and then IndexError from indexing the scalar minimum. Correct the branch condition and preserve documented scalar/component return shapes. Compare the analogous maximum implementation and metadata-backed minima; include wet/dry/all-masked cases according to their established contract.

Build small independent analytical tests for partial-layer overlap and weighted values, not tests that simply repeat implementation arithmetic. Cover first/interior/last layers, single-layer columns, top/bottom orientation, elevation/sigma equivalence where defined, zero-width/outside ranges, NaN layers and all-missing data. Test scalar and vector minima/maxima, magnitude versus split components, on-cell/on-vertex paths and stored-metadata versus fallback results. Add only fixture sizes needed to demonstrate the risks. The prior review used isolated actual-source functions; the PR must supply tests against the imported implementation and real public-reader integration where available.

Inspect tests/test_map_output_pymesh.py, tests/test_map_output.py, tests/nc_mesh and tests/regression_test_comparisons before adding tests. Run the focused analytical cases plus affected existing FV/PyMesh cases. Windows Python 3.12 and 3.14 are the common acceptance platforms; use W5's shared gates when available. QGIS-provider parity is a separate validation lane and must be reported as unexecuted if unavailable. Retain baseline failures separately from new regressions and do not weaken expected values to make checks pass.

Update the PR with exact fixes, missing-data evidence/policy, analytical expected values and tolerances, test commands/counts, source revisions and remaining provider limitations. Keep the PR draft until acceptance is complete. Preserve lexical paths and avoid Path.resolve(). Do not alter deferred work, W3/W4, private SMB data or unrelated hydraulic algorithms; do not launch solvers, merge, release or change production dependency pins.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
