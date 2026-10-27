# Optional TUFLOW input validation — ownership and migration contract

**Status:** draft design and implementation handoff; no production validator is enabled by this document.

**Integration prerequisite:** the #42 → #41 → #39 performance/correctness stack must be merged into this fork's `master` and its exact merged head recorded before implementing the validator. This proposal is **not** part of the completed performance PR and must not change its behaviour.

## Goal and ownership

PyTUFLOW should be the authoritative library for **interpreting and optionally validating TUFLOW source-file requirements**. The current ryan-tools implementation duplicates TUFLOW-specific existence, wildcard, GeoPackage layer and BC CSV header logic. Move those checks behind a separately invoked PyTUFLOW validator, then migrate the consumer after the library API is accepted.

| PyTUFLOW owns | ryan-tools owns |
| --- | --- |
| Parse TCF/TGC/TBC/ECF/TEF and related control files | BAT/CMD parsing, exact ordered run lists and multi-TCF grouping |
| Resolve event/scenario/variable substitutions, included files and active BC source ownership | Decide when to run preflight, CLI options, run scheduling and solver launch |
| Return immutable per-run syntactic source references and CSV selector requirements | Orchestrate repeated project checks and human-facing report/issue routing |
| Optionally check source file existence and file-vs-directory status | Choose resource limits, logging, reporting format and failure policy |
| Optionally expand TUFLOW-aware wildcards and inspect GeoPackage layers | Integrate with workflows, consumer version detection and user documentation |
| Optionally validate ordinary BC CSV Source headers against resolved Time/Value selectors | Use structured findings; no duplicate TUFLOW-aware parsing/checking once migrated |
| Deduplicate identical physical inspections within a single validation invocation | Coordinate multiple independent model validation invocations |

**Non-negotiable boundary:** `TCF.collect_file_dependencies()`, `collect_batch_dependencies()` and `context(..., file_resolution="deferred")` remain syntactic/read-only reference collection by default. They do not open new GIS/CSV sources, enumerate wildcards or stat every referenced file as an implicit side effect.

## Existing implementations to reconcile

- PyTUFLOW: `pytuflow/_tmf/file_reference.py` (`FileReference`, `DeferredDatabaseSource`, resolved `csv_columns`, scan intent), `deferred_database.py` (active BC row/source interpretation), `tfpathlib/file.py` (`TuflowPath.exists/is_file/glob`), `fragment_dependencies.py` (immutable per-run dependency projection).
- ryan-tools PR #161: `ryan_library/functions/tuflow/dependency_index.py` (stat, bounded directory scans, read-only SQLite `gpkg_contents`, per-invocation deduplication/limited workers), `csv_headers.py` (five-line/1-MiB bounded header search), `input_preflight.py` (run provenance, inventory and reports).
- PyTUFLOW's existing `TuflowPath.exists()` returns a Boolean and may inspect a GeoPackage; it is **not** a drop-in replacement for the richer present/missing/unresolved and bulk-inspection result contract. Preserve existing behaviour until the new validator proves equivalent.

## Provisional public API (not implemented or frozen)

```python
from pytuflow.validation import ValidationOptions, validate_dependencies

dependencies = model.collect_file_dependencies(run_flags)
validated = validate_dependencies(
    dependencies,
    options=ValidationOptions(
        check_files=True,
        check_gpkg_layers=True,
        check_bc_csv_headers=True,
        max_header_lines=5,
        max_header_bytes=1_048_576,
        io_workers=1,
    ),
)
```

The interface is illustrative only. Establish the actual exported module, input types and stable immutable result dataclasses through the first implementation review. It should accept an ordinary or fragment-produced per-run dependency projection without assuming a mutable `Context` or a ryan-tools object.

Each finding should preserve the originating run ordinal, input UUID/command provenance, resolved path/layer, the relevant BC activation/source, `csv_columns` where applicable, and a typed status (at least present, missing, unresolved, unsupported). A common physical result can be shared among contexts without losing per-run ownership and order.

## Inspection semantics

### Physical source files and wildcards

- Stat only sources the active run requires; do not treat output/check/log directories as required input files.
- Distinguish missing paths, directories instead of files, permission/network/format errors and unsupported operations.
- Resolve TUFLOW path and layer representations, relative paths, scenarios/events, wildcard patterns, quoted paths, UNC/mapped-drive spellings and selected include identities before physical validation. Do not recompute scenario selections using a second parser.
- Preserve the TUFLOW Linux filename case-resolution policy where applicable; do not silently replace it with host-specific matching.
- Bound directory entries and avoid recursive scans. Deduplicate per-file/layer checks across all applicable runs; parallelism, if enabled, must have deterministic output ordering and bounded workers.
- Do not interpret wildcard misses or inaccessible sources as successful matches.

### GeoPackage layers

- Open a distinct GeoPackage in read-only mode, once per invocation where possible, and inspect the relevant `gpkg_contents` layer names.
- Check exact layer requirements, `>> all`, wildcard layer names and implicit layer selection against the parser's already resolved `FileReference.layer_pattern`; do not infer the layer solely from a filename.
- Respect error separation: missing file vs present GeoPackage with missing layer vs invalid/unreadable database.
- Do not read GIS features/geometry by default, mutate metadata or require a full QGIS runtime for ordinary GPKG metadata checks.

### Ordinary BC Source CSV column headers

- PyTUFLOW currently resolves Source paths and the two required `Column 1`/`Column 2` selectors. The new validator should determine whether both requested names exist unambiguously in the selected Source CSV header.
- Support BOM, comments, permitted introductory records and multiline CSV records. Detect duplicate/missing selectors and malformed/oversized/unreadable sources. Do not load time-series values.
- The existing ryan-tools **rapid mode** checks at most five physical lines and 1 MiB per unique source; expose this as a named configurable **bounded preflight policy**, not a universal claim that all TUFLOW-valid CSV layouts end within five lines.
- Respect format-specific semantics: FEWS CSV and other nonordinary Source formats, constant BC entries with blank Source, and unsupported selectors must not be incorrectly validated as ordinary two-column CSV sources.
- Header checks are per distinct physical Source path; selector findings are attached to every affected run/activation. A shared CSV can have several different valid or invalid selector pairs.

Official format reference: [TUFLOW Classic/HPC 2026.3 boundary-condition database](https://docs.tuflow.com/classic-hpc/manual/2026.3/07-Boundaries-and-Initial-Conditions.html) and [BC Database command](https://docs.tuflow.com/classic-hpc/manual/2026.3/80-AppendicesA-TCFCommands.html).

## Phased implementation in this new PR

1. **Contract and differential fixtures:** freeze current ryan-tools `check_unique_dependencies`, `read_csv_header` and preflight outputs. Propose typed validation options and results without public breaking changes. Build file/layer/CSV fixtures, error cases and no-I/O-during-projection assertions.
2. **Physical inventory:** implement file/type, wildcard and GPKG layer checks as an explicit, read-only PyTUFLOW API. Prove case/path/permission/error semantics and one physical inspection per unique item.
3. **CSV headers:** add Source CSV bounded header and two-name selector validation; preserve format exclusions and per-run source ownership.
4. **Batch composition:** accept immutable ordinary/deferred/fragment projections, deduplicate safely, retain UUID/order/source provenance, bounded optional workers and stable structured issue records. No TUFLOW solver execution.
5. **Acceptance:** compare complete projected dependencies and validation findings to the existing ryan-tools implementation on representative synthetic and authorised private 480/36/240-context workloads. Confirm independent Python 3.12/3.14 Windows, Linux, installed-wheel and actual consumer behaviour. Measure wall/CPU/memory and physical I/O separately; no profiler-based speed claim.
6. **Separate ryan-tools PR:** after the PyTUFLOW API is accepted, make ryan-tools consume it and remove duplicate TUFLOW-specific inspection code without changing BAT/CMD, runner or report responsibilities.

## Cross-repository rollout and compatibility

The published ryan-tools dependency is currently `pytuflow>=1.2,<2`, and the published PyTUFLOW 1.2.x package does **not** provide the new fragment/validator APIs. ryan-tools PR #161 has a reviewed P1 because its standalone wrapper defaults to the unpublished rapid mode. Preserve the old supported checker as the default or gate the new mode behind explicit capability/version selection until a compatible parser distribution is available. Do not silently fall back after an explicitly requested strict rapid mode.

This phantom fork currently declares Python 3.12–3.14. The separately curated Chain-Frost upstream **PR C** for optional deferred/batch facilities targets Python 3.11 minimum; avoid unnecessary syntax barriers and test both programmes independently. The current fork merge is not an official upstream submission.

## Acceptance gates and exclusions

- Exact ordinary/deferred/fragment dependency/provenance parity; no regression to selected includes, nested BC ownership, transitive variables, TEF substitution, Linux case policy or cache invalidation.
- Read-only model and metadata behaviour, no hidden physical I/O in syntactic collection, no private source material committed.
- Test missing/wrong-type/permission errors, case-sensitive paths, UNC, wildcards, GeoPackage literal/wildcard/all layers, Source CSV BOM/preamble/line limit/malformed/duplicate/missing column names, multiple BC activations and invalid/missing selectors.
- No new runtime dependency on ryan-tools, TUFLOW solver, QGIS or external services for ordinary checks.
- No transfer of BAT/CMD parsing, simulation execution, resource scheduling, output reporting or whole-model hydraulic correctness claims into PyTUFLOW.
- Do not merge this draft PR solely on this design document. Review and implement independently testable code with host CI and focused native acceptance before enabling consumer defaults.
