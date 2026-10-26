# Serial call-reduction follow-up

Status: scoped implementation brief and prompt; no production optimisation implemented in this PR.
Updated: 27 October 2026 (Australia/Perth).

This PR is stacked on [PyTUFLOW #41](https://github.com/phantom-branch/PyTuflow/pull/41),
branch `perf/compiled-effective-dependencies`. Its creation base and profiled source are
`404101f82349d52687b739a5cdce26623f277098`. The follow-up branch is
`perf/serial-call-reduction-followup`.

[Ready-to-use implementation prompt](prompts/serial_call_reduction_followup.md) |
[Sanitised call-count evidence](evidence/2026-10-27-serial-call-audit/summary.json) |
[Parent implementation and correctness handoff](compiled_effective_dependencies.md).

## What the current improvement represents

The measured path uses one Python process, one configured I/O worker and the consumer's
serial inventory branch. No production multiprocessing explains the improvement. Fresh
processes are used for independent measurements, not concurrent production evaluation.

These counts come from instrumented profiles. They identify work, not accepted incremental
speed-ups. The historical parent is `36ad04b`; the current profiled source is `404101f`.
The same frozen consumer, original 480-context inputs and profiling boundary were used.

| Full-consumer profile calls, 480 contexts | Historical parent | Current source |
| --- | ---: | ---: |
| Total Python/C calls | 190,971,049 | 32,850,552 |
| Scope constructions | 5,877,564 | 38,863 |
| Scope expansions | 5,511,000 | 18,048 |
| Scope comparisons | 6,164,954 | 4,034 |
| Scope membership operations | 387,002 | 2,402 |
| Config/event-database copies | 26,530 | 14,316 |

## Prioritised opportunities

1. **Configuration/event-database copies.** Start here. The 480-context consumer still makes
   14,316 `from_config()`/`EventDatabase.copy()` calls and 605,055 event-dictionary assignments.
   After initial parsing, 8,271 copies and 387,035 assignments remain. Investigate faster
   independent copies of already normalised mappings and redundant copies in proven read-only
   paths. Preserve the current special handling of `variables`, mutable nested maps, input
   lists, case-insensitive lookup, event overrides and custom hooks. Sharing mutable Context
   or configuration instances between runs is not an acceptable shortcut.
2. **Path conversion and decomposition.** `TuflowPath.__str__()` runs 437,418 times and
   `_split_db_and_lyr()` 237,774 times. Collection alone accounts for 265,499 conversions and
   138,264 splits. Investigate reusing parsed components and avoiding repeated conversion
   within operations. Preserve GeoPackage/NetCDF layer identity, case policy, trailing slashes,
   relative/absolute paths, mapped-drive/UNC handling, wildcard and substitution semantics.
3. **Compiled membership overhead.** Collection makes 196,939 membership accesses and
   165,641 eligibility checks. Reusing merged event membership within the existing
   representation/invalidation boundary may remove allocations. Keys can become visible
   progressively during event loading; direct key changes and supported reload methods must
   remain observable. Do not introduce another cache of already cached decisions.

The remaining 2,880 full-key fallbacks are a correctness boundary to preserve. TEF results
legitimately differ across contexts; its 480 evaluations on the original workload are not
proof of inefficient caching. Do not force result reuse or weaken fallback coverage.

## Parsing and collection must be measured separately

| Workload | Contexts | Config copies during parse | During collection | Event assignments during collection |
| --- | ---: | ---: | ---: | ---: |
| Original | 480 | 6,045 | 8,271 | 387,035 |
| Small | 36 | 6,711 | 1,109 | 51,780 |
| Ensemble | 240 | 6,723 | 2,701 | 134,580 |

All three workloads passed consumer checks and complete public-record parity. The small
workload includes the BC comment-row fix from #41. Its prior failed state is not a valid
performance comparator. Parsing dominates that small batch, so reducing config-copy work
could help both initial loading and larger batches. Do not sum nested cumulative profile
times or combine full-consumer and parse/collection profiling boundaries.

## Acceptance and handoff

Use the linked prompt to implement each candidate as an independently removable step in this
same PR when implementation is requested. Retain a change only after complete provenance
parity, focused regressions, appropriate local/hosted checks and reproducible native benefit.
If an idea does not improve native timings beyond plausible noise, remove its production
change while retaining useful diagnostic evidence.

For future measurements, freeze the latest #41 head and this branch's candidate before work.
Use normal Python 3.14, one worker, separate fresh processes and balanced ABBA/BAAB blocks.
Keep profiler runs separate, compare the same storage location/options, and report parse,
collection, total wall/process CPU, memory and compilation/setup costs. Run correctness
against all retained 480/36/240-context workloads where available, and preserve synthetic
coverage when private inputs are unavailable. No solver, model edits or production
multiprocessing is authorised by the optimisation brief.

Raw model names/paths, flags, commands, CSVs, complete records, profiles and source mappings
stay private. The checked-in JSON contains only aggregate counts and provenance hashes.
This documentation PR makes no new performance or implementation acceptance claim.
