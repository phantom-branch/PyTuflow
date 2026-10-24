# W5 — Original-library regression and installed-wheel infrastructure

## Implemented checkpoint and status

Implementation is complete on `test/original-library-regression-ci`, based on `master`, under the [assigned execution prompt](https://github.com/phantom-branch/PyTuflow/pull/19#issuecomment-6380972632). The implementation checkpoint is [`cdaacf1313ad3b172dc7ae993ab7416164be1632`](https://github.com/phantom-branch/PyTuflow/commit/cdaacf1313ad3b172dc7ae993ab7416164be1632). Native validation passed in [Actions run 40075325512](https://github.com/phantom-branch/PyTuflow/actions/runs/40075325512). **All five jobs passed: three complete regression comparisons and two installed-wheel jobs.** The raw suite failures below remain visible; a passing comparison does not assert that all original tests pass. The documentation/evidence commit after this checkpoint changes no tested implementation file. Infrastructure validation reports **82 passed tests plus 10 passed subtests** in each regression job; subtests are reported separately from top-level tests.

The contributor and feature-agent contract is [ci/README.md](../ci/README.md). This handoff supersedes the initial planning commands: use normal checkouts and the implemented snapshot runner, without new worktrees, virtual environments, or direct execution of the original suites in a working checkout.

## Delivered scope

- `.github/workflows/original-library-regression.yml` runs Windows Python 3.12/3.14 with the documented dependency baseline, Python 3.14 with dependencies resolved under existing package metadata, and separate installed-wheel jobs for both interpreters. Relevant production, test and packaging changes trigger these checks.
- `ci/run_regression.py` independently executes all five standalone groups: time series, Python mesh/raster, TMF, project and FM. Each group uses a disposable committed source/fixture snapshot. Project caches and inspected Python CLI children are isolated. Source checkouts and reference fixtures remain unchanged.
- JSON, JUnit and captured logs record actual collection, each test phase, counts, skips, failures, source/harness identities, dependencies and import provenance. The comparator rejects missing, empty, interrupted or inconsistent evidence, removed tests, new failures, changed failure signatures and unexplained skips. Existing failures remain failed in raw evidence; comparison acceptance is a separate result.
- Shared FM helpers now compare relative CSV/ECF/GPKG/layer identities and actual reference text. Generated `csv/` and `gis/` category roots are explicit; nested relative names remain significant. The same two test-only overlays apply to every source revision. Production files and public reference data are never overlaid.
- Wheels are built from the sdist with `python -m build --no-isolation`, installed in each hosted interpreter, and inspected from outside the checkout with isolated Python imports. Checks cover import origin, distribution metadata/RECORD, every installed package file against the wheel, public exports, packaged JSON/schema/templates, a generated control file and project CLI help. The registered console entry-point target is exercised; the operating-system launcher shim is not.

## Native evidence

Each matrix entry executes these source identities in the same interpreter/dependency environment and with the same harness:

| Source | Exact revision |
| --- | --- |
| Canonical upstream | `cf908cc922ca8448ed6002834877b0b377329eae` |
| Fixed fork baseline | `e162c04330d24c37bee3ade94479cc4602651060` |
| Candidate implementation | `cdaacf1313ad3b172dc7ae993ab7416164be1632` |

| Native matrix | Source | Collected | Passed | Failed | Errors | Skipped | Gate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Python 3.12.10 / baseline | upstream | 1257 | 1244 | 1 | 0 | 12 | complete |
| Python 3.12.10 / baseline | baseline | 1259 | 1243 | 4 | 0 | 12 | reference |
| Python 3.12.10 / baseline | candidate | 1259 | 1243 | 4 | 0 | 12 | no regression |
| Python 3.14.9 / baseline | upstream | 1257 | 1244 | 1 | 0 | 12 | complete |
| Python 3.14.9 / baseline | baseline | 1259 | 1243 | 4 | 0 | 12 | reference |
| Python 3.14.9 / baseline | candidate | 1259 | 1243 | 4 | 0 | 12 | no regression |
| Python 3.14.9 / current | upstream | 1257 | 991 | 254 | 0 | 12 | complete |
| Python 3.14.9 / current | baseline | 1259 | 1004 | 243 | 0 | 12 | reference |
| Python 3.14.9 / current | candidate | 1259 | 1004 | 243 | 0 | 12 | no regression |

Artefacts are `original-regression-3.12-baseline`, `original-regression-3.14-baseline`, `original-regression-3.14-current`, `original-wheel-3.12` and `original-wheel-3.14`. Each regression artefact includes source reports, exact inherited failure IDs, JUnit, logs, dependency inventories and comparisons. Wheel artefacts include distributions, provenance and smoke reports. Actions retention is 30 days. The committed [machine-readable baseline](evidence/W5_cdaacf1_windows.json) preserves all counts, exact nonpassing IDs, signatures, source/environment identities and artefact URLs. The [raw report bundle](evidence/W5_cdaacf1_reports.zip) preserves the original JSON, JUnit, logs, dependency inventories, comparisons and wheel smoke/provenance with a SHA-256 file manifest. It contains no models or built distributions.

### Inherited baseline failures

The Windows 3.12 and 3.14 pinned environments have the same inherited failures:

| Exact test ID | Recorded reason |
| --- | --- |
| `tests/fm_lib/integration_tests/test_conversion.py::TestConversion::test_convert_river_flood_relief_arch` | AssertionError: Generated ECF has four lines; the two-line reference omits the ORIFICE directive. |
| `tests/tmf/test_control_file.py::test_load_rainfall_database` | ValueError: No Control File/Database has been loaded for read grid rf |
| `tests/tmf/test_input.py::test_input_files_ref_in_gis` | AssertionError: Referenced-file list omits q_flow.csv; complete expected/actual lists are preserved in the raw report. |
| `tests/tmf/test_input_context.py::test_input_files_ref_in_gis` | AssertionError: Referenced-file list omits q_flow.csv; complete expected/actual lists are preserved in the raw report. |

These are existing TMF behaviour and FM reference issues for owner triage. This infrastructure does not change their expected engineering output. The three TMF failures are historical upstream-to-fork regressions already present at the recorded fork baseline; the corrected FM assertion also fails on upstream. Route the TMF omissions to their owning TMF/deferred workstream, preserving its existing gates. All three candidate-to-fork comparisons and all three canonical-upstream completeness checks pass.

### Current dependency evidence

The current lane resolves pandas 3.1.0, NumPy 2.5.4, PyVista 0.49.1 and VTK 9.7.1 under unchanged package metadata. Candidate and recorded fork both retain **243 raw failures**, with no new/changed failure. This establishes regression equivalence; it does not certify current-dependency compatibility.

| Failure type | Candidate count |
| --- | ---: |
| `Pandas4Warning` | 181 |
| `AssertionError` | 29 |
| `KeyError` | 16 |
| `ValueError` | 8 |
| `AttributeError` | 6 |
| `TypeError` | 2 |
| `ParserError` | 1 |

The 181 direct pandas warnings arise from production `inplace=True` operations under the existing warning-as-error policy. Another 58 failure records contain earlier pandas deprecation warnings; their empty outputs and data-loading errors are consistent with loaders catching promoted warnings and retaining incomplete data. This is diagnostic evidence, not a causal claim verified by a production fix. Together with the four baseline failures, these account for all 243 failures. The complete raw tracebacks and a separately labelled derived classification remain in the bundle. Package-compatibility triage belongs to #22. No separate numerical/time defect is inferred from a failure that stops during loading. #16/#17/#23 retain production and feature-test ownership.

A small reproduced mesh case is `tests/test_map_output_pymesh.py::TestXMDF::test_load_2dm_only`, which reaches `pytuflow/_outputs/pymesh/mesh_geom/py2dm.py:92` and raises `Pandas4Warning`. Run the `python_mesh` group using the recorded current environment to reproduce; use its JSON dependency inventory rather than assuming future package resolution is identical.

### Installed-wheel evidence

Both Windows interpreters pass **23/23** checks. Each wheel verifies **553** installed package files against the wheel and RECORD, **22** public exports, **15** JSON/schema resources, **2** templates and a generated TCF. Both CLI probes return zero with empty stderr; `pip check` reports no broken requirements. Imports originate from each interpreter’s `Lib/site-packages/pytuflow/__init__.py`; the isolated smoke process runs in `D:/a/_temp/original-wheel/outside`. Exact origins, hashes, dependency inventories and source provenance are preserved in the committed evidence.

Local supplemental evidence: Python 3.12.14 on Linux passed 82 infrastructure tests plus 10 subtests and built the sdist/wheel without isolation. Native Windows acceptance above is independently executed evidence.

One confirmed inherited reference mismatch is `tests/fm_lib/integration_tests/test_conversion.py::TestConversion::test_convert_river_flood_relief_arch`: the generated ECF includes the ORIFICE network directive absent from the reference ECF. Both GeoPackages contain that layer. This suggests an incomplete reference ECF; neither production behaviour nor reference data was changed to make the assertion pass.

The first diagnostic run, [40073567141](https://github.com/phantom-branch/PyTuflow/actions/runs/40073567141), identified two infrastructure issues now corrected: a hosted-interpreter dependency conflict, addressed only in the new CI pin (`packaging==26.3`), and `%TEMP%` short-name aliases, addressed by placing snapshots beside explicit report folders. Its raw results remain diagnostic evidence, not acceptance for the final checkpoint.

## Reproduce the complete standalone gate

Use an already installed Python 3.12 or 3.14 and normal clones of this branch and canonical upstream. Run the commands from the matching implementation checkout. Choose a **fresh, writable report root with its explicit long Windows path**, outside both repositories; avoid a short-name alias such as `RUNNER~1`. Replace the example drive/path below to suit the machine. Never reuse nonempty report directories.

```powershell
$reportRoot = 'D:\Validation\PyTuflow-PR19-cdaacf1-python314'
$candidateSha = 'cdaacf1313ad3b172dc7ae993ab7416164be1632'
$forkSha = 'e162c04330d24c37bee3ade94479cc4602651060'
$upstreamSha = 'cf908cc922ca8448ed6002834877b0b377329eae'
$requiredGroups = @('--required-group', 'time_series', '--required-group', 'python_mesh', '--required-group', 'tmf', '--required-group', 'project', '--required-group', 'fm')

py -3.14 -m pip install -r ci/requirements-regression.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
py -3.14 -m pytest -q tests/ci
if ($LASTEXITCODE -ne 0) { throw 'Infrastructure tests failed' }

# Raw failures intentionally return 1 and remain visible in each report.
py -3.14 ci/run_regression.py --source ../pristine-upstream --ref $upstreamSha --label upstream --report-dir "$reportRoot/upstream"
py -3.14 ci/run_regression.py --source . --ref $forkSha --label baseline --report-dir "$reportRoot/baseline"
py -3.14 ci/run_regression.py --source . --ref $candidateSha --label candidate --report-dir "$reportRoot/candidate"

# Record historical upstream/fork differences independently of candidate acceptance.
py -3.14 ci/compare_regression.py --baseline "$reportRoot/upstream/report.json" --candidate "$reportRoot/baseline/report.json" --output "$reportRoot/upstream-comparison.json" @requiredGroups
# Inspect the historical comparison; a difference does not replace the gates below.

# Required: complete canonical-upstream evidence, even when historical differences exist.
py -3.14 ci/compare_regression.py --baseline "$reportRoot/upstream/report.json" --candidate "$reportRoot/upstream/report.json" --output "$reportRoot/upstream-completeness.json" @requiredGroups
if ($LASTEXITCODE -ne 0) { throw 'Canonical upstream evidence is incomplete' }

# Required: candidate has no regression against the fixed fork baseline.
py -3.14 ci/compare_regression.py --baseline "$reportRoot/baseline/report.json" --candidate "$reportRoot/candidate/report.json" --output "$reportRoot/candidate-comparison.json" @requiredGroups
if ($LASTEXITCODE -ne 0) { throw 'Candidate regression or incomplete evidence' }
```

Repeat with `py -3.12` and a different report root. Dependency pins belong to these test environments; package metadata and production dependency policy are unchanged. A lowest-supported dependency job remains assigned to #22 after its lower-bound contract is made coherent; #22 has not been started.

## Capability boundaries and retained limitations

- Standalone jobs explicitly record QGIS as `not_selected`. They do not claim it is unavailable or validated. The documented `--group qgis` route requires the real supplied QGIS interpreter and MDAL provider; missing capabilities or incomplete reports fail. **Live QGIS acceptance is now passed**; see the three-source execution record below. The owner may mark this PR non-draft and consider merging.
- Without `osgeo.ogr`, exactly ten named OGR writer tests and `test_input_attrs_3` receive explicit capability skips. The existing Linux-only path test skips on Windows. GeoPandas writer coverage remains required; there are no blanket result-suite skips or new warning filters/xfails.
- Existing deferred/compiled-graph workflows, triggers, pins, comparisons and acceptance gates remain unchanged. This workflow supplies additional original-library coverage; it does not supersede those gates or claim a new deferred acceptance run.
- No solver, private model, private NAS access, native NAS benchmark, merge, release, tag, publication or production consumer repin occurred.

## Parallel ownership and downstream handoff

| Owner | Reusable selection / next boundary |
| --- | --- |
| #16 | `time_series` and `python_mesh`, plus its own dedicated time-semantics regression module |
| #17 | `tmf` and `project`, plus its own dedicated save/encoding regression module |
| #23 | `python_mesh` and applicable real-QGIS coverage, plus its own numerical regression module |
| #19 | `ci/`, new general workflow, `tests/ci`, the two shared FM helpers and evidence records |
| #22 | Reuse this checkpoint and installed-wheel gate; retains package metadata, runtime import/logging/typing and root README ownership; not started |

The feature agents retain their production files and new tests. Dedicated feature tests must still be run by their owners; the five original-suite selections do not automatically discover unrelated top-level feature modules. Shared-fixture changes require coordination on the PR. No unfinished feature branches were merged into this branch.

Codex review and any subsequent findings are tracked in the PR conversation. The real-QGIS boundary has now passed as recorded below. The PR is ready to be marked non-draft and considered for merging; the owner retains that action.


## Completed native QGIS/MDAL validation (24 October 2026)

**W5 QGIS acceptance passed. Ready to mark non-draft and consider merging.**
No W5 implementation defect or necessary code change was identified. This
handoff/evidence update does not change the tested production, runner, helpers,
tests, workflows or dependency policy. No draft conversion or merge was done.

Frozen candidate/harness: `4ca199c55d6d388a0019128332e8f0adafdace93`.
Canonical upstream: `cf908cc922ca8448ed6002834877b0b377329eae`, obtained from
`https://github.com/TUFLOW-Support/PyTuflow.git` in a separate normal checkout.
Fork baseline: `e162c04330d24c37bee3ade94479cc4602651060`, from
`https://github.com/phantom-branch/PyTuflow.git`. Both checkouts were clean and
readable by `git archive`; the unchanged runner created independent snapshots.

| Full QGIS group | Collected | Passed | Failed | Errors | Skips | Raw exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Upstream | 239 | 239 | 0 | 0 | 0 | 0 |
| Fork baseline | 239 | 239 | 0 | 0 | 0 | 0 |
| PR #19 candidate | 239 | 239 | 0 | 0 | 0 | 0 |

Every run executed all of `tests/test_map_output.py`, including mesh geometry,
extraction and module-order-dependent CATCHJson tests. The strict candidate
comparison, required upstream self-completeness and independently recorded
upstream-to-fork comparison all passed, each raw exit 0. No failing IDs,
collection errors, incomplete reports, unexpected skips, xfails or xpasses
occurred. Collected IDs, JSON outcomes and JUnit counts agree; every role has
identical required capabilities, package inventory and harness fingerprints.
All reports record unchanged source checkouts and a clean harness.

The actual installed environment is QGIS 4.2.3, CPython 3.12.15, Qt 6.11.0 and
GDAL 3.13.3, using the existing OSGeo4W launcher/W3 bootstrap and compatible
additive dependency targets. A real QgsApplication and MDAL provider were
verified. No bundled Python/Qt/GDAL/NumPy/pandas package was replaced. Runtime
versions, provider hash and origins are in the linked record. One local utility
filename shadowed stdlib inspect during preflight; renaming that report utility
resolved the environment issue without editing W5 or changing its independently
executed probe/test subprocesses. Corrected preflight and complete test reports
are retained as acceptance evidence.

[Published underlying JSON/JUnit/logs, commands and summary](evidence/W5_qgis_4ca199c/README.md)
contain sanitised machine roots/identifiers, explicit source-import roles and
checksums. Original raw reports and exact local launch commands remain local.
The final delivery comment identifies the evidence-only pushed head; all tested
implementation remains identical to the frozen candidate/harness above.

[Hosted run 40076415079](https://github.com/phantom-branch/PyTuflow/actions/runs/40076415079)
was rechecked at exact source `4ca199c`: all five Windows jobs remain successful.
Prior Codex review is complete with no findings and zero unresolved threads.
No further implementation/review cycle is needed for unchanged W5 code.

No remaining work was identified within W5's required acceptance scope. The
four inherited baseline production/reference failures and separately recorded
current-dependency failures remain visible and belong to their owning TMF/FM
reference or package workstreams; they are not newly fixed or accepted as
compatible by this QGIS result. #16/#17/#23 retain feature implementations;
#22 has not been started. Existing deferred/graph gates remain unchanged.
