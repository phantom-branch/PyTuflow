# W9 — Restore QGIS geometry public surface cell positions

**Status (25 October 2026):** Native Windows QGIS/MDAL acceptance passed, including matched baseline reproduction and complete affected regressions. Updated master is incorporated; final exact-head hosted CI and Codex review are the remaining delivery gates. See the final PR #26 acceptance comment for their terminal state.

- Repository: `phantom-branch/PyTuflow`
- Branch: `fix/qgis-public-surface-cell-position`
- Base: `master` (after merged [W8 / PR #23](https://github.com/phantom-branch/PyTuflow/pull/23), squash commit `0679d9c758c07e786f23d552295366baa4bea10b`)
- Ownership: QGIS-backed geometry face positions and dedicated public-surface regression tests. Other agents own #16 time semantics, #17 safe saves, #19 shared CI, #20 reader/cache recovery. No deferred/graph work.

## Reproduced failure path and baseline

`PyMesh.surface(data_type, time, to_vertex=False)` obtains scalar/vector face data via `self.cell_data(...)` and then requests coordinates using
`self.geom.cell_position(slice(None), scope=coord_scope)` in `pytuflow/_outputs/pymesh/pymesh.py`.

`QgisMeshGeometry` in `pytuflow/_outputs/pymesh/mesh_geom/qgismesh_geom.py` does **not** implement `cell_position`. Its inherited `PyMeshGeometry.cell_position` in `pymesh_geom.py` raises `NotImplementedError("cell_position method not implemented yet.")`. As a result, public cell-centred surfaces using QGIS geometry can fail **after data reduction succeeds**. This is inherited from the original library; it was deliberately not altered by W8.

The [W8 QGIS acceptance handoff](https://github.com/phantom-branch/PyTuflow/pull/23#issuecomment-6382778980) and [sanitised MDAL numerical evidence](https://github.com/phantom-branch/PyTuflow/blob/4fdcde77c2b86f14b19c96f97c2b8328d60e998c/agent_workstreams/evidence/W8_missing_endpoints/README.md) confirm QGIS provider cell reductions work and that netCDF4/h5py geometry surface paths work; this public QGIS-geometry positioning path remains outstanding.

This is not a defect in the numerical weights, missing-data policy or W8 `depth_averaging` corrections.

## Implementation scope

1. Inspect `QgisMeshGeometry`, `PyMeshGeometry`, `PyMesh.surface`, `CellDataMixin.cell_data`, the QGIS layer/provider topology and existing mesh geometry tests. Document existing `cell_position` expectations (shape, ordering, CRS and Z coordinate) before implementing.
2. Implement `QgisMeshGeometry.cell_position` for a scalar face ID, an ordered list/array of IDs (including duplicates), empty selections and `slice(None)`. Preserve face ID order, stable `N × 3` coordinate array shape and the documented global/local coordinate scope. Handle invalid IDs consistently with other geometry accessors.
3. Compute **actual face centroids** for triangles and quadrilaterals from the QGIS/MDAL mesh geometry, not an unweighted vertex average for an irregular quad. Test non-rectangular and rotated shapes, with independent polygon-centroid references. Determine and document a defensible Z contract (bed elevation/mesh Z if available or an explicitly missing Z) without inventing zero bed elevations. Public surfaces currently consume `pos[:, :2]`.
4. Avoid rebuilding `QgsMesh` or its spatial index for every requested face. Preserve lazy load, caching, QGIS application lifetime, CRS precision and face-to-dataset alignment; do not assume planar mesh centroids are geodesic. Coordinate scope handling must be explicit, not silently mislabelled.
5. Restore `surface(..., to_vertex=False)` end-to-end for QGIS geometry with an actual initialized `QgsApplication` and MDAL provider. Exercise both relevant QGIS geometry plus native extraction combinations, scalar/vector, 2D and 3D/depth-averaged outputs where supported, inactive cells, and output geometry/data alignment.
6. Inspect `surface(..., to_vertex=True)` separately. Its underlying `cell_to_vertex_weights` path may be unsupported. Do not claim that this PR fixes vertex interpolation unless there is specific implementation and test evidence. Record any separate gap without expanding this branch into a generic mesh-geometry rewrite.
7. Add focused tests in a dedicated module (e.g. `tests/test_qgis_surface_cell_positions.py`) and appropriate existing QGIS regression tests. Use small, public or generated mesh fixtures. Compare baseline reproduction, corrected public `surface` results and independent centroids with exact file/runtime provenance.

## Required acceptance

- Verify failure against unchanged pre-fix `master` and passing implementation on this branch, using **the same real QGIS environment**. State collected/passed/failed/errored/skipped counts and exact test IDs. QGIS or MDAL unavailable is a blocker, not a passing skip.
- Validate triangles and irregular quadrilaterals, face order/duplicates/empty input, `slice(None)`, shape, global/local scope, numerical precision, masked/dry datasets, scalar/vector surface values, output masks, 2D and supported FV 3D reductions.
- Run the affected QGIS suite in `tests/test_map_output.py`, new targeted tests, existing `tests/test_map_output_pymesh.py` and W8 numerical regressions in the installed QGIS runtime where available. Run standalone Windows Python 3.12/3.14 checks for non-QGIS regressions using existing workflows. Coordinate any shared harness change with #19.
- Keep baseline defects separate from new regressions. No skips, warning suppression, weakened tolerances, private NAS model, native benchmark, TUFLOW solver, release, merge or unrelated algorithm changes.
- Preserve Windows drive-letter/UNC paths lexically, prefer `Path.absolute()` to `.resolve()`, and keep truthful Python 3.12 and 3.14 support.
- Publish a compact sanitised JUnit/runtime/source-provenance report with explicit before/after public-surface behaviour. Add GitHub links and request Codex review only after implementation and available checks pass.

## Agent handoff

Continue on the **existing** `fix/qgis-public-surface-cell-position` branch, based on merged `master`; do not create a second PR or alter #23. Start by inspecting the current PR comments, repo guidance, and actual QGIS environment. Deliver implemented code, executed tests, a committed handoff and passing review, not another plan. Keep this PR draft until it is validated, and do not merge or release without the owner's instruction.

## Implementation checkpoint

Branch commits (in order):

- `54a9147029f9df933a26c22af9f98aabd1e38d00`: implement `QgisMeshGeometry.cell_position` with native `QgsMesh` face topology, area-weighted triangle/quad polygon centroids, signed triangle-fan Z when native vertex Z exists, NaN when it does not, selected/sliced face order, duplicate and empty selection support, explicit invalid-index/scope errors, cached positions and local `Transform2D` handling.
- `31d1be16296951913f3f7a533b19372aae182d9c`: add `tests/test_qgis_surface_cell_positions.py`, designated **real QGIS/MDAL** regression cases. Uses generated triangle/irregular quadrilateral 2DM and the public generated FV fixture from `tests.test_numerical_fv_reader`. Checks selection and coordinate contracts plus end-to-end public `surface(..., to_vertex=False)` for 2D and 3D scalar/vector data via QGIS geometry with native and QGIS data extractors.
- `213baf2d8a7621bd3f56fc9eb66a48ae05c6d051`: standalone analytical centroid tests, `tests/test_qgis_centroid_math.py`, intentionally distinct from QGIS provider validation.
- `f81ed2f8e54a286a1ebe8ddadfcc4bee8bcc1c9b`: dedicated Windows Python 3.12/3.14 centroid maths workflow. Existing original-library and W8 workflows are preserved.

### Geometry decisions

- Face locations use the *native untriangulated* QGIS mesh to retain one position per dataset face. XY is the **signed-area polygon centroid in the native mesh CRS**, not a mean of vertices and not geodesic. Relative coordinates are shifted by the first vertex for numerical precision with large projected eastings/northings.
- The output is `N × 3` even for one face or no faces. `global` means native dataset CRS; `local` applies the existing `geom.trans` transform (identity unless configured), preserving Z. Invalid scopes/face IDs fail explicitly.
- Z is computed only when all original `QgsMeshVertex` values report 3D with finite elevations. A signed triangle-fan area integral supplies the surface-weighted Z; missing native Z is NaN and is not substituted with a fabricated `0` or unverified bed dataset value. Public surface extraction uses XY.
- One native mesh population and spatial index is reused; centroids are memoised by source face ID. Requested order and duplicates are retained. No public numerical averaging or wet/dry policy is changed.
- `surface(..., to_vertex=True)` remains outside scope: the inherited `cell_to_vertex_weights` capability needs separate evidence before claiming support.

### Validation status and hard boundary

A local standalone analytical reproduction of the area-centroid formula passed **5/5** checks using NumPy and pytest (irregular quad, triangle Z, winding reversal, missing Z, degenerate geometry). This is a mathematical preflight, **not** executed repository tests nor QGIS validation. The committed 7-case standalone suite is being run by GitHub Actions.

This environment has Python 3.13.5 but no `qgis` bindings or MDAL provider, so it **cannot** execute `tests/test_qgis_surface_cell_positions.py`. A true QGIS validation agent must execute that module plus the affected `tests/test_map_output.py`, `tests/test_map_output_pymesh.py`, and W8 numerical cases using the installed QGIS 4 runtime. An unavailable QGIS provider is a blocker, not a passing skip. Record the actual tested source head, QGIS/Python/GDAL versions, commands and JUnit; compare the pre-fix merged-master geometry `NotImplementedError` with the candidate's public scalar/vector surfaces, checking independent centroid expectations and wet/dry masks.

Do not claim the PR is accepted or merge it without that lane and subsequent Codex review. The branch must stay draft until these gates pass. No private models, solver, benchmark, unrelated changes, merge or release were used.

## Native Windows completion — 25 October 2026

This section supersedes the earlier environment limitation and outstanding native
validation statements above. Work used dedicated normal clones; the main checkout
and other agents' work were untouched.

- Safely merged current master `f1ceb77f74cb521f50be80209b929ecf0b58bf20` as
  `6c048477960bce2d9ca6e6956d725681027515a4`, supplying merged W5 infrastructure.
  Prior hosted failures were missing `tests/ci`, requirements and runner paths;
  no shared harness/workflow modification or error suppression was required.
- Native QGIS 4.2.3 / Python 3.12.15 / Qt 6.11.0 / GDAL 3.13.3 and real MDAL:
  original provider module **29 passed**. No production correction was needed.
- The identical 13-case public reproduction at baseline
  `0679d9c758c07e786f23d552295366baa4bea10b` fails only with the inherited
  `cell_position` NotImplementedError; all 13 candidate cases pass.
- Both baseline and geometry candidate pass **1118/1118** identical affected
  map/Python-mesh/W8 numerical tests, with zero failures/errors/skips.
- Added real-provider cache/array-isolation regression at
  `3f0627d7bf5988019fe472e8f812594ba6d10309`; committed focused validation is
  **37 passed** (30 provider, seven analytical), zero failures/errors/skips.
- [Committed sanitised evidence and commands](evidence/W9_native_qgis/README.md)
  include JUnit, logs, all test IDs, source/runtime provenance, actual public
  surface tables, independent centroid expectations, raw exits and checksums.
- Both source clones were clean after execution. No production changes beyond
  the existing W9 implementation, dependency writes, solver/private model use,
  worktrees, virtual environments, merge or release occurred.

Next action: await terminal Windows 3.12/3.14 centroid/numerical and W5
regression/wheel checks on the evidence delivery head, request final Codex review,
and address concrete findings. Keep draft; do not merge. Next review: 25 October
2026, when those checks finish. The authoritative final PR comment records exact
delivery SHA, terminal hosted URLs and review disposition without rewriting the
historical execution SHAs here.

Delivery checkpoint: `ceb657fd461e3d94d54917e0aec51dc6493bd73d` contains the
implementation, tests and sanitised evidence; all 37 focused native tests also
passed directly on this head. Its hosted runs are [W9 centroid maths](https://github.com/phantom-branch/PyTuflow/actions/runs/40126497429),
[W8 numerical regressions](https://github.com/phantom-branch/PyTuflow/actions/runs/40126497433)
and [W5 regression/wheel](https://github.com/phantom-branch/PyTuflow/actions/runs/40126497432).
Both centroid jobs, both numerical jobs and both wheel jobs passed at this
checkpoint; the three W5 comparisons were still running when this record was
updated. This handoff-only follow-up preserves the validated implementation and
tests. Its final-head reruns and review disposition are linked in the final PR
acceptance comment. [Current branch workflow runs](https://github.com/phantom-branch/PyTuflow/actions?query=branch%3Afix%2Fqgis-public-surface-cell-position).
