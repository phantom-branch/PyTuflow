# Local agent — trim-from-fast native parity and performance

Repository: https://github.com/phantom-branch/PyTuflow
Branch: experiment/trimmed-fragment-dependencies
Baseline: master@0d4082b06c3e4cbb4b72cfdd24fa7aa22445fac7
Reference: PR #45 native result, M480 master 3.656 s and slow graph-free 77.040 s (preflight-through-report)
Consumer: https://github.com/Chain-Frost/ryan-tools/pull/161 (freeze an exact SHA)

## Goal and prerequisites

Determine whether extracting the proven fast fragment collector away from the optional compiled batch graph maintains exact correctness and speed. Read agent_workstreams/trimmed_fragment_architecture.md, PR #41/#42, PR #45's local acceptance comment, and the existing native runner/consumer contract before running anything.

Keep this an independent draft. Do not edit proprietary TUFLOW models, BAT/CMD launchers or input files, execute a TUFLOW solver, enable auto-merge, release, repin consumer packages or modify other agents' checkouts. Use separate worktrees and isolated Python 3.14 environments. Preserve all private flags, paths, records and profiles locally; GitHub receives sanitised aggregates only.

## A. Focused tests

Run the following against the candidate:

    py -3.14 -m pytest -q tests/test_trimmed_fragment_dependencies.py tests/test_fragment_dependencies.py tests/test_effective_dependency_manifests.py tests/test_compiled_scope.py tests/test_fragment_inactive_scope.py tests/test_fragment_key_phase_attribution.py tests/tmf/test_context.py tests/tmf/test_scope.py
    py -3.14 -m pytest -q tests/test_batch_dependencies.py tests/test_batch_ordered_inputs.py tests/test_compiled_control_tree.py tests/test_group_constructor_guards.py
    py -3.14 -m ruff check pytuflow/_tmf/dependency_records.py pytuflow/_tmf/fragment_context.py pytuflow/_tmf/deferred_dependency_fallback.py pytuflow/_tmf/fragment_dependencies.py tests/test_trimmed_fragment_dependencies.py
    py -3.14 -m compileall -q pytuflow/_tmf

Check hosted Windows Python 3.12/3.14 and Linux Python 3.12. The phantom fork declares Python >=3.12; eventual Chain-Frost PR C must separately validate 3.11. Never suppress inherited pytest 9.2 regression-harness failures.

## B. Functional parity FIRST

Use actual original local run flags for authorised M480, M36 and M240 models. Never generate Cartesian products from PR #44. Freeze exact parser candidate, reference master, consumer SHA, Python version and configurations.

Compare complete, direct per-run records from:
- Candidate model.collect_file_dependencies(flags) (trimmed fast fragments)
- Candidate model.collect_batch_dependencies(flags, compile_tree=False)
- Candidate model.collect_batch_dependencies(flags, cache_scopes=False, compile_tree=False)
- Reference master model.collect_file_dependencies(flags) in separate environment

Assert exact parity of ALL flag/index, UUID, ordered command including reference-free commands, owner file and source line, reference attributes/layer/CSV column selectors, activation UUID and sequence, secondary database rows and errors. Use deterministic parse-time UUID instrumentation only in separate untimed cross-process equality checks. Do not silently accept missing, extra or reordered records.

Test scenario/event negation and ELSE, scoped/transitive Set Variable, TEF substitution cascades, partial angle brackets, dynamic nested includes, custom hooks/fallback, BC database reassignment, wrong/ambiguous sources, Linux filename casing and postparse no-I/O. Require identical complete consumer reports and no extra fallback.

## C. Matched fresh-process performance

Committed benchmark script:

    py -3.14 tests/benchmark_trimmed_fragments.py --tcf "<PRIVATE_TCF>" --flags-file "<PRIVATE_JSON>" --mode fragments --verify

For reference master, locally copy the same script into its detached worktree without committing it. Compare candidate versus master in ABBA/BAAB order, at least four uninstrumented fresh Python processes per revision/workload (eight if variance warrants). Do NOT pool producer timing with the untimed --verify comparison. Report collect_seconds, parse_seconds, range, sigma, memory and exact SHA for M480/M36/M240.

Separately run the actual ryan-tools PR #161 fragment API consumer end-to-end, preflight through CSV report, with the SAME one-worker warm-cache SSD settings and original flags. Measure imports/setup, TCF parse, dependency/context, physical files/GPKGs, CSV headers and report time. Expected M480 resources: 480 contexts, 50 unique paths, 24 headers, 480 selectors, zero findings and zero whole-run fallbacks. M36: 20 paths/1 header/36 selectors; M240: 32 paths/12 headers/240 selectors. Stop and explain mismatches.

M480 candidate target is <=6 s total preflight-through-report with zero semantic differences. Previously measured master 3.656 s is only a historic point; obtain a fresh matched master median. If candidate loses 5-10% performance, use separate profiling to isolate fragment-context overhead, then restore only necessary per-run helpers. Do not add a new general graph.

## D. Handoff

Post a new PR comment with exact source/consumer SHAs, tests/CI outcomes, M480/M36/M240 recursive parity and consumer reports, timings with n/ranges/median, memory, dependency fragment evaluation/reuse and fallback metrics, original physically validated input counts, and PASS / CORRECTNESS FAIL / PERFORMANCE FAIL / INCONCLUSIVE verdict.

Important: old graph modules remain in the fork for existing batch API and comparisons; this extraction proves the fast collector's import independence. Distinguish potential upstream C footprint savings from actual branch net lines. Keep PR draft, unmerged, no release or production rollout.
