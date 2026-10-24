# P10 — Opt-in run-projection producer boundary

## Purpose and boundary

Expose each **fully projected** deferred batch run to an opt-in synchronous
consumer callback, before starting the next run, without changing default
batch behaviour, model loading, graph construction, cross-run caches, or the
immutable batch result. This is the producer boundary needed to test safe
overlap of SMB inspection with subsequent context construction. **It does not
perform I/O or launch a worker itself.**

Sequential bootstrap remains intact: the caller loads the TCF/TGC/TBC and
other parsed controls and PyTUFLOW builds the variable/compiled graph state
before delivering any run. This retains shared cache identity and provides
the first possible useful reference set without speculatively reading nested
or event-conditioned sources.

## Implementation

- `TCF.collect_batch_dependencies(..., on_run=None)` forwards an optional
  callback to the existing collector.
- Emits each complete frozen `BatchDependencyRun` in original index order
  for ordinary, identical-flags, scenario/invariant reuse and failed runs.
- Failed runs have empty reference, command and activation projections.
- Callback exceptions propagate immediately; they are not converted into a
  parser failure or partial-success result. Caller owns worker cleanup.
- There is no callback, queue, thread, disk read, or inspection overhead in
  normal calls beyond checking the opt-in `None` parameter.
- Callback must not mutate parser/build states. Consumers should enqueue
  only stable primitive/immutable reference descriptors and bounded work.

## Downstream proposed read-only pilot (separate ryan-tools PR)

- Keep the parser in one main thread and use at most one I/O worker initially.
- Use a bounded queue with backpressure; derive eligible literal, complete
  paths from fully projected per-run references; deduplicate by the appropriate
  stable path spelling/inspection settings. No wildcard/BC/GIS attribution
  guessing or early acceptance on a partial projection.
- The final existing inventory and public preflight are authoritative.
  Opportunistic reads must not suppress them until equivalent re-use semantics,
  mutation/TOCTOU handling, directory batching, layers and all error paths
  are explicitly proven.
- Retain ordering, command/activation provenance, and failure parity.
- Test local SSD vs SMB with controlled opt-in runs; do not infer a performance
  advantage from reduced elapsed time in an incomplete or observational pilot.

## Validation and delivery

Added focused synthetic tests for callback sequence (including duplicate flags),
fail-closed invalid contexts and propagation of consumer exceptions.
Existing collection/graph/ordered-command and materialised Windows CI remain
required before this boundary is ready for downstream adoption.

This independent PR must stay draft. No package publication, native benchmark,
solver launch, private model data, or combination with parser PR #14/#15.
