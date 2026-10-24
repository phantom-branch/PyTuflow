# P9: bounded construction attribution

| Field | Value |
| --- | --- |
| Status | Implemented; focused local tests pass; hosted real-parser validation pending |
| Updated | 2026-10-24 |
| Next review | Exact-head CI/review, otherwise 2026-10-25 |
| Branch | `test/nested-construction-attribution` |
| Base | Frozen parser `e162c04330d24c37bee3ade94479cc4602651060` |
| Ownership | Developer diagnostics only; production parser/cache code unchanged |

## Implemented boundary

[Attribution](../tests/construction_attribution.py) observes registered Python
code objects without replacing constructors, descriptors, callbacks or parser
methods. Exclusive cells form one operation-by-active-control-file-kind table.
Summing its cells equals the observed wall interval. Operation and control-file
marginals are two views of the same time and must not be added together.
Nested inclusive spans are retained separately and deliberately overlap.

The [bounded diagnostic](../tests/profile_construction_attribution.py) registers
actual parser definitions for context bootstrap, event loading, scope/variable
work, command/input construction, configuration copies, references, database
activation/Source projection, control-file traversal and cache work. Critical
missing definitions fail explicitly. Runtime constructor identity guards are
not bypassed or invalidated by diagnostic wrappers.

Owner labels come from exact TCF/TGC/TBC/TEF classes at control-file evaluation
boundaries. They describe the active evaluation context, not the source ownership
of every returned reference. Work with no known active owner is UNATTRIBUTED;
an unknown child owner cannot be charged to its known parent. Event-database
loading outside a TEF evaluation is an event-loading operation with an
UNATTRIBUTED owner. No path-based ownership guesses are made. Further reference
and database owner attribution is a remaining scope, not completed here.

Registered generator call/return segments cover actual resumption and cleanup,
not time suspended while a consumer works. Counts are activation segments;
generator resumes are not new constructor calls or allocation counts. Failures
and KeyboardInterrupt/SystemExit finalise partial data without replacing the
workload exception. Reporting errors cannot replace an existing workload error.
An existing classic/monitoring profiler is refused; a hook replaced by the
workload is not overwritten on exit and makes the capture incomplete.

## Measurement limits

This is nearest-registered-boundary **wall time**, not exact exclusive CPU time.
Unregistered helpers, native calls, I/O waits and observer overhead stay inside
the nearest active boundary. Only the calling thread is observed. The Python
hook adds overhead even on unregistered calls. Paired plain/observed timings
report that perturbation together with order/cache variation; one pair is not
an unbiased overhead estimate or performance acceptance. Do not subtract
profiling overhead as a constant from individual operation timings.

The driver makes four sequential public API calls: plain off, observed off,
observed on, plain on, all with cache_scopes=True. One stable parsed model is
used so all public BatchDependencyRun fields, including UUIDs, can be compared
exactly. Invocation-local batch caches are fresh for each call. Parsing is
reported separately. This is NOT the fresh-model eager/deferred/four-mode native
protocol. Failed/incomplete runs or any full-projection difference fail the
command. Equal counts alone cannot pass.

## Use only for a separately authorised diagnostic

Read an existing approved run export and select at most six contexts locally.
Keep exact dictionaries, order and duplicates. This utility does not interpret
or execute a BAT file and refuses an unfiltered full run list. From the matching
checkout with the user's ordinary Python installation:

```powershell
python -m tests.profile_construction_attribution --tcf "<selected.tcf>" --runs-json "<six-selected-runs.json>" --output "<new-private-report-directory>"
```

The supplied paths retain lexical absolute spelling for I/O. Resolving links is
limited to source-import identity and report containment checks. Existing output
directories and destinations inside the checkout are refused. Summary starts
incomplete; per-mode reports are written before cross-mode comparison so failed
work remains inspectable. Reports are PRIVATE, with no upload/publication step.

`accepted_for_benchmark` is always false. The utility verifies that PyTUFLOW
imports from this checkout, but does not verify clean Git heads, source hashes,
model inventory, materialisation or public preflight. Source provenance must be
recorded independently before an approved native capture. These diagnostics may
load parser-referenced control/database inputs, but they never launch a solver.

[PR #24](https://github.com/phantom-branch/PyTuflow/pull/24) separately retains raw
cProfile evidence. Do not run the two profilers simultaneously. This PR is based
on the frozen parser, not #24 or either optimisation candidate. A future approved
capture can use separate passes with clearly distinguished boundaries.

## Validation and handoff

Local Linux CPython 3.13.5: 36 dependency-free accounting/driver tests pass.
They cover deterministic nesting/recursion, generators, exceptions, hook
ownership, exact code identity, unknown owners, projection failures/differences,
unchanged flags/duplicates/cache switches, run limits and both CLI entry points.
Compilation and Python 3.12 syntax parsing pass. These are controlled-callback
checks, not installed-parser or Windows validation. Container GitHub DNS is
unavailable; connected reads/writes deliver the changes. No full package was
cloned/installed locally and no model diagnostic/native benchmark was run here.

The new Windows 3.12/3.14 workflow runs the unit tests, two real-package tests
(including a six-context nested-TGC graph differential), existing batch/ordered/
compiled-tree contracts and CLI checks. The temporary semantic fixtures contain
syntactic references only; they are not native/materialised acceptance data.
Record exact-head terminal outcomes before claiming those checks passed.

Next: resolve exact-head CI/review findings. Then extend the explicit ownership
and bounded-capture provenance contracts as separately reviewable milestones.
Invariant subtree and database Source reuse remain independent future changes.
No cache optimisation is implemented here.

Preserve #14/#15, frozen ryan-tools #158 diagnostic
`f1f7958b79f3ffe84ba8ac0b04658f27c311460a`, the accepted earlier baseline and
supplementary three-trial SMB_PC2 result. Neither baseline validates candidates
or runner #159. No new native run, private model publication, unsorted inspection,
merge, dependency repin or release is authorised by this work.

### Bounded review corrections

Two additional regression tests failed on the initial implementation and now
pass. Returned asynchronous iterators are rejected alongside ordinary iterators
and awaitables. Reporting failures use an explicitly captured workload exception,
not sys.exception(), which can refer to an unrelated exception being handled by
the caller and incorrectly suppress a new report-write failure. The CLI summary
uses the same explicit exception ownership. No parser behaviour changed.

Initial head `d283231a2d9a1eea68f1789624ec1a20f9c7608d` passed the
[Windows workflow](https://github.com/phantom-branch/PyTuflow/actions/runs/40066973472)
on Python 3.12 and 3.14, including real-parser parity and existing batch
contracts. This evidence predates the two corrections above; refreshed
exact-head validation remains required.
