# Eager source completeness: separate review record

Updated: 2026-10-22. Status: implemented locally, unstaged and uncommitted.
Base: `546ab20`, branch `feat/deferred-file-resolution`.

This record separates changes affecting eager consumers from the
[deferred parsing implementation](deferred_file_resolution_implementation.md).
The findings apply to the checkout and consumer tested here; they are not a claim
that every published PyTUFLOW version has the same defect.

## Change classification

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
deferred parsing acceptance remains a separate work item. Both repositories need
review/commit, then the consumer's immutable upstream CI pin needs updating before
hosted validation can cover these changes.
