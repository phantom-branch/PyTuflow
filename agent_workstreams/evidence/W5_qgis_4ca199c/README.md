# W5 native QGIS/MDAL acceptance - 24 October 2026

**Passed. PR #19 is ready to be marked non-draft and considered for merging.**
The owner retains that decision; no merge, release or draft conversion occurred.
This evidence update changes no production, harness, test, workflow or dependency.

| Role | Repository | SHA |
| --- | --- | --- |
| Upstream | https://github.com/TUFLOW-Support/PyTuflow.git | `cf908cc922ca8448ed6002834877b0b377329eae` |
| Fork baseline | https://github.com/phantom-branch/PyTuflow.git | `e162c04330d24c37bee3ade94479cc4602651060` |
| Candidate and unchanged harness | https://github.com/phantom-branch/PyTuflow.git | `4ca199c55d6d388a0019128332e8f0adafdace93` |

All three independent `--group qgis` runs executed **all of
`tests/test_map_output.py`**. Each collected/passed **239 tests**, with **zero
failures/errors/skips/xfails/xpasses** and raw exit **0**. Exact collected IDs and
per-phase outcomes are retained in each JSON; JUnit IDs/counts were verified.
Failing IDs: **none**. No subset, fake provider, weakened expectation or warning
filter was used. A local bootstrap-directory utility named `inspect.py` was
renamed to avoid shadowing Python's standard library; no harness/package change
was required. Independent child capability reports and the corrected preflight
are the authoritative runtime evidence.

## Underlying reports

| Source | JSON | JUnit | Complete captured log |
| --- | --- | --- | --- |
| Upstream | [report](upstream/report.json), [group](upstream/qgis.json) | [XML](upstream/qgis.xml) | [log](upstream/qgis.log) |
| Baseline | [report](baseline/report.json), [group](baseline/qgis.json) | [XML](baseline/qgis.xml) | [log](baseline/qgis.log) |
| Candidate | [report](candidate/report.json), [group](candidate/qgis.json) | [XML](candidate/qgis.xml) | [log](candidate/qgis.log) |

- [Strict candidate comparison](candidate-comparison.json): passed, raw exit 0,
  no new/changed failures, removed tests or unexpected skips.
- [Upstream self-completeness](upstream-completeness.json): passed, raw exit 0.
- [Independent historical upstream-to-fork comparison](upstream-comparison.json):
  passed, raw exit 0; no differences in the selected QGIS group.
- [Machine-readable summary](summary.json), [commands](commands.json),
  [runtime/provider identity](runtime.json), [preflight](preflight-capabilities.json)
  and [checksums](sha256.json).

All three reports have identical environments, harness SHA/hash and collected
IDs, `harness.dirty: false`, and `source.checkout_unchanged: true`. Their actual
`pytuflow.__file__` entries distinguish independent source snapshots. The same two
recorded test-only FM helper overlays were applied identically; no production or
QGIS test was overlaid. The complete normal source/harness checkouts remained
unchanged throughout execution. Snapshots were ordinary temporary directories,
not virtual environments or Git worktrees.

## Actual installed runtime

QGIS **4.2.3**, CPython **3.12.15**, Qt **6.11.0**, GDAL **3.13.3**. A real
`QgsApplication` initialized and its provider registry contained **mdal**; every
required dependency imported successfully. The supplied OSGeo4W launcher and
previously validated W3 bootstrap/dependency targets were reused. No QGIS/Python,
Qt/GDAL/NumPy/pandas installation or replacement was performed.

NumPy 2.4.6, pandas 3.0.6, netCDF4 1.7.5.1.post1, h5py 3.14.0 / HDF5 1.14.6,
PyVista 0.49.1, VTK 9.7.1, rasterio 1.5.2, GeoPandas 1.1.4, Shapely 2.1.2,
pytest 9.1.1 and pygltflib 1.16.5 are recorded alongside the full report inventory.
The MDAL provider binary SHA256 is
`6d0f860167c9bcdd3b23e6603c0da0bd7a561cdcf37de15d9bd1268d6744ea9b`.
No separate MDAL version API/export is available; no version was invented.

Only machine-specific roots, user temporary directories and host identifiers
are replaced by explicit aliases. Source SHAs, repository-relative paths,
commands, test identities, all result phases and useful diagnostics are retained.
Raw unmodified reports remain local. SHA256 describes canonical repository LF
bytes; Windows checkout CRLF conversion does not change that identity.

## Hosted checks, review and ownership

[Exact-candidate hosted run 40076415079](https://github.com/phantom-branch/PyTuflow/actions/runs/40076415079)
was rechecked: **all five jobs remain successful** at `4ca199c`. Those standalone
and installed-wheel jobs are distinct from these locally executed QGIS reports.
The existing [Codex review](https://github.com/phantom-branch/PyTuflow/pull/19#issuecomment-6381759592)
completed on that SHA with no findings and zero unresolved threads. This
containing handoff/evidence update changes no tested implementation file.

W5's required QGIS/MDAL acceptance boundary is now closed for the installed
runtime. No remaining W5 implementation/validation task was identified. Existing
TMF/Flood Relief Arch reference failures and current-dependency compatibility
remain separately recorded production/reference work; passing W5 comparisons
never relabel those raw failures as passes. Feature owners #16/#17/#23 and the
not-started package workstream #22 retain their boundaries.

No sibling implementation, existing deferred/graph gate, production pin, private
NAS model, solver or benchmark was changed/used. #22 was not started. No merge,
release, package publication or draft conversion was performed.
