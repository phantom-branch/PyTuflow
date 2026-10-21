# Deferred reference implementation status

The initial code introduces `TCF.context(..., file_resolution="deferred")` and
`InputRunState.file_references`, keeping eager resolution as the default.
References are immutable syntactic records for paths, GeoPackage layers,
originating commands and pending GIS attribute scans.

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
