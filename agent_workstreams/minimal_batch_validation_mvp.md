# Phantom-branch MVP: standalone deferred batch validation

**Status:** development candidate, draft PR #47. Do not port to Chain-Frost,
change the Chain-Frost roadmap or migrate ryan-tools until native acceptance.

## Objective

Provide one stable, explicitly invoked library operation to check an ordered
list of TUFLOW runs for missing input files and GeoPackage layers, including
source files linked from recognised GIS feature attributes and cached databases.
Preserve the canonical TCF/Context/Set Variable/TEF parser and eager defaults.

The implementation deliberately keeps the orchestration in the new
`pytuflow/batch_parser.py`. It does not add another method to TCF or change
existing parser function implementations.

## Use

    from pytuflow.batch_parser import validate_batch

    checks = validate_batch(
        r"runs\model.tcf",
        [
            "-s1 Existing -e1 Q10",
            "-s1 Proposed -e1 Q100",
        ],
    )

    if not checks.passed:
        for issue in checks.issues:
            print(issue.run_index, issue.kind, issue.status,
                  issue.path, issue.layer, issue.detail)

Callers may instead pass an already parsed `TCF`. The caller owns the actual
run list and flag positions; PR #44 discovery is informational and does not
generate valid run combinations.

## Separation

1. Parse the model once (or reuse the supplied TCF). The original eager parser
   and `Context` own scenario, event, Set Variable, included control files,
   variable/TEF expansion and BC activation ordering.
2. `TCF.collect_file_dependencies(run_flags)` emits immutable, source-owned,
   ordered per-run syntactic file dependencies without physical inspection.
   The PR #46 fast fragment cache reuses only proven-equivalent fragments.
3. `pytuflow.validation.validate_dependencies` explicitly checks physical
   files, globbed filename matches, known GeoPackage layers and ordinary BC
   CSV column selectors. Physical input lookups are deduplicated per call.
4. For recognised GIS attribute-bearing 1D or BC layers,
   `validation_links.extend_gis_dependencies` reads already validated
   physical GIS sources read-only, detects linked source paths, checks curve/BC
   identifier ownership, and creates an *additional, private validation-only*
   projection. Original public dependency records remain unchanged.
5. A second explicit physical validation includes any newly discovered linked
   source files. All missing/unsupported/unresolved findings are attributed to
   the original run and command. The report passes only when all are present.

Standard file, wildcard, implicit/explicit GPKG layer, BC CSV and read-only
journal/alias protections are adopted from the reviewed PR #43. Attribute
discovery is separated from the normal TCF parse and from physical validation.

## Contract and limits

- `BatchValidationResult.dependencies` is the untouched fast fragment
  projection. `.validation` contains original and linked-source findings.
  `.passed` requires both stages to pass, and `.issues` excludes successes.
- Initial TCF parsing may open control files and load cached tables. After
  initial parse, fragment collection does not add physical I/O. Only explicit
  validation opens physical inputs.
- The MVP validates file and selected GIS-layer *existence*. It is not a
  raster-content validator, TUFLOW solver or guarantee of model hydraulic
  correctness.
- Direct feature-file link inspection supports GeoPackage and Shapefile
  metadata using standard library SQLite and the existing `dbfread` package.
  Unknown GIS feature schemas/formats are reported unresolved when they require
  file-valued attribute inspection. Do not treat such reports as success.
- MIF/MID attribute-linked source inspection, source-level GIS table joins
  beyond tested types, and broader inactive candidate BC file selection are
  still compatibility gates before unrestricted 'all TUFLOW inputs' claims.
  The native M480/M36/M240 campaign must quantify these gaps.
- GeoPackage metadata safety is strict: active WAL/rollback journals, uncertain
  symlink targets and hard-linked aliases fail closed rather than being read
  through an unsafe mutable database view.
- Physical case policy uses `TCF.config.case_sensitivity` (Linux -cs0 default
  with explicit -cs1/-cs2 and native Windows filename handling). An override
  disagreeing with the parsed model is rejected.
- The outer batch operation performs a second physical inventory only when
  recognised GIS linked files are discovered; this may require optimisation
  after correctness is established.

## Acceptance gates

- Hosted Windows 3.12/3.14 and Ubuntu 3.12 validator+fragment+batch tests;
  existing original-library regressions are an independent gate.
- Public TCF/GPKG + missing file/layer + CSV + linked 1D file and BC identifier
  fixtures; precise fail-closed unresolved cases.
- Native local agent: record/consumer parity and file/layer/BC-header checks on
  M480/M36/M240. Measure the full validation boundary, not the earlier
  producer-only ~3.78-second benchmark, since physical GIS attribute checks
  are now explicitly included. Retain source SHAs and full observed counts.
- No private source data, raw paths or flags in GitHub, no solver execution.
- Port only after acceptance to a separately curated Chain-Frost PR C
  candidate based on the actual upstream-accepted PR A baseline, not before.
