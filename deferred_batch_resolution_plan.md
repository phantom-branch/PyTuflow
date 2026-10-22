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
