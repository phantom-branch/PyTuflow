# Eager source completeness: separate review record

## Existing materials CSV separator/comment defect (2026-10-22)

The replacement model also exposed an existing materials loader error: CSV
separator rows (`',,,'`) and whole-line comment records reached integer material-ID
conversion, producing a NaN/string conversion error and leaving no cached table.
The integer conversion is also pre-existing in commit `dbc3cb40`.
Materials loading now excludes wholly empty separator rows and rows whose ID
starts with `!` or `#`, before building entries. A nonempty row without an ID still
fails validation. This repairs original eager/shared initial loading, not deferred
resolution. Synthetic tests verify retained material IDs, rejection of malformed
rows and eager/deferred/batch source-accessor parity. Native files are unchanged.

## Existing eager/shared Context slot-nine defect (2026-10-22)

Native replacement-model validation exposed an existing off-by-one error in
`Context._create_list`: it enumerated numbered scenario/event slots 0 through 8,
although argument loading supports slots 1 through 9. As a result `-s9` / `-e9`
were available for placeholder translation but omitted from conditional scopes.
Git blame traces the defective loop to pre-existing commit `dbc3cb40`.
This affects original eager contexts as well as deferred and batch contexts;
it is an existing behaviour fix, **not new deferred functionality**. Scope
collection now includes slots 1 through 9. Synthetic regressions cover ninth
scenario/event selection and real parsed conditional/PAUSE parity across modes.
No native input files or launcher flags are changed.

## Network evaluation corrections (2026-10-22)

Two further parser blockers were found while evaluating batch/deferred resolution
on supplied native network models. They are distinct from the existing two-BC
declaration/feature-selection issue, which the owner has deferred.

- **Deferred/batch compatibility repair:** an unresolved output/check/log directory
  expression could abort context creation even though eager mode does not require
  those destinations as source inputs. Destination-only folder expressions now
  retain that eager boundary; actual READ dependencies still require resolution.
  This is not a general relaxation of unresolved input checks and does not establish
  that an engine output destination is valid.
- **Shared source-accessor repair, including eager callers:** one BC declaration
  can preload several scenario-specific database files during initial parsing.
  The new source projection previously demanded one table across all cached
  candidates. It now chooses the cached file matching the context's resolved
  primary path. Initial loading retains lexical paths before canonicalisation,
  allowing selection without stat/open/glob or mapped-drive/UNC conversion.
  This corrects the source-inspection API introduced by the deferred work; it is
  not a redefinition of original eager `.files` or a multi-declaration BC join.

Nine eager/deferred/batch regressions exercise output-folder exclusion, two
scenario candidate tables, and refusal to substitute another table when the
selected candidate is absent. Accessor tests prohibit open/stat/glob/SQLite I/O.
The affected local batch/reference/database/context/GIS selection passes **218
tests**. Native evaluation and its exact revisions are recorded separately; no
broader immutable control-file graph or elimination of run-state allocation is
implemented by these corrections. No proprietary model data is included.

Updated: 2026-10-22. Status: shared/eager changes committed as `22e2413`, followed
by the eager EventCommand accessor repair in `8e7bc30`. Strict Windows hosted
example parity passes on that repair; remaining external acceptance/final review
is described in the implementation status record.
Base: `546ab20`, branch `feat/deferred-file-resolution`.

This record separates changes affecting eager consumers from the
[deferred parsing implementation](deferred_file_resolution_implementation.md).
The findings apply to the checkout and consumer tested here; they are not a claim
that every published PyTUFLOW version has the same defect.

## Change classification

### Earlier eager changes already included in PR #1

The distinction also applies to work committed before `22e2413`. Compared with
upstream base `cf908cc`, these affect existing eager behaviour and must appear
explicitly in the upstream review/release summary:

| Existing eager surface | Before / after | Relevant files and coverage |
| --- | --- | --- |
| Hydraulic BC lookup | Substring lookup could include AD BC; hydraulic and AD accessors now use distinct exact command roles | `abc/tcf_base.py`; `test_hydraulic_and_ad_bc_databases_are_independent` |
| Rainfall CSV inventory | Eager `.files` exposed only the index; now includes context-expanded grids from cached rows | `inp/cf.py`; `test_eager_rainfall_csv_inventory_includes_cached_grid_sources`, `test_eager_rainfall_grid_projection_is_cached_in_memory` |
| Rainfall context compatibility | Pandas string-array assignment could fail; cached rows use object dtype before context substitution | `db/db_run_state.py`; affected database/context tests and unmodified rainfall examples |
| NetCDF rainfall loading | Created a placeholder database with no physical path; now treats NetCDF as a terminal rainfall input | `inp/db.py`; `test_netcdf_rainfall_is_terminal_primary_not_database` |
| Assignment classification | File-looking BC Event Source / Set Variable values could be classified as inputs; now assignments are excluded and their actual consumers remain checked | `parsers/command.py`; `test_nested_output_variables_are_assignments_not_input_files` and BC event tests |
| Network/pit attribute interpretation | File-like curve/control identifiers could become false paths; M/QO file components, Ignore flags and Q/P/pit database identifiers now have distinct rules | `gis.py`, `inp/gis.py`; positional network-role tests and full example replay |

AD Global cached-table loading and typed database roles are added source-inspection
capabilities, even though eager consumers can use them. The multipart materials
lazy loader and deferred `>> all` expansion restore compatibility after changes
introduced while implementing deferred resolution; describe them as PR regression
repairs, not independently proven defects in the original upstream base. Rainfall
index column validation is an explicit new schema check, not just a performance change.

### Latest shared-source/eager correction

| Change | Classification | Review boundary |
| --- | --- | --- |
| Preserve nested command parent, part index, line number, definition blocks and event name when reconstructing eager commands | Eager behaviour correction | `pytuflow/_tmf/inp/inp_run_state.py`; deferred mode already preserved this metadata |
| Add `TCFRunState.database_sources()` for either context mode | Additive shared API enabling eager consumers | `pytuflow/_tmf/cf/tcf_run_state.py`; `.files` and the default eager mode retain their existing meaning |
| Classify cached source rows with a copied syntax-only configuration when the accessor is called from eager mode | Eager accessor correctness and I/O guarantee | `pytuflow/_tmf/inp/inp_run_state.py`; does not switch eager context construction to deferred mode |
| Delegate `deferred_database_sources()` to the shared accessor while retaining its deferred-only guard | Deferred implementation refactor | Same TCF module; document and review separately from eager corrections |
| Collect AD source identities and join active GIS curve IDs in eager preflight | Downstream consumer completeness fix | ryan-tools `ryan_library/orchestrators/tuflow/input_preflight.py`; not an upstream eager GIS join |

## Eager finding and resulting behaviour

### Existing eager behaviour corrected in PyTUFLOW

The original eager reconstruction was checked directly in the local
`origin/master` snapshot, commit `cf908cc922ca8448ed6002834877b0b377329eae`,
as well as the eager branch of the PR base `546ab20`. This is a source comparison
against those exact commits, not a fresh upstream fetch or a test of all released versions.

In `InputRunState._resolve_scope_in_context()`, the original implementation used:

```python
self._command = self.bs.command().__class__(cmd_txt, self.config)
```

That reconstructed the command using constructor defaults rather than carrying
over its source parent, part index, ordinary-command line number, definition
blocks or event name. The PR already preserved this information in deferred mode;
the local correction now applies the same preservation to eager mode.

After the correction, nested commands retain their actual owning control file,
ordinary commands retain their part/line metadata, and event commands retain
their event name. Definition blocks are copied and the value is reloaded with
that metadata in place. EventCommand has no line-number constructor parameter;
this change does not add one. This is a correction to existing eager command
reconstruction, independent of whether a caller requests deferred resolution or
uses the new source accessor.

The nested AD regression checks the concrete observable result: source records
identify `controls/model.adcf` as owner, rather than losing that nested owner,
and AD BC paths use the AD Global table's directory. It also keeps two source
entries distinct when they reference one CSV. The test does not separately assert
every copied metadata field; those other preservation changes are established
by the implementation diff, not claimed as independent regression coverage.

### Added functionality supporting deferred and eager source inspection

`TCFRunState.database_sources()` is a **new shared API**, not a repair to the
existing `.files` contract. It exposes the typed cached-row projection to eager
callers as well as deferred callers. The syntax-only configuration copy makes
that new eager-accessor path avoid filesystem/GIS resolution while classifying
source rows; this is a guarantee of the added accessor functionality, not evidence
that original eager context construction should have performed zero I/O.

`deferred_database_sources()` retains its existing deferred-only guard and now
delegates to the shared method. That delegation is the deferred refactor. The
opt-in `file_resolution="deferred"`, syntactic reference representation and deferred
acceptance requirements remain additions tracked in the separate deferred record.

### Downstream eager collection gap

The example replay previously found 19 deferred-only source identities across
eight cases, with no eager-only identities. The eager preflight consumer collected
`.files` and hydraulic BC rows, omitting AD BC/Global secondary records and active
pit/depth-discharge curve sources. This was a dependency-collection gap, not proof
that the engine's inputs were absent or that eager parsing failed to load a model.

Eager command reconstruction also discarded metadata retained in deferred mode.
Preserving the actual nested owner keeps relative-source interpretation and
reported command provenance attached to the correct control file. The shared
accessor now exposes cached, context-resolved database records without opening
secondary files, globbing directories or inspecting GIS attributes. Distinct
database entries retain distinct identities even when they share one CSV.

Curve rows are candidates: callers must join active GIS curve IDs before treating
their Source values as required files. AD BC Source paths are relative to the AD
Global Database. Rows from context-active database declarations are inspected
conservatively; this does not emulate engine selection of individual time-series
rows or columns. Scenario-inactive declarations are excluded.

The ryan-tools eager consumer uses this API and its existing GIS materialiser.
Older eager parsers without the capability produce an unresolved diagnostic for
declared AD/curve roles instead of silently certifying complete coverage.

## Validation and limits

### Review repair: eager EventCommand reference accessor (2026-10-22)

The fresh review identified a separate compatibility defect in the **new**
`InputBuildState.file_references` accessor: cloning an eager TEF EventCommand used
the ordinary Command five-argument signature and raised TypeError. This affected
both eager build-state inputs and eager run-state reference access. It is a
regression in functionality added by this deferred-resolution PR, not a demonstrated
defect in the original upstream `.files` implementation.

The accessor now uses EventCommand's supported four-argument constructor, retains
its event name, owner, part index and definition blocks, and leaves the original
eager configuration unchanged. Syntax-only inspection still uses a copied deferred
configuration. Two regressions fail with the original TypeError before the fix and
pass afterward, checking both access paths and metadata while prohibiting file
open/stat/glob/SQLite operations. The affected upstream selection is now **183 passed**.
This change adds no additional public API or materialisation feature.

Synthetic regressions in `tests/test_deferred_database_parity.py` assert expected
sources independently in eager and deferred modes: nested ownership, AD
Global-relative paths, distinct entries sharing a CSV, inactive scenario exclusion,
and no open/stat/glob/SQLite calls during source-accessor execution. The affected
upstream database/reference/context/GIS selection passed **181 tests**.

The ryan-tools focused selection passed **72 tests**. Its example replay passed
**161 TCFs / 174 runs**, with zero eager-only or deferred-only identities; all
eight formerly failing cases also passed using the rebuilt consumer wheel with
the local upstream source. These are local working-tree results, not hosted CI
or published-package acceptance. The comparator was not relaxed.

No default-mode change, redefinition of `.files`, upstream eager GIS feature join,
new performance benchmark or engine execution is included. Review the eager
correction and additive API explicitly when preparing commits/release notes;
deferred parsing acceptance remains a separate work item. The tested source is now
committed as upstream `22e2413` and consumer `09dfd502`. The upstream example workflow
pins that fixed consumer and requires all 161 TCFs/174 runs with zero missing/extra
identities. The downstream upstream-parser pin is updated separately. A successful
exact-head hosted replay and the native-model/activation checks remain merge gates;
the local results above are not relabelled as hosted results.
