# Phantom-branch MVP: standalone deferred batch validation

**Status:** development candidate, PR #47 (unmerged). Do not port to Chain-Frost,
change the Chain-Frost roadmap or migrate ryan-tools until native acceptance.

## Objective

Provide one stable, explicitly invoked library operation to check an ordered
list of TUFLOW runs for missing input files and GeoPackage layers, including
source files linked from recognised GIS feature attributes and cached databases.
Preserve the canonical TCF/Context/Set Variable/TEF parser and eager defaults.

The implementation deliberately keeps the orchestration in the new
`pytuflow/batch_validation.py`. It does not add another method to TCF or change
existing TCF/Context parser method contracts. The only inherited BC method
change extracts the already-supported TS1 group-key rule into a shared helper.

## Use

    from pytuflow.batch_validation import validate_batch

    checks = validate_batch_inputs(
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

Standard file, wildcard, implicit/explicit GPKG layer and BC CSV checks
are adopted from the reviewed PR #43. The stable read-only GeoPackage
connection and journal/alias safety now live in PyTUFLOW core as
`pytuflow._tmf.gpkg_safety.readonly_gpkg`; both primary metadata checks
and batch feature scanning share it. Attribute discovery is separated from
ordinary TCF parsing and is not implicitly invoked by eager methods.

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
- Direct GIS feature-file link inspection supports GeoPackage and Shapefile
  metadata using standard library SQLite and the existing `dbfread` package.
  MIF/MID attributes are read through the existing PyTUFLOW
  `GISAttributes` provider, with no independent MIF/MID syntax parser.
  Existing PyTUFLOW also provides shared 1D attribute positioning, M/QO
  classification, BC grouping and context-aware cached constant evaluation.
  Unknown GIS feature schemas/formats are reported unresolved when they
  require file-valued attribute inspection.
- MIF/MID 1D and BC inspection now has synthetic acceptance coverage; non-
  standard GIS table links, unavailable geometry providers and unexercised
  mixed-network GIS types remain explicit unresolved boundaries. The native
  M480/M36/M240 campaign must measure correctness and performance at the
  exact candidate SHA before unrestricted all-input claims.
- Core GeoPackage inspection is strictly read-only: active WAL/rollback
  journals, uncertain symlink targets and hard-linked aliases fail closed.
  Existing eager GIS APIs are intentionally not altered to silently introduce
  new read restrictions; this explicit core helper is reusable by those APIs
  if a separate, compatible migration is authorised.
- Physical case policy uses `TCF.config.case_sensitivity` (Linux -cs0 default
  with explicit -cs1/-cs2 and native Windows filename handling). An override
  disagreeing with the parsed model is rejected.
- The outer batch operation performs a second physical inventory only when
  recognised GIS linked files are discovered; this may require optimisation
  after correctness is established.

## Acceptance gates

- Hosted Windows 3.12/3.14 and Ubuntu 3.12 validator+fragment+batch tests;
  original-library regressions use pytest 9.2.0 in both baseline and current
  dependencies with corrected regression-harness isolation lifecycle hooks.
- Public TCF/GPKG + missing file/layer + CSV + linked 1D file and BC identifier
  fixtures; precise fail-closed unresolved cases.
- Native local agent: record/consumer parity and file/layer/BC-header checks on
  M480/M36/M240. Measure the full validation boundary, not the earlier
  producer-only ~3.78-second benchmark, since physical GIS attribute checks
  are now explicitly included. Retain source SHAs and full observed counts.
- No private source data, raw paths or flags in GitHub, no solver execution.
- Port only after acceptance to a separately curated Chain-Frost PR C
  candidate based on the actual upstream-accepted PR A baseline, not before.
