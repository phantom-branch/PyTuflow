# W10 genuine QGIS/MDAL acceptance

Windows acceptance on 25 October 2026. [Sanitized JUnit, logs, before/after outputs and reproduction scripts](https://gist.github.com/Chain-Frost/0a098cf631b6feae1b38e3ba67c3bf6a).

- Unchanged current-master baseline: `0aba6b79db0ecc4922b910867f2c96905acb8d3a`.
- Initial W10 head: `279ef67927bcc494262a057fad1e3b32d8d9a003`.
- Corrected source/test checkpoint: `af3cede953e625c365641293915aad6b47d46919`.
- This evidence delivery changes only documentation/records; `provenance.json` contains exact production/test SHA256 hashes.

| Run | Collected | Passed | Failed | Errors | Skips | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial native W10 | 19 | 18 | 1 | 0 | 0 | 1 |
| Corrected native W10 | 19 | 19 | 0 | 0 | 0 | 0 |
| Baseline affected modules | 1148 | 1148 | 0 | 0 | 0 | 0 |
| Candidate affected modules + analytical W10 | 1157 | 1157 | 0 | 0 | 0 | 0 |

All 1148 baseline test identities match passing candidate cases; nine additional analytical cases pass. `summary.json` retains every identity/outcome. The identical external public reproduction uses real `NCMesh(..., driver='qgis geometry data extractor').surface('tracer',0.,to_vertex=True)` and the same generated FV NetCDF file. Baseline reaches inherited `PyMeshGeometry.cell_to_vertex_weights` and raises NotImplementedError; candidate returns 16 vertex rows. `before.json`/`after.json` retain the exception and actual public data.

The initial native failure demonstrated sorted provider bed Z attached to unsorted XY. The correction restores requested vertex order (including duplicates) after chunk extraction and repairs the full-slice cache condition. Tests cover both the cache and direct provider extraction paths. The interpolation rule, native non-QGIS reader and W8/W9 numerical contracts remain unchanged.

Real native W10 cases exercise all three QGIS geometry/extractor combinations, 2D and depth-averaged FV-3D scalar/vector parity with the native NetCDF reader, changing wet states over two times, repeated calls, zero/missing values and coordinate scope. The generated connected triangle/irregular-quad has shared angles pi/4 and atan2(2,1): weights 0.4149953542513913 and 0.5850046457486088, giving 6.5100278744916515 for scalar observations 3 and 9. An isolated native vertex is retained and inactive; the unused triangle slot has zero weight. The separate rectangle analytical reference gives 7. Missing/masked vectors and dry/valid normalization have explicit standalone checks; no alternative interpolation algorithm is introduced.

Runtime: installed OSGeo4W QGIS 4.2.3, CPython 3.12.15, Qt 6.11.0, GDAL 3.13.3, pandas 3.0.6, NumPy 2.4.6. The unchanged existing bootstrap adds compatible h5py 3.14.0 and other pre-existing extras; no dependency was installed/replaced. Genuine QgsApplication and MDAL registered. MDAL provider SHA256 `6d0f860167c9bcdd3b23e6603c0da0bd7a561cdcf37de15d9bd1268d6744ea9b`; no separate version API/export. Runtime, source/import and six NCMesh/XMDF provider controls are retained without stubs. No venv/worktree, private model, solver, benchmark, merge, release or upstream push.

Commands below run through the installed `python-qgis.bat` plus the existing bootstrap, from each clean normal source checkout. Machine paths/hostnames in public artifacts are redacted.

```text
<QGIS launcher/bootstrap> -m pytest -q tests/test_qgis_cell_to_vertex_interpolation.py --junitxml=<reports>/native.xml
<QGIS launcher/bootstrap> -m pytest -q tests/test_qgis_surface_cell_positions.py tests/test_numerical_qgis_reductions.py tests/test_numerical_fv_reader.py tests/test_numerical_depth_averaging.py tests/test_numerical_mesh_reductions.py tests/test_map_output.py tests/test_map_output_pymesh.py --junitxml=<reports>/baseline-affected.xml
<QGIS launcher/bootstrap> -m pytest -q tests/test_qgis_surface_cell_positions.py tests/test_numerical_qgis_reductions.py tests/test_numerical_fv_reader.py tests/test_numerical_depth_averaging.py tests/test_numerical_mesh_reductions.py tests/test_map_output.py tests/test_map_output_pymesh.py tests/test_qgis_vertex_angle_math.py --junitxml=<reports>/candidate-affected.xml
```

The initial native failure and inherited baseline failure are expected negative evidence. All final native commands exited zero. Hosted final-head W10/W9/W8/W7/W5 and final Codex review are independent gates; their latest status is recorded on PR #32, and this native evidence alone is not permission to merge.
