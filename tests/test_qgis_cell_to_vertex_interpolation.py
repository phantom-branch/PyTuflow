"""W10: original QGIS cell-centred surface -> vertex compatibility tests.

This is a *real-QGIS/MDAL* acceptance module. It deliberately requires QGIS
at collection time: it is not a standalone-Python substitute for provider
validation. Initially reproduces the inherited unimplemented-weight gap.
"""
from pathlib import Path

import numpy as np
import pytest
from qgis.core import QgsApplication, QgsProviderRegistry

from pytuflow import NCMesh
from tests.test_numerical_fv_reader import _write_fv
from tests.test_qgis_surface_cell_positions import mixed_mesh


@pytest.fixture(scope="module")
def qapp():
    app = QgsApplication.instance()
    if app is None:
        app = QgsApplication([], False)
        app.initQgis()
    assert "mdal" in QgsProviderRegistry.instance().providerList()
    yield app


@pytest.fixture
def fv(qapp, tmp_path: Path) -> Path:
    path = tmp_path / "w10-cell-to-vertex.nc"
    _write_fv(path)
    return path


@pytest.mark.parametrize("driver", [
    "qgis geometry data extractor",
    "qgis geometry netcdf4",
    "qgis geometry h5py",
])
@pytest.mark.parametrize("data_type", ["tracer", "velocity", "salinity"])
def test_qgis_public_fv3d_cell_to_vertex_matches_native(fv, driver, data_type):
    qgis = NCMesh(fv, driver=driver)
    native = NCMesh(fv, driver="netcdf4")
    actual = qgis.surface(data_type, 0.0, averaging_method="sigma&0&1", to_vertex=True)
    expected = native.surface(data_type, 0.0, averaging_method="sigma&0&1", to_vertex=True)
    columns = ["x", "y", "value-x", "value-y"] if data_type == "velocity" else ["x", "y", "value"]
    assert len(actual) == len(expected) == 16
    np.testing.assert_allclose(actual[columns].to_numpy(dtype=float),
                               expected[columns].to_numpy(dtype=float),
                               rtol=1e-12, atol=1e-12, equal_nan=True)
    np.testing.assert_array_equal(actual["active"], expected["active"])
    np.testing.assert_array_equal(actual["active"], np.repeat([True, True, True, False], 4))


@pytest.mark.parametrize("driver", [
    "qgis geometry data extractor",
    "qgis geometry netcdf4",
    "qgis geometry h5py",
])
def test_qgis_public_2d_cell_to_vertex_matches_native(fv, driver):
    qgis = NCMesh(fv, driver=driver)
    native = NCMesh(fv, driver="netcdf4")
    actual = qgis.surface("water surface elevation", 0.0, to_vertex=True)
    expected = native.surface("water surface elevation", 0.0, to_vertex=True)
    assert actual.shape == expected.shape == (16, 4)
    np.testing.assert_allclose(actual[["x", "y", "value"]], expected[["x", "y", "value"]],
                               rtol=1e-12, atol=1e-12, equal_nan=True)
    np.testing.assert_array_equal(actual["active"], expected["active"])


def test_native_qgis_triangle_and_quad_vertex_mapping(qapp, mixed_mesh):
    geom = mixed_mesh
    nodes = geom.cell_nodes
    weights = geom.cell_to_vertex_weights()
    assert nodes.shape == weights.shape == (2, 4)
    assert geom.vertices.shape[0] == geom.lyr.dataProvider().vertexCount()
    assert np.issubdtype(nodes.dtype, np.integer)
    assert ((0 <= nodes) & (nodes < geom.vertices.shape[0])).all()
    assert np.isfinite(weights).all() and (weights >= 0).all()
    assert weights[0, 3] == 0.0, "Unused triangular corner must contribute zero"
    assert weights[1].min() > 0.0, "Every valid quadrilateral corner must contribute"
    normalised = np.bincount(nodes.ravel(), weights=weights.ravel(),
                             minlength=geom.vertices.shape[0])
    np.testing.assert_allclose(normalised, 1.0, rtol=1e-12, atol=1e-12)


def test_repeated_qgis_vertex_interpolation_is_stable(fv):
    reader = NCMesh(fv, driver="qgis geometry data extractor")
    first = reader.surface("tracer", 0.0, to_vertex=True)
    second = reader.surface("tracer", 0.0, to_vertex=True)
    np.testing.assert_allclose(first[["x", "y", "value"]], second[["x", "y", "value"]],
                               rtol=0, atol=0, equal_nan=True)
    np.testing.assert_array_equal(first["active"], second["active"])
