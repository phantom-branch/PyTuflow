# Graph-free scope-driven dependency experiment

**Status:** isolated draft PR #45; not approved for upstream PR C, production ryan-tools, release, or default use.

## What is being tested

The production master at 0d4082b06c3e4cbb4b72cfdd24fa7aa22445fac7 includes the accepted PR #41 manifest/fragment optimisation and PR #42 semantic regressions. The fast 480-context actual-consumer result was recorded at an earlier PR #41 runtime SHA (median 4.260864 s SSD; see PR #41); this must be freshly remeasured against this exact master and current consumer.

This branch adds an alternative experimental producer: one pass over the **already parsed** TCF per distinct provided run, using its original Context/RunState machinery. It does not synthesize runs from PR #44's read-only inventory, nor does it create dependency graphs. It accepts the caller's explicit scenario/event flag strings and retains the library's existing scope/variable/TEF semantics, input order and error boundaries.

- **Keep:** original Context, scope and event evaluators, TEF, Set Variable, deferred FileReference and per-activation database accessors.
- **New experiment:** one small graph-free collector, built around those APIs; immutable per-run records; once-per-invocation parsing of raw variable declarations; exact-flag duplicate reuse only.
- **Do not use:** compiled control tree, transitive variable graph, effective dependency manifests, fragment cache or cached mutable RunStates.
- **Intentionally unchanged:** default TCF.context, collect_file_dependencies, collect_batch_dependencies, physical validation, ryan-tools, QGIS, and solver execution.
- **Limitations:** this intentionally may be slower. Successful graph-free parity does not establish throughput, and success on preflight syntax does not establish physical file/GIS materialisation. It still imports existing batch record dataclasses, so source-line reduction requires a later curation step; this branch measures the alternative evaluator, not a complete removal of modules.

## Local use

From a checked-out PR #45 worktree and installed package:

    python -m pytest -q tests/test_scope_driven_dependencies.py
    python tests/benchmark_scope_driven_dependencies.py --tcf "X:\PRIVATE\model.tcf" --flags-file "X:\PRIVATE\flags.json" --mode scope --verify
    python tests/benchmark_scope_driven_dependencies.py --tcf "X:\PRIVATE\model.tcf" --flags-file "X:\PRIVATE\flags.json" --mode fragments --verify

The flags file is a **local only** JSON array of complete argument strings, in actual scheduled order. Do not infer or generate the Cartesian product from discovery. The runner prints aggregated metrics, never paths/flags/references. The reported collect_seconds excludes model parse, process startup and post-timing parity evaluation. Measure the actual consumer separately to compare the historical ~4.26 s boundary.

Additional producer controls:

    --mode batch-graph-off
    --mode batch-uncached

Both run on the same PR #45 parser source and therefore isolate existing batch graph/reuse benefits without another checkout. --verify compares complete per-run immutable records to the current source's fragment collector. For each native comparison, still inspect any first differing record and explain its cause **locally**; no private fragments are to be uploaded.

## Acceptance decision

Require all the following before recommending this approach for upstream PR C:

1. Hosted Windows Python 3.11/3.12/3.14 and Linux Python 3.12 parser/scope tests pass.
2. Exact recursive public-record parity for each actual run: flags, UUID/ordinal/owner/line, commands (including reference-free), resolved paths/layers, input references, database activations and secondary source selectors, error semantics and full empty-on-failure behaviour. Disallow silent whole-run fallbacks and missing/extra records.
3. Explicit variable/TEF regressions including cascaded variables, conditional scopes (IF/ELSE IF/ELSE), nested/dynamic includes, repeated/reordered BC declarations, unresolved cases, Linux case policy and custom extension hooks.
4. At least four independent **unprofiled fresh-process samples per mode**, balanced ABBA/BAAB, same frozen TCF, flags, data cache state, selected consumer SHA and options. Prefer eight samples per mode if low-variance measurement permits. Record medians and ranges; separate parser setup, dependency generation, real physical checks, CSV header inspection, reporting, process startup and warm/cold storage.
5. Use the native actual ryan-tools #161 preflight adapter, not just synthetic counters. With each sample, retain expected 480 contexts / 50 distinct files / 24 headers / 480 selectors, zero findings and no whole-run fallback when that known workload applies. Recheck 36 and 240 context cases as available.
6. Keep the original master/PR #41/PR #42 benchmark evidence distinguishable from new exact-head native samples; do not pool timings measured at different source SHAs.

**Outcome may be rejection.** If slower, keep the graph-free prototype unmerged and identify the measured bottleneck before proposing any small additional reuse. If comparable, curate the smallest independent deferred PR C against accepted upstream A, removing superseded graph/caching code and redundant test infrastructure rather than shipping both paths.

See agent prompt at agent_workstreams/prompts/scope_driven_local_benchmark.md.
