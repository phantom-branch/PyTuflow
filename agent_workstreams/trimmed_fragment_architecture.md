# Trim-from-fast dependency architecture experiment

Status: **draft, independent of PR #45**. No upstream PR, merge, release, consumer repin or solver execution is authorised.

## Baseline and goal

Start from immutable phantom-branch/PyTuflow master
`0d4082b06c3e4cbb4b72cfdd24fa7aa22445fac7`, which includes PR #41/#42.
Native PR #45 evidence recorded **3.656 s** exact-master M480 preflight-through-report (four warm SSD Windows 3.14.6 samples) versus **77.040 s** for a graph-free full RunState build. The optimised source had 1,096 fragment evaluations and 23,399 fragment reuses, with zero whole-run fallbacks.

Instead of optimizing the slow evaluator by adding another compiled tree, **extract the existing fast immutable fragment path from optional graph-based batch implementation**. Keep the production fast semantics and all its current proof safeguards, then measure whether the smaller runtime loses measurable speed.

## Implemented isolation

- `dependency_records.py`: immutable per-run command, reference and result records; `batch_dependencies` reexports the SAME dataclasses for compatibility.
- `fragment_context.py`: small per-context cache for active scopes, translations and event/variable invalidation. It inherits canonical `Context`, not `BatchContext`; the original scenario/event/Set Variable evaluator remains authoritative.
- `deferred_dependency_fallback.py`: conservative graph-free fallback using ordinary `TCF.context(file_resolution="deferred")`. Reuses only identical full flags and returns empty records on run errors; never infers valid scenario/event combinations from PR #44.
- `fragment_dependencies.py`: unchanged fragment-assembly, transitive binding proofs, `EffectiveDependencyManifest` and `ScopeProgram` logic, now importing only the small records/context/fallback helpers. Successful fragment projection does not import the graph modules. Unsupported model hooks fail over to the graph-free authoritative evaluator.
- Old `collect_batch_dependencies` continues to exist **unchanged in its public signature** as an internal differential control and fork-compatible API. The graph modules and their existing tests have NOT been deleted or rewritten here.

**Important distinction:** this is an **architectural extraction, not yet a net deletion of the graph implementation from the development fork**. The old batch collector remains present so its contracts and performance can be compared and so ongoing work is not broken. If this experiment passes, curate upstream PR C to include only the necessary fragment modules and a deliberately limited fallback, and separately decide whether any graph batch API is required. Do not claim that the repository's total source line count fell by the prospective removal size.

The file contents still retain fully defensive fallbacks for TEF-dependent includes, incomplete variable/flag substitutions, event cascades, database activation ownership, conditional and nested source selection, custom Context/input hooks, and in-batch snapshot changes. Do not remove those solely to save LOC.

## Production compatibility

The `TCF.collect_file_dependencies` public record shape is unchanged and consumed by ryan-tools PR #161. No physical checks, synthetic runs, BAT/CMD planning, dynamic flag discovery, report writing, or TUFLOW solver execution moved into PyTUFLOW.

The fast fragments retain parser-selected command order and source provenance; no mutable RunState or context is reused between different contexts. Compilation and fragment caching remain per-call and bounded.

The current phantom-branch package declares Python >=3.12, so hosted validation is Windows 3.12/3.14 and Ubuntu 3.12. The eventual Chain-Frost PR C baseline requires independent Python 3.11 acceptance.

## Tests and acceptance

The new `tests/test_trimmed_fragment_dependencies.py` checks unchanged batch-record identities, precise active source/TEF and BC ownership parity, no filesystem probes after parsing, fail-closed custom-hook fallback and (via an isolated interpreter) that the fully supported fast path runs while graph/batch modules are forbidden from importing.

Check all existing fragment, manifest, scope, BC, unusual input, file case and original-library tests, plus installed-wheel and actual ryan-tools PR #161 compatibility. Preserve inherited CI failures rather than suppressing them.

Native agent must compare exact complete per-run records in M480/M36/M240 against immutable master, graph-disabled batch and uncached mode. Instrumented runs are separate from performance samples.

Use four or more **unprofiled independent fresh-process samples per revision** in balanced ABBA/BAAB order. Record medians, ranges, σ, source SHAs, parser and consumer version, warm/cold/SMB state and complete stage counts. Compare the actual ryan-tools preflight-through-report boundary, not only dependency-only measurements. For M480 on the accepted warm SSD workload, target ≤6 s with zero changed records, zero new whole-run fallbacks, 50 physical files, 24 headers, 480 selectors and zero findings. Report every observed regression and do not rerun selectively.

This is a performance/correctness experiment. If fragments slow significantly, restore only the demonstrably needed per-run helper (not the whole compiled graph), then repeat matched testing. If correctness differs, no performance claim is accepted.

Local-agent prompt: `agent_workstreams/prompts/trimmed_fragments_local_benchmark.md`.
