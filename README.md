# PyTuflow

![](docs/assets/TUFLOW.png)

**PyTUFLOW** is a library that acts as an API for your TUFLOW model. It allows easy interaction with the model results,
contains a number of useful utilities for building TUFLOW models, and contains some useful parsers for files within the
TUFLOW eco-system.

## Documentation

The documentation for PyTUFLOW can be found at: https://docs.tuflow.com/pytuflow/

## Installation

You can install PyTUFLOW using pip.

```bash
pip install pytuflow
```

## Dependencies

PyTUFLOW supports Python **3.12–3.14** in this fork. The default `pip install pytuflow`
installs the declared dependencies, including **netCDF4**, **Shapely**, NumPy,
pandas, h5py, PyVista, GeoPandas and rasterio. These are not optional extras,
and no lightweight `pytuflow[core]` distribution is currently provided.

- **GDAL/OGR Python bindings**: Additional native bindings are needed for
  GDAL-specific GIS functionality, including some `GisInput` operations.
  Install bindings compatible with your runtime's native GDAL library.
- **QGIS/MDAL**: Required for QGIS-backed map/mesh operations. The dedicated
  `tests/test_map_output.py` suite requires a real QGIS runtime and the MDAL
  provider. Other supported XMDF and NCMesh readers provide Python-based
  extraction without requiring QGIS, so QGIS is **not** a universal prerequisite
  for those file formats.

On Windows, use a compatible GDAL distribution where native bindings are needed.
A QGIS/OSGeo4W Python interpreter is distinct from the ordinary Python launcher.
See the [QGIS environment guide](https://docs.tuflow.com/pytuflow/examples/working_with_tuflow_outputs/#qgis-environment).

Changing extras cannot remove packages already required by the default
installation. A smaller core distribution would require a separately reviewed
compatibility/dependency migration.

## Quickstart

The best place to get started is the [Load and Run a TUFLOW Model](https://docs.tuflow.com/pytuflow/examples/tcf_load_and_run/) example, or to browse through the other
[Examples](https://docs.tuflow.com/pytuflow/examples/).

## Development

The code base can be cloned from GitHub:

```bash
git clone https://github.com/TUFLOW-Support/PyTuflow.git --recurse-submodules
```

The pinned `requirements-dev.txt` is a broad environment snapshot: it
includes documentation, notebook and profiling tooling as well as test
dependencies, so it is **not** a minimal runtime requirements file. For the
focused tests, install the default package with pytest and build tooling:

```bash
python -m pip install -e . pytest build
```

For reproducing the complete pinned development environment, use:

```bash
python -m pip install -r requirements-dev.txt
```

GDAL Python bindings are supplied separately when required and must match the
installed native GDAL library. Do not overwrite QGIS/OSGeo4W's bundled stack
with unrelated pip wheels.

### Building the Docs

To build the documentation, navigate to the `docs` folder and run:

```bash
# from the pytuflow project root directory
cd docs
.\make.bat dirhtml
```

To serve the documentation locally, you can use (on Windows):

```bash
.\serve.ps1
```

### Running Tests

Tests are under the repository-level `tests/` directory. Use the installed
Python interpreter (and the dependencies it needs) without replacing QGIS's
bundled native libraries.

```bash
# From the repository root: focused package API regression tests
python -m pytest -q tests/test_package_api_quality.py

# Standalone original-library suites
python -m pytest -q tests/test_time_series.py tests/test_map_output_pymesh.py
python -m pytest -q tests/tmf tests/fm_lib
```

Some original FM/TMF tests have documented inherited reference/fixture failures;
the [baseline comparison contract](ci/README.md) retains them as actual
failures while rejecting newly introduced ones.

For QGIS-backed mesh tests, **use the real QGIS Python launcher** with an
initialised QGIS application and MDAL provider:

```bash
python -m pytest -q tests/test_map_output.py
```

The repository's [general regression and installed-wheel workflow](ci/README.md)
checks Windows Python 3.12 and 3.14 independently; use its `--group qgis`
runner for strict baseline comparisons under the real QGIS environment.

### Building the Package

```bash
# from the pytuflow project root directory
python -m build --wheel
```

## Local implementation review notes

- [Eager source completeness fixes](eager_source_completeness_fixes.md): eager corrections,
  shared API additions and downstream consumer scope, recorded separately for upstream review.
- [Deferred reference implementation](deferred_file_resolution_implementation.md): deferred parsing status.

These notes describe local implementation work awaiting review, not released functionality.

## LICENCE

MIT LICENCE (see `LICENSE` file for details).
