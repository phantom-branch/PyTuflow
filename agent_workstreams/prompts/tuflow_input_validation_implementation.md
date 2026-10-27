# Agent handoff — implement optional PyTUFLOW input validation

Repository: https://github.com/phantom-branch/PyTuflow

New branch: `feat/tuflow-input-validation`. Start from the existing draft PR on this branch; **do not open another PR**. Its target must be `master` **after the #39/#41/#42 stack is merged there**. Before any implementation, verify that the branch incorporates the resulting exact `master` head without rewriting published history, or report a blocker.

Required first reading:
- `agent_workstreams/input_validation_ownership_and_migration.md` (authoritative scope/boundaries)
- Source: `pytuflow/_tmf/file_reference.py`, `deferred_database.py`, `tfpathlib/file.py`, `batch_dependencies.py`, `fragment_dependencies.py`.
- ryan-tools PR #161: `ryan_library/functions/tuflow/dependency_index.py`, `csv_headers.py`, `orchestrators/tuflow/input_preflight.py` and tests.
- TUFLOW 2026.3 BC database documentation linked in the scope document.

## Required deliverable

Create a separate **opt-in, read-only, PyTUFLOW-owned physical dependency validation API**. Do not cause existing `TCF.collect_file_dependencies`, `collect_batch_dependencies` or deferred `Context` to probe secondary files as a side effect.

Review and agree an immutable public result/options contract before freezing exports. Accept already projected per-run dependencies (ordinary or fragment) and return typed per-source/per-run findings retaining input UUIDs, command positions, selected control-file identities, active BC ownership and error provenance. Use explicit statuses for present, missing, unresolved and unsupported. Do not depend on ryan-tools types, CSV report schemas or subprocesses.

Implement and validate in independently reviewable stages:

1. Source file existence and file-vs-directory classification, correct error separation, bounded/optional per-invocation deduplication, and wildcard path resolution using established PyTUFLOW path semantics.
2. Read-only GeoPackage `gpkg_contents` layer validation for explicit/implicit, wildcard and `>> all` requirements. Keep GIS feature/attribute inspection out of the basic metadata check. Preserve Linux case behaviour, Windows, UNC and mapped-drive semantics.
3. Ordinary BC Source CSV header checking using parser-resolved `Column 1` and `Column 2`, including UTF-8 BOM, comments, preamble, duplicate/missing names, multiline records, unreadable/oversized sources and an explicit configurable bound (initial rapid policy: five physical lines, 1 MiB). Preserve constants, FEWS and other Source-format exclusions; never load time-series data just for header checking.
4. Compose across hundreds of run contexts: inspect each unique physical requirement once per invocation where safe; map one result to every affected run and activation; preserve original run ordering, error isolation and raw file/layer identities. Benchmark overhead and validate deterministic result order when using bounded I/O workers.

## Correctness gates

- Test no new source `stat/open/scandir/sqlite3.connect` in syntactic-only `collect_file_dependencies`, with and without fragments, custom hooks and failed contexts. Reading the original parsed TCF and referenced BC database during construction is a distinct, already-established operation.
- Compare validation outcomes and file inspections with frozen ryan-tools PR #161 behaviour on synthetic and authorised private 480/36/240-context workloads. Reconcile differences explicitly with the TUFLOW documented semantics.
- Validate mixed scenario/event-dependent filenames, nested selected TGC/TBC/TEF includes, `<<~s1~>>` and transitive variable aliases, TEF cascades, unresolved tokens, multiple/changed BC databases and CSV selectors.
- Check missing file vs directory vs permission/read error, empty/oversized wildcard directory, `db.gpkg >> layer`, `>> all`, literal/wildcard GeoPackage layer, corrupted or unreadable databases, ordinary Source CSV with preamble/header on lines 3/5/6, and missing/ambiguous columns.
- Run applicable Ruff/strict Pyright, Windows Python 3.12 and 3.14, Linux, wheel installation and real ryan-tools consumer checks. Keep forward portability with the separately curated Python 3.11-minimum upstream-C programme in mind.
- Measure physical I/O counts, wall/CPU/memory and parity separately; do not claim speedups from synthetic counts or profiler time. Do not launch the TUFLOW solver or change private model inputs.

## Migration gate

Leave ryan-tools PR #161's published-package P1 explicitly unresolved until the supported default checker is restored or a compatible parser version is distributed. Only after this PyTUFLOW validator passes its contract should a **separate ryan-tools PR** consume it, retire duplicated TUFLOW-specific checking and preserve run-planning/CLI/reporting in ryan-tools.

Keep this PR draft. Do not merge, release, retarget, rewrite remote history, add production multiprocessing, transfer BAT/CMD orchestration, or submit official upstream A/B/C PRs without separate authorisation.

Post a source map and exact-SHA validation report on the draft PR, with grounded coverage limits and any unsupported input formats.
