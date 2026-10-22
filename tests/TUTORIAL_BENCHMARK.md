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

## Current comparison and limitations

The harness compares individual deferred context resolution, uncached batch,
and cached batch on the same parsed TCF. It compares complete immutable
BatchInputCommand, BatchInputReference, FileReference,
DeferredDatabaseActivation and DeferredDatabaseSource fields, including
UUID, command ordinal, owner, line, activation order, source row and layer.
Both **missing and extra** records, pure reordering and incomplete/error
runs fail. Duplicated records must not be collapsed. Unresolved primary
variables fail acceptance. Unavailable graph counters appear as null, not zero.

The compiled-tree API and its instrumentation belong to
[PR #9](https://github.com/phantom-branch/PyTuflow/pull/9).
**Reconcile the PR #9 commits into #7 before final benchmarking.**
In the current PR #9 implementation, the cached batch mode also compiles
the control tree, and the report captures its actual graph counters when
that implementation is present. On a checkout without #9 those counters
remain unavailable. Retargeting the PR alone does not move its Git commits.

To measure old cached (without compiled tree) versus compiled cached
**on the same source head**, P2 needs a safe per-call graph opt-out,
while preserving the existing cached semantics. Until that interface
is supplied, report uncached and compiled-cached as separate modes, but
do not invent an additional cached-without-graph measurement.

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
