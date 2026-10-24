# W8 missing physical endpoints - sanitised live-QGIS evidence

Code/test source: **37fc565218775a06252252a15cdb6e79e4e28c3c**.
Pre-fix source: **26c6bad101811af2945ce7558e69bb6c1c37685e**.
Original baseline: **e162c04330d24c37bee3ade94479cc4602651060**.
The containing evidence commit changes reports/handoff only. Exact final pushed
head and hosted standalone CI/review are recorded in PR #23's delivery comment.

These are locally executed **real QGIS/MDAL** reports, distinct from hosted
standalone Windows Python artifacts. No fake providers, broad skips, warning
suppression, weakened tolerances, solver or private model was used.

| Report | Collected | Passed | Failed | Errors / skips | Raw exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Candidate, all six modules](candidate.xml) | 1118 | 1118 | 0 | 0 / 0 | 0 |
| [Pre-fix new behavioural reproductions](pre-fix-reproduction.xml) | 208 | 160 | 48 | 0 / 0 | 1 |
| [Original-baseline new behavioural reproductions](baseline-endpoints.xml) | 208 | 88 | 120 | 0 / 0 | 1 |
| [Unchanged existing baseline QGIS/PyMesh](baseline-existing.xml) | 349 | 349 | 0 | 0 / 0 | 0 |

Candidate modules: 280 analytical depth, 55 extrema, 264 FV public-reader,
170 live-provider, 239 existing QGIS map-output and 110 existing PyMesh.
The pre-fix/baseline selected IDs are identical to passing candidate IDs.
The unchanged legacy baseline report is reused from the earlier valid run:
its source, runtime/package inventory and scope are unchanged. No existing
baseline failure is relabelled as a pass. Original raw reports remain local.

## Provenance and reproduction

- [Runtime and provider identity](candidate-runtime.json): QGIS 4.2.3,
  Python 3.12.15, Qt 6.11.0, GDAL 3.13.3; real initialized application and MDAL.
  Provider SHA256 and package inventory are included. QGIS's MDAL build does not
  expose a separate version API/export; no version was inferred.
- [Source/import provenance](source-provenance.json),
  [pre-fix runtime](pre-fix-runtime.json), [baseline runtime](baseline-runtime.json)
  and [reused baseline runtime](baseline-existing-runtime.json) distinguish the
  actual imported checkout, source SHA, clean production files, Git blob IDs,
  runtime-file hashes and copied test-module hashes.
- [Exact commands, raw exits and path aliases](commands.json). `QGIS_RUN` means
  the installation's `python-qgis.bat` plus the local runpy bootstrap which adds
  compatible target-directory dependencies after launcher initialization.
  Run baseline/pre-fix commands from their separate normal checkouts and the
  candidate command from its checkout. No worktree or virtual environment.
- [Summary](summary.json), all `*-ids.json`, and [SHA256 manifest](sha256.json).
  JUnit retains numerical assertion details, failure categories and test IDs.
  Only explicit machine roots/user temporary paths/host names are replaced by
  role aliases; repository-relative paths, observations and expectations remain.
  No raw machine paths or user/host identities are published.

The copied test harness on pre-fix/original baseline contains only test modules.
Production matches each recorded HEAD. The published source/test hashes explain
these instrumented reproductions rather than claiming new tests were present
in the historical baseline. The pre-fix copied module predates the extra ragged
case, which is outside the selected reproduction IDs; those 208 IDs are the same.

## Endpoint comparison

[Underlying analytical/Python/QGIS observations](endpoint-comparisons.json)
include raw values, physical counts, boundaries and QGIS block validity. The
candidate JUnit also records those observations as properties for both ordinary
and simultaneously missing-observation variants of all eight requests.
JSON encodes non-finite observations as the string `NaN`.

| Missing endpoint | Request | Analytical / Python | QGIS 4.2.3 |
| --- | --- | --- | --- |
| surface | depth 0-0.5 | NaN | NaN |
| surface | height 0-0.5 | 20 | NaN |
| surface | elevation -2 to 0 | 20 | NaN |
| surface | sigma 0-1 | NaN | NaN |
| bed | height 0-0.5 | NaN | NaN |
| bed | depth 0-0.5 | 10 | NaN |
| bed | elevation -2 to 0 | 10 | NaN |
| bed | sigma 0-1 | NaN | NaN |

Boundaries are `[NaN,-1,-2]` or `[0,-1,NaN]`; values `[10,20]`.
The genuine MDAL blocks retain two physical layers and missing boundaries.
Installed `.calculate(...)` returns valid NaN output blocks in all eight cases.
Python intentionally permits bounded layers for known-origin/absolute requests;
this is an explicit provider difference, **not universal parity**. Small Float64
fixtures retain rtol=atol=1e-12; public Float32 tolerances remain unchanged.

The inherited QGIS public-surface `cell_position` limitation remains documented
in the main W8 handoff. No general geometry/API or sibling implementation repair
is included. PR #23 stays draft and unmerged.
