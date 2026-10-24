# W9 native Windows QGIS/MDAL evidence — 25 October 2026

Native acceptance passed. Raw machine-specific reports remain private; these JSON,
JUnit and logs replace machine roots and hostnames while retaining test identities,
outcomes, diagnostics and returned public surfaces.

## Frozen identities

- Pre-W9 baseline: `0679d9c758c07e786f23d552295366baa4bea10b`.
- Updated master merged without conflicts: `f1ceb77f74cb521f50be80209b929ecf0b58bf20`.
- Geometry candidate / merge checkpoint: `6c048477960bce2d9ca6e6956d725681027515a4`.
- Candidate with added cache regression: `3f0627d7bf5988019fe472e8f812594ba6d10309`.
- The evidence commit changes documentation/evidence only. Production geometry and
  all six affected regression modules match the geometry candidate byte for byte;
  the final provider module matches the cache-test checkpoint.

Both normal clones were clean after test execution, before adding this evidence.
No worktrees, virtual environments, bundled dependency edits or production fixes
were needed. The base update supplies missing `tests/ci` and
`ci/requirements-regression.txt`; shared W5 infrastructure is unmodified.

## Results

| Execution | Collected | Passed | Failed | Errors | Skipped | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Identical baseline reproduction | 13 | 0 | 13 | 0 | 0 | 1 |
| Identical candidate reproduction | 13 | 13 | 0 | 0 | 0 | 0 |
| Original dedicated provider module | 29 | 29 | 0 | 0 | 0 | 0 |
| Final provider + analytical modules | 37 | 37 | 0 | 0 | 0 | 0 |
| Baseline six affected modules | 1118 | 1118 | 0 | 0 | 0 | 0 |
| Candidate six affected modules | 1118 | 1118 | 0 | 0 | 0 | 0 |

The final focused run is 30 real-provider cases plus seven analytical cases.
All 13 baseline failures are exactly
`NotImplementedError: cell_position method not implemented yet.`; no other failure,
collection error or skip was observed. Baseline/candidate test identities match in
both paired executions. `summary.json` lists every test and failing baseline ID.

`before.xml`/`after.xml` and `before.log`/`after.log` retain the matched public
reproduction; candidate JUnit properties contain actual returned scalar/vector
surface tables. `before_after_reproduction.py` is the exact executed external test
module (saved under a non-discovery filename). It imports real source implementations
and the same public/generated FV fixture helper from each checkout. No production
function was copied or patched. `provider-committed.xml` and its log record the
37-case committed focused execution. Both complete 1118-case runs have separate
JUnit and logs.

## Runtime

QGIS **4.2.3**, CPython **3.12.15**, Qt **6.11.0**, GDAL **3.13.3**.
A real `QgsApplication` initialised and the provider registry includes `mdal`;
generated 2DM and FV NetCDF layers loaded through the native provider. MDAL
provider DLL SHA256 is
`6d0f860167c9bcdd3b23e6603c0da0bd7a561cdcf37de15d9bd1268d6744ea9b`.
There is no separate MDAL version API/export. Runtime inventories include source
origins, source SHA, provider identities and dependency versions for both clones.

NumPy 2.4.6, pandas 3.0.6, netCDF4 1.7.5.1.post1, h5py 3.14.0/HDF5 1.14.6,
PyVista 0.49.1, VTK 9.7.1, rasterio 1.5.2, GeoPandas 1.1.4, Shapely 2.1.2,
pytest 9.1.1 and pygltflib 1.16.5. The same installed QGIS launcher and existing
compatible additive dependency bootstrap served both sources; no package was installed.

## Independent geometry and public results

The triangle centroid is `(2/3, 2/3, 2)` from a uniform triangle's barycentric
integral. The irregular quadrilateral has XY centroid `(10 + 37/21, 20/21)`;
this follows from the signed shoelace moments and differs from the vertex mean.
Winding reversal and large projected offsets retain these values. Native 3D Z is
tested when supplied by MDAL; otherwise Z remains NaN. Local translation and
global/native coordinates are tested independently.

Generated FV faces have expected XY `(0.5,0.5)`, `(2.5,0.5)`, `(4.5,0.5)`,
`(6.5,0.5)`. At time zero, full-depth scalar salinity/tracer on the first face
are 15/10 and velocity components are 3/4. The second face has missing scalar/vector
observations, the third is zero and the fourth is inactive with zero data.
Active flags are `[true,true,true,false]`; the 2D water surface is zero. These
expectations pass for QGIS geometry with QGIS, netCDF4 and h5py data extraction.

The added provider test counts real centroid computations: two unique faces
compute twice, duplicate/repeated requests compute no further centroids, the native
mesh/spatial-index objects persist, and mutating a returned array preserves the cache.

## Commands

`QGIS_RUN` means the installed `python-qgis.bat` plus the existing W3 `run.py`
bootstrap, with Git on child PATH and compatible dependency targets propagated
to child PYTHONPATH. `REPO` is the relevant clean normal checkout. The original
local reproduction filename is `REPORTS/test_before_after.py`. Use fresh report
and temporary directories for every invocation.

```text
# In each baseline/candidate checkout; identical external reproduction source:
QGIS_RUN -m pytest -q REPORTS/test_before_after.py -o junit_family=xunit1 --basetemp=REPORTS/ROLE-tmp --junitxml=REPORTS/ROLE.xml
# The xunit1 format retains actual public surface tables as testcase properties.

# Candidate, committed cache-test checkpoint:
QGIS_RUN -m pytest -q tests/test_qgis_surface_cell_positions.py tests/test_qgis_centroid_math.py --basetemp=REPORTS/provider-committed-tmp --junitxml=REPORTS/provider-committed.xml

# In each baseline/candidate checkout:
QGIS_RUN -m pytest -q tests/test_map_output.py tests/test_map_output_pymesh.py tests/test_numerical_depth_averaging.py tests/test_numerical_mesh_reductions.py tests/test_numerical_fv_reader.py tests/test_numerical_qgis_reductions.py --basetemp=REPORTS/ROLE-regression-tmp --junitxml=REPORTS/ROLE-regression.xml
```

No warning suppression, tolerance widening or altered engineering expectations.
`to_vertex=True` interpolation remains inherited and outside W9 scope. No private
models, solvers, native benchmarks, release, merge or dependency repin.

## Hosted and review delivery

The corrected branch triggers separate Windows 3.12/3.14 centroid and numerical
workflows plus all W5 regression/wheel jobs. Consult PR #26's final acceptance
comment and exact-head check links for their terminal results and final Codex review.
Native acceptance alone does not make a pending hosted job pass.
