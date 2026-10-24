# W4 — Bounded raster surface cache and NetCDF reader recovery

## Implementation checkpoint and branch

- Work package: [PR #20](https://github.com/phantom-branch/PyTuflow/pull/20), branch `fix/raster-cache-reader-recovery`, targeting `master` after [W3 / #16](https://github.com/phantom-branch/PyTuflow/pull/16) was squash-merged.
- Original W4 plan head: `a682f29160e04b495b1baa2324a50410e18c56da`.
- Parent alignment commit: `8304ca8e6d0936cb25e7954e6fef11f24acc7600`, with original W4 head and then-current `master` (`0679d9c758c07e786f23d552295366baa4bea10b`) as parents. This preserves the original branch history and incorporates the accepted W3 source without force pushing or duplicating production changes in the PR diff.
- Core implementation: `a5c1a223791bd669e745eb6d0f2448640ba4f98c`.
- Streaming reductions: `57badb0cce19b7114a39f130a22fe29023d98a78`.
- Reader ownership fix for minimum: `742f298e28a77b00f958a96dc89ddf3c1af0b8e5`.
- Mask-preservation fix following Codex P2 finding: `20d1cc5b68b5a8b3a3f058f7ff56baa1970c6a66`.
- This documentation-only follow-up records the contract separately; validate the actual branch head when comparing results.

## Lazy-cache contract

`Grid._surface()` and `NCGrid._surface()` now retain an LRU dictionary **per variable**, not a float64 time cube. The ordinary retained cache has these hard limits:

- **At most four slices per variable.**
- **At most 64 MiB of stored arrays per variable**, except when one individual surface exceeds 64 MiB; one such surface may be retained alone.
- Reads of one timestep therefore allocate **one two-dimensional source slice** and its returned copy, never an all-time cube. Temporary returned arrays for an explicit multi-index selection or full time selection may still be large by the caller's request.
- The bound concerns the retained `_surface_cache` (not other Python/NumPy temporaries or provider-internal buffers); it does not multiply with the length of the file's time axis.
- A hit updates LRU order; eviction removes the least-recently-used slice. Returned data are independent copies, so a caller cannot corrupt cached values. NumPy `MaskedArray` subclasses retain their masks through copies, temporal stacking and extrema calculations.
- The old `_cached_data` remains reserved for `Grid(dict)` / `load_into_memory`, which are intentionally **unbounded** with respect to the lazy budget, loading the entire variable when explicitly requested.

Temporal selection accepts integers and NumPy integer scalars, 1-D integer lists/tuples/ndarrays, 1-D Boolean masks, and Python slices including zero bounds, reverse direction and non-unit steps. It normalises Python-style negative indices, preserves requested order and repeated timesteps, and rejects invalid/out-of-range selectors. A single selected timestep retains the existing squeezed 2-D return shape; multi-timestep requests stack into time-first arrays; empty selection produces an empty time-first array. Static variables retain one 2-D slice.

`maximum()` and `minimum()` reduce incrementally across requested timesteps without materialising an all-time array; the NCGrid public wrappers keep the NetCDF handle open during both operations. Flux already loops across timesteps and now benefits from the bounded cache. The previously inherited memory pseudo-path lookup on `Grid(dict)` has been corrected to use its resident data for point/time-series reads.

For reference, the old float64 allocation at 500 × 2000 × 2000 would be **16 GB per variable**, versus one 2000 × 2000 slice at **32 MB**. This is analytical allocation arithmetic, not a native benchmark. New tests examine actual retained array shapes and slice counts for small generated time axes.

## NetCDF reader ownership contract

`NCGrid._open()` owns and closes a handle only if it opened that handle. Its `finally` path clears `_nc` even after an extraction exception. Nested `_open()` calls borrow the outer handle; a handle acquired through `open_reader()` remains open until explicit `close()`. Repeated `close()` is safe. A fault does not silence the original exception, leave a closed handle cached or block a subsequent successful read.

## Regression evidence

Dedicated `tests/test_raster_cache_reader_recovery.py` uses small generated NetCDF and in-memory fixtures. It exercises allocation versus time count, LRU hits/evictions, returned-copy isolation, direct numerical parity, reordered/duplicate/reversed/empty/Boolean selectors, invalid selection, static data, explicit preload, resident in-memory readers, streaming extrema, masked static/temporal resident arrays, injected read failures, nested contexts and explicit ownership.

Run in a normal supported Python environment:

```text
python -m pip install -e . pytest "pandas==2.3.3"
python -m pytest -q tests/test_raster_cache_reader_recovery.py
python -m pytest -q tests/test_result_time_correctness.py tests/test_map_output_pymesh.py tests/test_time_series.py
```

- [First validated Windows implementation run](https://github.com/phantom-branch/PyTuflow/actions/runs/40084833007): both Windows Python 3.12 and 3.14 jobs passed **23 focused** and **457 inherited W3/PyMesh/time-series** tests, with no failures.
- The streaming-extrema follow-up exposed a reader-context issue in `NCGrid.minimum()` (23 passed, 1 failed in the first follow-up run); this was corrected in `742f298`, without suppressions or expectation changes.
- [Current Windows acceptance workflow](https://github.com/phantom-branch/PyTuflow/actions/runs/40085144957): Python 3.12/3.14, **24 focused** cases plus **457 existing** cases per interpreter, all passing. A subsequent Codex P2 finding identified mask loss for resident NumPy masked arrays; the follow-up adds **2 focused cases** (26 total) and preserves masks in resident/cache copies, stacking and reductions. The new exact-head run must be checked separately rather than claimed passing in advance.
- This work does **not** claim an actual QGIS/MDAL provider run. QGIS/MDAL comparison on an installed QGIS 4 runtime remains a separate acceptance lane to be conducted using the actual provider and the accepted W3 baseline. Never treat a non-QGIS run as passing the QGIS suite.

## Coordination and exclusions

Retain the W3 time-unit and timestep-selection contract. The source and tests are W4-owned; W5/#19 retains shared regression infrastructure and W8/#23 owns numerical FV reductions. Do not modify those workstreams to manufacture green CI. No production dependency pins, deferred/graph workflows, solver runs, native SMB benchmarks, private model data, merge or release are included in this implementation.

The first Codex review on documentation head `c6697f0` found a genuine P2 mask-preservation issue; the follow-up implementation and regression tests are in `20d1cc5`. Re-review the new head after its CI gates pass. Final readiness also requires the separate native QGIS/MDAL lane. Any QGIS results and Codex review findings must be recorded explicitly.
