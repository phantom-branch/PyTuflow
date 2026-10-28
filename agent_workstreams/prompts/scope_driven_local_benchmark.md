# Local native agent — PR #45 graph-free dependency parity and performance

Repository: https://github.com/phantom-branch/PyTuflow
Experimental PR: https://github.com/phantom-branch/PyTuflow/pull/45
Branch: experiment/scope-driven-dependencies
Immutable parent: master at 0d4082b06c3e4cbb4b72cfdd24fa7aa22445fac7
Reference optimisation: PR #41 (the historical 480-context SSD actual-consumer result was 4.260864 s); PR #42 retained only regression/evidence changes, and PR #43 is physical validation.
Consumer: https://github.com/Chain-Frost/ryan-tools/pull/161, freeze the exact SHA used for the new campaign.

## Objective

Determine whether the graph-free scope-driven collector can replace most compiled dependency graphs, fragment manifests and caches in eventual upstream PR C **without a material performance regression**, while preserving exact full-record and actual consumer semantics. This is a real acceptance experiment. Do not favour the new code when results fail.

## 1. Protect ongoing work and establish revisions

- Read PR #45 description, agent_workstreams/scope_driven_dependency_experiment.md, its new tests/benchmark runner, PR #41/#42 performance records, and current ryan-tools #161 adapter.
- Fetch, record exact candidate HEAD, exact parent SHA and pinned consumer revision. Do not overwrite other agents' working directories, branch heads or unpublished edits. Use a separate detached worktree and isolated Python 3.14 interpreter/venv.
- Do not modify private model inputs, BAT/CMD launchers, data, solver configuration or production consumer code. No TUFLOW executable is to run. Never push private paths, flags, results or proprietary model artefacts to GitHub.
- Do not merge, auto-merge, release or repin dependencies.

## 2. Run portable native tests

From the independent PR #45 checkout:

    py -3.14 -m pytest -q tests/test_scope_driven_dependencies.py tests/test_fragment_dependencies.py tests/tmf/test_context.py tests/tmf/test_scope.py
    py -3.14 -m compileall -q pytuflow/_tmf/scope_driven_dependencies.py tests/test_scope_driven_dependencies.py tests/benchmark_scope_driven_dependencies.py
    py -3.14 -m ruff check pytuflow/_tmf/scope_driven_dependencies.py tests/test_scope_driven_dependencies.py tests/benchmark_scope_driven_dependencies.py

If a test fails, reproduce with unchanged master and PR #45. Fix only focused PR #45 bugs, without changing the accepted fragment baseline; post exact SHA/evidence. Verify hosted Windows 3.11/3.12/3.14 and Ubuntu 3.12 checks. Run additional real QGIS/MDAL tests only if a path touches QGIS functionality.

## 3. Prove complete parity BEFORE performance claims

Use the same real TCF and original ordered run flags, explicitly supplied by the existing local preflight harness. Do not derive a Cartesian product from PR #44 discovery. Cover actual 480-, 36- and 240-context workloads where authorised.

Create a local JSON array of complete run flag strings. Keep it OUTSIDE the repo and all GitHub/log uploads. On the same parsed TCF object compare:
A: model.collect_file_dependencies(flags), current PR #41/#42 optimised fragments
B: collect_scope_dependencies(model, flags), new PR #45 alternative
C: model.collect_batch_dependencies(flags, compile_tree=False), existing cached graph-disabled control
D: model.collect_batch_dependencies(flags, cache_scopes=False, compile_tree=False), ordinary uncached control

Require direct equality of the complete per-run record dataclasses, not just filename sets or counts. This means run indices and flag strings; selected command UUIDs, original order, owner path and line; input-reference count and all FileReference fields; paths/layers and CSV selectors; database activation UUID/sequence and exact secondary source rows; and identical error/fail-closed results. Unresolved, unparsed or ambiguous cases must not silently pass.

Exercise scenario branches, negations, ELSE IF/ELSE, Set Variable precedence and transitive replacements, TEF-driven names and late substitutions, S1–S9/E1–E9 selection, nested and dynamic control files, repeated BC declarations, inactive commands, unknown inputs, fresh source edits and strict Linux case handling where possible. Pay special attention to PR #44's noted dynamic-inclusion limitations. Report any difference immediately, with only non-identifying error categories/record counts posted publicly; keep exact private values local.

## 4. Producer-only benchmark — fresh process per sample

The committed safe runner is:
    py -3.14 tests/benchmark_scope_driven_dependencies.py --tcf "<LOCAL_TCF>" --flags-file "<LOCAL_JSON>" --mode scope --verify
    py -3.14 tests/benchmark_scope_driven_dependencies.py --tcf "<LOCAL_TCF>" --flags-file "<LOCAL_JSON>" --mode fragments --verify
    py -3.14 tests/benchmark_scope_driven_dependencies.py --tcf "<LOCAL_TCF>" --flags-file "<LOCAL_JSON>" --mode batch-graph-off --verify
    py -3.14 tests/benchmark_scope_driven_dependencies.py --tcf "<LOCAL_TCF>" --flags-file "<LOCAL_JSON>" --mode batch-uncached --verify

Use independent Python processes for each timed sample. Run at least four observations per mode in balanced ABBA/BAAB mode order (eight each preferred). No profiler, debug instrumentation or additional print statements inside timed calls. Capture median, min/max, variance, Python version, CPU, drive/warm-cache state, exact SHAs and per-run count. Timing excludes initial TCF parse and post-timing parity checks; report parse separately. Do NOT use synthetic timing to justify a performance claim.

## 5. Actual ryan-tools preflight integration — separately measured

Freeze ryan-tools #161 and its actual 480-context preflight-through-report settings. Compare unchanged fragment provider against graph-free provider using the SAME consumer code, input data, one-worker policy, header inspection and output/report boundary.

The consumer BatchModelView selects model.collect_file_dependencies() with reuse_fragments=True and only requires .runs plus optional counters. In an isolated, local-only benchmark child process, replace that method temporarily on the loaded TCF type with collect_scope_dependencies (Python function binding automatically passes self); restore it after execution. Do not commit or push this adapter patch or alter the consumer's reporting/error defaults. Alternatively add a local-only provider injection at the same call site, with complete record equality proven before timing.

Capture separately: process import/startup, initial TCF/TEF/BC parse, producer dependency collection, physical file/GPKG existence/layer checks, CSV headers, reporting and total preflight-through-report. Compare newly measured fragment results, not only the historical ~4.26-second PR #41 figure.

For the known M480 comparison expect 480 contexts, 50 unique physical file paths, 24 CSV headers and 480 selectors, zero reported issues and zero whole-run fallbacks. If input sets/consumer options differ, document why and do not equate those times. Include the 36/240 workloads as available. No solver launch, no production multiprocessing, no extraneous SMB scans. Keep proprietary details on the local machine.

## 6. Report and stop conditions

Deliver a concise public PR #45 comment with exact parser and consumer SHAs; environment and version; green/failing test counts; direct parity result for each workload; independent timing tables of all modes and full consumer runs (median, range, n, warm/cold); resource counts; and one of:
- PASS — graph-free is fully equivalent and comparable in real consumer time; suitable for upstream C simplification review.
- FAIL — mismatched records or failed model/consumer correctness, with minimal non-private reproducer.
- PERFORMANCE FAIL — parity correct but materially slower; retain existing optimised collector, identify dominant phase.
- INCONCLUSIVE — insufficient matched native evidence, with concrete missing steps.

Do not claim that low line count proves equivalent performance. Do not suppress warnings, relax checks, remove existing regressions or rerun selectively until obtaining a favourable sample. Keep PR #45 draft and unmerged. If a focused code change is justified, make it on PR #45 only and rerun the entire pairing against the new exact head.
