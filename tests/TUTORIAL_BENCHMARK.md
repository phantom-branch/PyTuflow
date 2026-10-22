# P3 — Public TUFLOW tutorial benchmark

This is a **read-only syntactic-dependency benchmark**, not an end-to-end
simulation launcher or a substitute for the materialised ryan-tools input
preflight. No solver or project batch file is executed.

## Dataset and setup

Use the pinned **public** fixture in
[ryan-tools-test-data](https://github.com/Chain-Frost/ryan-tools-test-data/tree/feat/tuflow-preflight-example-fixture/tuflow/example_input_preflight),
not a private/local/SMB engineering model. In a ryan-tools checkout run:

~~~powershell
git submodule update --init tests/test_data
$Bundle = "E:\Github\ryan-tools\tests\test_data\tuflow\example_input_preflight"
~~~

From the **PyTUFLOW** checkout:

~~~powershell
py -3.14 -m pytest -q tests/test_tutorial_benchmark.py
py -3.14 tests/benchmark_tutorial_dependencies.py --bundle $Bundle --output "$env:TEMP\pytuflow-public-tutorial.json"
~~~

The benchmark checks SHA-256 of the ZIP **and all 1,464 archive members**,
validates the baseline TCF/run counts (161/174), then extracts to one new
temporary local directory. Extraction and checksumming are **not timed**.
A missing fixture returns **status=unavailable, exit 2**, never PASS.
Malformed archive/launcher/baseline contents fail visibly. Output must not
be written into the fixture checkout.

Launchers are **read as text, never executed**. Their event/scenario flag
values are stored as dictionaries and passed directly into PyTUFLOW, so
quoted multiword values survive without lossy whitespace tokenisation.
The displayed `-s1 value` label is diagnostic text only, not reparsed input.
The JSON counters distinguish `input_runstates_constructed`,
`input_runstates_elided`, `invariant_projection_reuses` and
`reusable_input_groups`. The first two measure actual constructor work,
while the latter two distinguish whole-run reuse from eligible literal input
groups in mixed models. An observed zero must not be confused with an
unavailable (`null`) metric; no counter alone proves a speedup.

For CPU hotspot profiling (cProfile **distorts** wall time and is not
valid speedup evidence), use the same public TCF, from the PyTUFLOW checkout:

~~~powershell
py -3.14 tests/profile_tutorial_dependencies.py --bundle $Bundle --tcf "EG16_~s1~_~s2~_002.tcf"
~~~

For a genuine multi-context tutorial case:

~~~powershell
py -3.14 tests/benchmark_tutorial_dependencies.py --bundle $Bundle --tcf "EG16_~s1~_~s2~_002.tcf"
~~~

For a **repeated-combination throughput stress test**, NOT 500 distinct
context signatures:

~~~powershell
py -3.14 tests/benchmark_tutorial_dependencies.py --bundle $Bundle --tcf "EG16_~s1~_~s2~_002.tcf" --runs 500
~~~

Use --trials 3 (default) for three rotating-order warm-cache repetitions
on **one workstation / source checkout / extracted dataset**. --trials 1
is suitable only for a smoke test. Report source SHA (or explicitly missing
Git information), Python version, requested runs, documented combinations,
distinct complete flag signatures, counters, trial values and medians,
phase timings, and ~20 ms sampled RSS **if psutil is installed**.
Sampled RSS is not an exact allocation peak or proof of memory savings.
Phases are measured independently and need not sum exactly to wall time.

## Optional full public CI replay

PR unit-test CI checks syntactic fixture safety and four-mode parity on
minimal correctness fixtures, **not** the full 161-TCF tutorial dataset.

To run the complete approved public replay without an SMB workstation,
apply the `run-public-tutorial` label to PR #7. Its
`public-tutorial-replay` Windows Python 3.14 job checks out a specific
public ryan-tools-test-data revision
(`d2dae3ecf9a7ed306e1340de54a8d12ca9f53f58`), verifies the pinned
ZIP/member hashes and manifest, then benchmarks all documented TCF/run
combinations with three rotated trials and attaches a JSON report.
Any unsupported case, missing/extra identity, unresolved primary path or
run error fails the job. No solver is started. The job is opt-in to avoid
unnecessary Windows CI cost. Once the workflow exists on the default branch,
it can also be triggered via `workflow_dispatch` with its
`run_public_tutorial` option.

The uploaded JSON is **public tutorial syntactic evidence only**; materialised
GIS/BC/attribute checks require the independent ryan-tools public preflight
runner, and the native SMB benchmark remains a later separate agent task.

## Current comparison and limitations

The harness compares **four modes on the same source checkout and parsed TCF**:

1. Individual deferred context construction.
2. Uncached batch (scope/command caches disabled).
3. Cached batch **without** the compiled graph (`compile_tree=False`).
4. Cached batch **with** the compiled graph (`compile_tree=True`).

The third and fourth modes keep the same non-graph batch caches, isolating
the graph's effect. Report their three rotating-trial wall-time medians and
the signed graph time-reduction percentage; a negative percentage means
the compiled tree was slower. The ratio is only for the public tutorial
workload, NOT private distinct-run or SMB throughput.

The comparator examines complete immutable
BatchInputCommand, BatchInputReference, FileReference,
DeferredDatabaseActivation and DeferredDatabaseSource fields, including
UUID, command ordinal, owner, line, activation order, source row and layer.
Both **missing and extra** records, pure reordering and incomplete/error
runs fail. Duplicated records must not be collapsed. Unresolved primary
variables fail acceptance. Unavailable graph counters appear as null, not zero.

The compiled-tree API, instrumentation and safe per-call graph opt-out
are implemented in [PR #9](https://github.com/phantom-branch/PyTuflow/pull/9).
This PR inherits that implementation. Its `compile_tree=False` option keeps
the other cached-batch optimisations enabled. Graph counters are measured
separately and are not inferred from elapsed time. The benchmark does not
claim that the graph eliminates all InputRunState constructions; the P2
run-state allocator retains its conservative correctness fallback.

If PR #9 advances again, incorporate those commits and recheck exact-head
CI before final same-source-head benchmarking.

Syntactic equality does NOT prove physical file existence, wildcard
expansion, GeoPackage layers, Shapefile/GPKG feature attributes, BC row
activation and selection, GIS table links, rainfall/raster metadata or
missing-input parity. The separate public ryan-tools preflight diagnostic
remains the materialised acceptance gate. Report status
passed_syntactic_parity is deliberately narrower than full acceptance.
The public tutorial set does not simulate 500 genuinely distinct production
event/scenario contexts.

The older tests/benchmark_batch_dependencies.py and
tests/profile_batch_dependencies.py are **synthetic microbenchmarks** for
developer correctness, instrumentation and CPU profiling only. Their
durations must not be advertised as native SSD/SMB performance gains.

## Native SMB validation deferred to separate agent

The designated SMB-capable agent alone performs native B1/B2/B3 checks
**in place** after P1/P2/P4 implementation milestones. No proprietary
files, SMB paths, local reports or captures may enter GitHub, CI, test-data,
attachments or PR review comments. Public PRs may contain anonymised
aggregate results. Historical 22 October 2026 B0 measurements used older
parser/consumer revisions; they cannot validate the compiled graph and
must not be combined with future same-head comparisons.

Before merge: run Windows Python **3.12 and 3.14** tests at exact PR head;
run the tutorial differential with zero missing/extra/unresolved/error
records; run separate materialised preflight; record measured graph and
run-state allocations after #9. Do not merge, publish, repin or request
Codex review while implementation remains incomplete.
