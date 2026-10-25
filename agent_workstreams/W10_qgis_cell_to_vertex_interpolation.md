# W10 — Restore QGIS-backed cell-to-vertex interpolation

**Status:** Draft; confirmed inherited public-API gap, implementation pending genuine QGIS/MDAL acceptance. This is an upstream bug-fix candidate, not a new interpolator.

- Fork: `phantom-branch/PyTuflow`, branch `fix/qgis-cell-to-vertex-interpolation`
- Branch base: merged W9/#26 on `master` at `73e0041f1fa5e3ce074fd71e8c5ffb36a6cf7d07`
- Upstream: `TUFLOW-Support/PyTuflow` at inspected master `cf908cc922ca8448ed6002834877b0b377329eae`
- Candidate for later upstream submission: **yes**, after independent native-QGIS evidence; isolate this patch in the consolidated upstream contribution. Do not submit unverified code directly to upstream.

## Why this is an inherited bug

`Mesh.surface(..., to_vertex=True)` and `PyMesh.surface(..., to_vertex=True)` document interpolation of *cell-centred* result datasets to mesh vertices. The direct cell-centred path calls `CellDataMixin.cell_data(..., to_vertex=True)`, whose `cell2node` routine requests `self.geom.cell_to_vertex_weights()`, `self.geom.cell_nodes` and `self.geom.vertices`.

On upstream and the fork, `QgisMeshGeometry` inherits `PyMeshGeometry.cell_to_vertex_weights()`, which raises `NotImplementedError`. It also retains the base geometry's empty `cell_nodes` and `vertices` arrays. Implementing just the weights method is therefore insufficient. By contrast, `PyNCMeshGeometry.cell_to_vertex_weights()` already implements a per-corner angle-weighted interpolation scheme.

For QGIS *native vertex-centred* data, `vertex_data()` is a distinct path and must not be disturbed. The confirmed scope is **cell-centred result → vertex surface** for QGIS-backed geometry, both QGIS/MDAL and native data extractors where supported. W9/#26 repaired `to_vertex=False` cell-position extraction independently and is merged.

## Minimal, upstream-compatible implementation contract

1. Demonstrate the pre-fix error using the real public `NCMesh(..., driver="qgis geometry data extractor").surface("tracer", 0., to_vertex=True)` (and at least one QGIS geometry + native data extractor). Capture actual exception, source identity and QGIS/MDAL runtime. Do not substitute a mock provider.
2. Make QGIS geometry expose consistent vertex coordinates, `N×4` cell-to-vertex mapping, and `N×4` interpolation weights, using **original MDAL/QgsMesh face indices**. Support mixed triangles/quadrilaterals by padding triangle's unused fourth corner with a valid vertex index **and zero weight**; never allow `-1` indexing to become a contributor. Ensure a mesh vertex count is retained including isolated/unreferenced vertices.
3. Mirror the **existing** non-QGIS implementation's per-corner angle-based weighting; do not introduce IDW, nearest-neighbour, VTK interpolation, or another default algorithm. Use a separate small, independent analytical reference (for triangles, irregular quads and a shared vertex) to prove weights and preserve the established numerical convention. Avoid double-normalisation and zero-divisions.
4. Respect wet/dry masks per cell and per time. Missing observations or a partially invalid vector must not contaminate valid neighbours or be silently converted to physical zero. Preserve genuine zero observations. A vertex with no valid contributing cell should obey the existing public missing/mask contract—characterise it from the native reader and explicit tests before deciding a change.
5. Keep data shape correct for 2D/3D scalar/vector, single and multiple time steps, and mixed geometry. The current `cell2node` assumes four columns, caches weighted values across components/time, and allocates some 3D arrays using `self.geom.vertices.shape[0]`; inspect all these interactions. Do not fix one exception while leaving empty arrays, ragged invalid topology, NaN poisoning or wet/dry reuse behind.
6. `QgisMeshGeometry.vertex_position(..., get_z=True)` may depend on a `Bed Elevation` provider group. Verify real native and FV mesh behaviour and preserve known Z vs unknown Z correctly; never fabricate a 0 bed level. Preserve global/local XY semantics as validated in W9.
7. Cache static geometry/weights appropriately without retaining dataset/time-dependent wet/dry state. Preserve existing optional QGIS import fallbacks and compatible Python 3.12/3.14 syntax (upstream Python minimum must be reconfirmed before export).
8. Keep public signatures, package imports, W8 depth averaging and vector reductions, W9 centroids, W3 time semantics, W4 caching/lifetime work, W2 model edits, deferred/batch graph code and all shared CI gates unchanged unless a specific failing contract requires a narrowly scoped correction.

## Validation requirements (native QGIS is mandatory)

- Baseline and candidate checkouts under the same installed QGIS 4 runtime with **real MDAL**; inspect native QGIS/MDAL compatibility before claiming support. Synthetic generated FV fixtures and a small triangular/quadrilateral 2DM are sufficient. No proprietary data.
- Confirm direct public `surface(...,to_vertex=True)` succeeds for all supported QGIS geometry engine combinations: `qgis geometry data extractor`, `qgis geometry netcdf4`, `qgis geometry h5py`.
- Compare directly with the existing native netCDF4/h5py reader for cell-to-vertex interpolation. Independently check nonuniform triangle/quad angles and at least one **shared** vertex with two contributing cells; isolated, dry-only, wet+missing, shared wet/dry and vector-component partial-missing cases.
- Exercise scalar/vector, 2D and depth-averaged FV-3D, including multiple time steps, original face/vertex order, missing/zero, repeated calls, cache invalidation, and `coord_scope`.
- Run newly added real-provider tests plus affected `tests/test_qgis_surface_cell_positions.py`, `tests/test_numerical_qgis_reductions.py`, `tests/test_numerical_fv_reader.py`, `tests/test_map_output.py`, `tests/test_map_output_pymesh.py`, and relevant W8/W9/W5 hosted gates. Compare exact baseline/candidate cases separately; do not confuse inherited failures with regressions.
- Publish sanitised JUnit, exact test IDs/results, before/after samples, source/import SHAs, runtime/provider versions and commands to GitHub; avoid any SMB paths, solver/model details. QGIS-unavailable = explicit unverified blocker, never a simulated success or broad skip.
- Correct focused issues, rerun, request Codex review only when implementation is completed and relevant gates pass, and address concrete findings. Remain **draft and unmerged** pending explicit owner approval.

## Non-goals / upstream contribution hygiene

- No new interpolation method, API-breaking change, general QGIS geometry redesign, broad performance/graph/deferred work, solver execution, SMB benchmark, virtual environments, git worktrees, production dependency repin, release or direct upstream push.
- Retain the W10 patch independently reviewable. Once accepted, document the minimal cherry-pick/squash diff and native proof for inclusion in the broader upstream work; recommend the upstream maintainers review this fix as a coherent unit, even if submitted together with other original-library bug fixes.
- Coordinate with PRs #18 and #20: do not mix their work into W10. Update branch from merged `master` when appropriate without force-pushing or altering sibling checkouts.

## Agent delivery

Continue on this **existing** branch; complete implementation and tests (not another planning document), push to this draft PR, publish exact-head QGIS + Windows evidence and request final Codex review. Keep it draft/unmerged until accepted.
