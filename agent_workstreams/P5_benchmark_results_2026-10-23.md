# P5 workstation benchmarks and file-sharing investigation

**Date:** 2026-10-23, Australia/Perth. **PR:** #12. **Status:** supplied correctness
gates pass; measured graph benefit remains limited. No merge or release performed.

## Source and protocol

- Retained benchmark source: `c305a6d2d5425ad72f388ef386ace375b4e53f99`,
  PyTUFLOW 1.2.6, Windows/Python 3.14.6. Initial measurements on an earlier
  source were superseded after agent fixes arrived; the figures here use c305a6d.
- Later CI/documentation head `eebbb166e109f0894689398c3b3d4a3734e4a911`
  has identical parser and benchmark code. The `pytuflow` Git tree at both is
  `0f3115cc964691a6b86830026fffcb3d5aa013ef`; the tutorial harness blob at both
  is `292f0a3891ba3e4b3e0cdd1fb96d4d6a670b536b`.
- Consumer diagnostic source: ryan-tools `5685fda8c2259bae99ec01f137d2a5ea905408e3`,
  PR #143. Its later `f63bc029` update changes an unrelated regression test only;
  library and diagnostic code are identical. Child PR #156 is a separate consumer
  implementation and was not substituted into this benchmark.
- Four modes on the same parsed TCF/source/flags: individual deferred,
  uncached batch, cached batch with graph off, cached batch with graph on.
  Three sequential warm-cache trials rotate mode order. Parse is reported
  separately. Mode totals include context construction and reference/database
  projection, not solver execution or downstream physical inventory.
- M480 and N42 timed workloads ran sequentially on SMB. Their literal launcher
  flags were reread and match the selected 480/42 distinct combinations.
  Launchers and TUFLOW were never executed. Materialised correctness replays
  are separate from these parser timings.
- The user's existing SSD copy was used for the untimed M480 file/parameter/I/O
  investigation. Its launcher flags match; all 49 required file sizes and four
  control-source hashes match the network copy. Large binary contents were not
  exhaustively hashed. This is not a new SSD-versus-SMB speedup comparison.

## Correctness and tests

- **273 focused parser/integration tests**, **67 consumer tests**, **2 CI comparator
  tests**, and compilation pass. Consumer tests enable both real-fork gates;
  they report one NumPy binary-compatibility warning with process exit 0.
- Verified public archive: 1,464 members, 161 TCFs / 174 documented combinations,
  SHA-256 `e374c8e072679fc6c4dc11e63b270caa1101b6aebb84d70060872cdd1b0aa7d6`,
  fixture revision `d2dae3ecf9a7ed306e1340de54a8d12ca9f53f58`.
  Full four-mode parser comparisons and the separate eager/deferred/batch
  materialised/public-preflight replay pass. No missing, extra, failed or
  unresolved parser records.
- M480: all 480 runs pass ordered parser identity parity and full materialised
  eager/deferred/batch parity: 12,480 identities / 49 resolved inventory paths.
  N42: all 42 pass, retaining 1,922 identities / 196 paths. Both individual and
  batch public preflight pass with zero issues and identical checked paths.
- All eight active hosted checks pass at eebbb16; the optional second full-public
  replay is skipped. [Windows integration and full tutorial replay](https://github.com/phantom-branch/PyTuflow/actions/runs/39883026606)
  includes the three-way upstream compatibility differential. Green comparison
  CI does **not** mean every upstream TMF test passes: pre-P5 and P5 both have
  **39 failed, 530 passed, 11 skipped** on hosted Python 3.14, with **zero new
  P5 regressions**. Three pre-P5 differences from canonical upstream remain
  separately identified below.

## Timings and work avoided

Median parser seconds; public totals are sums of per-model medians, not one
suite wall-clock measurement:

| Workload | Runs | Individual deferred | Uncached batch | Cached graph off | Cached graph on |
| --- | ---: | ---: | ---: | ---: | ---: |
| Public tutorial, 161 TCFs | 174 | 7.699 | 7.712 | 5.821 | 5.885 |
| M480, SMB | 480 | 68.230 | 68.469 | 42.895 | 42.790 |
| N42, SMB | 42 | 35.586 | 36.446 | 11.310 | 11.367 |

Graph-on is about **1.1% slower** on the public aggregate, **0.24% faster** on
M480 and **0.50% slower** on N42. These small differences do not establish a
meaningful general graph speedup. Existing batch-cache gains are much larger
and must not be attributed to the new group cache.

All native trial values, seconds (chronological within each mode):

| Workload / mode | Trial 1 | Trial 2 | Trial 3 |
| --- | ---: | ---: | ---: |
| M480 individual | 67.345 | 69.498 | 68.230 |
| M480 uncached | 68.469 | 69.205 | 67.235 |
| M480 cached graph off | 43.117 | 42.895 | 42.541 |
| M480 cached graph on | 42.922 | 42.790 | 42.138 |
| N42 individual | 36.643 | 35.496 | 35.586 |
| N42 uncached | 35.900 | 36.446 | 37.118 |
| N42 cached graph off | 11.345 | 10.876 | 11.310 |
| N42 cached graph on | 11.866 | 11.240 | 11.367 |

Native parse times: M480 0.752 s; N42 2.047 s, outside mode totals.
Last graph-on trial phase costs (M480 / N42): compilation 0.002 / 0.008 s,
context construction 33.448 / 9.509 s, reference collection 2.804 / 0.420 s,
database projection 4.193 / 0.626 s. These categories do not exhaust the total.
Repeated context work remains the dominant measured parser cost.

Last-trial graph counters (public figures sum across TCFs):

| Workload | Graph-off input constructors | Graph-on input constructors | Elided constructors | Reusable groups | Contexts constructed | Whole-run projection reuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Public | 7,073 | 7,047 | 26 | 328 | 174 | 0 |
| M480 | 31,680 | 29,764 | 1,916 | 4 | 480 | 0 |
| N42 | 4,148 | 4,148 | 0 | 0 | 42 | 0 |

An elision skips a normal input-state constructor; independently cloned mutable
wrappers are still allocated. It is neither a count of disk checks nor time saved.
M480 avoids 6.0% of constructors. All 1,920 eligible visits account for four initial
constructions plus 1,916 reuses; there are no clone/exception fallbacks. Its other
29,760 visits are ineligible. N42 marks all 4,148 ineligible. This points to limited
coverage, not failed matching among M480's eligible keys.

Maximum sampled process RSS, MiB (individual / uncached / graph off / graph on):
M480 **440.3 / 441.0 / 439.8 / 439.8**; N42 **428.8 / 428.3 / 428.5 / 428.5**.
Sampling is approximately every 20 ms, includes native allocations and retained
process memory, and is not an isolated allocator-peak or memory-regression proof.

## M480: actual file sharing, parameters and graph coverage

The private SSD exports capture every run's launcher flags, final variable map,
event-variable map, graph input decisions, syntactic file references and final
materialised required-file list. All 480 parameter records are present and unique.
The final variable maps have nine constant and six varying parameter names; four
event-variable fields vary. Values and identifying paths remain private.

- Every run requires **25 distinct normalised paths**; **23 are common to all 480**
  (92% of each run's required paths). The union is **49**.
- The remaining paths are two alternative BC database files and 24 BC-source CSVs.
  Each run selects one of each, producing **48 unique required-file sets** across
  the 480 simulations. The ten-value temporal-pattern flag does not add distinct
  files here; parameters can change while the required path set stays the same.
- All scenario flags are fixed. Event dimensions have 6 / 4 / 10 / 2 values.
  Geometry, grid, GIS and materials reference groups remain constant; the two
  primary inventory variants are BC-related, not extent changes.
- The requested launcher lines 4-49 contain 46 simulations. Their primary reference
  inventory is identical, with **22 of 23 file-bearing groups constant**; only the
  BC secondary-source group varies. Five source-inventory variants occur in that
  slice, despite 46 distinct parameter combinations.
- **Graph and materialised required-path sets match on every one of the 480 runs.**
  Input discovery is correct for this model; broader safe construction reuse is
  the missing optimisation.

Observed graph-construction categories in the private SSD trace:

| Input visits | Static category | Interpretation |
| ---: | --- | --- |
| 24,480 | Not a READ input | Control/settings/variable/other states; profile costs before optimising |
| 3,840 | Scenario-conditional command | Current partial-group cache rejects these, despite fixed scenario flags here |
| 1,920 | Candidate for the literal path | Four initial seeds, then 1,916 constructor bypasses |
| 1,440 | Unsupported command | Outside the two supported READ command classes |

These classifications are observations, not sufficient invariance proofs. Equal
file sets do not establish equal mutable state, settings or database side effects.

## File checks, path spelling and diagnostic overhead

The untimed SSD production batch-preflight trace observes:

| Phase | Selected observed Python API requests |
| --- | --- |
| Initial parse | 13 `Path.resolve`, 21 opens, 1 SQLite connection, 1 raster open, 12 glob requests |
| Post-parse batch evaluation | **0 observed file-I/O requests** |
| Per-run reference collection | **0 observed file-I/O requests** |
| Shared raster metadata | 6 raster opens |
| Shared unique inventory | **26 stat calls, 1 directory scan, 13 SQLite connections** |

The production inventory receives 50 path spellings for 49 normalised locations.
One pair of TIF spellings is confirmed to refer to the same file. This small alias
duplication is distinct from thousands of repeated checks. Shared inspection is
not performed again merely because a file appears in another run's manifest.

The temporary consumer parity diagnostic is different:
`tests/fixtures/tuflow_example_repro/run_checks.py` deliberately calls `Path.resolve()`
inside its per-reference physical-identity loop. A separate SSD trace observes
**12,480 identity-resolution calls for 49 normalised targets**, in addition to
13 parse-time calls. This overhead must not be attributed to the production graph
or interpreted as its disk-check count. Parser timings above exclude this loop.

A direct workstation check confirms mapped-drive `.resolve()` changes spelling to
UNC; `.absolute()` retains the drive spelling. The SSD spelling stays unchanged.
No `.resolve()` occurs in the group-cache key, compiled graph or batch evaluator.
M480's eligible groups all match after their first seed, so the evidence does not
support path-spelling mismatch as the cause of its limited elision.

The trace counts Python API requests, **not physical disk reads or SMB requests**.
Native GDAL/SQLite/OS internal calls and sidecar opens are not comprehensively
traced. Warm OS caches may satisfy requests. Shared checks have phase attribution;
the required-file manifest does not claim that each file is opened in every run.

## Recommended next work

1. **Remove repeated identity-resolution overhead from the temporary benchmark
   diagnostic.** Memoise physical identity per exact input spelling within an
   invocation, preserving deliberate alias comparison and original mapped-drive
   paths for I/O. Do not replace archive-containment/link checks or globally swap
   `resolve()` for `absolute()`. Validate mapped-drive/UNC and linked-path cases.
2. **Extend the proof to invariant scenario-conditioned groups in mixed models.**
   M480 has fixed scenario flags and 3,840 rejected conditional READ visits.
   Prove exact slot/order, branch activation and transitive variable/settings
   dependencies per group. Keep rainfall/BC effects separate. Never infer safety
   solely from the observed 92% path sharing.
3. **Profile and expand useful command coverage.** Account separately for proof,
   prototype certification, cloning and normal construction. Target proven
   constant GIS/grid/material groups and relevant-variable signatures rather than
   the entire event tuple. Context construction dominates; adding more graph
   lookups without avoiding expensive work is unlikely to help.
4. **Avoid preparing caches that cannot be reused.** The public replay seeds
   314 groups in single-run TCFs; N42 has no eligible group. Consider a cheap
   eligibility/single-run bypass or lazy certification while preserving streaming,
   failure isolation, counters and bounded invocation-local storage.
5. **Keep existing compatibility work separate.** The three canonical-upstream
   differences already present before P5 are `test_control_file::test_load_rainfall_database`,
   `test_input::test_input_files_ref_in_gis` and
   `test_input_context::test_input_files_ref_in_gis`. Investigate them in a separate
   eager/shared-behaviour change with owner-facing before/after evidence. This
   benchmark report changes no eager functionality, and the clone/counter fixes
   being validated repair the new P5 optimisation rather than original eager code.

## Retained artifacts and delivery

Raw native reports, file names, source snippets and parameter values are not
uploaded. Private SSD exports include `M480-run-parameters.csv`,
`M480-parameter-cardinalities.csv`, `M480-event-parameter-cardinalities.csv`,
`M480-materialised-input-files.csv`, `M480-graph-file-references.csv`,
`M480-graph-inputs.csv`, `M480-unique-inventory.csv`, `M480-inventory-aliases.csv`,
`M480-observed-python-io.csv` and `M480-diagnostic-path-resolutions.csv`, plus
aggregate JSON summaries. The workstation retains source snapshots, public
results, native reports and process exit records outside Git.

Only anonymised findings are committed here. PR #12 remains draft; further proof
coverage is not implemented by this report. Consumer PRs and production dependency
pins are unchanged. No engine, launcher, release or additional merge was performed.
