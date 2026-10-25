# W10 — Restore QGIS-backed cell-to-vertex interpolation

**Status:** Implementation and tests pushed on this draft branch; actual QGIS/MDAL execution and final exact-head acceptance remain outstanding. This is an upstream bug-fix candidate, not a new interpolator.

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

## W10 implementation checkpoint (25 October 2026)

Initial implementation on branch `fix/qgis-cell-to-vertex-interpolation`:

- `fe97185614cb06b663ca5dcad055821343c273d6`: Adds `QgisMeshGeometry.cell_to_vertex_weights()` using original `QgsMesh` faces and the same normalised per-corner angle convention as `PyNCMeshGeometry`. Topology is populated *lazily*, with triangle slot four repeating the third vertex at zero weight. The full native vertex array includes isolated vertices. The original `to_vertex=False` face-centroid implementation remains unchanged.
- `98cd641c74a187781f3df548fe28771390c4106c`: Adds a QGIS-specific cell-to-vertex reduction. Existing cell-centred results are first acquired with `to_vertex=False`, including W8 FV depth averaging, then projected with per-result/time validity. This avoids reusing cached wet-weight arrays across components or time. A valid vector contribution requires all components present; actual zero remains valid, wet/all-missing returns NaN and dry-only returns zero with an inactive flag. Other reader backends retain their existing code.
- `d1dd59e9e2ec11bc1dcb5a8c2650cce01be36684` and follow-up `2469756b35899c62ce2b4e959cf3799444fe5b7b`: Pure/standalone analytical regression cases with an independent shared triangle/quad angle reference, masked vectors, wet/dry, all-missing and two different time steps.
- `f405d6c7075044f7733d906b5e8cacfc40dcdb7a`, `a51cb9610ebf0b5f8936638f801ba99415c125eb`, `c398d8a1cd85360d866c6d7fce051f3148f96a70`, and `9b64ed5af74189e7bd942547a86e1167926a8eb2`: Extend genuine-QGIS regression coverage with a connected triangle+quad 2DM, native-vs-QGIS 2D/FV-3D public `surface(to_vertex=True)` comparisons for all three extraction combinations, local/global vertex scope, and changing wet masks across two physical output times. Adjust one test to obtain lazily populated `cell_nodes` **after** creating the weights.
- `ccf8d5aee22a221bb48c14553a9a84337f41062e`: Honour explicit global/local vertex coordinate scope while preserving original cached native positions. When no separate provider Bed Elevation group exists, retrieve genuine native mesh vertex Z if present and return NaN when not.
- `15f2bcd00cc05c8faf3fc50ae0849d2e9a45299c`: Safely merge the existing `master` with W2/#18 without changing three unrelated W2 paths.
- `5ca5306b73255475d919d63d0adbe53e3dd6aecd`: Add an independent Windows Python 3.12/3.14 workflow for provider-independent angle-weighting regression tests.

### Verified analytical evidence and remaining gates

The new standalone `tests/test_qgis_vertex_angle_math.py` covers a shared node where triangle internal angle is 45° and quadrilateral internal angle is 90°. Existing angle weighting gives weights 1/3 and 2/3; the interpolated scalar values 3 and 9 therefore produce **7** at the shared node. This was independently reproduced with NumPy. Other tests distinguish dry-only zero from wet missing NaN and exclude partially masked vector cells. The new standalone workflow passed both Windows Python 3.12/3.14 jobs on source head `a51cb9610ebf0b5f8936638f801ba99415c125eb`. Exact-current-head hosted workflow jobs have been requested and must be checked independently.

Codex reviewed `a51cb96` and identified a test-order issue (reading `geom.cell_nodes` before lazy weighting). The test is corrected in `c398d8a`; no algorithmic issue was demonstrated by that review, and review needs refreshing on a final tested implementation head.

**Native QGIS/MDAL validation has not been run here.** The new `tests/test_qgis_cell_to_vertex_interpolation.py` is required to be executed by an agent with installed QGIS 4 and genuine MDAL, along with `tests/test_qgis_surface_cell_positions.py`, the relevant W8/W9 numerical suites, and native NetCDF reader parity cases. Reproduce the inherited `NotImplementedError` on the unchanged pre-W10 `master` in the same QGIS runtime and publish baseline/candidate JUnit, source/runtime/MDAL provenance and exact raw exits. Check expected shapes, masks, missing/wet/zero/multi-time semantics, vector components and coordinate scope. Do not infer parity from standalone CI.

The entire work remains **draft, unmerged and unreleased**, with no direct upstream PR or push; this should be independently validated before inclusion in the consolidated upstream-compatible contribution.
