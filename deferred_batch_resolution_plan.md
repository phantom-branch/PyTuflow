# Batch-aware deferred dependency resolution — PR #5 scope

Status: **scoped, not implemented**. This is a stacked development PR against PyTUFLOW PR #2 (branch `feat/deferred-parity-database-kinds`), which itself targets PR #1. No merge, release, or change to the published PyTUFLOW package is authorised.

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
