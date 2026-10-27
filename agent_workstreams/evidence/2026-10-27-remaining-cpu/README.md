# Current-head serial CPU investigation

Measured 27 October 2026 (Australia/Perth). [PR #41](https://github.com/phantom-branch/PyTuflow/pull/41), stacked on [#39](https://github.com/phantom-branch/PyTuflow/pull/39).

**Recommendation:** retain #41 and investigate configuration/event-database copying first in [#42](https://github.com/phantom-branch/PyTuflow/pull/42). Path conversion and membership representation remain secondary candidates. Do not add a decision cache or force TEF reuse. No production optimisation was implemented in this investigation.

## Frozen sources and scope

- Parent #39: `36ad04bd7cb045c48f3b77e8794c48a956c90c06`.
- Latest corrected #41 at measurement: `5c32395e30029bdd3d1053d18374234d0120fab4`.
- Actual consumer PR #161: `04999e77d497173294f43e137dedbd0bde60d88a`.
- Normal Windows Python 3.14.6, existing installed dependencies, immutable Git archive snapshots; no venv or worktree.
- Original retained 480-context workload, SSD only. No SMB evaluation/benchmark was performed, as requested by the owner; earlier network validation remains separate. No other model set is mixed into this comparison.
- One process and one I/O worker per check, `context_mode=batch`, `inspection_mode=files`, fragment reuse and BC header/column checking enabled. Fresh measurement processes are sequential, not production multiprocessing.
- Guarded model/control/database sources and command-list hashes are stable. This is not a content-hash guarantee for every GIS/raster/time-series payload. Raw paths, flags, records, profiles and mapping receipts remain private.

[Protocol and source/archive hashes](protocol.json) | [Environment](environment.json) | [Native trials](native.json) | [Complete parity receipts](parity.json) | [Operation counts](operations.json) | [Phase clocks](phases.json) | [CPU profile](profile-top30.json) | [Scaling](scaling.json) | [Validation](validation.json).

## Correctness and filename variation

All six modes pass complete recursive equality of decoded public `BatchDependencyRun` records for all 480 contexts: ordinary uncached, ordinary cached, parent fragments, compiled preparation only, manifests only and combined. Comparison covers every dataclass field, UUID, ordered command, owner/selected control-file path, layer, reference, database activation/source, selector and error field. Deterministic UUIDs are used only while parsing for parity and restored before evaluation. Equality is checked directly; hashes are receipts, not the comparison criterion. All six record hashes remain `68ceba1fb5e865c8d3894165c8e99eb2d73096dfda9609dc2307f5959a8d8d93`.

Each native pass retains 480 contexts, 50 checked paths, 24 headers and 480 selectors, zero issues and zero whole-run fallbacks. The targeted source-head regression run passes **141 tests, zero skips**, covering manifests/dynamic selection, compiled scopes, fragments/failed runs and deferred database parity. The real workload itself contains no failed runs; error/fallback safety comes from those regressions.

[Reference variation](reference-variation.json) separates direct references from selected database sources. Across all runs, 24 path/layer pairs are invariant and 26 vary, making 50 union pairs and 48 distinct per-run sets of 26. Direct references have 24 invariant pairs plus two alternate BC database files, selected by event slot 4. BC time-series sources select 24 distinct files through event slots 1 and 2. Event slot 3 changes selectors rather than filenames. All six evaluators agree per simulation. Scenario slots are constant in this workload; variable-dependent geometry/nested includes and changed-source identity are validated by synthetic regressions, not inferred from these invariant flags. No filenames or flag values are published.

## Uninstrumented SSD timing

Two balanced fresh-process blocks, `ABBA` then `BAAB`, give four observations per version. Native measurements have no profiler, tracing wrappers or detailed diagnostic CSV generation. The primary boundary is API entry through the normal CSV report completing, including parsing, compilation, preparation, dependency projection, inventory and report writing. Imports/setup are outside it.

| Native measurement | Parent median s | Current median s | Current minus parent s |
| --- | ---: | ---: | ---: |
| Preflight through CSV report | 22.849923 | 4.260864 | -18.589059 |
| Startup/import/setup inside worker, outside API | 0.883866 | 0.843259 | -0.040607 |
| Model parsing | 0.723660 | 0.730635 | +0.006974 |
| Context, dependency and consumer projection (inclusive) | 22.052826 | 3.501477 | -18.551349 |
| Inventory, including headers (inclusive) | 0.010411 | 0.008968 | -0.001442 |
| CSV report writing | 0.000473 | 0.000645 | +0.000172 |
| Process CPU over API/report boundary | 22.765625 | 4.257812 | -18.507812 |
| Outer launch through exit (includes artefacts/shutdown) | 23.936533 | 5.314306 | -18.622227 |

The primary median reduction is **81.35%**, or 5.36 times the throughput at 480 contexts. Peak process working-set medians are 207.982 MiB parent and 202.984 MiB current. Memory is process-lifetime peak, not an incremental allocation measurement.

| Revision | Native range s | Sample SD s | Values in observation order s |
| --- | --- | ---: | --- |
| Parent | 22.621899–23.997757 | 0.637663 | 23.997757, 23.025759, 22.621899, 22.674087 |
| Current | 4.153609–4.383619 | 0.105579 | 4.153609, 4.202008, 4.319720, 4.383619 |

Order is `A B B A / B A A B`. Parent timings drift down (23.998 to 22.674 s), while current timings drift up (4.154 to 4.384 s). Both blocks retain a large improvement; balanced order does not remove background/cache/frequency uncertainty. The first parent inventory is an outlier at 0.165 s versus roughly 0.009–0.012 s otherwise. No observation is discarded. Four samples do not establish formal statistical significance or general speed-ups on arbitrary models. Do not add medians or subtract costs measured in different profiling boundaries.

## Work avoided and replacement work

| Operation | Parent | Current/remaining | Avoided |
| --- | ---: | ---: | ---: |
| All Python/C profile calls | 190,971,050 | 32,867,136 | 158,103,914 |
| Scope constructions | 5,877,564 | 38,863 | 5,838,701 |
| Scope expansions | 5,511,000 | 18,048 | 5,492,952 |
| Scope equality | 6,164,954 | 4,034 | 6,160,920 |
| Scope membership | 387,002 | 2,402 | 384,600 |
| Compiled program dispatches | 0 | 139,706 | -139,706 |
| Full dependency keys | 24,495 | 2,880 | 21,615 |
| Compact signatures | 0 | 21,615 | -21,615 |
| Compact cache hits | 0 | 21,501 | -21,501 |
| Compact cache misses | 0 | 114 | -114 |
| Fragment evaluations | 2,494 | 1,096 | 1,398 |
| Fragment reuses | 22,001 | 23,399 | -1,398 |
| All compiled predicate evaluations | 0 | 166,121 | -166,121 |
| Certificate evaluations | 0 | 142 | -142 |
| Certificate cache hits | 0 | 25,793 | -25,793 |
| Expression evaluations | 34,299 | 27,961 | 6,338 |
| Expression pool hits | 34,636 | 3,238 | 31,398 |
| Transitive expression bindings | 70,375 | 31,199 | 39,176 |
| Effective manifest bindings | 0 | 25,935 | -25,935 |
| Dataclass replace calls | 46,588 | 46,588 | 0 |
| InputRunState constructions | 2,494 | 617 | 1,877 |
| Config copies | 26,530 | 14,316 | 12,214 |
| Event assignments | 1,070,355 | 605,055 | 465,300 |
| TuflowPath string conversions | 846,417 | 437,418 | 408,999 |
| Database/layer splits | 451,109 | 237,774 | 213,335 |
| Audit event: open | 66 | 66 | 0 |
| Audit event: sqlite3.connect | 34 | 34 | 0 |
| Audit event: os.scandir | 1 | 1 | 0 |
| Audit event: os.listdir | 1 | 1 | 0 |
| Profiled nt.stat calls | 119 | 125 | -6 |

Negative avoided counts identify new/replacement work, not a regression by themselves. Full scope expansion is replaced by 139,706 compiled program dispatches and 166,121 total predicate evaluations (including direct manifest predicates). Translation-pool hit counts shrink because fewer translations are requested. A compact-key lookup is not a disk access. Audit `open`, `sqlite3.connect`, `listdir`, `scandir` and profiled `nt.stat` counts describe observed APIs, including lazy imports; OS caching and library-internal I/O mean they do not count physical disk transfers. Constructor counts can overlap parent/child class initialisers. Dataclass replacement remains 46,588 calls; immutable rebasing is not eliminated.

## Phase attribution and fallback cost

These are separate narrowly instrumented diagnostics. Wall clocks below are exclusive only of other observed nested labels; remaining unobserved descendants are included. Recursive fragment/join frames subtract observed child frames. Process CPU counterparts are in the JSON; their finite resolution can give zero for small phases. Observer overhead is included. These numbers must not be added to or subtracted from native timings. Context construction is included in the native context total; event/variable clocks below are separate portions of it, not another batch total.

| Observed phase, exclusive wall s | Parent | Current |
| --- | ---: | ---: |
| Plan compilation | 0.001908 | 0.006100 |
| Event loading | 2.019065 | 0.131915 |
| Variable preparation | 2.207499 | 0.093944 |
| Context constructor excluding observed event loading | 0.042241 | 0.032574 |
| Completed run-record initialisers | 0.002227 | 0.001146 |
| Key construction | 3.435233 | 0.790452 |
| Fragment evaluation excluding observed keys/children/copies | 13.456986 | 2.195386 |
| Join/assembly excluding observed descendants | 0.425767 | 0.409591 |
| EventDatabase copies while parsing | 0.123054 | 0.109844 |
| EventDatabase copies after parsing | 0.590150 | 0.280454 |
| Consumer reference collection | 0.351274 | 0.368070 |
| CSV header reads (part of inventory) | 0.003213 | 0.001761 |
| CSV selector checks | 0.003522 | 0.003341 |
| BatchInputCommand initialisers | 0.053367 | 0.041442 |
| BatchInputReference initialisers | 0.014973 | 0.012797 |

After parsing, config/event copies fall from 20,485 to 8,271; parsing still makes 6,045 copies. Current event-copy wall observations total about 0.390 s across parse/collection, with a separate repeated copy probe at 0.387 s. This is an inclusive observed copy budget, not an achievable saving: fresh snapshots, normalisation/merging and variable reference semantics remain required. The combined fragment phase still contains much of configuration copying, command/path evaluation and output projection. Consumer reference collection is about 0.37 s; normal report writing is below 1 ms median. Parsing and per-run CPU dominate the roughly 9 ms inventory.

All **2,880** full-key fallbacks carry the existing `event-substitution` reason: 480 TEF include keys (about 0.552 s inclusive observed key wall) and 2,400 leaf keys (about 0.05 s). That reason labels the current proof failure, not a universal claim that every future failure involves a literal TEF token. There are zero compiled-scope fallbacks and zero whole-run ordinary fallbacks on this workload. TGC and TBC each evaluate once/reuse 479 times. TEF evaluates 480 times and produces **480 distinct complete fragments**; reducing this count would be wrong without a new equivalence proof.

Manifest certificates are evaluated 142 times, with 25,793 hits from 25,935 lookups. `_include_selection()` is called 1,922 times but takes only about 0.021 s exclusive observed wall; cached selected-source identity validation is already cheap. Compact signatures number 21,615, with 21,501 hits and 114 misses. The complete key still carries selected source identity and resolved include selection.

## Top 30 production functions by self CPU

A separate cProfile run uses the thread CPU clock, not default elapsed timing. Total profiled self CPU is 21.296875 s versus 4.257812 s median native process CPU: clock/profiler callbacks substantially perturb execution. CPU accounting is quantised; averages are approximate and not nanosecond-level native call costs. Self CPU rows do not overlap each other, but cumulative CPU rows do. Generated functions retain source line numbers in JSON.

| Module:function (line) | Calls | Self CPU s | Cumulative CPU s | Mean self µs/call |
| --- | ---: | ---: | ---: | ---: |
| event.py:__setitem__ (14) | 605,055 | 0.640625 | 1.562500 | 1.059 |
| case_insensitive_dict.py:__setitem__ (17) | 605,072 | 0.484375 | 0.578125 | 0.801 |
| file.py:__str__ (455) | 437,418 | 0.421875 | 1.531250 | 0.964 |
| event.py:copy (35) | 14,316 | 0.406250 | 2.359375 | 28.377 |
| fragment_dependencies.py:_compiled_membership (221) | 196,939 | 0.359375 | 0.968750 | 1.825 |
| file.py:__new__ (34) | 164,315 | 0.343750 | 0.890625 | 2.092 |
| file.py:_split_db_and_lyr (89) | 237,774 | 0.328125 | 1.437500 | 1.380 |
| settings.py:from_config (433) | 14,316 | 0.296875 | 4.671875 | 20.737 |
| patterns.py:replace_exact_names (184) | 168,083 | 0.265625 | 0.906250 | 1.580 |
| fragment_dependencies.py:<genexpr> (217) | 780,445 | 0.265625 | 0.265625 | 0.340 |
| fragment_dependencies.py:_compiled_scope_eligible (210) | 165,641 | 0.250000 | 0.593750 | 1.509 |
| fragment_dependencies.py:<genexpr> (119) | 439,248 | 0.250000 | 0.390625 | 0.569 |
| case_insensitive_dict.py:__contains__ (14) | 605,055 | 0.234375 | 0.343750 | 0.387 |
| input_preflight.py:add_file (318) | 12,480 | 0.218750 | 0.687500 | 17.528 |
| context.py:translate (219) | 27,961 | 0.203125 | 1.265625 | 7.265 |
| file.py:dbpath (190) | 171,051 | 0.187500 | 1.468750 | 1.096 |
| fragment_dependencies.py:_full_key (630) | 2,880 | 0.187500 | 3.343750 | 65.104 |
| compiled_scope.py:evaluate (35) | 166,121 | 0.171875 | 1.140625 | 1.035 |
| scope.py:__init__ (183) | 38,863 | 0.156250 | 0.296875 | 4.021 |
| file.py:__init__ (59) | 164,315 | 0.156250 | 0.375000 | 0.951 |
| fragment_dependencies.py:evaluate (775) | 71,546 | 0.156250 | 14.343750 | 2.184 |
| fragment_dependencies.py:<genexpr> (657) | 147,600 | 0.156250 | 0.171875 | 1.059 |
| batch_preflight_adapter.py:__init__ (115) | 480 | 0.140625 | 0.859375 | 292.969 |
| command.py:is_file (136) | 27,569 | 0.140625 | 4.890625 | 5.101 |
| fragment_dependencies.py:_key (601) | 24,495 | 0.140625 | 3.906250 | 5.741 |
| fragment_dependencies.py:bindings (71) | 31,199 | 0.125000 | 0.843750 | 4.007 |
| compiled_scope.py:evaluate (130) | 139,706 | 0.125000 | 1.828125 | 0.895 |
| file.py:suffix (182) | 105,811 | 0.109375 | 2.343750 | 1.034 |
| fragment_dependencies.py:translate (259) | 40,552 | 0.109375 | 2.484375 | 2.697 |
| command.py:is_valid (284) | 434,600 | 0.109375 | 0.109375 | 0.252 |

The CPU/profile JSON also lists `_manifest_signature`, `_key`, `_full_key`, both binding implementations, `event_independent`, `_include_selection`, `_join` and both evaluator layers. Use self CPU for attribution, not sums of overlapping cumulative columns. The default elapsed-clock profile is retained separately in that JSON for comparison; neither is a native benchmark.

## Repeated predicates, TEF and output assembly

There are 104 distinct predicate shapes; 76 return the same result across their observed calls (124,361 of 166,121 evaluations). This does not prove they are globally invariant: event-definition keys become visible progressively, and flags/variables differ outside this workload. `_compiled_membership` still runs 196,939 times and eligibility 165,641 times. Investigate merged membership representation/invalidation, not another decision cache. Cheap empty predicates and a high hit count alone do not justify more caching.

[Assembly counts](assembly.json) show 31,680 emitted command descriptors but 99 distinct values, 12,000 input-reference records but 26 values, and 960 activations but three values. All 480 database-source records differ, including selectors. These are equality counts, not evidence of current object sharing or permission to drop per-run identities/order. The 33,752 command and 12,518 reference initialisers cost about 0.055 s combined in the narrow probe. Whole join/assembly costs more (~0.4 s exclusive observed wall), but rewriting provenance assembly to avoid only constructors has a small ceiling. Existing immutable compiled expressions/manifests already share invariant source data; mutable contexts/event values must remain independent.

## First result and scaling

Each row is a fresh process and a prefix of the same ordered command list; one observation per prefix/version, no fit or confidence interval. Scaling measures parser plus dependency collection, excluding consumer inventory/report/imports. First-result time starts immediately before collection and includes plan construction plus the first completed run record; parsing is listed separately. Native startup/import/setup is about 0.84–0.88 s separately. Do not add unrelated medians as a measured launch-to-first-result time.

| Contexts | Parent parse s | Current parse s | Parent first context s | Current first context s | Parent collection s | Current collection s | Parent/current marginal ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0.711397 | 0.693301 | 0.099099 | 0.082455 | 0.099285 | 0.082748 | n/a |
| 10 | 0.733604 | 0.715167 | 0.102177 | 0.078773 | 0.447949 | 0.135011 | 38.419 / 6.249 |
| 40 | 0.720683 | 0.812719 | 0.097989 | 0.085343 | 1.630886 | 0.364510 | 39.305 / 7.158 |
| 160 | 0.763685 | 0.772871 | 0.105268 | 0.078693 | 7.289132 | 1.020149 | 45.182 / 5.921 |
| 480 | 0.725741 | 0.734366 | 0.100575 | 0.077461 | 21.489513 | 3.174714 | 44.653 / 6.466 |

Current marginal collection cost is roughly 5.9–7.2 ms/context across these prefixes, versus 38.4–45.2 ms parent. At 480 contexts it is 6.466 versus 44.653 ms. This is consistent with approximately linear work after initialisation, with workload composition/timing variation; it is not proof of a constant slope for arbitrary contexts. The first dependency result improves only modestly (~0.10 to ~0.08 s after parsing), while parsing remains ~0.7–0.8 s. Throughput improvement should not be presented as the same first-result improvement. No first-run scheduling change is proposed.

## Ranked opportunities and retention decision

| Priority/candidate | Measured budget | Mechanism | Estimated recoverable native time | Risk/recommendation |
| --- | --- | --- | --- | --- |
| 1. Config/event copies | 14,316 copies; ~0.381–0.387 s observed EventDatabase copy wall, including ~0.272–0.275 s after parse; `from_config` has 4.672 s cumulative CPU in the perturbed profile | Bulk-copy already normalised mappings into independent snapshots; eliminate clones only on proven read-only paths | Unproven; less than the observed ~0.39 s event-copy budget for that operation alone. The full config subtree overlaps it, so do not add the budgets | Medium: subclasses/hooks, nested mutable maps, lists, variables-reference rules. Prototype and measure only this first |
| 2. Path conversion/decomposition | 437,418 string conversions and 237,774 splits; their non-overlapping self CPU sums to 0.750 s in the perturbed CPU profile | Reuse parsed components within an operation; avoid repeated conversion | No defensible native estimate yet; the profile budget is attribution, not a prediction | Medium: GeoPackage/NetCDF, relative/UNC/case/layers and dynamic filenames. Investigate only after priority 1 |
| 3. Membership representation | 196,939 membership accesses; 165,641 eligibility checks; their self CPU sums to 0.609 s in the perturbed profile | Avoid repeated event-name union/temporary allocation within existing invalidation | No defensible native estimate yet; predicates are already cheap | Medium/high mutation risk. No extra scope-decision cache |
| 4. Immutable result assembly/consumer projection | ~0.4 s observed exclusive join wall, ~0.37 s consumer collection; constructor subset only ~0.055 s | Reuse invariant descriptors or reduce rebases where ordering/source/activation ownership is unchanged | Less than each observed subtree budget; do not add them to estimate a combined saving | High provenance complexity; defer unless priorities 1–3 disappoint and profiling still justifies it |
| Reject for now: certificate caching, forced TEF reuse, report formatting | Certificates already 99.45% hits; 480 distinct TEFs; report median <1 ms | No additional cache or forced equivalence | Small or invalid saving | Stop here for these ideas; preserve all fallback and cascade proofs |

These are budget bounds or explicit unknowns, not projected speed-ups. No proposed mechanism has earned retention yet. [PR #42](https://github.com/phantom-branch/PyTuflow/pull/42) should start with one independently removable configuration-copy step and retain it only after complete records/regressions and balanced uninstrumented native gains beyond noise. Stop if no safe change earns that result. Do not implement a bundle merely because call counts are high.

## Reproduction and delivery limits

The [audit snapshots](audit/) take private JSON configuration with `parser_sources`, `consumer_source`, `tcf`, `runs_json`, `output`, expected counters and options. Inspect them before running. `.txt` files are source snapshots, not installed commands; copy them to a private campaign directory and supply matching configuration. `campaign.py` runs six complete-record comparisons followed by the SSD ABBA/BAAB native blocks; `diagnostic_campaign.py` runs attribution, elapsed/CPU profiles and prefix scaling separately. `diagnose.py` also supports the independent `copies` probe. Raw diagnostic CSVs/profiles/records must stay outside the repo.

The final phase probes were rerun with the same final constructor/copy instrumentation on both revisions; an independent candidate copy probe remains separate. The current public validation is 141 targeted tests, not a claimed rerun of every parser/consumer/hosted workflow. Hosted checks and documentation commits remain distinct from measured runtime head `5c32395`. No model edit, solver, production code, new PR, merge, release or multiprocessing is included.

Artifact hashes use canonical UTF-8 text with LF line endings, so Windows checkout line endings do not invalidate the receipt. The six measured-runtime hosted workflows are terminal successes; IDs are in validation.json. No new runtime/head CI claim is made for subsequent documentation commits.
