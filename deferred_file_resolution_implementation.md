# Deferred reference implementation status

The initial code introduces `TCF.context(..., file_resolution="deferred")` and
`InputRunState.file_references`, keeping eager resolution as the default.
References are immutable syntactic records for paths, GeoPackage layers,
originating commands, database inspection requirements and pending GIS attribute scans.

Initial model parsing remains eager and can perform filesystem operations.
The bulk resolver is not implemented in this change. The consumer must
aggregate file patterns and materialise them, accounting for layer/attribute
dependencies before comparing dependency coverage.

## Before upstream review

- Confirm zero filesystem/GIS operations during context creation using spies.
- Include targeted tests for read-only reference access from an eager build state,
  variable expansion, output classification and unresolved variables.
- Cover nested TGC/TBC/TEF/TRD ownership and database paths.
- Compare all dependencies with eager materialisation, including GIS attributes.
- Rerun the representative 440-context network-drive benchmark; record I/O
  operations as well as timings.
- Confirm no regression in default eager mode and supported Python versions.

The complete acceptance matrix is in `deferred_file_resolution_plan.md`.

## Shared database-source projection (2026-10-22)

Eager behaviour corrections, the additive eager/shared API and the downstream
consumer completeness fix are recorded separately in
[Eager source completeness](eager_source_completeness_fixes.md). They must not be
reported solely as deferred parsing improvements. This section describes the
shared interface and deferred delegation.

**Existing eager behaviour fixed:** command reconstruction now preserves the
source owner and definition/event metadata instead of recreating the command
with constructor defaults. The original eager form is present in the local
upstream snapshot `cf908cc922ca8448ed6002834877b0b377329eae`; the separate eager
record contains the before/after and regression-coverage limits.

**Added functionality:** the shared `database_sources()` accessor exposes cached
source metadata in either mode; its syntax-only eager projection supports that
new capability. This does not redefine the existing eager `.files` API.
Delegating the deferred-only accessor to it is a deferred refactor. The ryan-tools
AD/curve collection fixes belong to the consumer and are not upstream eager
parsing fixes.

`TCFRunState.database_sources()` returns immutable typed source records in either eager or
deferred mode. It uses context-resolved, initially cached rows; it does not open the secondary
source files, glob directories or inspect GIS attributes. `deferred_database_sources()` retains
its deferred-mode guard and delegates to this shared projection. The new accessor does not change
the default context mode or the meaning of `Input.files`.

This makes AD BC/Global secondary sources available to an eager preflight consumer. Each source
retains its database entry name, owning command and original nested control-file path, even when
multiple entries reference one CSV. AD BC Source paths remain relative to the AD Global Database.
Command reconstruction now preserves the actual owner and definition metadata in both modes.

Pit/depth-discharge rows are candidate curves, not unconditional input requirements. Consumers
must join active GIS curve identifiers before adding their Source files, and preserve errors for
missing/ambiguous active identifiers. Scenario-inactive database declarations are excluded by the
resolved context. The ryan-tools consumer uses this projection and its shared GIS materialiser in
both modes; older parsers without the capability are not silently accepted for AD/curve roles.

Synthetic regressions cover eager/deferred nested ownership, AD Global-relative paths, distinct
entries sharing a CSV, zero I/O during the accessor and inactive scenario database exclusion.
