# Deferred supported-input parity audit — upstream workstream

Status: **in progress, not merge-ready**. Supporting PR #2 builds on upstream PR #1; ryan-tools PR #143 owns shared GIS materialisation and the real-model harness. No TUFLOW engine was launched.

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
| `Read GIS Table Links` / 1d_xs, 1d_tab etc | Primary GIS layer with `requires_table_link_scan`; eager no longer treats shapefile/GPKG as CSV cross-section database | **Incomplete until Agent 1 materialises per-feature paths**; EG02/EG04 examples required |
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
8. No status in this file supersedes the downstream baseline: **107 TCFs / 119 runs accepted and 54 TCFs / 55 runs unresolved**, as supplied for PR143 head `b8d7adc` and PyTUFLOW head `65f24fa`. No revised full example sweep has yet been executed on this supporting branch.

## External engineering semantics

- TUFLOW Classic/HPC 2026.3 §9.4: AD Global and AD BC are separate databases. AD BC Source paths are relative to the **AD Global Database**; AD Global Initial Condition and Minimum Dispersion may name GIS layers.
- TUFLOW 2026 special/operational channel guidance: network Q/P are depth–discharge curve IDs, QO specifies an operational-matrix file after its control ID, and M refers to matrix inputs.
- `Read GIS Table Links` resolves secondary cross-section/tabular sources via the GIS feature attributes, not by parsing the GIS source file as a CSV database.

Sources: https://docs.tuflow.com/classic-hpc/manual/2026.3/075-Advection-Dispersion.html and https://docs.tuflow.com/classic-hpc/manual/2026.0/TwoDBoundaries-2.html .

## Read-only GitHub Actions example sweep (22 October 2026)

Run [39652484033](https://github.com/phantom-branch/PyTuflow/actions/runs/39652484033)
used Linux/Python 3.14 with PyTUFLOW code commit `172af012f88ccb9088e894dc3b8fde85adc7623d` and
pinned ryan-tools commit `aaa475e30eb5397d7b88adeffb970ff0c5155b6f`. The verified 1,464-member
archive was extracted into a temporary directory; no TUFLOW executable was launched.

**Observed results (older code SHA, not the current head):**
- 161 TCFs / 174 run combinations checked; 21 TCFs / 21 runs accepted.
- Eager-only dependency identities: **2** (EG05_018).
- Deferred-only dependency identities: **18** (16 rainfall grids in EG03_012; one each in EG15_007/008).
- No whole-context parser exceptions returned by the harness, but **one eager collection issue**:
  pandas 3 StringArray assignment fails inside `DatabaseRunState._resolve_scope_in_context`
  for EG03_012, resulting in an incomplete eager inventory.
- 145 preflight missing-file findings included case-sensitive Linux lookups:
  the control input asks for `model/materials.csv` but the stored member is `model/Materials.csv`.
  This makes the Linux accepted-count **not comparable** to the earlier Windows baseline of
  119 accepted / 55 unresolved. Agent 1 must implement shared case-insensitive literal
  materialisation (or retest on Windows), without per-run filesystem scans.
- The pinned downstream consumer accepts only `bc` and `materials` database source kinds.
  It correctly fails closed on `pit_inlet` (13 cases), `ad_bc` (4), `depth_discharge` (3)
  and `rainfall` (1). Other blocked cases include GIS table links (12).
- EG03_011 passed both modes with 16 identical reference identities. EG03_012's eager
  pandas failure has subsequently been repaired in `db_run_state.py`; the eager
  rainfall CSV index inventory now projects cached grid Source rows.
- Do not suppress empty BC Source `GT01` in EG05_018 or treat the two network curve
  differences as solved without checking source row semantics and active identifiers.

The job stores full per-case JSON and CSV in its Actions artifact. The GitHub diagnostic
workflow's full sweep is **opt-in** via `[run examples]` in the supporting PR title;
ordinary synthetic CI remains automatic. A later exact-head rerun must overwrite none
of the original example bundle, and must compare missing **and** extra dependencies.

