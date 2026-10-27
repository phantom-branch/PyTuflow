# Serial CPU follow-up: snapshot and path semantics

Status: copy and path experiments complete; neither production fast path retained.
Updated: 27 October 2026 (Australia/Perth).

Existing [PR #42](https://github.com/phantom-branch/PyTuflow/pull/42) targets
[PR #41](https://github.com/phantom-branch/PyTuflow/pull/41), branch
`perf/compiled-effective-dependencies`. Parent `0fa632d` was incorporated with normal merge
`70b8b07` before implementation, retaining the newer correctness fixes and published history.
The final parser tree is byte-identical to the parent: `c5d4402e3886e145b1e49c941e4cdb1b5d7ddff6`.
#41 has not been changed by either experiment.

[Path experiment and source-specific evidence](evidence/2026-10-27-path-decomposition/README.md) |
[Earlier copy experiment](evidence/2026-10-27-event-copy/README.md) |
[Future-work guardrails](prompts/serial_call_reduction_followup.md) |
[Parent implementation](compiled_effective_dependencies.md).

## Latest result: path decomposition

The profile showed 437,418 current-path string conversions and 237,774 database/layer split
requests, mostly from dbpath and lyrname. A small independently removable prototype tested
bounded reuse of the pure literal text split. It still obtained str(self) on every request,
retained only immutable string/component tuples, and used uncached fallback for changed regex
policies or custom string/split callbacks. It cached no Path/model/file result or selection;
fragment source identity and actual relative/path/variable resolution stayed authoritative.

Prototype `74f3544` passes 15 complete recursive public-record comparisons across the separate
480-, 36- and 240-context workloads: current-parent fragments and experimental ordinary
uncached/cached, full-key reference and combined modes. UUIDs, selected source paths/layers,
commands, references, activations, database selectors and errors remain equal.

Against current #41 `0fa632d`, using the same SSD 480-context workload, normal Python 3.14.6,
one worker and actual consumer #161 `04999e7`, two balanced clean campaigns give:

| Campaign | Current #41 median s | Path prototype median s | Reduction |
| --- | ---: | ---: | ---: |
| Initial, eight observations per revision | 3.922109 | 3.928140 | -0.15% |
| Confirmation, eight observations per revision | 3.907233 | 3.942116 | -0.89% |

There is no reproducible incremental native gain. All 32 observations are retained, with
ranges/drift and inclusive phase, process CPU, memory and setup metrics in the evidence.
Every native pass has 480 contexts, 50 paths, 24 headers, 480 selectors and zero issues or
whole-run fallbacks. No profiler or tracing wrappers run during native timing.

The separate profile executes the parsing helper only 350 times inside the API/report
boundary, but all 237,774 split-entry requests and 437,418 string conversions remain. The
whole-process cache has 237,435 hits and 351 misses, including setup. Near-total avoidance
of repeated parsing does not establish recoverable end-to-end time: dispatch, hashing,
cache maintenance and current rendering remain. Neither profile durations nor the historical
81.35% #39-to-#41 gain are counted as an incremental result.

The cache was removed in `1e50dff`. Retained work is 27 useful path-semantics cases and their
Windows 3.12/3.14 CI coverage, alongside the earlier 16 snapshot-safety cases and evidence.
Final local validation passes **630 parser/context/dependency tests and 119 actual consumer
tests, zero skips**. Ruff/format/Pyright on the new tests and scoped strict Pyright pass.
No production cleanup or suppression remains. Exact-head hosted checks and fresh review
are separate delivery states recorded in the PR description.

## Earlier result: configuration/event copying

The guarded bulk-copy prototype at `dbdc4d8` reduced event insertions from 605,055 to 110
while preserving 14,316 independent snapshots. Its initial median improved 2.76%, but an
independent confirmation was 1.32% slower. The production path was removed in `d340034`;
16 mutation/extension/case-order/error-contract regressions remain. Do not revive that
mechanism based on call counts or its non-recoverable roughly 0.39-second observed budget.

## Recommendation

Retain #41. Stop these two bounded micro-optimisation experiments: neither has earned native
retention. Further performance work needs a new measured budget/mechanism and separately
requested scope. Leave TEF full-key fallbacks, immutable assembly, membership decisions and
production multiprocessing unchanged. No new performance improvement is claimed in #42.

The parent's [corrected-head investigation](https://github.com/phantom-branch/PyTuflow/blob/0fa632dab996ad40f6c20bcc466cb5d4d0beadf6/agent_workstreams/evidence/2026-10-27-remaining-cpu/README.md)
remains historical attribution; the [first call audit](evidence/2026-10-27-serial-call-audit/summary.json)
is tied to `404101f`. Do not pool sources or timing boundaries. Private models, paths, flags,
commands, records and profiles stay outside the repo. No solver, model edit, SMB benchmark,
extra PR/worktree, venv, PR merge, release, retarget or parent change was performed.
The unrelated local `.gitignore` edit remains untouched.
