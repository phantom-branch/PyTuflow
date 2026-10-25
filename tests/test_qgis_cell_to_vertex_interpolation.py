"""W10: original QGIS cell-centred surface -> vertex compatibility tests.

This is a *real-QGIS/MDAL* acceptance module. It deliberately requires QGIS
at collection time: it is not a standalone-Python substitute for provider
validation. Initially reproduces the inherited unimplemented-weight gap.
"""
from pathlib import Path
from math import atan2, pi

import numpy as np
import pytest
from qgis.core import QgsApplication, QgsProviderRegistry, QgsMeshLayer
from netCDF4 import Dataset

from pytuflow._outputs.pymesh.mesh_geom.qgismesh_geom import QgisMeshGeometry
from pytuflow._outputs.pymesh.cell_data_mixin import _qgis_cell_to_vertex
from pytuflow._outputs.pymesh.transform import Transform2D

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
    weights = geom.cell_to_vertex_weights()  # Lazily creates native face mapping.
    nodes = geom.cell_nodes
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


def test_connected_triangle_and_quad_real_mdal_angle_parity(qapp, tmp_path):
    """Shared vertex must integrate two *different* corner angles."""
    path = tmp_path / "shared-triangle-quad.2dm"
    path.write_text(
        "MESH2D\n"
        "E3T 1 1 2 3 1\n"
        "E4Q 2 2 5 6 4 1\n"
        "ND 1 0 0 0\nND 2 2 0 0\nND 3 0 2 0\n"
        "ND 4 3 2 0\nND 5 4 0 0\nND 6 4 2 0\n"
        "ND 7 9 9 0\n",
        encoding="ascii",
    )
    lyr = QgsMeshLayer(str(path), "shared", "mdal")
    assert lyr.isValid() and lyr.dataProvider().faceCount() == 2
    geom = QgisMeshGeometry(path)
    geom.lyr = lyr
    geom.load()
    weights = geom.cell_to_vertex_weights()
    nodes = geom.cell_nodes
    assert nodes.shape == weights.shape == (2, 4)
    assert geom.vertices.shape[0] == lyr.dataProvider().vertexCount()
    # Independently: triangle corner is 45 degrees, irregular quad corner
    # between (2, 0) and (1, 2) is atan2(2, 1), not a right angle.
    triangle_angle, quad_angle = pi / 4, atan2(2, 1)
    total_angle = triangle_angle + quad_angle
    np.testing.assert_allclose(weights[0, 1], triangle_angle / total_angle, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(weights[1, 0], quad_angle / total_angle, rtol=1e-12, atol=1e-12)
    assert len(geom.vertices) == 7  # Include a native isolated vertex.
    assert weights[0, 3] == 0.
    active_values, active = _qgis_cell_to_vertex(
        np.array([3., 9.]), [True, True], nodes, weights, len(geom.vertices),
    )
    expected = (3 * triangle_angle + 9 * quad_angle) / total_angle
    np.testing.assert_allclose(active_values[1], expected, rtol=1e-12, atol=1e-12)
    assert active[1]
    assert active_values[6] == 0 and not active[6]
    dry_values, dry_active = _qgis_cell_to_vertex(
        np.array([3., 9.]), [True, False], nodes, weights, len(geom.vertices),
    )
    np.testing.assert_allclose(dry_values[1], 3., rtol=1e-12, atol=1e-12)
    assert dry_active[1]
    np.testing.assert_allclose(dry_values[[3, 4, 5]], 0.)
    assert not dry_active[[3, 4, 5]].any()
    missing_values, missing_active = _qgis_cell_to_vertex(
        np.array([3., np.nan]), [True, True], nodes, weights, len(geom.vertices),
    )
    np.testing.assert_allclose(missing_values[1], 3., rtol=1e-12, atol=1e-12)
    assert missing_active[1] and np.isnan(missing_values[[3, 4, 5]]).all()


def test_qgis_vertex_position_scope_and_cached_subset(qapp, mixed_mesh):
    geom = mixed_mesh
    global_pos = geom.vertex_position(slice(None), get_z=True)
    assert global_pos.shape[1] == 3
    geom.trans = Transform2D(translate=[17., -21.])
    local_pos = geom.vertex_position(slice(None), scope='local')
    np.testing.assert_allclose(local_pos[:, :2], global_pos[:, :2] + [17., -21.],
                               rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(local_pos[:, 2], global_pos[:, 2], equal_nan=True)
    # Cache path must respect scope and requested ordering, not return global.
    reverse = geom.vertex_position([2, 1, 0], scope='local', get_z=True)
    np.testing.assert_allclose(reverse, local_pos[[2, 1, 0]], equal_nan=True)
    np.testing.assert_allclose(geom.vertex_position(slice(None), scope='global'),
                               global_pos, equal_nan=True)
    assert geom._vertex_positions_cache is not None
    for selector, indices in [(2, [2]), ((2, 0, 2, 1), [2, 0, 2, 1]),
                              (np.array([[2, 0], [2, 1]]), [2, 0, 2, 1])]:
        np.testing.assert_allclose(geom.vertex_position(selector, get_z=True),
                                   global_pos[indices], equal_nan=True)
    # Also exercise provider extraction without a full-mesh cache, including
    # duplicates: chunked bed values must retain the caller's vertex order.
    geom._vertex_positions_cache = None
    subset = [2, 0, 2, 1]
    np.testing.assert_allclose(geom.vertex_position(subset, get_z=True),
                               global_pos[subset], equal_nan=True)
    for selector, indices in [(2, [2]), ((2, 0, 2, 1), [2, 0, 2, 1])]:
        np.testing.assert_allclose(geom.vertex_position(selector, get_z=True),
                                   global_pos[indices], equal_nan=True)


@pytest.mark.parametrize("driver", [
    "qgis geometry data extractor",
    "qgis geometry netcdf4",
    "qgis geometry h5py",
])
def test_qgis_vertex_wet_state_not_reused_between_times(qapp, tmp_path, driver):
    path = tmp_path / "changing-wet.nc"
    _write_fv(path)
    with Dataset(path, "a") as nc:
        state = nc["stat"][:]
        state[1] = [0, 1, 1, 0]
        nc["stat"][:] = state
    reader = NCMesh(path, driver=driver)
    native = NCMesh(path, driver="netcdf4")
    first = reader.surface("tracer", 0., to_vertex=True)
    second = reader.surface("tracer", 1., to_vertex=True)
    first_expected = native.surface("tracer", 0., to_vertex=True)
    second_expected = native.surface("tracer", 1., to_vertex=True)
    for result, expected in ((first, first_expected), (second, second_expected)):
        np.testing.assert_allclose(result[["x", "y", "value"]],
                                   expected[["x", "y", "value"]],
                                   rtol=1e-12, atol=1e-12, equal_nan=True)
        np.testing.assert_array_equal(result["active"], expected["active"])
    np.testing.assert_array_equal(first["active"].to_numpy()[:8],
                                  [True] * 8)
    np.testing.assert_array_equal(second["active"].to_numpy()[:8],
                                  [False] * 4 + [True] * 4)
