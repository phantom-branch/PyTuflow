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

## Windows acceptance update (2026-10-22)

This update supersedes the initial checklist's validation status; the checklist
above remains the original acceptance scope. Parser/eager corrections were pushed
as `22e2413`, with strict replay workflow changes in `fb103a1`. The parser source
is unchanged between those commits.

- Affected local database/reference/context/GIS regression selection: **181 passed**.
  Downstream preflight/GIS/raster/launcher selection: **72 passed, zero skips**.
- [Windows 3.12/3.14 regression matrix](https://github.com/phantom-branch/PyTuflow/actions/runs/39711771111):
  both jobs pass for head `fb103a1`.
- [Windows Python 3.14 example replay](https://github.com/phantom-branch/PyTuflow/actions/runs/39711771147):
  **161/161 TCFs and 174/174 runs accepted**, zero missing/extra identities or parser
  errors, against fixed consumer `09dfd502`. The full comparison and public preflight
  must pass; failures are no longer tolerated as successful diagnostics.
  [Retained artifact](https://github.com/phantom-branch/PyTuflow/actions/runs/39711771147/artifacts/12397057423).
- Local full example replay independently repeats the same complete result.
- Private models P (4 runs, 68 identity records, 17 physical files) and B (240 runs,
  4,560 records, 32 files) pass first/middle/last checks and three full comparison
  pairs each, with zero missing/extra records and zero collection/inventory issues.
  Model data and paths remain outside both repositories.

### Local SSD measurements

Same parser and consumer source in both modes, fresh model per mode, three
alternating eager/deferred pairs, existing filesystem caches retained. Instrumented
timings include initial parse and complete reference collection/materialisation/
inventory, excluding process startup and report writing. These are local SSD results,
not network or cold-cache measurements. Independent phase medians need not sum to
the median total.

| Model / mode | Median total seconds | Range | Median parse / context / remaining seconds | Context audit glob / SQLite calls |
| --- | --- | --- | --- | --- |
| P eager | 1.176 | 1.156-1.293 | 0.400 / 0.635 / 0.140 | 84 / 15 |
| P deferred | 0.817 | 0.816-0.819 | 0.391 / 0.376 / 0.049 | 0 / 0 |
| B eager | 58.918 | 58.874-59.430 | 0.789 / 47.843 / 10.454 | 5,051 / 2,171 |
| B deferred | 38.897 | 38.753-39.077 | 0.577 / 34.722 / 3.607 | 0 / 0 |

Audit counts are stable across repetitions and cover Python `open`, directory
enumeration, `pathlib.Path.glob` and SQLite connection events by phase. They do not
measure every stat or native GIS/OS operation, or memory. Deferred context audit
counts were empty; the separate spy-based regression tests provide the broader
post-parse zero-I/O contract. Do not generalise these timings to other storage/models.

### Activation review and external acceptance

`deferred_database_activations()` preserves context-scoped declaration order and
UUIDs. `deferred_database_sources_for_activation(uuid)` returns only that table's
rows, with no new source-file/GIS I/O. Tests cover two declarations, separate source
identities, scenario exclusion, missing UUIDs and refusal to silently merge tables.
The shared all-source accessor deliberately rejects ambiguous multiple BC tables.

**The consumer does not yet associate each BC GIS feature with a declaration and
filter only its referenced rows.** Its ordinary single-table inspection remains
conservative. This is a downstream materialisation limitation, not proof of full
feature-level selection. Keep it visible during final review; a passing example
comparison is not independent evidence that this selection has been implemented.

The owner confirmed that the 42-run and 440-run models are on another network.
The later update below records completed 440-run evidence. **The owner withdrew
the 42-run external check as a merge requirement on 2026-10-22; it is not an
outstanding acceptance gate.** Use the versioned downstream native-model runner documented
in `tests/fixtures/tuflow_example_repro/README.md` (consumer commit `c80afd3` or later),
with the unchanged model TCF and launcher-exported command file, the expected run
count, and private output outside the checkout. Check the representative gate
before all runs; retain exact heads, anonymous summaries and actual storage/cache
conditions. No engine execution or project-data upload is needed. Keep the PR open
for final external acceptance/review; no merge or release is performed here.

## Review follow-up and external evidence (2026-10-22)

The later eager `file_references` EventCommand constructor finding is repaired
in `8e7bc303aa7306cbdc0a6760bc089f84121e3f6e`. This repairs the new accessor added
by this PR, not an independently established original `.files` defect. The
[separate eager record](eager_source_completeness_fixes.md#review-repair-eager-eventcommand-reference-accessor-2026-10-22)
contains the before/after evidence and two zero-I/O metadata regressions.
Local affected selections now pass **183 upstream tests / 72 downstream tests**.
P/B representative checks, one fresh full pair and public preflight were repeated
on the repair and still pass with the same 68/4,560 records and 17/32 files.
The three-trial SSD timing table above remains attached to the earlier source;
it is not relabelled as a new three-trial measurement of this follow-up.

At repair head `8e7bc30`, both the
[Windows 3.12/3.14 matrix](https://github.com/phantom-branch/PyTuflow/actions/runs/39713500347)
and [strict full example replay](https://github.com/phantom-branch/PyTuflow/actions/runs/39713500346)
pass. The latter again enforces **161 TCFs/174 runs accepted, zero differences**;
[artifact 12397837069](https://github.com/phantom-branch/PyTuflow/actions/runs/39713500346/artifacts/12397837069)
has SHA-256 `08859da6a0154c6a2101adcdf620fcb264261a4de52a0a34628d4f79bf6acb6e`.
The review thread was answered with the repair/regression evidence and resolved.

The other workstation has now committed the **440-run** external result in
consumer commit `e4518499`: consumer `b68f4ada`, parser `fb103a1`, Python 3.14.4,
mapped/network storage. It records zero preflight findings, 62 physical paths,
8,360 materialised identity records and zero eager-only/deferred-only entries.
One warm-cache eager/deferred dependency-generation pair measured 110.359 s and
29.650 s, respectively. These are externally recorded results on the stated
revisions, before the accessor repair; this workstation did not access or rerun
that network model. Do not combine those timings with the local SSD samples.
The **42-run external check is no longer required**, at the owner's explicit
instruction on 2026-10-22. Historical references to that gate are superseded.
The owner retains the final
external acceptance decision, including whether a repair-head network recheck is
required. Feature-to-BC-activation selection remains the documented consumer
limitation above. No merge or release is performed.

The example workflow now pins consumer `b32adc258c63957e06b482c3280eb8a02c428a13`,
including the native handoff's physical-import/version/source-hash verification
and the preserved external 440-run record. Consumer CI pins parser repair `8e7bc30`.
The consumer implementation itself is unchanged from the successful earlier replay;
the new pin also fixes the diagnostic/handoff provenance for reviewer reproduction.

## Shared database-source API details (2026-10-22)

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
