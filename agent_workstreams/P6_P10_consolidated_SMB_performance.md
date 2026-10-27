# Consolidated SMB preflight performance investigation (P6–P10)

## Scope and status

**Integrated development candidate, not an accepted speed-up.** Combines five
existing fork branches into one reviewable PR, while preserving distinct
source commits and independent behaviour tests:

| Source PR | Integrated component | Measured limitations |
| --- | --- | --- |
| #14 (P6) | Guarded incremental append/UUID bookkeeping | Prior matched native 480-run test did **not** show a convincing wall-time gain: graph-off 2.01% slower, graph-on 3.76% slower. This is **not** a reason to assume it accelerates a combined version. |
| #15 (P7) | Proven literal `SettingInput` reuse | Component construction count fell from 4,500 to 15 in synthetic case; a real end-to-end improvement is **not established**. |
| #24 (P8) | Retained private cProfile evidence | Diagnostic only; never include instrumented profile timings as production benchmark times. |
| #25 (P9) | Nested construction attribution | Earlier six-context observed call was ~5.8–6.1× slower than plain runs; its per-phase observations are useful for prioritisation, not unbiased elapsed-time results. |
| #28 (P10) | Optional completed-per-run callback | A safe producer boundary only. It does not make network reads concurrent or implement a downstream consumer. |

The source branches were each based on fork `master`
`fad6dae3038a9381c268b308ef4aae216682aba2` at integration.
No original PR is squashed, merged, deleted, or closed by this task.
The consolidated branch contains logically separated commits preserving the
source change blobs. The only shared-code reconciliations are:

- `batch_dependencies.py`: P6's callback/append safety helpers plus P10's
  completed-run callback in the collector.
- The two shared batch/deferred workflows: include both P6 and P7 test files.

This PR must not be automatically included in the single external
TUFLOW-Support upstream PR (#36) until proven beneficial and appropriately
scoped. Keep public API surface growth minimal.

## Why the observed ~40 seconds needs investigation

The workload involves more than checking ~100 unique file paths. The observed
time can include repeated per-run syntactic control evaluation, scope/event
processing, compiled-tree/graph proof overhead, repeated glob/stat/listdir or
GPKG/SQLite calls, network metadata latency and actual file reads. A path
being unique does not imply that it is evaluated or checked only once.

Past accepted consumer-level evidence showed sizeable time in parsing,
context/scope and event processing. The six-context P9 trace identified
`parser_processing`, `scope_evaluation`, `event_processing` and
`configuration_other` as large exclusive observed categories. The observer
itself was expensive, so those are diagnostic proportions only. Establish
actual uninstrumented wall time and the exact per-phase/call counts before
choosing another optimisation.

**Testable hypothesis:** expensive repeated evaluation and serial SMB
metadata operations, rather than raw transfer of 100 small files, dominate.
Do not treat this as a finding until matched runs and call counts support it.

## Stage A — Combined correctness

- Verify exact integration-head source provenance for P6/P7/P8/P9/P10.
- Run their complete focused regression selections and the original Windows
  Python 3.12/3.14 deferred, 161-TCF/174-run four-mode batch, full
  original-library/wheel and tutorial parity gates.
- Assert exact file-reference identities, input UUIDs/ordinals, event and
  scenario ordering, database activation, wildcard/GPKG resolution,
  missing/extra dependency outcomes and parser errors. Non-conforming
  callbacks must fail closed without duplicate projected indices.
- Compare standalone master, each bounded candidate and **combined**
  candidate; an individual candidate's past passing CI does not establish
  interaction safety. No skips/warning suppression to obtain success.
- Run profiler tests in the general CI, but **do not run profiling hooks
  during official elapsed-time benchmarks**.

## Stage B — Diagnose uninstrumented performance

The one authorised native Windows/SMB agent owns this stage. Use the existing
*same* 480-run batch and corresponding current ryan-tools consumer. Freeze
exact full SHAs and a single documented workload identity (TCF count, command
count, contexts, unique paths, reference identities and repeated accesses).
Previous reports from unmatched workloads are **not** comparable.

For every revision/mode, record (with low-overhead counters separated from
cProfile when necessary):

- Total wall clock, parse, context construction, per-run projection,
  DB activation/references, consumer physical materialisation, actual file
  validation and report output.
- Calls/time for `open`, `Path.stat`, `os.scandir/listdir`,
  `Path.glob`, `sqlite3.connect`, GPKG table/layer introspection,
  real bytes read and distinct paths touched.
- Total syntactic reference **identities** vs unique files, calls repeated
  per event/scenario, proven graph cache hits/fallbacks, and per-file
  timings over SMB (separate actual I/O from Python generation).
- Warm/cold cache status, fixed concurrency, processor and filesystem
  snapshots, materialisation mode and bounded worker queue if enabled.
- Complete report/test exit codes. Every accepted public projection must
  match byte- or structurally identical baseline on all four graph/eager/
  deferred/batch modes. Include extra as well as missing dependencies.

**Native experiment order**

1. Fresh `master` baseline, graph on/off, with production uninstrumented
   timing and separate cheap syscall counters.
2. Independent #14 P6 candidate versus same baseline; independent #15 P7
   candidate versus same baseline. Record benefits *and* regressions.
3. Fully combined candidate for interaction effects. Do not imply that two
   independent percentage improvements multiply.
4. #28 callback mode with a trivial no-I/O callback (measures producer
   overhead), then an opt-in conservative read-only consumer implementing
   a **bounded queue**, a **single I/O worker** and fail-closed completion.
   New consumer belongs in a reviewed companion change; do not invent
   thread safety or introduce asynchronous parsing into PyTUFLOW.
5. Only after discovering a real bottleneck, prototype one intervention
   at a time: reuse cached directory listings, memoise invariant path
   lookups, coalesce GPKG metadata access or bound SMB read concurrency
   where correctness permits. Instrumentation must reveal the corresponding
   drop in actual repeated operations.

Use a balanced repeated/alternating run design with clean source snapshots
and identical environments. Report medians and spread with full raw trial
counts, not a single warmed run or percentage without a denominator.
Preserve all raw proprietary model locations, file names and reports
privately. Post sanitised *aggregate* results only.

## Stage C — Performance decision

Retain an optimisation only if all of the following hold:

- Semantics are identical to baseline across event/scenario, file/layer/BC
  activation, missing file handling and public editing/callback contracts.
- There is a reproducible decrease in uninstrumented end-to-end wall time
  *on the relevant SMB workload*, not merely fewer constructor calls or
  profiler seconds.
- Memory, CPU, SMB bytes/operations and complexity remain bounded and
  explained. No broad feature drift for a marginal/unrepeatable gain.
- Native QGIS/MDAL acceptance is repeated if result-reader surfaces are
  touched; otherwise mark QGIS checks as not affected rather than passed.

If combined behaviour fails, isolate and fix the smallest branch-specific
interaction in this same PR; do not silently remove tests. If an experiment
remains neutral or slower, explicitly disable/exclude its production
optimisation from the final upstream staging branch even if its diagnostic
code remains useful locally.

## Coordination / open-PR clean-up

Source pull requests #14/#15/#24/#25/#28 were **closed administratively
as superseded** on 25 October 2026 after a source-blob comparison verified
all non-overlapping changed files were byte-identical on the combined branch,
the shared P6/P7/P10 code/CI files were reconciled and the first combined
Windows 3.12/3.14 contract gates passed. They were **not merged** into
`master`; their original branches, discussion and private evidence remain
available. This housekeeping is not final combined acceptance.

The consolidated #39 PR remains draft until full original-library parity,
native SMB end-to-end measurement, performance decision and final review.
If a component fails integration, repair it here or reopen an original
source PR for an isolated fix; never silently discard its contract.
The eventual single upstream contribution remains owned by #36.

[#4](https://github.com/phantom-branch/PyTuflow/pull/4) Linux
deferred-parity tracking is **intentionally left open** and is explicitly
the **last** clean-up item after the remaining PRs. Do not close it now.
