# Batch-aware deferred dependency resolution — PR #5 scope

Status: **implementation in progress; first batch API and per-run memoisation implemented, full shared-graph compilation outstanding**. This is a stacked development PR against PyTUFLOW PR #2 (branch `feat/deferred-parity-database-kinds`), which itself targets PR #1. No merge, release, or change to the published PyTUFLOW package is authorised.

## Purpose and ownership

Optimise many TUFLOW event/scenario contexts derived from **one parsed TCF** without repeating identical command expansion, scope evaluation and dependency-reference construction. Keep full supported-input eager/deferred-then-materialised parity and the existing public eager mode. The ryan-tools PR stacked on #143 owns physical filesystem/GIS materialisation and user-facing preflight integration; do **not** duplicate that implementation here.

Current downstream same-fork local SSD observation (single ordered pair, not a performance guarantee): 240-run Model B eager contexts 52.482 s, deferred contexts 41.835 s, final shared inventory ~0.029 s. Context resolution is the principal opportunity. PR #143 also has earlier 440-run network-drive baseline; do not compare unlike storage/modes as a validated improvement.

## Baseline and dependencies

- PR #1: `feat/deferred-file-resolution` (syntax-only per-context file references and explicit deferred secondary database inspection).
- PR #2: `feat/deferred-parity-database-kinds` (database roles, rainfall grids, GIS table-link/raster metadata markers, ownership and external-source semantics).
- PR #5 (this branch): `feat/batch-dependency-context-cache`, initially based on #2's exact head. Rebase/merge from #2 while it evolves.
- New downstream ryan-tools PR: `feat/tuflow-batch-preflight-optimisation`, based on PR #143's `feat/tuflow-run-preflight`; it consumes the eventual public batch API.

## Deliverable A — profile and define a correctness baseline

1. Add narrowly scoped instrumentation for initial TCF parse, control-file traversal, `Context` and `InputRunState` construction, variable/scope evaluation, command reconstruction, cached database-row projection, and creation of immutable `FileReference` records.
2. Count actual glob/stat/scandir/GPKG/SQLite/file-open operations, command evaluations, cache hits/misses, unique signatures, and peak RSS where measurable. Separate Python CPU/allocations from storage/GIS work.
3. Benchmark synthetic batches of 1, 50, 240, 440 and 500 runs using a single TCF, plus realistic TCF trees. Use the same source, same fork SHA, same storage, same flags and three warm-cache trials for mode comparisons. Capture local SSD and Windows network-share evidence separately.
4. Build an exact, unordered but provenance-preserving dependency identity contract: run flags, owning control file and source command/line, lexical path expression, materialised physical path, layer selector, database role/row and secondary source. Compare missing **and** extra items; distinguish errors, unresolved and supported valid inputs.

## Deliverable B — immutable dependency plan

1. Compile the initial parsed TCF and cached nested TGC/TBC/ECF/TEF/TRD/ADCF control trees into an immutable, reusable *dependency plan*. Keep original ownership, ordering and source line metadata.
2. Track the actual free variables used by each command and by its conditional scopes, including *transitive* dependencies introduced by `Set Variable` and TEF event substitutions. Include negative/else scope rules, nested conditions and ordering-sensitive assignments.
3. Separate static commands (zero relevant variables) from context-dependent ones. Avoid allocating mutable input/run-state objects when the compiled reference expression suffices.
4. Preserve the existing `context(..., file_resolution="eager"|"deferred")` API. Add a new **opt-in batch API**; provisional shape:
   ```python
   tcf = TCF(tcf_path)
   batch = tcf.collect_batch_dependencies(run_flags)
   for run in batch.runs:
       references = run.file_references
   ```
   The exact naming and return types must be finalised against current PyTUFLOW architecture before committing an external API. Return structured per-run provenance, issue/error states and aggregate counters, not flattened paths only.
5. Keep the existing single-context API working and retain a usable non-batch path for correctness comparisons.

## Deliverable C — context-sensitive memoisation

1. Cache only *immutable* compiled expressions and context-independent results. Never share mutable `RunState`, command `config`, variable maps, DataFrames or active-context state across runs.
2. For each command, derive the memoisation signature from **all semantically relevant values**: event/scenario scope matches, ordered variable assignments, TEF variables, nested owner context, relevant database row selection and any external mode switches. Equivalent irrelevant flags must not force reevaluation; different relevant assignments must not collide.
3. Compile the signature conservatively: if variable provenance, conditional effects, path rules or dynamic state cannot be proven safe, evaluate normally and mark a cache bypass. Do not silently skip a dependency.
4. Reuse static path templates, parsed database rows, event selectors and source classification in memory within one batch only. Track memory growth; bound cache entries or offer deterministic bypass when memory becomes excessive. Do **not** persist a cross-run disk cache or cache raster contents in this PR.
5. A fresh TCF load must observe changed project files. Mutating a loaded `TCF`/build state must invalidate its compiled plan; if safe invalidation is not feasible, document and enforce a fresh-plan boundary.
6. Preserve lexical `..` and mapped-drive/UNC path semantics. Do not canonicalise source path strings as a global cache key, follow junctions inadvertently or use `Path.resolve()` to rewrite user-facing references.
7. Preserve deferred semantics: after initial parsing, creating/using the batch's syntactic references must not perform file probing, GIS reading, SQLite queries or rasters reads. Explicit database projection may use only already-parsed cached data; unsupported requirements remain marked unresolved.

## Deliverable D — parity, compatibility and safety tests

- Compare batch results with repeated individual **deferred** contexts and eager-then-materialised identities, including originating file/command, flags, layer names and secondary dependencies. A matching pair of incomplete inventories is not a pass.
- Test static paths, shared TGC, variables inherited from TEF, different `e1`–`e5`/`s1`–`s4` combinations, missing/nonexistent flags, nested/negative/else scopes, multiple active databases, duplicate command values, and mutable model edits.
- Test wildcard patterns, literal paths, `>> all` and implicit GeoPackage layers; GIS table links, Shapefile/GPKG network and pit fields, AD BC/AD Global, BC/materials/soils, XS, rainfall CSV and NetCDF/raster metadata markers.
- Test valid output-only `Set Variable` expressions (including nested output paths) without treating assignments as missing inputs; preserve real READ consumers of those variables.
- Instrument a 500-run synthetic batch to prove that shared static references are compiled/evaluated once per semantic signature, not 500 times. Assert conservative bypass for unknown semantics.
- Run complete existing PyTUFLOW parser/context tests and focussed fork feature tests. Downstream owns the end-to-end 161 TCF/174-run example replay and 42/240/440-run native regression datasets; cross-link exact SHAs and result artifacts.
- On malformed/unsupported data, report unresolved, do not invent missing files or classify unknown sources as output. Do not execute TUFLOW or mutate the source project.

## Deliverable E — performance evidence and documentation

- Report median/range for parse, compilation, per-run evaluation, database projection, downstream GIS/FS inspection, issue routing, total elapsed and peak RSS, **each independently**.
- Provide per-stage operation and cache counters, including `unique_dependency_signatures`, `commands_evaluated`, `cache_hits` and `fallbacks`; avoid misleading aggregate claims when a phase is omitted.
- Compare exact 240/440/500-run flags and dependency coverage with existing deferred and eager reference pathways. Benchmark three warm-cache trials per mode per storage location. Network results are not interchangeable with local SSD results.
- The target is a measurable, material reduction in context-evaluation work/time on shared-TCF batches without increased per-run file operations or materially worse memory usage. Set the quantitative gate **after** the profiler identifies the bottleneck; do not promise a specific multiple before measurement.
- Add public API documentation and an isolated microbenchmark runnable without the TUFLOW executable or proprietary project data.

## PR acceptance and merge order

1. #1/#2 parity fixes must be incorporated; #5 is not a vehicle for suppressing their outstanding correctness findings.
2. All synthetically supported cases pass exact identity parity, no silent omissions/extras, and existing eager single-context behaviour remains unchanged.
3. New batch API is opt-in, side-effect free after parse (outside explicitly requested cached database projection), typed/documented and benchmarked against repeated individual contexts.
4. Full downstream regression parity and benchmark evidence are linked from the consumer PR before that consumer switches behaviour.
5. Merge #2 into #1; retarget #5 to #1. After merging #1 into `master`, retarget #5 to `master`. Do not delete a base branch before moving #5. No automatic merge/publication.

## Out of scope

- New TUFLOW command semantics beyond parity fixes owned by #1/#2; TUFLOW executable `-x` checks; executing simulations.
- Persistent caches, distributed model scanning, multiprocessing/parallel SQLite readers or speculative filesystem prefetched state.
- Changes to ryan-tools launch defaults, installer, wheel dependency or PyPI version.
- A replacement of PyTUFLOW with an independent TUFLOW parser.

## Current handoff

Only this implementation scope exists in #5 initially. Next action: implement stage A and an identity-equivalence harness, then add the immutable plan and batch API incrementally. Source branch will track #2; review and validation must always name exact head SHA.

## 22 October implementation checkpoint

**Implementation committed on the stacked #5 branch:**

- Added `pytuflow/_tmf/batch_dependencies.py` with an opt-in `TCF.collect_batch_dependencies(..., cache_scopes=True)` public facade, immutable per-run projections, per-run parse/resolve failures, and measured construction/cache counters.
- `BatchContext` caches available scopes, scope decisions by retained object identity and context-translated values **within one run**. Cache invalidation on `load_context_from_dict`, `load_events` and `load_variables` prevents stale TEF/variable substitutions. Default `TCF.context()` remains eager and unmodified.
- Identical **full flag strings** reuse already-projected immutable references during a single batch, retaining distinct requested-run indices. Contexts with distinct flags are **still evaluated individually**; a 500-run alternating-two-flag benchmark would therefore be misleading as evidence of cross-run dependency compilation.
- `deferred_database_activations()` and `deferred_database_sources_for_activation(uuid)` preserve database-declaration ownership; batch source projections are candidate rows, **not** authorisation to union all rows from multiple BC databases.
- Added focused parity, invalid flag, cache invalidation, probe-free, duplicate/unique event flag and 500-run synthetic tests plus a separate comparable distinct-500-flags manual benchmark harness.
- Windows Python 3.12/3.14 deferred CI [run 39661657613](https://github.com/phantom-branch/PyTuflow/actions/runs/39661657613) passed on commit `f85cd9c`. Exact-head CI including added unique-event regression and distinct-run benchmark must still complete before using the data as evidence.

**Still missing:** a compiled immutable dependency graph, transitive relevant-flag signatures, reuse of static command-reference expansion **across different runs**, benchmark profiles on representative 240/440/500 combinations and 174-run materialised GIS/database/raster parity. No speedup or feature-parity sign-off, no downstream dependency repin, no merge or release.

The next action is to inspect the distinct-run benchmark output and profile the hot paths, then implement conservative cross-run command-level memoisation. If a command's dynamic scope, variable lineage or database activation cannot be proven safe, bypass caching rather than risk incomplete dependencies. Keep the upstream #2 branch synchronised without overwriting concurrent agent changes.


### First comparable distinct-flag measurement (Windows CI)

[Run 39662149567](https://github.com/phantom-branch/PyTuflow/actions/runs/39662149567) on commit `97c03a3` passed Windows Python 3.12/3.14 focused and existing context tests. The Python 3.14 manual benchmark used 500 **distinct** event-flag strings, 3 warm-cache trials, one parsed temporary TCF and identical syntactic dependency/provenance outputs across all modes:

| Mode | Median contexts (s) | Trials (s) |
| --- | ---: | --- |
| Individual deferred | 4.839097 | 4.832053, 4.853546, 4.839097 |
| Batch without caching | 4.845993 | 4.845993, 4.820860, 4.852573 |
| Batch with per-run caching | 4.839513 | 4.799496, 4.839513, 4.862291 |

The cached batch constructed **500 contexts**, reused **zero** complete-run signatures, built 500 available-scope views, reused 1,250 scope views, hit 14,500 translations and missed 1,500. **No meaningful speedup was observed.** This benchmark deliberately excludes initial parse, physical file/GIS checking, network drives and any TUFLOW executable; it is **not** end-to-end preflight performance evidence.

After this measurement, a separate commit precomputed the immutable list of `Set Variable` build-state declarations once per batch, re-evaluating each declaration's scope/value for every distinct run. Exact-head CI and comparable benchmark are required to establish any improvement from this change.

**Engineering conclusion:** context-local memoisation is insufficient; next implement cross-run immutable compiled command/dependency representations and relevant-flag signatures, not another round of file `stat` micro-optimisation. Preserve old single-context methods and conservative fallback for unsupported dynamic syntax.


### Follow-up cross-run variable-inventory optimisation checkpoint

After the first benchmark, `BatchContext` was supplied with the parsed `Set Variable` build-state declaration list once per batch. `ControlFileRunState` uses that list instead of traversing the same TCF control tree for every context; every scenario's active declarations and substitution values are still individually evaluated. New tests assert one declaration traversal for twelve distinct flag combinations and exact cached/uncached dependency identity.

[Windows CI 39662701759](https://github.com/phantom-branch/PyTuflow/actions/runs/39662701759) passed Python 3.12 and 3.14, including the added variable-scope regression. The 500-distinct-flag synthetic benchmark remained exactly equal across modes (zero missing/extra references); medians were individual **4.8233 s**, batch without caching **4.9150 s**, cached batch **4.8025 s**. The ~0.4% nominal cached-versus-individual difference is too small to establish a meaningful speedup, and the synthetic benchmark TCF contains **no Set Variable declarations**, so it does not measure the new traversal optimisation.

Before claiming faster real-world batches, add a benchmark fixture containing substantial nested control files and scenario/event-dependent variable declarations; then implement cross-run immutable command compilation. Maintain parity first and do not promote the code to ryan-tools #148 just to report an inconclusive timing.


## 22 October subsequent checkpoint — initial cross-run benefit and CPU profile

**Branch dependency:** PyTUFLOW PR #2 has now merged into #1; this optimisation PR #5 targets #1's `feat/deferred-file-resolution` branch. No changes are merged into `master`, and no publication is authorised. Python Windows 3.12/3.14 validation only; Linux parity is deliberately deferred to separate PR #4.

**Implemented:** batch-scoped reuse of immutable file references from literal inputs (not unresolved placeholders/TEF tokens), cross-event reuse of decisions depending exclusively on scenario scopes, once-per-batch parse of immutable Set Variable name/value templates, and UUID/command-index/owner/line metadata in `BatchInputReference`. Event-scoped, dynamically translated and unknown commands still use ordinary per-context resolution. The default `TCF.context()` path is unchanged.

**Verified synthetic workload at commit `ce1286008`:** [Windows CI 39708797831](https://github.com/phantom-branch/PyTuflow/actions/runs/39708797831) passed both matrix jobs, and Python 3.14 produced these **three warm-cache** medians (identical syntactic references and database activation records in all modes):

| Workload | Individual deferred | Cached batch | Change |
| --- | ---: | ---: | ---: |
| 500 distinct event-flag strings; 2 shared scenario branches | 2.3273 s | 1.2271 s | approximately 47% lower |
| 120 distinct event flags and 20 additional static GIS READ commands | 4.0646 s | 2.2282 s | approximately 45% lower |

Counts for first fixture: 500 distinct contexts constructed; **0 whole-run reuse**, 1,992 cross-run scope hits, 4,496 cross-run reference hits, 8 scope misses and 4 reference misses. These measurements cover **syntactic dependency collection only**, excluding initial parse, filesystem/GIS/raster materialisation, real project data and the network drive. Do not extrapolate to a 440/500-run production speedup without exact materialised parity and real-model timings.

**Profile:** [Windows CI 39709059027](https://github.com/phantom-branch/PyTuflow/actions/runs/39709059027) passed and ran cProfile with 120 distinct runs/20 extra static READs. The top overlapping cumulative hotspots were `TCF.context` (~25.15 profiled seconds across all benchmark modes), `InputRunState` (~24.49), `Command.__init__` (~19.27), `Command.parts` (~15.17), `InputBuildState.file_references` (~11.58) and `from_config` (~8.09). Cumulative values overlap and are not separately additive. This supports further reductions in redundant parsing/config copies rather than directory stat tuning.

**Current further work:** A narrow batch-only short circuit avoids `Command.reload_value()` for plain commands already expanded in `Command.__init__`, excluding EventCommand and any non-empty DEFINE blocks. Await the **exact-head** Windows regression and benchmark outcome before attributing any additional improvement to this change. New tests cover duplicate path UUID provenance, nested TGC owner/line metadata, invalid-context fail-closed clearing and dynamic event source separation.

**Outstanding high-priority gates:** Exact eager/deferred/batch materialised parity for all valid supported inputs (including GIS attributes, active database rows, rainfall and raster metadata) remains owned by #1/#143. #5 still constructs one mutable context for each distinct complete flag combination: it does **not yet** compile a complete immutable cross-run dependency graph, skip all unchanged command constructors or provide end-to-end speedup evidence. The downstream ryan-tools #148 remains a separate draft, not merged into #143 or main.


## 22 October continuation — resolved-reference signature and master sync

After PR #1 merged into `master`, this branch was reconciled with its final
merge commit; the six files added/changed upstream since the earlier development
merge were verified to have **identical Git blob SHAs** in the batch branch.
The merge synchronised ancestry without changing those file contents. PR #5
now directly targets `master` and is kept **draft**.

The opt-in cache now additionally supports fully resolved variable-derived READ
commands **when the originating build input, expanded command text, owner,
parts and relevant file/GIS configuration are identical**. The cache is bounded
to 10,000 distinct resolved signatures per batch. Dynamic or incompletely
resolved cases, DEFINE/EventCommand specialisations, unresolved event wildcards
and unproven translations bypass caching and use the existing resolver.

The result distinguishes genuine cross-run reference hits from repeated
accesses within the same run and exposes
`cross_run_reference_bypasses`, `unique_reference_signatures` and
`within_run_reference_hits`. These counts describe syntactic reference
projection only. No immutable run states or filesystem/GIS content are cached.
A new collection call constructs a new cache; edited build-state commands
cannot accidentally reuse results from an earlier call.

New regression cases compare cached and uncached projections for scenario
variables under distinct event flags, variable-derived GeoPackage layer names,
distinct event-dependent file names and a subsequently edited loaded TCF.
The latest Windows Python 3.12/3.14 jobs and complete example-model parity
must pass before any acceptance or speedup claims for this work. Historical
benchmark results in this document were recorded on earlier commits and do
**not** measure the new cache or represent end-to-end performance.

**Still outstanding:** compile the complete immutable cross-run dependency
graph, including proven transitive variable/scope signatures; instrument
command evaluation and bypass counts; obtain three-trial representative
same-drive timing and exact materialised preflight parity on the new head
through ryan-tools #148. Linux remains separate PR #4. No release, merge,
consumer default switch or solver execution is part of this work.

### Phase instrumentation and safe GIS fallback

The batch result now reports measured one-time variable/declaration
`compilation_seconds`, `context_construction_seconds`,
`reference_collection_seconds` and `database_projection_seconds`,
as well as `commands_constructed` (actual batch command reconstructions).
The isolated benchmark emits three-trial median and individual phase samples,
including cache misses, safe bypasses, genuine cross-run hits and
within-run reference accessor hits. These phases are not comprehensive OS/GIS
operation counts and do not include downstream physical inspection.

In regression testing, a variable-derived GeoPackage layer did not satisfy
the conservative signature eligibility guard. It correctly uses the original
deferred resolver. The test now requires exact cached-versus-uncached
provenance and asserts the bypass instead of forcing an unsafe memoisation.
This is an intentional correctness boundary, **not** a completed GPKG
layer-signature optimiser.

The full immutable dependency graph and any elimination of redundant
`InputRunState`/`Command` allocations remain outstanding; the new command
counter explicitly measures this cost. Windows exact-head validation and
materialised parity must be checked before final review.

### Literal command template compilation — further development

An additional **batch-only** compiled-command pathway now avoids constructing
a full `Command` parser object on every run for the same proven-literal
`READ GIS ...` or `READ GRID ...` input. The first eligible evaluation
creates a normal deferred `Command` and retains a private prototype under a
per-batch signature comprising input identity, expanded command text, parent,
part/line provenance and relevant GIS/grid/control-file settings. Subsequent
equivalent evaluations create an independent shallow copy with a **fresh
configuration snapshot and expander**. A prototype is never directly returned.
This is a limited *command-template cache*, **not yet a compiled dependency
graph** and not a means of sharing mutable run-state objects.

Eligibility intentionally excludes EventCommand or other specialisations,
variable-substituted expressions, DEFINE blocks, event wildcards, GeoPackage
`>>` expressions, and other cases whose semantics are not proven static.
These use the established constructor. Command-template entries are bounded
to 10,000 per invocation; all caches are discarded after
`collect_batch_dependencies` returns. A second invocation after editing the
loaded build state therefore starts fresh. Existing eager and individual
deferred contexts are unchanged.

Added batch counters:

- `commands_constructed`: normal command constructors executed along the
  opt-in batch path, including bypassed commands.
- `commands_cloned`: template-copy operations replacing eligible constructors.
- `command_template_bypasses`: commands not eligible, or excluded by capacity.
- `unique_command_templates`: retained prototype count.

Regression coverage verifies cached-versus-uncached immutable dependency
identities, retained input UUID/owner/command order, independent per-run
mutable command/config/expander state, safe fallback for event-dependent
paths and absence of stat/glob/open probes after initial parse.

**Acceptance:** record current-head Windows 3.12/3.14 CI and strict
161-TCF/174-run read-only example parity before claiming validation. Compare
three alternating warm-cache trials of the same workloads on the same runner;
these are parser/reference timings only, not native 240/440/500-run or network
drive performance. An immutable graph with transitive context/variable
signatures and elimination of input run-state allocation remain unimplemented.


### Immutable Set Variable lineage — staged dependency graph

Further work compiles a per-batch **immutable variable-dependency graph** from
the already parsed `Set Variable` declarations. Each name collects edges
from **all** its possible scenario/event-scoped declarations; this is a
conservative union, not a claim that every declaration is active. The
bottom-up safe set excludes cycles, unknown names, reserved scenario/event
flag slots, malformed placeholders, `~` wildcards and GeoPackage `>>`
syntax. A READ command's immutable node captures direct and **transitive**
variable names. Read nodes are compiled once per parsed input, retained with
input identity, and not shared with subsequent batch calls.

During each run, the original `Context` still evaluates scopes, applies
ordered variable assignments and expands the command. A compiled READ may
reuse a private command template only if **all** relevant variables have
ordinary string values, the translated command is fully resolved and
idempotent, and its signature matches the previously evaluated input,
command, control-file/GIS settings and **relevant values**. Irrelevant event
flags do not enter that signature. Different actual transitive values cannot
collide. Scope evaluation, database activation selection and provenance are
not elided. Malformed, cyclic and ambiguous cases use existing deferred
resolution instead of emitting guessed references.

New independent tests verify graph immutability, multiple declarations,
transitive scenario-dependent paths, unknown names, cyclic assignments,
event wildcards and GeoPackage syntax, and exact cached/uncached input
provenance. A separate synthetic benchmark exercises 120 distinct event
contexts with eight variable-derived READs using three alternating warm-cache
trials. It compares complete syntactic results before reporting timings.

Additional counters include `compiled_variable_nodes`,
`compiled_read_nodes`, `command_plan_hits` and
`variable_template_clones`. All plans and command templates live only
inside one synchronous `collect_batch_dependencies` call; re-invocation
after a model edit compiles a fresh plan. **Modifying the model during one
collection call is unsupported.**

This is a **partial immutable dependency DAG**, not the complete parsed
control-tree / event / GIS / database graph specified by deliverable B.
Inputs with side effects, uncertain context provenance and secondary GIS
dependencies remain handled by the original run-state and downstream
materialisation paths. The current-head Windows CI, strict 174-run replay,
and new variable-heavy timing must be verified before signing off. No
merger, publication, production repin, or solver execution is authorised.


### Native downstream evaluation checkpoint - 22 October 2026

Parser source `b1c9cfd4712b2ee7a7bd35ef0ec7ca32c9de6b92` passes the affected local
218-test regression selection and both exact-head Windows workflows:
[deferred references](https://github.com/phantom-branch/PyTuflow/actions/runs/39788800172)
and [strict example replay](https://github.com/phantom-branch/PyTuflow/actions/runs/39788800177).
The downstream diagnostic at `4ad6f1407e9ecf44a4c61bd3dc230520cf6ac58a` also passes
its exact-source local strict 161-TCF / 174-run eager/deferred/batch materialisation
comparison and the dedicated hosted batch smoke.

Native SSD and SMB three-mode rechecks are in progress. The larger SMB launcher
was read without execution: its requested parameter product has 792 combinations,
rather than the active text-file mode's 14 commands. A separate read-only PO-source
existence check finds 787/792 expected files absent, affecting both catchments.
Keep these input-data findings separate from parser defects and do not claim an
accepted overall speedup for that incomplete workload. Private model paths and
reports remain outside either repository.

This revision excludes output/check/log folder destinations from required-input
validation, matching existing eager behaviour, and selects a contextual cached
source table under one primary declaration without new filesystem reads. The
latter repairs the new shared source-inspection API for eager callers too; it is
not an original eager `.files` fix. See `eager_source_completeness_fixes.md` for the
separate compatibility account. The owner's two-BC-declaration investigation is
explicitly deferred. Repeated run-state construction remains; the broader
immutable control-file graph is future work, not part of these compatibility fixes.


### Replacement native model and existing eager fixes

The owner replaced the incomplete 792-combination model with a saved 480-command
model on local SSD, then copied that model to an SMB share for matched-storage
comparison. The command-file bytes and all 480 parsed flag dictionaries match.
The owner intentionally omitted unrelated files; acceptance uses the required-input
inventory, not equality of project directory contents. Large binaries are size-checked,
not claimed byte-hashed. Detailed manifests and model identifiers remain private.

Source `a9f654c1ec0812fc70035e227fb2f9f12290f449` separately repairs existing slot-nine
conditional scopes and material CSV separator/comment handling. Both are original
eager/shared behaviour fixes, explicitly separated from deferred functionality in
`eager_source_completeness_fixes.md`. The affected local selection passes 223 tests;
exact-head deferred reference and strict archive workflows both pass:
[reference CI](https://github.com/phantom-branch/PyTuflow/actions/runs/39791230176),
[archive CI](https://github.com/phantom-branch/PyTuflow/actions/runs/39791230068).
The replacement model passes the representative eager/deferred/batch materialisation
and matching public inventory checks with no findings. Full trials are in progress.


## Interim native benchmark results (2026-10-22)

PyTUFLOW **1.2.6**, source `a9f654c1ec0812fc70035e227fb2f9f12290f449`; consumer diagnostic
`2e03c0b110a272d9c6a05cc6da3bc08817130164`, Windows Python 3.14. Three sequential warm-cache
trials per model, rotating eager/deferred/batch order. The 480-run local and SMB tests use identical saved
command-file bytes and flags. The owner intentionally removed irrelevant files from the network copy.

| Model | Storage | Runs | Eager median, s | Deferred median, s | Batch median, s |
| --- | --- | ---: | ---: | ---: | ---: |
| P | SSD | 4 | 1.234 | 0.852 | 0.688 |
| B | SSD | 240 | 62.640 | 40.876 | 26.285 |
| M480 | SSD | 480 | 118.843 | 65.007 | 45.223 |
| M480 | SMB | 480 | 229.062 | 91.844 | 70.014 |

All listed full trials have identical materialised `(run, flags, normalised command, physical path, layer)`
sets across modes and **zero collection/inventory findings**. P/B and M480 SSD also pass the separate full
public individual/batch preflight with matching checked paths and issue sets. **Still running:** M480 SMB's
final public comparison, followed by the newly supplied 42-command network model. Do not describe those
pending gates as passed.

Timings include parsing, reference materialisation, diagnostic physical-path identity normalisation and
shared inventory. They exclude process startup, report writing and the separately repeated public-preflight
comparison (which validates raster headers). These are diagnostic timings, not complete launcher wall times.
No native data or identifying P/B paths are committed; no model simulation is launched.

Source fixes are split explicitly: `a9f654c` repairs existing eager/shared ninth-slot conditional scopes and
materials CSV blank/comment loading; `b1c9cfd` repairs the new shared cached-source accessor (including eager
callers) and deferred/batch output-folder compatibility. The UNC/mapped-drive inventory fix is diagnostic-only.
The affected upstream selection passes **223 tests**; dedicated consumer checks pass **59 deferred + 9
batch/diagnostic tests** and strict **161-TCF / 174-run** replay. The general Python workflow separately fails
one Nmx snapshot column-axis pandas StringDtype comparison (`<NA>` versus `nan`); do not claim all CI green.

Batch still constructs one context per run (480 for M480). The broader immutable control-file graph remains
future optimisation. The owner explicitly deferred the two-BC model. The incomplete 792-run model was replaced;
its direct expected PO-file existence check found GD08 393/396 and GD14 394/396 absent, not a valid benchmark.

The consumer work record is the authoritative native-evaluation status:
https://github.com/Chain-Frost/ryan-tools/blob/feat/tuflow-run-preflight/docs/work/2026-10-22-tuflow-batch-preflight-optimisation.md


## Final native benchmark results (2026-10-22)

All supplied native workloads pass **three full rotated trials**, with zero missing/unresolved input findings,
identical eager/deferred/batch materialised identity sets, and matching successful public individual/batch
checked-path and issue sets. The 480-run network copy retains all inputs needed by this benchmark after the
owner's removal of irrelevant files. No TUFLOW simulation was launched.

PyTUFLOW **1.2.6**, parser source `a9f654c1ec0812fc70035e227fb2f9f12290f449`; consumer diagnostic
`2e03c0b110a272d9c6a05cc6da3bc08817130164`. Windows Python 3.14. Model names P/B and all native paths
remain private. The M480 command-file bytes and 480 flag dictionaries match between SSD and SMB copies.

| Model | Storage | Runs | Eager median (min-max), s | Deferred median (min-max), s | Batch median (min-max), s |
| --- | --- | ---: | ---: | ---: | ---: |
| P | SSD | 4 | 1.234 (1.229-1.264) | 0.852 (0.847-0.887) | 0.688 (0.685-0.689) |
| B | SSD | 240 | 62.640 (62.504-66.919) | 40.876 (40.779-44.050) | 26.285 (25.781-26.549) |
| M480 | SSD | 480 | 118.843 (114.569-122.171) | 65.007 (64.672-67.559) | 45.223 (43.873-45.557) |
| M480 | SMB | 480 | 229.062 (228.122-230.345) | 91.844 (90.437-96.858) | 70.014 (69.540-71.085) |
| N42 | SMB | 42 | 80.892 (80.308-82.257) | 40.232 (39.470-43.397) | 16.818 (16.817-19.501) |

For M480, batch reduces diagnostic elapsed time versus individual deferred by **30.4% on SSD** and **23.8%
on SMB**. Network elapsed remains higher in every mode. These are sequential warm-cache observations,
not cold-cache guarantees. Each repeat rotates mode order; no timed model workloads run concurrently.

Timings include fresh parsing, reference materialisation, physical-identity normalisation and shared inventory.
They exclude process startup, report writing and the separate public-preflight replay (including raster-header
validation). They are **diagnostic timings**, not complete launcher wall times. Native identity keys compare
`(run index, flags, normalised command, physical path, layer)`; upstream UUID/control-line provenance has
separate synthetic cached/uncached tests. Required-input inventory, not equality of all project files, gates
acceptance. Large copied binaries were size-checked, not exhaustively byte-hashed.

M480 retains **12,480 compared identities / 49 distinct physical paths** per copy in every mode;
N42 retains **1,922 identities / 196 paths**. Median timing phases for the matched 480-run copies:

| Storage / mode | Parse, s | Context or batch call, s | Remaining materialisation/identity/inventory, s |
| --- | ---: | ---: | ---: |
| SSD / eager | 0.572 | 95.865 | 22.406 |
| SSD / deferred | 0.556 | 56.850 | 7.601 |
| SSD / batch | 0.560 | 43.708 | 0.928 |
| SMB / eager | 0.701 | 181.811 | 46.741 |
| SMB / deferred | 0.716 | 58.676 | 32.458 |
| SMB / batch | 0.710 | 43.595 | 25.946 |

Column medians are computed separately and need not sum to the median total. Last-trial M480 eager-context
audit counts are 6,253 SQLite connects, 13,454 glob events and 1,440 scandir events in each storage case;
individual deferred contexts and the batch call record none of these selected events. This does not measure
all native I/O: in particular, physical path identity normalisation remains in the residual diagnostic phase,
which is noticeably more expensive on SMB. Do not misattribute that entire residual to the production parser.

### Accounting and limits

Process RSS is sampled every 20 ms with GC between modes; it includes native allocations but is not an exact
peak or an isolated allocator regression proof. Maximum sampled RSS across the three full trials:

| Model / storage | Eager MiB | Deferred MiB | Batch MiB |
| --- | ---: | ---: | ---: |
| P / SSD | 263.4 | 263.4 | 263.4 |
| B / SSD | 332.7 | 331.2 | 332.1 |
| M480 / SSD | 344.3 | 341.9 | 341.5 |
| M480 / SMB | 342.1 | 339.5 | 341.0 |
| N42 / SMB | 353.1 | 353.7 | 350.4 |

The M480 SSD last batch trial still constructs **480 contexts / 28,327 commands**, reusing 3,353 command
templates. Its 43.708 s batch call includes 34.597 s context construction, 2.936 s reference collection and
4.480 s database projection. A broader immutable control-file graph remains future optimisation, not work
completed by this evaluation. Phase categories differ across modes; individual database projection is part
of residual collection, whereas batch projection is inside the batch call. Python audit events count selected
open/directory/SQLite/glob calls, not all native/stat I/O; retain independent no-I/O spy tests.

### Delivery and remaining scope

- Parser source a9f654c passes 223 affected local tests, exact-head reference CI and strict archive CI.
  Consumer code 2e03c0b passes **68 focused local tests** against a9f654c with both real fork integration
  gates enabled. Hosted batch smoke passes 9 tests and strict 161-TCF / 174-run three-mode replay on a9f654c.
  The earlier hosted 59-test dedicated deferred job used its older 8e7bc30 pin; that workflow is now aligned
  to a9f654c as well. Its new hosted result must be checked separately rather than attributing the old green
  result to the new parser revision.
- Existing eager/shared fixes are recorded separately upstream: ninth-slot conditional scopes and materials
  CSV blank/comment loading (a9f654c). New shared cached-source accessor repair, deferred/batch output-folder
  compatibility (b1c9cfd), and diagnostic mapped-drive SQLite handling remain separately identified.
- The replaced 792-run workload is not accepted: direct PO-file existence checks found GD08 393/396 and
  GD14 394/396 absent. This is not a reason to suppress findings or silently skip both catchments.
- N42 here is the newly supplied 42-command network benchmark. It does not reinstate the withdrawn external
  42-run gate. The historical external 440-run evidence is revision-specific and was not rerun on this machine.
- The owner explicitly postponed the two-BC-model investigation. No new two-BC functionality is claimed.
- General Python CI separately fails the Nmx snapshot column-axis StringDtype NA-value comparison
  (`<NA>` versus `nan`): 1380 passed, 6 skipped, 7 deselected, one failure on source 2e03c0b.
  Dedicated parser checks are green; the whole PR is not all-checks-green or ready for automatic merge.
- No solver run, default-on switch, production dependency repin, merge or release. Raw native data and reports
  remain outside Git; only anonymised findings and benchmark information are published.


### Benchmark revision boundary after publication

Concurrent follow-up commits `37a69b3` (host filesystem case handling for cached database paths) and
`f3325b8` (POSIX case-sensitive selection regressions) landed in PyTUFLOW during publication and are
preserved. **The native benchmark evidence above is for a9f654c, not those later source changes.**
All five recorded native source snapshots match retained a9f654c Git contents with normal checkout
LF/CRLF conversion accounted for. A retained a9f654c source extraction independently passes all 68
focused consumer tests with both real-fork gates enabled. The later case-handling source was not rerun
through the native performance matrix. Benchmark figures must remain associated with their recorded
source rather than being relabelled as current branch-head timings.
