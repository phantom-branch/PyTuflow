# Future serial CPU investigation guardrails

The two requested bounded experiments are complete. Neither production fast path remains
in PR #42. This is a closeout and future-work boundary, not an instruction to repeat the
same campaigns or implement another optimisation without a new task.

## Current stack and retained scope

Existing [PR #42](https://github.com/phantom-branch/PyTuflow/pull/42), branch
`perf/serial-call-reduction-followup`, targets [#41](https://github.com/phantom-branch/PyTuflow/pull/41)
branch `perf/compiled-effective-dependencies`. Parent `0fa632d` was incorporated normally at
`70b8b07`. The final parser tree is the unchanged parent tree. Retained changes comprise
16 snapshot-safety and 27 path-semantics cases, existing Windows 3.12/3.14 workflow coverage,
sanitised experiment records and the indexed handoff. Do not merge, release or retarget.

Read [the current handoff](../serial_call_reduction_followup.md),
[the path results](../evidence/2026-10-27-path-decomposition/README.md),
[the copy results](../evidence/2026-10-27-event-copy/README.md) and
[the parent handoff](../compiled_effective_dependencies.md) before proposing new work.

## What has already been tested

- Guarded event-database bulk copying: initial median reduction 2.76%; confirmation
  reduction -1.32%. It removed almost all event insertions, but native benefit did not
  reproduce. Prototype `dbdc4d8`; rollback `d340034`.
- Bounded literal database/layer splitting: initial median reduction -0.15%; confirmation
  -0.89%. The profile reduced actual parsing bodies to 350 while retaining all 237,774
  entry requests and 437,418 string conversions. A 99.85% whole-process hit rate did not
  deliver native improvement. Prototype `74f3544`; rollback `1e50dff`.

Each experiment uses two separate balanced 16-observation campaigns against current #41,
not #39. Each also has five-mode complete recursive record equality on the separate retained
480-, 36- and 240-context workloads. No cross-source/campaign/model pooling or favourable
sample selection. Raw records, models, paths, flags, mappings and profiles stay private.

The historical 81.35% #39-to-#41 gain belongs to #41. It is not evidence of an incremental
follow-up gain. Do not repeat either rejected mechanism based on fewer calls, high cache
hits, profiler timing or the earlier approximately 0.39-second copy budget. New work needs
a different justified mechanism and a material measured budget.

## If further performance work is requested

1. Check live parent/child/consumer metadata and source hashes. Preserve newer commits,
   unrelated state and published history. Incorporate newer parent commits with a normal
   branch merge only within the authorised child. No parent changes, force-push, extra PR,
   worktree, virtual environment, PR merge, release or unauthorised retargeting.
2. Define one independently removable change and its exclusive measured budget. Inspect
   relevant ordinary paths and extension hooks first. Current conversion/splitting counts
   alone do not establish recoverable runtime. Prefer avoiding repeated work within an
   operation before adding more caching; preserve callback and mutation semantics.
3. Use current corrected #41 as A, plus exactly that candidate as B. Freeze normal Python
   3.14, actual consumer and dependency versions, input/location/flag order and identical
   batch/file inspection/fragment/header options. Use SSD only, one process and one I/O
   worker. Independent sources may use Git archives outside the repo; no solver/model edits.
4. Add meaningful positive/negative regressions. Compare all public run-record fields:
   UUIDs, command ordering/positions/raw metadata, selected source-file identities/paths,
   layers/references, activation ownership, database sources/selectors and errors. Require
   recursive equality across ordinary uncached/cached, full-key reference and optimised
   evaluation. Hashes/counts are receipts, not the equality proof.
5. Preserve scenario/event/Set Variable ordering and transitive/late substitutions,
   fragmented and surplus literal delimiters, Unicode replacement rules, nested/multiple/
   wildcard includes, unresolved/missing/ambiguous/unparsed sources and reparsed snapshots.
   Different selected files must not share cached commands merely because values coincide.
6. Preserve Windows/POSIX case policy, relative/drive/UNC/trailing-separator and database/
   layer/NetCDF forms. Observe current rendering and authoritative custom hooks. Prove what
   is immutable, bounded and independent of source state; fall back when uncertain. No
   lexical shortcut may suppress file-selection errors or turn into filesystem/GIS I/O.
7. Retain independent mutation at existing copy depth, intentional variables-reference
   semantics, failed-run cache isolation, ordinary negative/Else scope handling, progressive
   event-key visibility and BC empty-row validation. Do not alter TEF full-key fallbacks,
   immutable assembly, membership decisions or public APIs merely to make an optimisation
   easier. Those areas and production multiprocessing require separate scope.
8. Bound the native campaign beforehand. Use fresh processes, balanced ABBA/BAAB blocks and
   at least four observations per condition. No profiler, tracing wrappers or diagnostic
   CSV generation in native acceptance. Report complete samples, medians/ranges/drift,
   process CPU, memory, setup and phase boundaries; inclusive times are not additive.
   Keep attribution separate. Stop on parity/integrity failures. Remove a production
   change if a claimed gain does not reproduce; do not keep measuring until it looks good.
9. Run appropriate Ruff/format/Pyright and parser/context/deferred checks plus actual
   consumer compatibility. Current local evidence is 630 and 119 passing tests, zero
   skips. Run applicable Windows 3.12/3.14 hosted matrices on the exact final head;
   distinguish local/earlier-head evidence and inherited diagnostics from new failures.
10. Update this same PR/title/body and indexed handoff around the retained scope, publish
    only sanitised source-specific receipts, obtain fresh exact-head review and resolve
    findings. Leave CI/review/access gates explicit. Deliver either a measured retained
    improvement or a documented negative result with its production experiment removed.

Current recommendation: keep #41 stable, retain the behavioural tests and evidence in #42,
and stop these two mechanisms. No additional production optimisation is authorised by this
closeout itself.
