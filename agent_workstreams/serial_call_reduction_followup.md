# Serial CPU follow-up: event-copy experiment and snapshot safety

Status: copy experiment complete; production fast path removed; tests/evidence retained.
Updated: 27 October 2026 (Australia/Perth).

This draft [PR #42](https://github.com/phantom-branch/PyTuflow/pull/42) targets
[PR #41](https://github.com/phantom-branch/PyTuflow/pull/41), branch
`perf/compiled-effective-dependencies`. The latest parent `0fa632d` was incorporated with
normal merge `70b8b0763a93010d1b894baaa009c4404a69de3a` before implementation, preserving
its newer cache-correctness fixes and published child history. The final `pytuflow` tree
is byte-identical to that parent. No new production optimisation is retained.

[Complete experiment, timings and decision](evidence/2026-10-27-event-copy/README.md) |
[Next bounded investigation prompt](prompts/serial_call_reduction_followup.md) |
[Original parent implementation](compiled_effective_dependencies.md).

## What was investigated

The first target was configuration/event-database copying: 14,316 snapshots and 605,055
event insertions remained in the measured 480-context consumer. A guarded bulk-copy
prototype used exact built-in storage and original class definitions; case aliases,
subclasses, custom callbacks/mappings and incomplete state retained the insertion loop.
Snapshots remained independent at the original shallow-copy depth, with variables passed
by reference as before. No mutable run state was shared.

The final prototype at `dbdc4d8` passes complete recursive public-record equality on the
480-, 36- and 240-context workloads, each comparing current parent fragments with ordinary
uncached/cached, full-key reference and combined experimental modes. Selected files,
paths/layers, UUIDs, commands, activations, sources, selectors and errors are included.
The diagnostic profile reduces event insertions from 605,055 to 110, while keeping all
14,316 copies. Guard checks and bulk/index construction replace some removed work.

## Native result and removal

Compare against **current #41 `0fa632d`**, not #39. Normal Python 3.14.6, one worker,
SSD only, frozen actual consumer #161 `04999e7`, matching inputs/options and fresh
processes. Each of two separately reported balanced campaigns has eight observations
per revision. No profiler or tracing wrappers run in native measurements.

| Campaign | Current #41 median s | Copy prototype median s | Reduction |
| --- | ---: | ---: | ---: |
| Initial | 3.882589 | 3.775467 | +2.76% |
| Independent confirmation | 3.884677 | 3.935824 | -1.32% |

The initial apparent gain does not reproduce. Direction changes and substantial drift
fail the required native retention criterion. Do not combine campaigns, select favourable
blocks or use call reductions/microbenchmarks as acceptance. All 32 native observations
pass with 480 contexts, 50 paths, 24 headers, 480 selectors and zero issues/fallbacks.

The production fast path was removed in `d340034`; the final runtime tree is the current
parent's `c5d4402e3886e145b1e49c941e4cdb1b5d7ddff6`. Experimental commits are retained in
history for provenance, but contribute no net production diff. The final PR retains 16
snapshot-safety tests and their Windows Python 3.12/3.14 workflow coverage, evidence and
this handoff. Final local validation passes **588 parser/context/dependency tests and
119 actual consumer tests, zero skips**. Ruff/new-test formatting and Pyright gates pass;
the legacy event module has the same two inherited default diagnostics as the parent.
Hosted exact-head CI and fresh review remain separate delivery states in the PR description.

## Recommendation and boundaries

Stop work on this bulk-copy mechanism. Investigate path conversion/decomposition next,
starting with reuse within a known operation and a fresh matched current-parent baseline.
No path optimisation is implemented or accepted here. Leave TEF full-key fallbacks,
immutable result assembly, production multiprocessing and first-run scheduling unchanged.

The parent's earlier 81.35% gain (22.849923 -> 4.260864 s) belongs to #39 versus corrected
#41, not to this follow-up. Its [current-head investigation](https://github.com/phantom-branch/PyTuflow/blob/0fa632dab996ad40f6c20bcc466cb5d4d0beadf6/agent_workstreams/evidence/2026-10-27-remaining-cpu/README.md)
remains the starting attribution. The [earlier call audit](evidence/2026-10-27-serial-call-audit/summary.json)
is historical at `404101f`; do not pool sources or timing boundaries.

All raw models, paths, flags, command lists, records, profiles and mappings stay private.
No model edit, solver, SMB benchmark, extra PR/worktree, venv, PR merge, retarget,
release or parent-branch change is included. The unrelated local `.gitignore` edit remains
untouched. See the linked prompt for the next task's correctness and measurement boundaries.
