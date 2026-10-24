# W8 — Numerical result reductions

## Status and source checkpoints

Implemented on the existing `fix/numerical-result-reductions` branch of
[PR #23](https://github.com/phantom-branch/PyTuflow/pull/23), targeting `master`.
Implementation and Windows Python 3.12/3.14 acceptance are complete. The PR
remains draft; live QGIS execution and remaining limitations are recorded below.

- Starting PR head: `ab986b392950456b46e7c62c7ba442e1a3cbf73e`.
- Fork baseline: `e162c04330d24c37bee3ade94479cc4602651060`.
- Implemented and Windows-tested head: `90f43363270e1fb702081f4da22b27fa9484e074`.
- Canonical upstream: `cf908cc922ca8448ed6002834877b0b377329eae`.
- The three changed production files were identical between those upstream and
  fork checkpoints; this was rechecked with `git diff`.
- Exact implementation/final heads and hosted run URLs are recorded in the PR
  Conversation after each push. Do not reset newer work to these initial SHAs.

## Corrections

### Physical vertical overlap

`depth` and `elevation` now use the intersection of each physical layer with
the requested interval. A layer cannot receive a negative thickness or two
conflicting partial-layer adjustments. Depth is measured below the surface;
height and sigma are measured above the bed. Sigma zero is bed, one is surface.
Reversed request bounds are sorted, intervals are clipped by intersection, and
zero-width or wholly outside intervals return NaN.

Relative-depth intersections use coordinates relative to surface/bed before
applying requested distances. This preserves fractional depths at large
absolute elevation datums; regression tests include representable 2 m layers
at a datum of 1e16.

A depth pair is shared across rows, including exactly two rows. Previously,
a two-element public URI was mistakenly interpreted as two separate endpoints
when the dataset contained two columns. Explicit `(N, 2)` intervals and
`(N, 1)` endpoints are supported. The unambiguous legacy length-N endpoint
form is retained when N is not two.

`multi_level` counts physical layer positions using valid geometry, including
padding after bottom-to-top reversal. A missing result in the top layer no
longer renumbers the second physical layer as level one.

The public FV time-series and section paths now honour requested averaging
intervals for single-layer columns, as point/surface extraction already did.

### Missing-data contract and authoritative evidence

The weighted-average contract is **exclude missing observations and their
thickness**. It is supported by an existing PyTUFLOW provider:

1. [QGIS 4.0.1 source at commit 1ccf690c2e0b8126253bcac2997398deac4ea150](https://github.com/qgis/QGIS/blob/1ccf690c2e0b8126253bcac2997398deac4ea150/src/core/mesh/qgsmesh3daveraging.cpp#L61-L216)
   initialises results to NaN, intersects physical intervals, and adds both
   weighted values and effective thickness only for non-NaN observations.
   Vector layers require both components to be present.
2. [QGIS 4.0.1 regression tests](https://github.com/qgis/QGIS/blob/1ccf690c2e0b8126253bcac2997398deac4ea150/tests/src/core/testqgsmesh3daveraging.cpp)
   deliberately include missing layers and prescribe exclusion from the
   denominator. [QGIS 3.44.3](https://github.com/qgis/QGIS/blob/1d1d67e9edd14957429476b52a93d32b428ad89e/src/core/mesh/qgsmesh3daveraging.cpp#L58-L228)
   has the same policy.
3. PyTUFLOW's supported QGIS path maps its public averaging URIs to these
   methods in [averaging_method.py](https://github.com/phantom-branch/PyTuflow/blob/e162c04330d24c37bee3ade94479cc4602651060/pytuflow/_outputs/helpers/averaging_method.py)
   and calls `averaging_method.calculate(dataset_3d)` in
   [mesh_result.py](https://github.com/phantom-branch/PyTuflow/blob/e162c04330d24c37bee3ade94479cc4602651060/pytuflow/_outputs/helpers/mesh_result.py#L191-L215).
4. The ordinary NetCDF slicing path already converts source masks to NaN in
   [NCEngine.data](https://github.com/phantom-branch/PyTuflow/blob/e162c04330d24c37bee3ade94479cc4602651060/pytuflow/_outputs/pymesh/engines/ncengine.py#L90-L105).

The Python averaging functions now consistently implement this policy:

| Input/state | Weighted-average result |
| --- | --- |
| NaN or masked value | Exclude both its weighted contribution and overlap thickness |
| Either vector component missing | Exclude that layer for both components; use one common validity mask |
| Physical zero | Include its thickness and zero-valued contribution |
| Missing boundary/padded layer | No valid geometric contribution |
| All observations missing, dry zero-thickness column, or no positive overlap | NaN |
| Explicitly inactive FV cell | Preserve the existing public activity-mask contract |

Inactive cells and wet cells with missing results remain different. Surface
results retain their `active` flag and existing zero placeholders for inactive
cells; point/time-series/section results for dry cells remain NaN. A wet cell
with no valid observations stays active with a NaN result.

Component validity is applied before averaging in surface, point, time-series
and section paths. Masked finite backing numbers are not accidentally used.
The implementation does not infer a new policy for arbitrary finite
source-file fill sentinels which a reader has not normalised to NaN/masks.

Compatibility implication: mixed valid/missing columns can now produce a
larger average than the incorrect zero-diluted result. Equal-thickness
`[10, NaN]` gives 10, while `[10, 0]` gives 5. Fully valid ordinary weighted
averages retain their values.

### Vector minimum

`PyMesh.minimum` takes the component tuple branch only when
`split_vector_components=True`, matching `maximum`. For vectors `[3,4]`
and `[6,8]`, fallback magnitude extrema are 5 and 10; component extrema are
`(3,4)` and `(6,8)`.

Existing extrema policy is preserved: inactive entries are excluded, active
zeros are valid, active NaNs propagate, and an entirely inactive fallback
domain raises the existing empty-reduction `ValueError`. The averaging
missing-layer policy does not redefine extrema.

## Independent numerical evidence

For boundaries `[0,-1,-2]` and values `[10,20]`:

| Top-depth interval | Analytical result |
| --- | ---: |
| [0, 0.5] | 10 |
| [0.2, 0.8] | 10 |
| [0, 1] | 10 |
| [0, 1.5] | 40/3 |

The reference oracle integrates piecewise-constant profiles using exact
`Fraction` antiderivatives. It does not call the production overlap routine.
Its own expectations are checked against prescribed areas. Float64 comparisons
use `rtol=1e-12, atol=1e-12`: these small profiles require only a few arithmetic
operations, and this tolerance is well below the defective contributions.

The QGIS regression fixture has boundaries `[-1,-2,-2.5,-4,-5]` and values
`[1,2,NaN,4]`. Independent expected results are full-column 2.4, top levels
1–3 equal to 4/3, and top-depth 1.25–3.5 equal to 10/3. These cases are tested
through the imported Python implementation.

Before/after reproductions used real imports:

- Initial 149 depth cases: original code **56 failed, 93 passed**; the final
  169-case module adds 20 datum/masked-geometry review cases.
- Initial 52 extrema cases: original code **16 failed, 36 passed**, all failures
  reproducing the scalar-indexing error. The final module also has three
  generated XMDF reader cases.
- Six selected public FV reader cases against the unchanged fork baseline:
  **5 failed, 1 passed**. This reproduces the three first-layer NaNs, incorrectly
  averaged incomplete vectors, and ignored single-layer intervals. The
  already-correct crossing-layer case passes before and after.

## Validation and reproduction

New modules:

- `tests/test_numerical_depth_averaging.py`: 169 independent analytical cases.
- `tests/test_numerical_mesh_reductions.py`: 55 extrema cases, including real
  generated XMDF/HDF5/PyVista extraction and stored-versus-fallback comparisons.
- `tests/test_numerical_fv_reader.py`: 112 real public NCMesh cases using both
  netcdf4 and h5py. Tiny generated fixtures exercise surface, point, time-series,
  section, vertex, wet/dry, masked, missing, zero and single-layer behaviour.

Use the repository's existing dependency baseline, without changing production
metadata or dependency pins:

```text
python -m pip install -c requirements-dev.txt -e . pytest
python -m pytest -q tests/test_numerical_depth_averaging.py tests/test_numerical_mesh_reductions.py tests/test_numerical_fv_reader.py --junitxml=focused.xml
python -m pytest -q tests/test_map_output_pymesh.py --junitxml=candidate-pymesh.xml
```

Local CPython 3.12.14 / Linux results with that dependency baseline:

| Suite | Baseline | Candidate |
| --- | --- | --- |
| New focused numerical suite | Reproductions above | 336 passed, 0 skipped |
| Existing complete PyMesh suite | 110 passed, 0 skipped | 110 passed, 0 skipped |
| Existing JUnit comparison | — | 0 additional regressions |

The local dependency set includes NumPy 2.4.4, pandas 3.0.3, h5py 3.16.0,
PyVista 0.48.2, netCDF4 1.7.4, rasterio 1.5.0 and pytest 9.0.3. Warnings retain
the repository's strict settings. No expected engineering results were relaxed.

A separate initial current-dependency baseline (pandas 3.1.0, NumPy 2.5.4)
reported 44 passed / 66 failed in the unchanged existing PyMesh suite, chiefly
pandas `inplace` deprecations promoted to errors. Those compatibility failures
are recorded, not suppressed or fixed in this numerical PR; shared/current
dependency work remains owned by #19/#22.

The separately named `numerical-result-reductions.yml` runs Windows Python
3.12 and 3.14. It records exact head, runtime and dependency versions; requires
all focused tests; executes the complete legacy PyMesh suite on the pinned
fork baseline and candidate; requires nonempty reports without errors/skips;
uses the existing unchanged JUnit comparator to gate extra failures; and
archives reports. Existing deferred/graph workflows are unchanged.
Hosted Windows evidence for implementation head
`90f43363270e1fb702081f4da22b27fa9484e074`:

| Runtime | Focused cases | Existing baseline | Existing candidate | New regressions |
| --- | ---: | ---: | ---: | ---: |
| Windows Server 2025 AMD64, CPython 3.12.10 | 336 passed | 110 passed | 110 passed | 0 |
| Windows Server 2025 AMD64, CPython 3.14.9 | 336 passed | 110 passed | 110 passed | 0 |

Both jobs have zero skipped tests and successful report-completeness gates.
[Run 40073565338](https://github.com/phantom-branch/PyTuflow/actions/runs/40073565338)
completed successfully. Individual evidence:
[Python 3.12 job](https://github.com/phantom-branch/PyTuflow/actions/runs/40073565338/job/120812016996),
[Python 3.14 job](https://github.com/phantom-branch/PyTuflow/actions/runs/40073565338/job/120812016814).
The run artifacts `numerical-reductions-python-3.12` (ID 12552576315) and
`numerical-reductions-python-3.14` (ID 12552705658) contain exact head/runtime,
dependency versions, focused JUnit, baseline JUnit and candidate JUnit.
The evidence-only follow-up commit changes this handoff; its exact head and
repeat workflow run are recorded in the PR Conversation.

## Earlier validation limits (before live execution)

- **Historical limitation, superseded by the live execution section below:** live QGIS-provider comparison had not run. `tests/test_map_output.py`
  imports QGIS at module scope; an explicit collection attempt failed with
  `ModuleNotFoundError: No module named 'qgis'`. The evidence above is authoritative provider
  source/tests plus executed Python-reader integration, not a claim of live
  QGIS parity. W5 owns the separate QGIS-capable test lane.
- Retained provider differences: QGIS uses a 1e-6 thickness threshold and
  directly returns a selected zero-thickness single ordinal layer, while the
  existing Python policy uses positive thickness. This PR does not silently
  change those edge policies.
- QGIS's sigma header mentions clipping while its runtime rejects fractions
  outside [0,1]. This PR preserves Python behaviour for invalid sigma inputs
  rather than resolving that unrelated discrepancy.
- QGIS metadata split-component extrema differ from XMDF's fallback support;
  no new QGIS metadata policy is introduced here.
- No solver, private/NAS data, native benchmark, merge, release, worktree,
  virtual environment or production dependency repin was used.

## Ownership and remaining handoff

This branch owns numerical averaging, its immediate averaging callers,
vector-minimum fallback, dedicated tests and this focused workflow. #16 owns
time semantics, #17 safe saves, #19 shared general/wheel infrastructure, and
#20 reader/cache lifecycle. No sibling branch was imported.

The available Linux and Windows numerical acceptance checks have passed.
Request Codex review on the completed branch and address concrete findings here.
Keep the live-QGIS limitation explicit; do not turn source inspection or saved
QGIS comparison fixtures into a claim of an executed QGIS-provider test.

## Live QGIS execution (2026-10-24)

**Partially closed:** installed QGIS averaging itself has now executed against
real MDAL volume blocks, with independent analytical and Python comparisons.
The designated provider lane has 98 passing cases and no skips. QGIS-geometry
public surface extraction remains limited by the inherited unimplemented
`cell_position` method; the surface reduction itself is tested through
`cell_data`, and public surfaces pass through netCDF4/h5py. Keep PR #23 draft.

The discovered installation is QGIS **4.2.3**, not the previously suggested
4.0.1. It uses CPython 3.12.15, Qt 6.11.0 and GDAL 3.13.3. A real
`QgsApplication` was initialized and `mdal` was present in the provider registry.
The installed `provider_mdal.dll` SHA256 is
`6d0f860167c9bcdd3b23e6603c0da0bd7a561cdcf37de15d9bd1268d6744ea9b`.
No separate MDAL version API/export is available; do not invent a version.
Legacy class/enum aliases used by the exercised routes still work in this
installation. No general QGIS compatibility rewrite was needed.

Runtime packages: NumPy 2.4.6, pandas 3.0.6, netCDF4 1.7.5.1.post1,
h5py 3.14.0 (HDF5 1.14.6), PyVista 0.49.1, VTK 9.7.1, rasterio 1.5.2,
GeoPandas 1.1.4, Shapely 2.1.2, pytest 9.1.1 and pygltflib 1.16.5.
Missing packages were installed with `--target` and `--no-deps` in separate
local directories, without replacing bundled Qt/GDAL/NumPy/pandas. h5py 3.16.0
was incompatible with the runtime's loaded HDF5 DLL; the separately installed
3.14.0 wheel matches HDF5 1.14.6. An omitted PyVista validation dependency was
also resolved before acceptance. Initial environment failures are retained in
local logs and are superseded by complete successful runs.

### Provider observations and scoped integration repair

`tests/test_numerical_qgis_reductions.py` is an explicit capability lane: imports
require real QGIS, the application fixture requires MDAL, invalid mesh/volume
blocks fail, and there are no skip/fake-provider fallbacks. It is intentionally
run explicitly, not added to the standalone-Python workflow or shared #19
infrastructure.

The original generated FV fixtures are MDAL compatible without added metadata.
A one-cell Float64 profile writer supports additional nonuniform/zero-thickness
profiles. Tests verify raw block validity, boundaries, physical counts,
face-to-volume offsets, scalar/vector metadata and NaNs before averaging.
`AveragingMethod(uri).to_qgis().calculate(provider.dataset3dValues(...))`
executes QGIS itself. The independent Fraction oracle remains separate.

All ordinary small-fixture comparisons use `rtol=1e-12, atol=1e-12`.
For `[0,-1,-2]` / `[10,20]`, analytical, Python and QGIS values are respectively
10, 10, 10 and 40/3 for the four requested first-layer intervals. The nonuniform
reference yields 2.4, 4/3 and 10/3 for full column, top levels 1-3 and depth
1.25-3.5. Missing-first/final/all-missing, zeros, clipping, outside/zero-width,
reversed bounds, depth/height/elevation/sigma and ordinal selections are tested.
Vector components are checked before magnitudes: incomplete `[6,NaN]` is
excluded alongside valid `[3,4]`, yielding `[3,4]` and magnitude 5. Opposite
missing components yield missing results; zeros stay valid. Public committed
`EST000_3D_001.nc` salinity/temperature/velocity volume blocks also compare
against analytical and Python results at source Float32 precision (1e-6).

The new tests exposed an **inherited extractor defect**: `QgisDataExtractor`
dropped every NaN after flattening, confusing missing observations with ragged
padding. This shortened columns and misaligned vector components. The scoped
repair trims each selected column by its geometric length and retains physical
NaNs (also retaining missing entries in non-volume blocks). Regression tests
exercise wet/missing versus dry masks, raw ragged columns, and public
point/time-series/section extraction. Existing numerical modules retain masked
finite-backing tests and the independent extrema/missing-data contracts.

### Edge differences and remaining routes

- QGIS returns NaN for depth width 1e-7; Python returns 10. At width 2e-6 both
  return 10. This confirms the documented effective-thickness threshold.
- QGIS directly returns 10 from selected zero-thickness top ordinal layer;
  Python returns NaN. This is characterized, not changed.
- Sigma bounds [-0.1,1] and [0,1.1] give invalid QGIS blocks; Python clips and
  returns 15. Ordinary valid requests compare separately.
- QGIS metadata extrema for vectors [3,4]/[6,8] are magnitude min=5/max=10;
  existing split requests also return those scalar metadata values. Dedicated
  assertions retain this inherited provider difference. The existing 55-case
  extrema suite separately validates split-component fallback tuples and
  active NaN/entirely inactive behaviour.
- Unnormalized finite sentinels remain finite observations; the dedicated
  source-sentinel case preserves this limitation rather than inferring policy.
- Both baseline and candidate QGIS geometry have unimplemented
  `cell_position`; no geometry/API rewrite is included. Legacy `v1.0` point
  averaging executes and returns 10 for the missing-layer profile, but that
  driver's public surface method explicitly raises NotImplementedError.

### Execution and artifacts

Starting remote/candidate SHA: `a7312e4fbed40e5f877ebaa7f3c0ffd26f8ac556`.
Baseline normal checkout: `e162c04330d24c37bee3ade94479cc4602651060`.
The baseline extractor was identical to the starting candidate. Source imports
and dependencies were recorded in separate processes for each checkout.
No new worktree or virtual environment was created.

| Suite in the same QGIS runtime | Baseline | Candidate |
| --- | ---: | ---: |
| Existing QGIS map-output | 239 passed | 239 passed |
| Existing PyMesh | 110 passed | 110 passed |
| Three focused numerical modules | Not acceptance scope | 336 passed |
| New designated provider module | 52 passed / 46 failed | 98 passed |

All completed acceptance runs have zero errors/skips. The baseline provider
failures are expected reproductions of old numerical/extractor defects; exact
IDs and tracebacks are retained in its JUnit/log. No new existing-suite
regression was observed. Earlier incomplete dependency runs are not acceptance.

Reproduction uses the installation's actual `python-qgis.bat` environment.
Its OSGeo4W launcher resets PYTHONPATH, so a small local runner inserts the
separate dependency directories and intended checkout into `sys.path` **after**
launcher initialization, then calls `runpy.run_module('pytest', run_name='__main__')`.
Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. In each checkout use:

```text
python-qgis.bat <local-runner> -m pytest -q tests/test_map_output.py tests/test_map_output_pymesh.py --junitxml=<reports>/existing.xml
python-qgis.bat <local-runner> -m pytest -q tests/test_numerical_depth_averaging.py tests/test_numerical_mesh_reductions.py tests/test_numerical_fv_reader.py tests/test_numerical_qgis_reductions.py --junitxml=<reports>/numerical.xml
```

For baseline reproduction only, copy the new numerical/provider modules into
that separate checkout's tests directory; the production baseline stays
unchanged. Local reports retain machine-specific paths, launcher/runner,
installation commands, runtime JSON, provider probes, JUnit and exact test IDs.
Their local directory is linked in the execution handoff supplied with delivery;
no private model data was used or published. Final tested SHA, hosted checks
and review are recorded below and in the PR Conversation after push.


### Exact implementation-head acceptance

At `68310088efa04c229508a8c86766eb7a385f5f34`, all six modules were run
together in one process: **783 collected / 783 passed / 0 failed / 0 errors /
0 skipped**, in 49.00 seconds. Existing baseline: **349/349 passed** in 34.25
seconds. New-provider baseline reproduction: **98 collected / 52 passed /
46 failed / 0 errors / 0 skipped**. This separates old defects from additional
regressions. The evidence-only follow-up does not change production/tests.

Hosted standalone Windows validation:
[run 40076444756](https://github.com/phantom-branch/PyTuflow/actions/runs/40076444756).
Codex review was requested on the implementation head; final review/check
outcomes and final delivery SHA are tracked in the PR Conversation.

### Codex review correction: missing physical boundaries

Review of the live-QGIS follow-up identified that the old ordinal offset used
the first layer with valid boundaries, so a missing physical surface could
renumber the next layer. The correction carries each reader's known physical
layer count through the averaging-method factory for point, surface reduction,
time-series and section requests. Ordinals are now computed from that extent,
independently of geometry/result validity. Direct callers treat their supplied
array as a physical column; padded direct arrays can supply `layer_counts`
and `layer_start` explicitly. NaNs alone cannot distinguish padding from a
missing physical boundary/observation.

New regressions cover missing/masked surface and bed boundaries, simultaneously
missing observations, explicit ragged counts, and real netCDF4/h5py/MDAL public
point/time-series/section and cell-data requests. Provider blocks are verified
to retain the missing physical boundary and original layer count. This corrects
the concrete review finding without changing the unrelated geometry API.
Final post-review counts and SHA are recorded in the delivery comment; the
783/98 figures above describe the earlier implementation checkpoint.
