# Deferred file-reference resolution

Status: design handoff for initial development. This document defines the intended boundary and acceptance evidence;
it does not adopt a final public API name or implementation.

## Problem

`TCF.context()` currently combines two different operations:

1. resolve the active event/scenario scope, variables and command values; and
2. materialise file references by globbing directories and, for GIS inputs, potentially opening layers and reading
   attributes.

This is convenient for an individual context but expensive for large ensembles on shared filesystems. A downstream
preflight benchmark reused one `TCF` and resolved 440 event/scenario combinations from a representative network-drive
HPC model. Initial parsing took 1.06 seconds, all `TCF.context()` calls took 160.40 seconds, and a subsequent
deduplicated inventory of 63 unique inputs took 0.06 seconds. Context construction therefore accounted for 99.3% of
the measured total.

The benchmark establishes where the elapsed time occurs, not how much is network latency versus Python object,
DataFrame or command-resolution work. Instrumentation must measure filesystem and GIS operations before performance
claims are made.

## Objective

Allow callers to generate structured, event/scenario-resolved file references without probing whether those files or
layers exist. A caller can then aggregate references from many contexts and materialise or validate them in bulk.

The intended workflow is:

```text
parse the control-file tree once
    -> resolve scopes, events, scenarios and variables for every requested run
    -> emit logical file references and wildcard/layer patterns without filesystem access
    -> deduplicate references across runs
    -> perform bounded directory, GeoPackage and optional GIS-attribute inspection once per unique target
    -> map results back to the dependent runs
```

Existing eager behaviour must remain the default for compatibility.

## Current I/O coupling

The initial implementation should verify and document these paths in the then-current source before changing them:

- `pytuflow/_tmf/cf/tcf.py`: `TCF.context()` constructs a new `TCFRunState` for each run.
- `pytuflow/_tmf/cf/cf_run_state.py`: active build-state inputs are converted into run-state inputs.
- `pytuflow/_tmf/inp/inp_run_state.py`: `_resolve_scope_in_context()` creates a fresh resolved input and accesses
  `self.files` to check variable resolution.
- `pytuflow/_tmf/inp/inp_build_state.py` and `pytuflow/_tmf/inp/file.py`: `.files` lazily calls `_load_files()`.
- `pytuflow/_tmf/parsers/line.py`: `iter_files()` calls `TuflowPath.glob()`.
- `pytuflow/_tmf/inp/gis.py`: GIS `_load_files()` may open layers, inspect geometry and collect files referenced in
  attributes.
- `pytuflow/_tmf/db/db_run_state.py`: each database run state reconstructs resolved entries and a DataFrame; source
  contents are loaded only through `value()` and should remain untouched by dependency discovery.

`BC Event Source` also needs correct command classification. It assigns an event value to a variable; a pipe-delimited
assignment such as `~AEP~ | 05.00p` is not a file path.

## Proposed public boundary

Add a deferred mode to context construction while preserving today's eager default. The exact spelling is open for
maintainer review; a representative API is:

```python
context = tcf.context(flags, file_resolution="deferred")

for input_ in context.find_input():
    for reference in input_.file_references:
        consume(reference)
```

`file_resolution="eager"` would retain current behaviour. A typed enum is preferable if it fits existing PyTUFLOW
configuration conventions.

`file_references` must not call `exists()`, `is_file()`, `glob()`, `resolve()`, `open_gis()`, SQLite/GPKG inspection or
GIS feature iteration. It should return immutable structured records containing enough information for a separate
resolver, for example:

```python
FileReference(
    base_directory=Path(".../model"),
    expanded_value="2d_mat_*.gpkg >> 2d_mat_*",
    path_pattern=Path(".../model/2d_mat_*.gpkg"),
    layer_pattern="2d_mat_*",
    origin="Read GIS Mat",
    requires_directory_scan=True,
    requires_layer_scan=True,
    requires_attribute_scan=False,
)
```

Field names and representation are deliberately provisional. Required semantics are:

- event, scenario and ordinary variable substitution is complete;
- relative paths are based on the control file that owns the command;
- lexical absolute paths do not dereference symlinks, junctions or mapped drives;
- literal paths remain literal references without an existence check;
- wildcard paths remain patterns rather than pretending to be concrete matches;
- GeoPackage/database path and layer pattern are separate fields;
- references discoverable only from GIS attributes are marked as deferred attribute work rather than silently omitted;
- output destinations and non-file commands are classified separately from required source inputs; and
- unresolved variables are reported without using filesystem failure as the signal.

## Internal design guidance

Do not cache or reuse mutable `RunState` objects across contexts. Separate syntactic reference generation from
materialisation instead.

A practical incremental implementation is:

1. Introduce the immutable file-reference model.
2. Teach command/input classes to produce references without calling `iter_files()`.
3. Change the run-state resolution check so it inspects generated reference text for unresolved variables instead of
   accessing `.files`.
4. Make GIS geometry and attribute inspection lazy in deferred mode.
5. Retain `.files` as the compatibility path that materialises references eagerly.
6. Optionally add a public resolver/session in a later commit or PR; downstream callers can initially provide their
   own bounded bulk resolver.

If PyTUFLOW adds its own resolver, it should be injectable and batch-scoped rather than a permanent module-level
cache. Reasonable cache keys include `(base_directory, glob_pattern)`, `(database_path, layer_pattern)` and the
specific GIS layer/attribute selection. A new session must observe filesystem changes. Do not cache whole rasters,
hydrograph CSV contents, unbounded feature collections or mutable contexts.

Avoid parallelising context construction as the first optimisation. Establish GDAL, SQLite and internal-state safety
and measure serial deferred performance first.

## Required tests

Add focused tests that fail if deferred context creation performs filesystem probes. Prefer injected spies or a
filesystem/resolver seam over production monkeypatching of private functions.

Coverage must include:

- literal relative and absolute paths;
- event, scenario and ordinary variable substitution;
- nested TCF/TGC/TBC/TEF ownership and path bases;
- wildcard path preservation without globbing;
- GeoPackage path plus literal and wildcard layer references;
- GIS commands with possible attribute-linked files;
- missing files and missing parent directories without an exception during generation;
- unresolved variables distinguished from missing files;
- `BC Event Source` treated as a variable assignment;
- output and write-only commands excluded from required source references;
- mapped-drive and UNC spelling retained;
- eager mode unchanged; and
- eager materialisation and deferred-then-materialised results equivalent on representative fixtures.

## Instrumentation and benchmark

Before and after implementation, record:

- initial `TCF` parse time;
- total context time for the same ordered run list;
- deferred reference generation time;
- bulk materialisation/validation time;
- calls to glob/directory enumeration;
- GIS and GeoPackage opens;
- GIS attribute iterations;
- BC database run-state reconstructions; and
- dependency parity, including originating command and affected run IDs.

Use both synthetic fixtures and the established 440-run network-drive model. The current eager baseline is 160.40
seconds for contexts. Success requires identical relevant dependencies and a material reduction in context time; do
not set a final performance threshold until instrumentation identifies the dominant operations.

The production benchmark data is not committed to PyTUFLOW. Run it through the downstream `ryan-tools` preflight
workflow, which already separates phase timings and performs bounded, deduplicated inventory checks.

## Downstream integration

During development, keep the PyTUFLOW checkout separate from `ryan-tools` and install it editably into the same Python
interpreter:

```powershell
python -m pip install --editable "C:\path\to\PyTuflow"
python -c "import pytuflow; print(pytuflow.__file__)"
```

Do not vendor PyTUFLOW, add it as a submodule, commit a local path dependency or add a repository `PYTHONPATH`
override. After an upstream release, `ryan-tools` can raise its minimum `pytuflow` version and replace its current
eager collection with the public deferred-reference API.

## Initial developer handoff

1. Confirm the current call graph and add operation-count instrumentation.
2. Propose the smallest backwards-compatible `FileReference` and deferred-mode API for maintainer review.
3. Add failing focused tests for zero-I/O reference generation before implementation.
4. Implement literal paths, variables and wildcard preservation first.
5. Add database/layer and GIS-attribute semantics without silently weakening dependency coverage.
6. Run unit tests and the 440-run downstream benchmark, documenting parity and timing evidence in the pull request.
