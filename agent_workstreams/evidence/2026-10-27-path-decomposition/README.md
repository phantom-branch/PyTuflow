# Path decomposition experiment: not retained

Completed 27 October 2026 (Australia/Perth), on existing [PR #42](https://github.com/phantom-branch/PyTuflow/pull/42).

**Decision: remove the lexical cache.** Full provenance parity passes and repeated parsing is almost eliminated, but neither clean native campaign demonstrates an incremental wall-time gain. Retain useful path-semantics regressions and the evidence. Keep #41, TEF fallbacks and immutable result assembly unchanged.

## Stack and frozen sources

- Baseline is current #41 `0fa632dab996ad40f6c20bcc466cb5d4d0beadf6`, not #39. It was already incorporated through normal merge `70b8b07` before this experiment.
- Prototype: `74f35440effa8fc9e15e95415929fdcdc9a40a81`. Later test-only formatting leaves its runtime tree unchanged.
- Rollback: `1e50dff1369c73b38f86e7bb155b1a7d65aeb85d`. Final parser tree is again exactly the parent: `c5d4402e3886e145b1e49c941e4cdb1b5d7ddff6`.
- Actual consumer #161: `04999e77d497173294f43e137dedbd0bde60d88a`, unchanged throughout the experiment.
- Normal Python 3.14.6, existing installed dependencies, immutable Git archives outside the repo, one process and one I/O worker per check. SSD only; no solver, model edits, venv/worktree, new PR, parent change, PR merge or release.

[Protocol and source hashes](protocol.json) | [Native observations](native.json) | [Complete-record parity](parity.json) | [Operation profile](operations.json) | [Final validation](validation.json) | [Environment](environment.json).

## Hypothesis and boundaries

Baseline splitting has 171,051 calls from dbpath, 64,195 from lyrname, 2,454 from reference construction and 74 from glob. Reusing property values directly would need to respect custom getter behaviour. The independently removable prototype therefore tested reuse at the pure lexical split boundary.

It rendered str(self) on every request and used an LRU of at most 512 entries keyed by exact literal text and the original immutable compiled regex. Values were immutable database/layer component tuples: no Path instances, parsed files, selected sources, models, run contexts, references, bindings, existence checks or file contents were retained. Non-default regex and non-exact string objects used the uncached body so stateful/unhashable hooks remained authoritative. Errors were not cached.

Relative resolution, case policy, variable replacement and file selection stayed with the existing evaluator. In particular, this was not a cached file result: #41 continued to include selected parsed source identity, resolved paths and child selection in fragment equivalence. Current string rendering observed changed text and trailing-separator state. Source reparsing or file-content changes cannot be inferred from a lexical tuple; the evaluator remained responsible for those states. No filesystem/GIS probe was introduced by decomposition.

## Native SSD acceptance

Two separate campaigns each contain 16 fresh-process observations, eight per revision. Initial block order: ABBA/BAAB/ABBA/BAAB. Independent confirmation: BAAB/ABBA/BAAB/ABBA. All 32 observations, including slowdowns, are retained. No profiler or tracing wrappers run during native timing; diagnostic profiles are separate after the native campaigns.

The boundary is preflight API entry through normal CSV report completion, including parsing, context/dependency projection, inventory and header work. Startup/import/setup is outside and reported separately. Outer-process timing also includes launch, artefact writing and shutdown. Keep inclusive phases and medians separate; do not add them or pool campaigns/earlier sources.

| Campaign | Current #41 median s | Prototype median s | Reduction | Current/prototype SD s |
| --- | ---: | ---: | ---: | --- |
| Initial | 3.922109 | 3.928140 | -0.15% | 0.146481 / 0.142306 |
| Confirmation | 3.907233 | 3.942116 | -0.89% | 0.168174 / 0.212147 |

The prototype median is 0.15% slower initially and 0.89% slower on confirmation. Ranges overlap and independent blocks vary; this is no demonstrated incremental gain, rather than proof of a general regression. The retention condition fails. No further unchanged-source campaigns were run to seek a favourable result.

| Block | Current #41 median s | Prototype median s | Reduction |
| ---: | ---: | ---: | ---: |
| 1 | 4.114047 | 4.070510 | +1.06% |
| 2 | 3.967182 | 3.943821 | +0.59% |
| 3 | 3.875097 | 3.796399 | +2.03% |
| 4 | 3.796136 | 3.845152 | -1.29% |
| 5 | 4.219431 | 3.970777 | +5.89% |
| 6 | 3.904989 | 3.929721 | -0.63% |
| 7 | 3.841755 | 4.210834 | -9.61% |
| 8 | 3.907233 | 3.941881 | -0.89% |

| Campaign / median metric | Current #41 | Prototype |
| --- | ---: | ---: |
| Initial: API/report process CPU s | 3.898438 | 3.890625 |
| Initial: parse s | 0.739506 | 0.714244 |
| Initial: context/projection s (inclusive) | 3.111785 | 3.126607 |
| Initial: inventory/header s (inclusive) | 0.007720 | 0.007628 |
| Initial: report write s | 0.004478 | 0.004276 |
| Initial: startup/import/setup s | 0.851900 | 0.847705 |
| Initial: process-lifetime peak MiB | 202.712891 | 202.755859 |
| Confirmation: API/report process CPU s | 3.898438 | 3.929688 |
| Confirmation: parse s | 0.728550 | 0.753284 |
| Confirmation: context/projection s (inclusive) | 3.129534 | 3.171404 |
| Confirmation: inventory/header s (inclusive) | 0.008090 | 0.007621 |
| Confirmation: report write s | 0.000447 | 0.000418 |
| Confirmation: startup/import/setup s | 0.848842 | 0.872834 |
| Confirmation: process-lifetime peak MiB | 202.669922 | 202.773438 |

All native passes retain 480 contexts, 50 checked paths, 24 headers and 480 selectors, zero issues and whole-run fallbacks. Native JSON retains every sample/range/SD and outer-process timing. CPU frequency/affinity, background load and warm OS caches remain uncontrolled; no cold-storage, confidence interval or general speed-up claim. No SMB or different workload is mixed into timing.

## Work avoided is not native acceptance

| Profiled operation | Current #41 | Prototype |
| --- | ---: | ---: |
| All Python/C calls | 32,867,112 | 32,390,852 |
| Current path string rendering | 437,418 | 437,418 |
| Split entry requests | 237,774 | 237,774 |
| Actual parsing bodies | 237,774 (entry body) | 350 |

The process-lifetime prototype cache has 237,435 hits, 351 misses and 351 retained entries (99.85% hits). It includes 12 setup requests before profiling; the API/report profile contains 237,774 entry requests and 350 helper computations. Do not conflate those timing/counter boundaries. Entries are bounded in count, and byte usage depends on input text length.

The cache retains live string conversions and adds dispatch, hashing and LRU bookkeeping. Even near-total removal of repeated parsing does not imply a material runtime saving. Default cProfile elapsed self/cumulative times in the JSON include observer overhead; cumulative rows overlap and cannot be summed or subtracted from clean native times.

## Provenance and retained tests

Fifteen complete recursive run-record comparisons pass on three separate retained workloads (480, 36 and 240 contexts), five modes each: current-parent fragments, experimental ordinary uncached/cached, experimental full-key reference (both private compilation switches off), and combined evaluation. Equality includes all UUIDs, ordered commands/positions, selected control-file paths, layers, references, activations, database sources/selectors and errors. It compares actual records, not only hashes/counts. Workload identities are kept separate.

The prototype passed 631 focused parser/context/dependency regressions, including a bounded-cache/no-Path-retention case. After removing the cache-specific resource test and adapting syntax cases to real path objects with controlled rendering, the final retained suite passes **630 tests plus 119 actual consumer tests, zero skips**. The final 27 new path cases cover Windows/POSIX/UNC syntax, both database/layer forms, NetCDF, wildcards and unresolved variables, Unicode/case spelling, live rendering and trailing separators, changed/custom regex and string callbacks, repeated malformed-input errors and filesystem-free property decomposition. All 15 existing path tests also run.

Ruff/format/default Pyright on the new tests and existing scoped strict Pyright pass. The prototype legacy module had 12 unchanged Ruff findings and default Pyright reduced 15 to 13, with no new rule messages. No legacy cleanup, type suppression or production annotation change remains in the final parser tree. Windows Python 3.12/3.14 combined and deferred workflows include the new cases; final-head hosted state and fresh review are separate receipts in the PR description.

## Retention decision and next action

The production cache is removed; the final parser tree equals current #41. Keep the new behavioural regressions, CI coverage, source-specific evidence and the earlier rejected copy investigation. Do not revive either mechanism because it has fewer calls/high cache hits. TEF fallbacks and immutable assembly remain unchanged. The existing 81.35% parent-#39-to-#41 gain is historical context, not an incremental gain here.

Stop this bounded path experiment. Further performance work needs a new measured budget/mechanism and explicit scope, rather than repeated campaigns on this implementation. No additional production optimisation is accepted by these findings.

## Reproduction and privacy

Inspect [audit snapshots](audit/) before adapting them. Copy .txt runners to a private directory and supply private W0/W1/W2 configuration, A/B source archives, consumer source, input guards and flag files. campaign.py runs complete-record checks followed by the initial native block; confirm.py runs the independent bounded confirmation. measure.py can run separate cProfile diagnostics and queries cache info only after instrumented timing.

Raw model/control paths, flags, records, mappings, reports and profiles remain private. Source archive and input-guard hashes provide receipts without filenames. Guards cover parsed control/database sources and command lists, not every GIS/raster/time-series payload. Artefact hashes use canonical UTF-8 LF text.
