# Next investigation prompt: path conversion and decomposition

The configuration/event-copy experiment is complete. Its production fast path was removed
because an initial apparent native gain did not reproduce. This prompt records the next
bounded investigation; no path optimisation has been implemented or accepted yet.

## Repository, stack and evidence

Continue on `perf/serial-call-reduction-followup` and existing draft
[PR #42](https://github.com/phantom-branch/PyTuflow/pull/42), targeting
`perf/compiled-effective-dependencies` ([parent #41](https://github.com/phantom-branch/PyTuflow/pull/41)).
Do not create another PR, worktree or virtual environment, or target master.

Read [the current handoff](../serial_call_reduction_followup.md),
[the rejected copy experiment](../evidence/2026-10-27-event-copy/README.md),
[the parent handoff](../compiled_effective_dependencies.md), applicable repository guidance,
and [the parent's CPU investigation](https://github.com/phantom-branch/PyTuflow/blob/0fa632dab996ad40f6c20bcc466cb5d4d0beadf6/agent_workstreams/evidence/2026-10-27-remaining-cpu/README.md).

Parent `0fa632d` was already merged normally into this child at `70b8b07`, bringing in the
newer correctness fixes that were absent at creation base `404101f`. Final copy-investigation
runtime source is exactly the parent tree. Fetch/check the live parent before new work;
incorporate newer parent commits with a normal branch merge, preserving published history
and unrelated changes. Do not modify the parent, force-push, merge a PR, release or retarget.
If its stack has changed, report that before choosing another base.

## Objective and scope

Investigate one small path conversion/decomposition improvement, measure it independently,
and retain it only after complete correctness and reproducible incremental native benefit.
Start with repeated conversions/splitting within a known operation before adding a cache.
Recorded counts are 437,418 TuflowPath string conversions and 237,774 database/layer splits
for the original 480-context consumer. These are hypotheses, not recoverable native time.

Do not revive the rejected bulk-copy mechanism merely because event insertions fell from
605,055 to 110. Native medians were 3.882589 -> 3.775467 s initially but 3.884677 ->
3.935824 s on confirmation. Its fast-path guards/construction replace some removed work,
and an observed roughly 0.39-second copy budget is not wholly removable. Retain its 16
snapshot-safety tests. Leave TEF full-key fallbacks and immutable result assembly unchanged;
all 480 TEF fragments differ and certificates already have 25,793/25,935 cache hits.

Inspect TuflowPath construction, __str__, _split_db_and_lyr, dbpath/lyrname/suffix access
and repeated use during dependency projection and consumer collection. Prefer a small,
reviewable change; do not bundle unrelated membership, copying or assembly work.

Preserve:

- Exact replacement order and unresolved/malformed token handling, including late/transitive
  scenario/event aliases, cascades, fragmented delimiters and surplus literal brackets.
- Relative/absolute paths, trailing separators, drive/UNC forms, Unicode and existing
  Windows/POSIX case policies; no new filesystem or GIS probes for lexical operations.
- GeoPackage >> and |layername= forms, NetCDF syntax, wildcard/multiple include selection,
  extensionless/layerless references and custom methods/hooks. Prove eligibility or fall back.
- Selected parsed source identity and resolved path in fragment equivalence, even when file
  contents/effective values coincide; nested includes, missing/ambiguous/unparsed selections
  and source changes must not reuse another file's output.
- Ordinary scope/negative membership and assignment ordering; event-key visibility,
  invalidation, custom Context translation, failed-run cache isolation and BC row validation.
- All public dataclasses, UUIDs, command order/positions, raw metadata, file/layer references,
  activation ownership, database selectors and errors. No mutable cross-run state sharing.

If caching is proposed, state exactly what is immutable, how mutation/source changes are
observed, how memory is bounded and why custom callbacks remain authoritative. A lower call
count, an invariant filename or a high cache-hit rate is not an equivalence proof.

## Correctness and native acceptance

1. Freeze exact latest parent, candidate and actual consumer sources and private workload
   identities/options. Use immutable Git archives outside the repo when needed. Preserve
   newer commits and unrelated local work; do not change installed dependency/source pins.
2. Use current corrected #41 as A and A plus the single path change as B. The historical
   #39-to-#41 81.35% gain is not a follow-up gain. Capture fresh matched baseline/candidate
   observations; do not pool sources, storage or timing boundaries.
3. Add meaningful positive/negative regressions for the change, then compare complete public
   records across ordinary uncached/cached, full-key reference and optimised modes. Compare
   actual records, not only counts/hashes. Retain all parent regressions, including Unicode
   TEF cases, dynamic filename/source identity, custom hooks and failed-run behaviour.
4. Check the separate retained 480-, 36- and 240-context private workloads when available;
   keep their status distinct. The previous copy experiment compared five modes on each.
   Do not edit inputs, invoke the solver or publish raw paths/flags/models/records/profiles.
5. Use normal Python 3.14, one process/one I/O worker, batch context, file inspection,
   fragments and BC CSV header/column checking. SSD only; do not rerun SMB unless requested.
   Native measurements use fresh processes in balanced ABBA/BAAB blocks, at least four
   observations per condition. No profiler, tracing wrappers or detailed diagnostic CSVs in
   acceptance timing; keep attribution separate. Include parse, collection, full API/report
   wall/process CPU, memory and setup costs, with inclusive/exclusive boundaries explained.
6. Bound the campaign before running. Report every sample, order, ranges/drift and independent
   block results, including slowdowns. Stop on integrity/parity failures. If an apparent
   gain fails confirmation, remove its production change; do not keep measuring until a
   favourable median appears. Retain useful tests and sanitised diagnostic evidence.
7. Run appropriate Ruff/format/Pyright gates, scoped parser/context/deferred regressions and
   actual PR #161 consumer compatibility. Keep inherited diagnostics separate. Run the
   applicable Windows 3.12/3.14 hosted matrix on the final head and distinguish it from local
   evidence and earlier-head CI. Previous final local counts are 588 and 119, zero skips.
8. Update this same draft PR/title/body and handoff around the final retained scope, with
   sanitised evidence, exact source IDs, limitations and a clear retention recommendation.
   Obtain a fresh exact-head review and resolve findings; leave remaining CI/review/access
   gates explicit. No PR merge, release, parent change or unauthorised retargeting.

No production multiprocessing, first-run scheduling, public API changes solely for speed,
new TEF equivalence assumptions or immutable output-assembly rewrite is part of this task.
Deliver an independently measured retained improvement, or a documented negative result
with its production experiment removed. Do not substitute profiler/call reductions for
native acceptance.
