# Original-library regression and wheel contract (W5 / PR #19)

This infrastructure validates committed public fixtures without launching
TUFLOW, Flood Modeller or another proprietary solver. It creates ordinary
temporary source copies; it does not create virtual environments or Git
worktrees. Existing deferred/graph workflows, pins and comparison tools are
unchanged.

## Sources and equivalent baselines

The workflow records three independently executed revisions in each Windows job:

| Label | Source |
| --- | --- |
| `upstream` | `TUFLOW-Support/PyTuflow` at `cf908cc922ca8448ed6002834877b0b377329eae` |
| `baseline` | Fork master at `e162c04330d24c37bee3ade94479cc4602651060` |
| `candidate` | Exact PR head, not GitHub's synthetic merge commit |

The fork reference is deliberately fixed. Updating it requires reviewing the
recorded failures; a moving branch must not silently redefine acceptance.
The same interpreter, installed dependency inventory, harness implementation
and corrected FM test helpers are used for all three runs. JSON records the
source SHA, harness SHA/dirty status, implementation/overlay hashes, dependency
versions, module origins, actual collected test IDs, all test phases, skip
reasons and subprocess exits. JUnit and captured output are retained beside it.

Two **test-only** overlays are applied identically to the public snapshots:

- `tests/fm_lib/integration_tests/test_conversion.py`
- `tests/fm_lib/common/compare_txt.py`

These correct a false-green reference comparator. No production module or
reference fixture is overlaid. Generated CSVs and GeoPackages have explicit
`csv/` and `gis/` category roots; committed reference fixtures are flat. Relative
file/layer identities must match within those roots before content comparison.
The previous text helper opened the first file twice and compared exhausted
streams; it did not validate the reference text. Both original source revisions
therefore run with the same corrected assertions, and reports identify this
instrumentation rather than claiming unmodified upstream tests.

## Collection and capability groups

| Group | Complete selection | Required capability / boundary |
| --- | --- | --- |
| `time_series` | `tests/test_time_series.py` | Actual NumPy/pandas, NetCDF/HDF and GIS runtime |
| `python_mesh` | `tests/test_map_output_pymesh.py` | Actual PyVista/VTK, NetCDF/HDF, rasterio and GIS runtime |
| `tmf` | `tests/tmf` | GeoPandas/pyogrio, shapely, pyproj and rasterio; optional legacy OGR cases listed below |
| `project` | `tests/project` | Packaged project data and GIS runtime; temporary template cache, including CLI children |
| `fm` | `tests/fm_lib` | Python DAT/GXY conversion and GeoPandas/pyogrio comparisons |
| `qgis` | `tests/test_map_output.py` | Separately selected real QGIS Python runtime with the MDAL provider |

The package eagerly imports several backends, so the standalone jobs require
the actual declared runtime dependencies even for smaller groups. Capability
probes run in a **separate process**: they cannot pre-import dependencies and
bypass pytest's existing warning-as-error policy. No new warning filters or
xfails are added. External pytest plugin autoload, `PYTEST_PLUGINS` and
`PYTEST_ADDOPTS` are removed from the new runner's subprocess environment so
unrelated local configuration cannot silently change selection.

Without `osgeo.ogr`, the ten named methods of
`tests/tmf/test_gis.py::TestOGRWrite` and
`tests/tmf/test_input.py::test_input_attrs_3` are explicitly recorded as skipped
with `GDAL not available`. The latter previously returned early and looked like
a pass. The GeoPandas writer tests remain required. On Windows, the existing
`test_load_command_with_absolute_fpath_linux` skip is also allowed. The recorder
contains exact IDs/reasons; every other test skip, xfail or collection skip fails
comparison. No entire results group is skipped.

The default standalone job explicitly excludes QGIS integration. This is a
declared job boundary, not evidence that QGIS tests passed. It appears in every
report with its reason. Selecting `--group qgis` changes it to a required group;
a standalone report uses `not_selected`, without claiming the interpreter lacks
QGIS. In the selected QGIS group,
a missing runtime/provider, empty collection or absent JUnit is an error.

## Fixture isolation

Every group receives a new `git archive` snapshot. Both its test modules and
public data are copied, because legacy TMF tests write beside `__file__`, and FM
conversion deletes/recreates `outputs_tmp`. The checkout and committed reference
data remain untouched. The runner fingerprints HEAD, tracked changes and
untracked file contents before and after execution.

Snapshots are created beside the explicitly supplied report folder (under
`RUNNER_TEMP` in Actions). This avoids the hosted Windows `%TEMP%` short-name
alias `RUNNER~1`, which creates artificial differences in legacy tests that
compare lexical paths with expanded paths. Failure signatures remove only
known snapshot locations and the exact generated temporary directory component;
model filenames, relative path depth, failure category and phase remain checked.
Numeric values, including hexadecimal values, are never rewritten as addresses.

An opt-in pytest fixture redirects only the two project `CACHE_ROOT` values.
The three inspected project CLI child-process sites are wrapped with
`ci/project_cli.py`, which redirects those same cache paths and executes the
real CLI with unchanged arguments and exit behaviour. There is no global
`conftest.py`, startup hook, HOME override or production patch. The original
deferred tests never load this fixture.

## Run locally on Windows

Use an already installed interpreter; the hosted workflow supplies separate
Python 3.12 and 3.14 jobs. The dependency baseline in
`ci/requirements-regression.txt` comes from the recorded fork's
`requirements-dev.txt`; these are **test environment pins**, not a production
dependency change. `packaging` uses 26.3 instead of that file's 26.2 because the
hosted Python 3.12 interpreter also includes pipx, which requires 26.3. This
keeps the complete interpreter dependency check valid without a virtual
environment or a package-metadata change. The third Windows job installs current
dependencies allowed
by the existing package metadata, then compares all three sources within that
same environment. A lowest-supported dependency job is deferred to #22 until
the package's declared Python/dependency lower bounds are made coherent.

From this branch's normal checkout, with the pinned upstream commit available
in a separate normal clone:

```powershell
py -3.14 -m pip install -r ci/requirements-regression.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }

# Use a new report folder for each run. Reusing a nonempty folder is rejected.
py -3.14 ci/run_regression.py --source . --ref HEAD --label candidate --report-dir "$env:TEMP/pytuflow-candidate"
# A raw test failure intentionally returns 1. Inspect report.json and *.log.

py -3.14 ci/run_regression.py --source . --ref e162c04330d24c37bee3ade94479cc4602651060 --label baseline --report-dir "$env:TEMP/pytuflow-baseline"

py -3.14 ci/run_regression.py --source ../pristine-upstream --ref cf908cc922ca8448ed6002834877b0b377329eae --label upstream --report-dir "$env:TEMP/pytuflow-upstream"

py -3.14 ci/compare_regression.py --baseline "$env:TEMP/pytuflow-baseline/report.json" --candidate "$env:TEMP/pytuflow-candidate/report.json" --output "$env:TEMP/pytuflow-comparison.json" --required-group time_series --required-group python_mesh --required-group tmf --required-group project --required-group fm
if ($LASTEXITCODE -ne 0) { throw 'Regression or incomplete evidence' }
```

Repeat with `py -3.12` and new report directories for that interpreter. For a
focused iteration, repeat `--group` with the needed names; compare reports with
the same required-group contract. The final general CI always selects all five
standalone groups. The historical static function count is not an execution
count or an acceptance target.

### QGIS integration boundary

From the configured QGIS/OSGeo shell, first verify `python` is the actual QGIS
interpreter. Do not substitute `py -3.14` or pip stubs for it. Install only
missing test dependencies compatible with that supplied runtime, then run:

```powershell
python -c "import sys; from qgis.core import Qgis; print(sys.executable, Qgis.QGIS_VERSION)"
if ($LASTEXITCODE -ne 0) { throw 'Real QGIS runtime is required' }
python ci/run_regression.py --source . --ref HEAD --label qgis-candidate --group qgis --report-dir "$env:TEMP/pytuflow-qgis-candidate"
# Repeat for upstream and the recorded fork ref in the SAME configured runtime.
python ci/compare_regression.py --baseline "$env:TEMP/pytuflow-qgis-baseline/report.json" --candidate "$env:TEMP/pytuflow-qgis-candidate/report.json" --output "$env:TEMP/pytuflow-qgis-comparison.json" --required-group qgis
if ($LASTEXITCODE -ne 0) { throw 'QGIS regression or incomplete evidence' }
```

The probe initialises the real provider registry and requires `mdal`. Native
QGIS acceptance remains outstanding until these reports exist. The hosted
standalone Windows jobs do not claim to validate QGIS.

## Acceptance policy

`run_regression.py` returns the raw outcome; it does not turn known failures
into passes. The workflow retains those nonzero steps and runs an independent
comparison. Candidate acceptance requires all of the following:

1. Completed reports with exact source identities and matching harness and
   dependency evidence; the source checkout fingerprint is unchanged.
2. Every required group and backend is present and executes tests.
3. Actual collected IDs equal JSON outcomes and JUnit IDs/counts. Missing,
   malformed, duplicated, interrupted, empty or partially executed reports fail.
4. No removed baseline test, new failure, changed failure category/phase/signature,
   unexpected skip or new nonpassing test. Added tests must pass.
5. Identical optional capability and skip contracts. Existing failures stay
   failed in raw JSON/JUnit and are listed by exact ID under `inherited_failures`.

The upstream-to-fork comparison records historical differences. It does not
replace the candidate-to-fork gate. Infrastructure tests independently exercise
the fail-closed conditions, including faulty evidence that would otherwise
produce false greens.

## Installed-wheel acceptance

Separate Windows 3.12/3.14 jobs build sdist and then the wheel from that sdist
with `python -m build --no-isolation`. They install the wheel into the job's
configured interpreter and check declared dependency satisfaction. There is no
editable install or virtual environment. From outside the checkout:

```powershell
python -I C:/path/to/checkout/ci/wheel_smoke.py --source-root C:/path/to/checkout --wheel C:/path/to/dist/pytuflow-1.2.6-py3-none-any.whl --report C:/path/to/reports/wheel-smoke.json
if ($LASTEXITCODE -ne 0) { throw 'Installed-wheel acceptance failed' }
```

The smoke verifies noneditable distribution origin, RECORD, every installed
package file against the supplied wheel, 22 public exports, 15 JSON/schema
resources, two templates and a generated control file. It invokes module CLI
help and the registered console-entry-point target in isolated child processes,
with only the template cache redirected. It tests the registered target rather
than the operating-system launcher shim. Missing checks fail the smoke.

## Parallel-agent selection and ownership

| Workstream | Focused original groups | Ownership |
| --- | --- | --- |
| #16 time selection/units | `time_series`, `python_mesh`, plus its dedicated regression module | Its production time semantics and feature tests |
| #17 save/encoding | `tmf`, `project`, plus its dedicated regression module | Its production save/encoding changes and feature tests |
| #23 numerical reductions | `python_mesh`, plus its dedicated regression module; QGIS when applicable | Its production numerical changes and feature tests |
| #19 infrastructure | All groups; `tests/ci` | New general workflow, `ci/`, these two shared FM helpers and evidence records |
| #22 package/API | Installed-wheel jobs and relevant original groups | Package metadata, runtime imports/logging/typing and root README; not started here |

Feature-specific tests remain in their owning branches. Agents may add dedicated
workflows without editing the shared W5 files. Coordinate changes to shared
fixtures on the PR before editing. Do not merge unfinished feature branches to
make this infrastructure green or change engineering expectations to match a
failure. General workflow triggers cover results, project, TMF, FM and test-only
changes. Existing deferred acceptance retains its independent gates.

## Evidence and handoff

Each Actions run uploads `original-regression-<python>-<dependencies>` and
`original-wheel-<python>` artefacts, including all source reports, exact failure
IDs, JUnit, logs, dependency inventories, comparisons, distributions and smoke
evidence. See `agent_workstreams/W5_original_library_regression_ci.md` and the
PR conversation for the latest validated commit, Actions URLs and outstanding
capability/product items. Do not infer Windows or QGIS acceptance from a local
Linux run.
