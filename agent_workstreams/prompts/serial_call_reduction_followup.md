# Implementation prompt: reduce remaining serial dependency work

Use this prompt when implementation of the follow-up is requested. This prompt documents
future work; its presence in the current documentation PR does not mean the work is done.

## Task and stack

Repository: `phantom-branch/PyTuflow`.

Continue on the existing `perf/serial-call-reduction-followup` branch and its existing draft
PR targeting `perf/compiled-effective-dependencies` ([parent PR #41](https://github.com/phantom-branch/PyTuflow/pull/41)).
Do not create another PR or target `master`. Check the actual PR metadata and latest remote
parent head before starting; the creation/profiled head was
`404101f82349d52687b739a5cdce26623f277098`, but it may advance. Preserve unrelated changes and
newer agent work. Do not modify the parent branch, rewrite published history, merge a PR, release
or retarget without separate authorisation. If the parent has merged or its branch has gone,
report that stack change before choosing a new base.

Before implementation, incorporate the latest parent into this child with a normal branch
merge that preserves published commits and unrelated changes; do not force-push or merge
the pull request. Confirm the resulting production tree contains the parent's correctness
fixes. This documentation branch was originally based on `404101f` and has not silently
acquired subsequent parent fixes merely because its PR targets that branch.

Read [the findings](../serial_call_reduction_followup.md),
[the sanitised counters](../evidence/2026-10-27-serial-call-audit/summary.json),
[the parent handoff](../compiled_effective_dependencies.md), applicable repository guidance
and the relevant existing tests before changing production code.

Also read [the completed current-head SSD investigation on #41](https://github.com/phantom-branch/PyTuflow/blob/0fa632dab996ad40f6c20bcc466cb5d4d0beadf6/agent_workstreams/evidence/2026-10-27-remaining-cpu/README.md).
It measures runtime source `5c32395e30029bdd3d1053d18374234d0120fab4`, parent #39 `36ad04b`
and actual consumer #161 `04999e7`. Six-mode complete 480-context parity and 141 focused
regressions pass. Eight native SSD runs give 22.849923 s parent versus 4.260864 s current,
an 81.35% reduction. Those are #39-to-#41 gains, not improvements earned by this follow-up.
Use the latest corrected **#41 production source as A** and that source plus one candidate
change as B for incremental acceptance. Reuse the completed investigation for attribution;
do not repeat its whole campaign merely to rediscover the priorities. Capture fresh matched
baseline/candidate timings for actual implementation changes.

The investigation confirms copying first, then paths and membership. Event-copy wall work
is about 0.39 s across parse/collection, only part of which may be removable. Path and
membership profile costs do not yet give defensible native saving estimates. All 480 TEF
fragments differ; the 2,880 full-key fallbacks remain necessary proof boundaries. Certificates
already have 25,793 hits from 25,935 lookups. Immutable assembly/consumer projection are later
options, with about 0.41/0.37 s observed subtree budgets and high provenance risk; constructor
cost alone is only about 0.055 s. Keep inclusive budgets separate.

## Objective

Reduce repeated CPU work in serial model parsing and cached dependency collection without
changing public outputs, required context effects or established APIs. The previous gain is
serial; keep one worker as the primary comparison. Profile counts are hypotheses, not native
speed-up evidence. Implement the smallest maintainable improvement, measure it, then decide
whether the next priority merits implementation.

## Priority 1: configuration and event-database copies

Inspect `settings.from_config()`, parse-context copying, `EventDatabase.copy()`,
`CaseInsDict`, `TuflowLine`/`Command` construction and deferred input/source projection.
The recorded 480-context consumer makes 14,316 config/event-database copies and 605,055
event-dictionary assignments; 8,271 copies and 387,035 assignments occur after parsing.

Find which clones are required and which repeat equivalent read-only work. Consider bulk
copying already normalised mappings into fresh independent snapshots. Preserve:

- Case-insensitive keys, original key spelling, insertion order and override/merge semantics.
- The existing depth of copying for nested dictionaries and the separate `inputs` list.
- The intentional reference handling of `variables` and declaration accumulation/order.
- Configuration subclasses, custom mapping/context hooks and conservative fallbacks.
- Independent mutation of source/copy and of different runs; no shared mutable run state.
- Source/build-state changes and invocation-local cache lifetimes.

Do not bypass overridden methods or merge behaviour on the assumption that every database is
an exact built-in instance. Prove eligibility or use the existing implementation.

## Priority 2: path conversion and decomposition

Inspect `TuflowPath` construction, `__str__()`, database/layer splitting, file-reference
projection and repeated use of the same path components. Recorded full-workload counts are
437,418 string conversions and 237,774 database/layer splits.

Prefer eliminating repeated conversion inside a known operation before adding broad caches.
If adding reusable parsed representations, prove their mutation and source-identity boundary.
Test GeoPackage `>>` and `|layername=`, NetCDF forms, extensionless/layerless references,
trailing separators, relative paths, Windows/POSIX case differences, mapped drives/UNC,
wildcards, unresolved variables and variable/event-dependent filenames. Do not turn a
lexical projection into filesystem, GIS or directory-scan work.

## Priority 3: compiled membership overhead

Inspect `_compiled_membership()`, `_compiled_scope_eligible()` and compiled predicate
execution. The original workload makes 196,939 membership accesses and 165,641 eligibility
checks during collection. Consider reusing merged event membership within the existing
representation rather than repeatedly allocating equivalent sets.

Preserve progressive event-key visibility, event-value overrides, flag slots, supported
context reload/invalidation methods, custom hooks, unknown variables and source mutation
boundaries. Preserve `If`/`Else If`/`Else`, mixed/whole negative alternatives and the precise
ordinary scope comparison rules. Do not add a redundant decision cache or change general
public Scope equality merely to make the fast path easier.

## Correctness boundaries for every priority

Compare complete public run records from the same parsed source identity, preserving UUIDs,
command order/positions, original command metadata, file/layer references, selected included
sources, database activation ownership, CSV selectors and errors. Cover ordinary uncached,
ordinary cached, full-key reference fragments and each independently enabled optimisation.
Retain negative tests deliberately attempting to collide keys or omit state changes.

Retain all #41 regressions, particularly:

- Variable-dependent include paths: scenario/event slots, transitive aliases, changed source
  identity with equal internal values, nested/multiple/wildcard selection, missing or
  ambiguous/unparsed children, case behaviour and reparsed/changed source snapshots.
- Transitive/cyclic/unresolved variables, overlapping/default/scoped assignments and event
  substitutions introducing additional tokens or variables.
- Fragmented delimiters in source expressions and late substitutions, plus surplus literal
  angle brackets: preserve actual Context replacement semantics and safe full-key fallback;
  conservative compilation must not introduce new ordinary-evaluator errors.
- Late Unicode TEF substitutions, including final sigma, dotless i and long s: respect the
  actual replacement-key semantics, not an assumed generic case-normalisation rule.
- Mixed negative membership alternatives such as `A | !B`, including event-definition keys.
- `PAUSE`, errors, custom hooks, transactional failed-run cache invalidation and no source I/O
  from the deferred dependency projection.
- Multiple BC databases, source provenance and selectors. Ignore only wholly empty unnamed
  BC rows left by separators/comments; retain invalid constant and data-bearing-row checks.

Do not force TEF fragment reuse: 480 distinct outputs can require 480 evaluations. Preserve
full-key and ordinary fallbacks when complete equivalence or mutation safety is unproven.

## Implementation and measurement sequence

1. Freeze the latest parent/candidate/consumer sources and input/environment identities.
   Capture a fresh matched baseline before changing production code. Separate parsing from
   context/collection and consumer inventory/report work.
2. Add focused correctness/negative regressions for priority 1. Implement only that step,
   verify it, then measure it independently. Commit a reviewable result.
3. Address priorities 2 and 3 one at a time only where measured attribution justifies them.
   Keep each change independently measurable/removable; do not combine unmeasured changes.
4. Compare complete outputs on the retained private 480-, 36- and 240-context workloads when
   available. Do not publish identifying data or edit those files. Retain each workload's
   complete/incomplete status if access or tooling is unavailable.
5. Use normal Python 3.14, no new venv/worktree, one worker and fresh processes in balanced
   ABBA/BAAB order. Keep model/input location, flags/order, dependencies, consumer revision,
   header/inventory options and logging identical. Use SSD only; the owner has already
   validated network access and does not request another SMB comparison. Revisit network
   benchmarking only if separately requested.
   No profiler or observer overhead in native acceptance timings. Bound each campaign;
   stop on parity/input-integrity failures and preserve failed checkpoints.
6. Report call/allocation counts, parse and collection time, total wall/process CPU, memory,
   setup/compilation overhead, fragment behaviour and full provenance parity. Distinguish
   logical filesystem calls from physical I/O and nested profile times from exclusive time.
7. Retain only changes with reproducible native benefit beyond plausible noise, acceptable
   memory/setup overhead and complete correctness. Remove non-beneficial production changes;
   keep useful tests and sanitised diagnostic evidence. Do not treat fewer calls as success.
8. Run Ruff, appropriately scoped Pyright and applicable parser/batch/fragment/deferred
   checks. Fix new diagnostics and identify inherited ones separately. Verify actual
   ryan-tools PR #161 consumer compatibility. Run the applicable Windows Python 3.12/3.14
   hosted matrix and distinguish local evidence from terminal exact-head CI.
9. Update this draft PR's description and indexed handoff around the final implemented scope,
   publish only sanitised evidence, and request a fresh exact-head Codex review. Resolve
   findings. Leave explicit remaining native/CI/access gates and a retention recommendation.

## Restrictions and deliverables

No solver execution, private model edits, production multiprocessing, first-run prioritisation,
public API changes solely for this optimisation, extra PR/worktree, new virtual environment,
PR merge, squash, release, parent-branch changes or unauthorised retargeting. Keep raw names,
paths, flags, commands, CSVs, records, mappings and profiles outside the repository.

Deliver reviewable source changes only after implementation is requested, focused regressions,
complete-output evidence, independently measured improvements, fallback/mutation limitations,
sanitised benchmark evidence and an accurate final-head CI/review handoff. If a candidate does
not earn retention, say so and leave its production code out of the final change.
