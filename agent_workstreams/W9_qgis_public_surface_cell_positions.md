# W9 — Restore QGIS geometry public surface cell positions

**Status:** Draft implementation work package; not yet a runtime fix.

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
