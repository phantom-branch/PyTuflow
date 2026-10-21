# Deferred supported-input parity audit — upstream workstream

Status: **in progress, not merge-ready**. Supporting PR #2 builds on upstream PR #1; ryan-tools PR #143 owns shared GIS materialisation and the real-model harness. **Windows only is in scope for current CI and real-model acceptance (Python 3.12/3.14). Linux portability is explicitly deferred to a separate follow-up PR.** No TUFLOW engine was launched.

## Parity contract

Compare records by **run flags, owning control file and command, physical source path, GeoPackage layer, database kind, database row/identifier, and secondary dependency**. Compare both eager-only and deferred-only records. A matching pair of partial sets is not a pass. Post-parse deferred `context()` and ordinary `.file_references` must not glob, stat, open files, enumerate GIS layers or connect to SQLite. Explicit `deferred_database_sources()` works only from databases parsed during the initial build-state load. Initial model parsing is **not** I/O free.

A deferred `FileReference` marks whether directory, layer, GIS attribute, table-link or database inspection is still needed. Deferred references are **not** existence assertions. A database identifier (for example a 1d network Q/P curve named `aa`) is not a path.

## Supported-input inventory

| Input class / command | Upstream record / handling | Materialised-parity status |
| --- | --- | --- |
| TCF/TGC/TBC/ECF/TEF/TRD/ADCF and other cached nested controls | Scope-aware recursive cached references and lexical child matching inherited from #1; no per-context file I/O | Synthetic nested controls covered; example-model parity still required |
| Direct GIS SHP/MIF/GPKG, implicit named layer, `>> all` | `FileReference.path_pattern`, `layer_pattern`, `requires_layer_scan`, `requires_attribute_scan` | Primary patterns represented; downstream format-specific scans required |
| Direct raster TIF/FLT/ASC and wildcard paths | Lexical path reference and wildcard scan marker | Physical resolution and raster metadata checks belong to bulk stage |
| `Read Grid RF == index.csv` | Loaded rainfall index rows exposed as typed `rainfall` secondary paths; raster metadata scan marked explicitly | Synthetic tests; EG03_011 and EG03_012 must be rerun and eager errors diagnosed |
| `Read Grid RF == rainfall.nc` | Terminal `rainfall_netcdf` primary with metadata scan marker; no synthetic empty database | Synthetic test; metadata validation at bulk stage |
| Hydraulic `BC Database` | Typed `bc`, cached source rows and event substitutions; eager lookup now excludes AD BC | Synthetic tests; active-row and 174-run parity needed |
| `AD BC Database` | Typed `ad_bc`, resolves Source paths relative to active AD Global Database as documented | Synthetic tests; actual ADCF examples needed |
| `AD Global Database` | Cached constituent CSV; numeric/blank optional initial condition and numeric minimum dispersion; GIS source paths and GPKG layers represented | Synthetic tests; model parity and raster/GIS field checks outstanding |
| `Read Materials File` / .TMF and inline material parameters | Cached material source, numeric and depth/n handling inherited from #1 | Existing synthetic tests; examples and malformed schemas must be checked |
| `Read Soil File` TSOILF | Existing syntax and inline methods NONE/ILCL/GA/HO/CO/SCS | Existing synthetic tests; example parity required |
| `Pit Inlet Database` | Typed `pit_inlet`, Source CSV from cached Name rows | Synthetic tests; active 1d_pit IDs must be mapped downstream |
| `Depth Discharge Database` | Typed `depth_discharge`, Source CSV; 1d_nwk Q/P fields are database curve IDs | Synthetic tests; active Q/P IDs and case-insensitive matching in downstream materialiser |
| 1d_nwk M and QO / ignored rows | Eager parser now classifies M matrix paths; QO file component only; Q/P identifiers are not fake files; Ignore Y/T skipped | Synthetic positional-field checks; actual feature geometry/attributes remain Agent 1's work |
| `Read GIS Table Links` / 1d_xs, 1d_tab etc | Primary GIS layer with `requires_table_link_scan`; eager preserves the existing GIS-aware `CrossSectionDatabase` view | **Incomplete until Agent 1 materialises per-feature paths**; EG02/EG04 examples required |
| `XS Database`, Flood Modeller/MIKE external data | Primary `cross_section`; cached CSV/GIS Source column yields secondary paths; Flood Modeller DAT cross sections are internally contained | Synthetic XS CSV tests; other external-driver schemas and model parity still require verification |
| Attribute-linked secondary files for 1d_xs/network/pit etc | `requires_attribute_scan` and upstream channel semantics; scan results delegated to Agent 1's shared SHP/GPKG materialiser | **Implementation gap until full-format scanner and identity comparison** |
| Output, log/check folders and variable assignments | Excluded from input-file inventory | Existing synthetic output/assignment regressions |

## Correctness risks and gates

1. Eager rainfall exceptions (`NoneType.resolve`, pandas indexer mismatch) do **not** establish that the model is invalid. Test EG03_011/012 using unmodified raster/index bytes and log exact errors after each parser fix.
2. Ambiguous hydraulic versus AD databases must be classified by exact command role, scoped run and owning ADCF. Never pick the first of two equivalent-role databases.
3. Secondary database rows may include entries not referenced by active GIS IDs. Downstream must compare **extra** as well as missing deferred inputs; all-row cached source enumeration is not proof that every row is an active dependency.
4. GIS attributes require the same element semantics for Shapefile and GeoPackage, including Ignore, Type, positional fields, database identifiers and row provenance. Do not substitute path-like heuristics for typed rules.
5. Rainfall grids, GIS secondary files and GeoPackage `>>` layers require separate batched inspection. None of these validations is implied merely by returning a syntactic reference.
6. Invalid and unsupported-but-valid inputs are different. Unsupported-but-valid cases are implementation blockers and remain **unresolved**, not accepted.
7. Repeat targeted regression tests, original 42-run model, P (4), B (240), and example reproduction bundle (161 TCFs / 174 runs); report exact SHAs and filesystem/GIS operations before any speedup claim.
8. The reference **Windows** baseline remains **107 TCFs / 119 runs accepted and 54 TCFs / 55 runs unresolved**, as supplied for PR143 head `b8d7adc` and PyTUFLOW head `65f24fa`. A full **Windows** sweep using the latest upstream and downstream heads is still required; historical Linux results are not an acceptance criterion.

## External engineering semantics

- TUFLOW Classic/HPC 2026.3 §9.4: AD Global and AD BC are separate databases. AD BC Source paths are relative to the **AD Global Database**; AD Global Initial Condition and Minimum Dispersion may name GIS layers.
- TUFLOW 2026 special/operational channel guidance: network Q/P are depth–discharge curve IDs, QO specifies an operational-matrix file after its control ID, and M refers to matrix inputs.
- `Read GIS Table Links` resolves secondary cross-section/tabular sources via the GIS feature attributes, not by parsing the GIS source file as a CSV database.

Sources: https://docs.tuflow.com/classic-hpc/manual/2026.3/075-Advection-Dispersion.html and https://docs.tuflow.com/classic-hpc/manual/2026.0/TwoDBoundaries-2.html .

## Current validation scope — Windows only

- Automated contract/context regression matrix: **Windows Python 3.12 and Python 3.14**.
- Read-only, explicitly opt-in 174-run example-model workflow: **Windows Python 3.14**.
- Preserve all existing controls: both missing and extra dependency comparison; fail-closed
  incomplete-attribute guard; no simulations; no fixture deletion; no merge or release.
- **Linux acceptance, POSIX path sensitivity and Linux-specific materialiser
  behaviour are excluded from this PR's acceptance criteria.** Linux work is
  tracked in a separate follow-up draft PR to be considered after Windows parity passes.
- Earlier cross-platform CI and Linux example results remain historical information in
  GitHub Actions logs; they are not used to approve or reject the Windows feature.

## 22 October continuation — Windows-only parser API handoff

- Required AD BC, pit inlet, depth-discharge and cross-section Source fields
  containing numeric-looking values now **fail closed** rather than silently
  disappearing from the inventory (Codex P2 review; regression matrix).
  BC/material inline constants retain their separate documented semantics.
- Multiple BC database declarations must not be combined into an invented
  database. `deferred_database_activations()` returns ordered declaration UUIDs;
  the new `deferred_database_sources_for_activation(input_uuid)` returns only
  the corresponding cached row sources, with `DeferredDatabaseSource.input_uuid`
  preserving declaration ownership. The caller must decide which declaration
  was active for each GIS/boundary command and which Source row identifiers
  were actually referenced. Fetching all row sources is **not itself parity**.
  Unknown UUIDs, duplicate inputs and unsupported database schemas fail closed.
- `Read GIS Table Links` primary references retain
  `requires_table_link_scan` and `requires_attribute_scan` for SHP and
  GPKG (explicit layers and `>> all`); they do **not** require CSV database
  parsing. Eager public `CrossSectionDatabase` behaviour is retained. Feature
  attribute reading and materialisation remain downstream Agent 1's work,
  not extra operations during a deferred context.
- CI/acceptance remains **Windows Python 3.12 and 3.14**; Linux checks are
  deferred to [tracking PR #4](https://github.com/phantom-branch/PyTuflow/pull/4).
- An exact-head Windows 161-TCF/174-run validation is still necessary after
  consumer integration, including missing *and* extra linked files.
