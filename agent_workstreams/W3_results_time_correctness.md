# W3 — Result timestep selection and NetCDF time units

## Status

Implemented on the existing `fix/results-time-correctness` branch, targeting `master`.
The public time contract, regression tests and feature-specific Windows workflow are implemented.
Local and Windows Python 3.12/3.14 validation pass. Codex review completed with no findings.
The originally unavailable QGIS/MDAL provider lane was subsequently completed on installed QGIS 4.2.3 with 239/239 existing QGIS tests passing on both baseline and candidate, plus 108/108 dedicated time tests passing on candidate. Final QGIS comparison exit code 0; no changes were needed. This handoff documents the result without altering the reviewed production implementation.

## Source checkpoints

- Original upstream review: `cf908cc922ca8448ed6002834877b0b377329eae`.
- Fork parent inspected at execution: `e162c04330d24c37bee3ade94479cc4602651060`.
- Actual starting PR head: `21617f29eed86d9e123aaf9353934b63d299ca07`.
- Implementation and test checkpoint: [`d5281da5373b6851b622b61ad949d801d8ac7dc6`](https://github.com/phantom-branch/PyTuflow/commit/d5281da5373b6851b622b61ad949d801d8ac7dc6).
- Tested implementation tree: `527f1637496b4768ac1fb5095e854836ff4e0b6f`.
- Regression module SHA-256: `93cb428053a9228e9202c175f78e82183378d8ec17a5b53c320c1fc2feee84ae`.

The implementation was added without resetting or rewriting the existing remote branch.
The PR description records the latest handoff head; the implementation checkpoint above identifies the runtime and tests independently of subsequent documentation commits.

## Implemented time contract

### Saved-sample selection

`Output._closest_time_index()` now selects the previous or next saved sample in the correct direction.
For `[0, 1, 2]` hours and request `0.6`, previous returns index `0`, next index `1` and closest index `1`.

- The first sample within tolerance wins, preserving the existing matching rule.
- Outside-range requests clamp to the first or last sample.
- Closest ties use the first sample, as before.
- An empty axis raises an explicit `ValueError`; `times()` on empty or incomplete metadata returns `[]`.
- Naive datetimes mean UTC; aware datetimes are compared as physical instants.
- Public extraction signatures are unchanged. `Grid`/`NCGrid.data_point()` and `surface()` use previous; `section()` retains its closest-sample policy.

**Tolerance compatibility decision:** retain the existing numeric tolerance, `0.001` hours (3.6 seconds), and apply the same physical tolerance to datetime requests. Previously datetime subtraction applied the same number in seconds, so equivalent numeric and datetime requests could select different samples. That inconsistency is deliberately corrected. A few floating-point ulps are allowed at the tolerance boundary so representation rounding does not reintroduce the discrepancy. Tests cover `0.999`, values inside/outside the boundary, naive requests and aware requests.

### NetCDF units and reference metadata

Temporal coordinates are converted once to seconds before step derivation; public relative times remain hours.
Supported fixed units are microseconds, milliseconds, seconds, minutes, hours and days, including the explicit aliases in `_TIME_UNIT_LABELS`. Equivalent unit encodings return the same times, aware datetimes and extracted values.

- `time_units` retains the normalised **source** unit label (`us`, `ms`, `s`, `m`, `h` or `d`).
- `source_time_units` retains the exact original units/reference string.
- `source_calendar` retains the original calendar, with `standard` as the omitted-attribute default.
- ISO date-only and date/time references support optional seconds, microseconds and numeric UTC offsets; `Z` and `UTC` are accepted. Reference instants are normalised to UTC.
- Unit-only axes use the existing `1990-01-01 00:00 UTC` default and do not claim an inherent reference.
- Missing/unknown units, malformed references, invalid offset ranges and unsupported calendars raise `ValueError`.
- `standard` and `gregorian` require the reference and samples to be on/after 1582-10-15. `proleptic_gregorian` uses Python's datetime range. Non-Gregorian calendars and months/years are explicitly unsupported.
- Missing, non-finite, duplicate and descending temporal coordinates are rejected; absolute dates outside Python's range are diagnosed.

The existing `_parse_time_units_string()` is reused. Its new no-regex path provides strict parsing for NCGrid. Existing readers that pass their own regex/format retain their date parsing and default-reference fallback.

### Empty, singleton, irregular and static axes

`NCGridVar` distinguishes a temporal `time` dimension from the existing singleton static convention (`static_time`, or another non-time singleton dimension) and two-dimensional static grids. A one-sample `time` variable remains temporal, including at a nonzero time. Static results continue to return no temporal times and remain extractable.

`_calculate_time_step()` accepts seconds consistently. The in-memory `Grid` constructor now converts hours **before** calling it, so a tuple of explicit times is never multiplied by a float.

All intervals, including the last, are checked. Empty, singleton and irregular axes retain explicit tuples of saved seconds. Nominal regular float32 coordinates retain the centisecond step convention only when reconstruction agrees to source float precision. Sub-centisecond axes are not rounded to zero or expanded with unsaved samples. The existing rounded-endpoint tolerance is capped at half an interval so it cannot swallow a whole short timestep.

## Validation

### Local baseline versus candidate

Python 3.12.14, Linux, normal interpreter; no new virtual environment or Git worktree.
The same dependency profile and the unchanged repository warnings-as-errors policy were used for both revisions.

| Suite | Inherited `21617f2` | Implementation `d5281da` | Skips |
| --- | --- | --- | --- |
| Dedicated time regressions | 36 passed, **72 failed** / 108 | **108 passed** / 108 | 0 |
| Existing `test_map_output_pymesh.py` | **110 passed** / 110 | **110 passed** / 110 | 0 |
| Existing `test_time_series.py` | **239 passed** / 239 | **239 passed** / 239 | 0 |
| Existing `test_map_output.py` | Not available in the original non-QGIS Linux environment | Later validated on actual QGIS 4.2.3: baseline 239/239, candidate 239/239 | 0 |

The exact focused baseline IDs and test-module hash are preserved in [`W3_result_time_baseline.json`](W3_result_time_baseline.json). The tests import the real package and create tiny NetCDF files under pytest's temporary directories; no copied function implementations or fabricated GIS providers are used.

Dependency profile: NumPy 2.5.4, pandas 2.3.3, pytest 9.1.1, netCDF4 1.7.5.1.post1, rasterio 1.5.2, geopandas 1.2.0, shapely 2.2.0, h5py 3.16.0 and pyvista 0.49.1.

A separate current-dependency baseline using pandas 3.1.0 produced 66 PyMesh and 131 time-series failures, including pandas deprecations promoted by the existing warning policy. Those inherited compatibility failures were recorded without suppressing warnings or changing production dependency requirements. W5/W7 own general current-dependency acceptance. The candidate has the identical 197 failing test IDs and 152 passes: zero added or resolved failures. This comparison is recorded in the baseline JSON.

### Reproduction commands

Use a separate normal checkout and the selected normal interpreter, without creating a virtual environment:

```text
python -m pip install -e . pytest "pandas==2.3.3"
python -m pytest -q tests/test_result_time_correctness.py --junitxml=focused.xml
python -m pytest -q tests/test_map_output_pymesh.py tests/test_time_series.py --junitxml=existing-results.xml
```

For baseline proof, place the exact new test module into a separate normal checkout of `21617f29eed86d9e123aaf9353934b63d299ca07` and run it against that checkout's unmodified imported package using the same dependency profile. The expected 72 failures are diagnostic evidence, not a passing acceptance job.

The original non-QGIS run could not collect `tests/test_map_output.py` because `qgis.core` was unavailable. The separate native QGIS/MDAL validation subsequently completed successfully; see the native acceptance record below.

### Windows acceptance and review

[Feature-specific Windows run](https://github.com/phantom-branch/PyTuflow/actions/runs/40073571572): Python 3.12 and 3.14, checking out the exact PR head and running the focused and all affected non-QGIS suites. Full environment JSON and JUnit reports are uploaded per interpreter. No existing deferred/graph workflow, common configuration, fixture or sibling branch was changed.

| Platform | Focused | Existing PyMesh/time-series | Failures / errors / skips |
| --- | --- | --- | --- |
| Windows Server 2025, Python 3.12.10 | 108 passed | 349 passed | 0 / 0 / 0 |
| Windows Server 2025, Python 3.14.9 | 108 passed | 349 passed | 0 / 0 / 0 |

Both jobs verified source `d5281da5373b6851b622b61ad949d801d8ac7dc6` and pandas 2.3.3. Report artifacts are `result-times-python-3.12` (ID `12552416857`) and `result-times-python-3.14` (ID `12551844644`). Both environments report QGIS unavailable.

[Codex review requested](https://github.com/phantom-branch/PyTuflow/pull/16#issuecomment-6381359281) after implementation and focused validation. Independent local review found malformed UTC-offset acceptance and a numeric/datetime tolerance-boundary discrepancy; both were corrected and verified with dedicated tests. [Remote Codex review completed](https://github.com/phantom-branch/PyTuflow/pull/16#issuecomment-6381380333) at `d5281da5373b6851b622b61ad949d801d8ac7dc6` with no findings and no unresolved review threads.

### Native QGIS 4.2.3 / MDAL acceptance (completed 24 October 2026)

[Published execution evidence and command summary](https://github.com/phantom-branch/PyTuflow/pull/16#issuecomment-6382509851) validates unchanged candidate `318a282181db642df4ee76ddf3d7731909fb6b3b` against inherited `21617f29eed86d9e123aaf9353934b63d299ca07` using the same QGIS environment and W5 harness `4ca199c55d6d388a0019128332e8f0adafdace93`.

- Real QGIS **4.2.3**, CPython **3.12.15**, Qt **6.11.0**, GDAL **3.13.3**; MDAL provider verified in the real registry.
- Full `tests/test_map_output.py`: **239 passed** on baseline and **239 passed** on candidate, no failures/errors/skips.
- Dedicated `tests/test_result_time_correctness.py`: **108 passed**, no failures/errors/skips.
- W5 strict baseline/candidate comparison: **exit 0**, no problems, changed failures, skipped groups or inherited failures.
- Same harness, dependencies and import provenance for both source snapshots; source checkouts unchanged.
- This closes the W3 provider-validation boundary for the installed runtime; it does not claim validation of every QGIS release.
- Detailed machine-readable summary is also preserved in `W3_result_time_baseline.json` under `qgis_acceptance`. Raw local reports remain with the executing agent; no private paths were committed.

### Final-head validation

[Final-head Windows 3.12 and 3.14 checks](https://github.com/phantom-branch/PyTuflow/actions/runs/40073837344) both passed **108 focused + 349 existing** tests on `318a282181db642df4ee76ddf3d7731909fb6b3b`, with zero failures, errors or skips. Codex's implementation review had no findings; any new review of this documentation-only follow-up remains separately recorded.

## Ownership and W4 handoff

Runtime changes are limited to `output.py`, `map_output.py`, `nc_grid.py`, `helpers/nc_grid_var.py` and the single constructor time-conversion expression in `grid.py`. Dedicated tests and `result-time-correctness.yml` are feature-owned; W5 retains ownership of general CI and common test infrastructure.

W4 / PR #20 can use the validated source checkpoint above when the owner authorises that work. Preserve the time contract, source metadata and tuple-valued axes while developing cache/reader recovery. Do not infer static data from the number of temporal samples. This task does **not** start, rebase or merge #20.

An inherited out-of-scope observation for W4: `Grid(dict).data_point()`/`time_series()` call `_value()`, which attempts to open the `memory` pseudo-path instead of using the existing in-memory surface. The time regressions therefore exercise its supported `surface()` path. No cache or reader-lifecycle repair was included here.

No numerical reductions, depth averaging, safe-save code, package requirements, production consumer pins, deferred/compiled evaluation or sibling PR implementations were modified. No solver, private data or native NAS benchmark was used; no merge or release was performed.
