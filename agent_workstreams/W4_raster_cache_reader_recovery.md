# W4 — Bounded raster surface cache and NetCDF reader recovery

## Implementation checkpoint and branch

- Work package: [PR #20](https://github.com/phantom-branch/PyTuflow/pull/20), branch `fix/raster-cache-reader-recovery`, targeting `master` after [W3 / #16](https://github.com/phantom-branch/PyTuflow/pull/16) was squash-merged.
- Original W4 plan head: `a682f29160e04b495b1baa2324a50410e18c56da`.
- Parent alignment commit: `8304ca8e6d0936cb25e7954e6fef11f24acc7600`, with original W4 head and then-current `master` (`0679d9c758c07e786f23d552295366baa4bea10b`) as parents. This preserves the original branch history and incorporates the accepted W3 source without force pushing or duplicating production changes in the PR diff.
- Core implementation: `a5c1a223791bd669e745eb6d0f2448640ba4f98c`.
- Streaming reductions: `57badb0cce19b7114a39f130a22fe29023d98a78`.
- Reader ownership fix for minimum: `742f298e28a77b00f958a96dc89ddf3c1af0b8e5`.
- Mask-preservation fix following Codex P2 finding: `20d1cc5b68b5a8b3a3f058f7ff56baa1970c6a66`.
- Original validated W4/QGIS checkpoint: `183f62c7ef4a1597670f23cd9999ffc019f9be7c`.
- [SMB benchmark evidence and recommendation D](https://github.com/phantom-branch/PyTuflow/pull/20#issuecomment-6389083597): 216 accepted process trials and 312 three-trial medians, used independent normal source checkouts; no code from the experimental prototypes was pushed.
- Recommendation D implementation: `28c5d9e66967899aab9b150ffefcf9aaabc4f241`; focused aggregation tests: `8b673ff3af703984ecf5b9c63559928da25e70b3`; all-missing fix: `fb2eaa0f7a7a7e623c6ba11d2dbc82c7014df1d1`.
- Follow-up Codex P2 fixes: `0e18751b6021a1cae9d71c8c6583d278ae0ec27e`. Packed NetCDF time-block sizing uses a conservative decoded float64 payload estimate when scale/offset packing is present; each completed block and its filtered array are released before the next read, avoiding overlapping lifetimes. Dedicated regressions cover decoded dtype and weakref-based buffer disposal.
- Read the PR head before testing. **The earlier QGIS and native SMB validation evidence covers the pre-D implementation only**; repeat native QGIS and SMB acceptance before marking the new code ready or merging.

## Configurable aggregate memory and bounded block reductions (recommendation D)

The previous W4 four-slice / 64 MiB-per-variable cache was replaced by a **single reader-wide LRU** spanning `(data_type, time_index)` entries. An entry accounts for its NumPy array data **plus any allocated mask**. Results from different variables compete for the same budget; a slice larger than that budget is returned but **not retained**. Cached surfaces and returned arrays remain independent defensive copies and preserve `MaskedArray` semantics.

- Configure the reader through the optional keyword `memory_budget_bytes` on `Grid(...)` or `NCGrid(...)`.
- **Default: 256 MiB per reader**, not 1 GiB; e.g. `NCGrid(path, memory_budget_bytes=512 * 1024**2)` for the measured multi-variable hotset, or `1024 * 1024**2` for an explicitly chosen 1 GiB limit. Values must be positive integers.
- There is **no independent four-slice cap**; the aggregate bytes govern retained slices. Changing the budget affects one reader instance, not a process-wide pool. Multiple readers can each use the configured allowance.
- The historical `_surface_cache` per-type views remain available internally; `_surface_lru` and `_surface_cache_bytes` record reader-wide eviction and retained bytes.
- Explicit `load_into_memory()` and resident `Grid(dict)` are **intentionally not bound** by the reader's lazy budget; they retain the full original/preloaded arrays.
- Source/library HDF5 caches, Python runtime allocations, caller-owned output arrays, and oversized single-surface operations lie outside this retained budget and require process-level planning.

**Reductions:** `maximum()` and `minimum()` bypass the surface-LRU path for time scans. They evict the retained lazy cache at scan start and read **contiguous blocks** via the existing NetCDF reader instead of one slice at a time. The block-step size derives from the variable's on-disk dtype/shape, up to **one-third** of `memory_budget_bytes` for input payload and remaining headroom for mask, selection and reducer temporaries. When feasible, block size is aligned downward to the NetCDF time-chunk length, with a partial final block. A single slice larger than the allowance can still be read as one unavoidable operation. This is a **bounded working allocation heuristic**, not a cap on peak RSS or HDF5's internal cache.

An ordinary reduction **clears prior retained cache entries before using the working block allowance**. Thus it does not quietly stack an additional block buffer on a full 1 GiB reader cache. The unchanged explicit full-memory mode remains an opt-in exception. Ordinary surface extraction still uses the aggregate cache; repeated/ordered/negative/Boolean selectors preserve the W3 time contract and requested shapes.

**Metadata:** `Grid._header()` memoises time counts, static status and spatial header values once per variable from the loaded, normally immutable `_info` DataFrame; replacement of that DataFrame invalidates the memoised entries. Callers that intentionally mutate metadata **in place** should use a new Grid/NCGrid reader. This avoids rebuilding the public `times()` results on every cache hit while leaving public `times()` unchanged.

For illustration, the benchmark's compressed SMB 40-step × 1536² float64 extrema took about **3.88 s** with W4's prior single-step scan versus **1.21 s** with a **256 MiB block prototype** (four steps per read). Its 288 MiB three-variable flux hotset fitted at **512 MiB aggregate** (not at 256 MiB). Those are results from the separately executed **prototype**, not an assertion of equivalent performance in this production implementation. A new matched Windows/SMB comparison is required.

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
- [Current Windows acceptance workflow](https://github.com/phantom-branch/PyTuflow/actions/runs/40085144957): Python 3.12/3.14, **24 focused** cases plus **457 existing** cases per interpreter, all passing. A subsequent Codex P2 finding identified mask loss for resident NumPy masked arrays; the follow-up adds **2 focused cases** (26 total) and preserves masks in resident/cache copies, stacking and reductions. [Reviewed W4 head Windows run](https://github.com/phantom-branch/PyTuflow/actions/runs/40085840750) passed all 26 focused and 457 existing tests per supported interpreter. That is pre-D evidence, not validation of the new implementation.
- [Native QGIS/MDAL acceptance](https://github.com/phantom-branch/PyTuflow/pull/20#issuecomment-6388178669) passed at pre-D head `183f62c`: baseline and candidate **239/239 QGIS** each; **134 W3/W4 focused**; strict comparison exit 0. Fresh provider acceptance remains **required** for this changed code.
- [Initial D Windows run](https://github.com/phantom-branch/PyTuflow/actions/runs/40169222591): **36 dedicated and 457 existing** passed per Windows interpreter. The later all-missing run passed **37 + 457** per interpreter.
- [Post-Codex memory fixes — Windows](https://github.com/phantom-branch/PyTuflow/actions/runs/40169892996): **39 dedicated and 457 existing** passed on each of Python 3.12 and 3.14, no failures/errors/skips. The correct raw runtime evidence is limited to these native Windows runner jobs; do not claim the production D version has repeated the local SMB/QGIS benchmark yet.

## Coordination and exclusions

Retain the W3 time-unit and timestep-selection contract. The source and tests are W4-owned; W5/#19 retains shared regression infrastructure and W8/#23 owns numerical FV reductions. Do not modify those workstreams to manufacture green CI. No production dependency pins, deferred/graph workflows, solver runs, private model data, merge or release are included. The separate approved native SMB benchmark was performed before D implementation, with only sanitised aggregates posted.

The earlier Codex P2 mask-preservation issue was fixed in `20d1cc5` and the review thread resolved. Recommendation D changes need a **new Codex review on the exact head**, followed by native QGIS/MDAL and SMB performance acceptance. Do not merge or claim acceptance on the strength of the prior W4 reviews.
