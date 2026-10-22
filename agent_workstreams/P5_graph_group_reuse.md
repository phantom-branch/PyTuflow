# P5: Reduce repeated run-state construction in mixed control-file graphs

**Status:** Agent implementation handoff; no P5 parser changes implemented yet.
**Baseline:** `master` at `3de5cd954a5bf6739377937c8ff2fe3341e86bfc`.
**Delivery:** PRs #6/#8/#9/#7/#10 were squash-merged as one atomic stack operation.
**Updated:** 2026-10-23. **Next review:** 2026-10-30.

## Task for the implementing agent

Improve the compiled graph so proven invariant command groups can avoid repeated
input run-state construction inside otherwise dynamic models. Continue on this
handoff branch and replace the draft PR description with the resulting code,
validation and measured outcomes. Do not merge or publish the follow-up PR.

The merged graph is a conservative foundation, not a completed implementation of
the broader optimisation. Native measurements below show graph traversal without
input run-state elision. Existing batch-cache improvements must remain distinct
from any new graph benefit. Preserve the established public APIs and opt-in modes.

## Reproducible evidence and current limitation

Benchmark source `5053a07` is tree-identical to integration source `5b11415`.
Documentation head `099434f` passed all eight active hosted checks; the merged
`3de5cd9` tree exactly matches `099434f`. Local Windows Python 3.14.6 validation
passes 266 parser/integration tests and 68 focused consumer tests.

Three sequential, rotating-order parser trials on the same SMB workstation:

| Workload | Distinct runs | Individual deferred median, s | Uncached batch median, s | Cached graph off median, s | Cached graph on median, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| M480 | 480 | 73.466 | 67.279 | 43.455 | 45.844 |
| N42 | 42 | 32.653 | 32.988 | 10.457 | 10.766 |

Graph-on adds 5.5% / 3.0% median overhead, respectively. Parse time is separate
(0.751 / 2.091 s). Both workloads pass complete ordered parser identity parity,
full eager/deferred/batch materialisation and individual/batch public preflight
with zero issues. M480 retains 12,480 identities / 49 physical paths; N42 1,922 / 196.

Last graph-enabled trial counters:

| Workload | Graph nodes | Eligible reads | Bypassed reads | Graph lookups | Contexts constructed | Input run-states elided |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| M480 | 181 | 7 | 20 | 3,360 | 480 | 0 |
| N42 | 551 | 11 | 202 | 462 | 42 | 0 |

The full verified public tutorial (161 TCFs / 174 documented runs) also passes
all parser and materialised gates. Sum of per-model three-trial medians is
5.746 s graph-off versus 5.794 s graph-on; no graph speedup is established.
These are warm-cache diagnostic measurements, not launcher or solver wall times.

[Complete benchmark protocol, trial values, RSS and provenance](https://github.com/Chain-Frost/ryan-tools/blob/2dbd5235/docs/work/2026-10-22-tuflow-batch-preflight-optimisation.md#pr-710-repair-and-benchmark-review---2026-10-23).

## Investigation and suggested implementation

Start with `pytuflow/_tmf/compiled_control_tree.py` and
`pytuflow/_tmf/batch_dependencies.py`. Current whole-model shortcuts use
`is_invariant_literal_model()` / `is_scenario_literal_model()`; mixed dynamic
models still take context construction paths. Read the current implementation
before choosing a design; the outline below is a proposal, not a proof.

1. Account for dominant constructed inputs and bypass reasons using public
   tutorial data or minimal synthetic correctness fixtures. Retain stable
   counters for actually constructed/elided input states and graph overhead;
   do not substitute lookups, templates cloned or graph nodes for work avoided.
2. Identify immutable command groups and their exact ordered scope, variable,
   event/scenario slot, control ownership, settings and include dependencies.
   Reuse groups by proven relevant signatures even if another group is dynamic.
   One unsupported subtree must not invalidate independently proven groups, but
   its side effects must invalidate any dependent proof.
3. Preserve Set Variable ordering, TEF and nested scope semantics, source/control
   line ownership, UUIDs, command ordering, database activations and secondary
   sources. Rebind immutable per-run projections without sharing mutable
   `Context` or input run-state objects across runs.
4. Keep conservative fallback for unknown dependencies, DEFINE/event constructs,
   dynamic paths, database declarations and failed projections until their
   semantics are explicitly proven. Do not simply remove safety checks or infer
   invariance from equal outputs on a few runs.
5. Compile/cache only within one invocation. Model/source changes between calls
   must be visible; bound caches and preserve failure isolation. No filesystem,
   GIS, raster or database probes during evaluation after parse. Preserve lexical
   mapped-drive/UNC paths.
6. Assess graph setup overhead when no useful group is eligible. A fast bypass
   may be appropriate, but must not hide counters or claim unimplemented elision.

## Acceptance and agent report

- Add focused executable regressions for partial-group reuse with genuinely
  distinct flags, relevant and irrelevant changes, variable ordering, nested
  conditions, failed projections, per-run provenance and mutation isolation.
- Run existing parser contracts and Windows Python 3.12/3.14 CI. Keep all
  missing/extra identities, pure ordering changes, failed runs and unsupported
  findings visible; a matching partial inventory is not a pass.
- Use the existing four-mode same-head harness and documented CLI in
  [tests/TUTORIAL_BENCHMARK.md](../tests/TUTORIAL_BENCHMARK.md). Verify the complete
  public archive and documented combinations. Repeated valid combinations are
  stress tests, not hundreds of distinct model configurations.
- Demonstrate actual nonzero input-state construction avoided on supported
  mixed-model cases; publish before/after counters, three rotated trial values,
  medians, phase costs and sampled RSS. Report regressions honestly. Profiling
  timings are not speedup evidence.
- Keep separate public/native materialised eager/deferred/batch acceptance.
  The companion consumer remains PR #143; do not merge it or change production
  dependency pins as part of this task.
- Native reruns require the authorised workstation. Ask its operator to run the
  retained M480/N42 protocol if unavailable to your agent. Publish anonymised
  aggregates only; never copy/upload/embed native input files, fragments,
  identifying paths or detailed reports in Git/CI/attachments. Public performance
  fixtures are restricted to the tutorial set; synthetic inputs prove correctness.
- Keep original eager/shared fixes explicitly separate from new deferred/batch
  functionality in commits and the PR report. This handoff does not request an
  eager behaviour change or reopen the postponed two-BC-model investigation.
- Final report: exact source/dependency revisions, tests and terminal CI URLs,
  fixture hashes, parity findings, work-elision counters, measured performance,
  supported scope and remaining fallbacks. No engine/launcher run or release.

## Delivery state

This PR initially contains this handoff and a discovery link only. P5 optimisation
is unfinished. Next action: implementing agent investigates group-level proofs,
implements bounded reuse, and supplies the acceptance evidence above.
