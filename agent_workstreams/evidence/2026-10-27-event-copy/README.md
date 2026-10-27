# Event-database copy experiment: not retained

Completed 27 October 2026 (Australia/Perth), in [PR #42](https://github.com/phantom-branch/PyTuflow/pull/42).

**Decision: remove the production fast path.** It preserves the tested copy contract and eliminates almost all event insertions, but does not demonstrate reproducible incremental native benefit. Keep the 16 useful snapshot-safety regressions and sanitised evidence. Path decomposition is the next candidate to investigate; TEF full-key fallbacks, fragment assembly and #41 remain unchanged.

## Correct source and stack

- Current parent #41 baseline: `0fa632dab996ad40f6c20bcc466cb5d4d0beadf6`, not #39.
- The child first incorporated that parent with normal merge `70b8b0763a93010d1b894baaa009c4404a69de3a`, preserving the newer cache-correctness fixes and published child history.
- Accepted experimental source: `dbdc4d82b9dd927e500234099e21f3f0c83b31a8`.
- Rollback: `d340034`. The final `pytuflow` tree is exactly the parent tree, `c5d4402e3886e145b1e49c941e4cdb1b5d7ddff6`. Experimental commits remain visible in history; there is no net parser source change.
- Actual consumer PR #161: `04999e77d497173294f43e137dedbd0bde60d88a`; fixtures use its gitlink `d2dae3ecf9a7ed306e1340de54a8d12ca9f53f58`.

[Protocol/source hashes](protocol.json) | [All native trials](native.json) | [Complete-record parity](parity.json) | [Diagnostic operations](operations.json) | [Final validation](validation.json).

## What was tried

The prototype bulk-copied an exact built-in EventDatabase only when original class definitions, ordinary attribute storage, string keys, plain dict values and a plain inputs list were proven. It rebuilt the case-insensitive key index rather than copying a potentially stale one. Case aliases, subclasses, overridden callbacks, custom value/list/attribute mappings and incomplete state retained the established insertion loop. No context/result sharing, persistent model cache or public API was introduced.

The initial copy-only microbenchmark favoured the mechanism, but was diagnostic only. Guard checks, type checks, temporary dictionaries and index construction replace some of the removed work. Fewer insertion calls are not pure savings, and the observed roughly 0.39-second event-copy budget is not wholly recoverable. No microbenchmark or profiler duration was used to accept the change.

Two early parity-only attempts were interrupted before native timing to tighten missing-input callback/error ordering and custom attribute-mapping fallback. Their raw records remain private. All accepted experimental results below belong to the final experimental source, not those earlier commits.

## Native SSD results

Normal Python 3.14.6, existing dependencies and immutable Git archive snapshots, one process and one I/O worker per check. Original retained 480-context workload, SSD only, batch/file inspection, fragments and BC CSV header/column checking enabled. Fresh processes run sequentially. No profiler/tracing wrapper runs during native timing. No model edit, solver, SMB benchmark, venv, worktree or extra PR.

Each campaign has 16 observations (eight per revision), four balanced blocks. The initial order is ABBA/BAAB/ABBA/BAAB; the separately reported confirmation reverses it to BAAB/ABBA/BAAB/ABBA. Do not pool campaigns or borrow the historical #39-to-#41 gain. The primary timing boundary is API entry through the normal CSV report completing; startup/import/setup is separate. Outer-process timing additionally includes launch, artefact writes and shutdown.

| Campaign | Current #41 median s | Prototype median s | Reduction | Current/prototype sample SD s |
| --- | ---: | ---: | ---: | --- |
| Initial | 3.882589 | 3.775467 | +2.76% | 0.249771 / 0.265565 |
| Confirmation | 3.884677 | 3.935824 | -1.32% | 0.095827 / 0.144588 |

The initial 2.76% median reduction does not reproduce: the confirmation median is 1.32% slower. All eight block results are retained, including slowdowns. Large overlaps/drift prevent a claim that the prototype improves native preflight beyond plausible noise. They also do not establish a general regression on other machines/models. The retention criterion fails.

| Block | Current #41 median s | Prototype median s | Reduction |
| ---: | ---: | ---: | ---: |
| 1 | 4.137143 | 4.255333 | -2.86% |
| 2 | 3.986412 | 3.719066 | +6.71% |
| 3 | 3.710611 | 3.703090 | +0.20% |
| 4 | 4.003202 | 3.835079 | +4.20% |
| 5 | 3.897577 | 4.033845 | -3.50% |
| 6 | 3.950354 | 4.009272 | -1.49% |
| 7 | 4.006941 | 3.841647 | +4.13% |
| 8 | 3.876773 | 3.797782 | +2.04% |

| Campaign / metric | Current #41 | Prototype |
| --- | ---: | ---: |
| Initial: API/report process CPU s | 3.867188 | 3.742188 |
| Initial: parse s | 0.700517 | 0.679372 |
| Initial: context/projection s (inclusive) | 3.129690 | 3.026381 |
| Initial: inventory/header s (inclusive) | 0.008539 | 0.007379 |
| Initial: CSV report write s | 0.002581 | 0.004408 |
| Initial: startup/import/setup s | 0.810009 | 0.809816 |
| Initial: process-lifetime peak MiB | 202.609375 | 202.783203 |
| Confirmation: API/report process CPU s | 3.875000 | 3.914062 |
| Confirmation: parse s | 0.726663 | 0.711687 |
| Confirmation: context/projection s (inclusive) | 3.107773 | 3.185483 |
| Confirmation: inventory/header s (inclusive) | 0.007524 | 0.007659 |
| Confirmation: CSV report write s | 0.004103 | 0.004195 |
| Confirmation: startup/import/setup s | 0.836976 | 0.843010 |
| Confirmation: process-lifetime peak MiB | 202.683594 | 202.716797 |

Native ranges, standard deviations, individual ordering and outer-process timing are in native.json. Inclusive phase medians are not additive. No confidence interval, controlled CPU frequency/affinity, cache flush or cold-storage claim is made. The confirmation is a bounded second campaign, not an excuse to keep measuring until a favourable result appears. Every native run passes: 480 contexts, 50 paths, 24 headers, 480 selectors, zero issues and zero whole-run fallbacks.

## Work removed and work replaced

| Diagnostic operation | Current #41 | Prototype |
| --- | ---: | ---: |
| All profiled Python/C calls | 32,867,112 | 31,154,585 |
| Config snapshots | 14,316 | 14,316 |
| EventDatabase copies | 14,316 | 14,316 |
| Event insertions | 605,055 | 110 |
| Fast-path source proofs | 0 | 14,316 |

Copy count remains 14,316: required independent snapshots were not eliminated. Insertion savings are replaced by guarded bulk construction and normalisation. The profile is a separate default elapsed-clock cProfile observation; absolute profile timings include observer overhead and cannot be subtracted from native CPU/wall timings. The call reduction does not override the failed native acceptance result.

## Correctness and mutation contract

Fifteen complete recursive record comparisons pass: five modes on each of the distinct 480-, 36- and 240-context retained workloads. Each workload compares unchanged #41 fragments with experimental ordinary uncached/cached, full-key reference fragments (both private compilation switches off), and combined evaluation. Comparisons decode every public run-record field and require recursive equality, not just matching counts/hashes. UUIDs, ordering, selected control-file paths/layers, references, activations, sources, selectors and errors remain represented. No workload sets are pooled as equivalent.

The 16 new synthetic cases retain the original copy contract: first-level event maps and input lists are independent across copies/runs; deeper nested objects preserve the original shallow sharing; variables retain their intentional reference semantics. Cases cover configuration variants/subclasses, case-alias merge order/spelling, index repair without source mutation, custom insertion/items/value/key/list/attribute callbacks, non-mapping values and existing exception/callback ordering. These tests pass on the unchanged parent implementation after the experimental fast path is removed.

Final retained source validation passes **588 parser/context/dependency tests and 119 actual consumer tests, zero skips**. Ruff, formatting of the new tests, default Pyright on the new tests and the existing scoped strict Pyright gate pass. The experimental legacy event module retains the same two default Pyright diagnostics as the parent, with no new messages; no suppression or event-module edit remains in the final diff.

The unchanged 2,880 TEF/full-key proof fallbacks and immutable record assembly are not targeted. Source identity and all newer #41 cache-correctness fixes stay intact. Final source-tree equality with the parent proves no experimental runtime code is retained. Hosted checks/review on the final documentation/test commit are separate from these local receipts.

## Next decision

Do not resurrect this bulk-copy implementation based on fewer calls. Investigate path conversion/decomposition next, starting with repeated splitting inside a known operation and measuring against current #41. Preserve relative paths, case/layer policy, wildcard/variable substitutions, source identity and custom hooks. Defer TEF fallback changes, immutable result assembly and multiprocessing.

The [updated follow-up prompt](../../prompts/serial_call_reduction_followup.md) records the next bounded task. No path optimisation is claimed or retained by this experiment.

## Reproduction and privacy

Inspect the [audit snapshots](audit/) before adapting them. Copy .txt source snapshots to a private campaign directory; supply private W0/W1/W2 configuration, parser archive folders A/B, consumer source, workload flags and input guards. campaign.py runs correctness then the initial clean block; confirm.py is the bounded independent confirmation. measure.py supports separate cProfile runs. Archive/source hashes identify the experiment. All raw flags, models, records, paths, mappings, CSVs and profiles remain private.

Artefact hashes use canonical UTF-8 LF text. Guard receipts cover parsed model/control/database sources and command lists, not complete GIS/raster/time-series payload content. Both source-specific partial attempts and every accepted native observation are retained privately; only sanitised aggregates and revision/hash receipts are published.
