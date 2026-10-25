"""Real-QGIS regression lane for original mesh face positions and public surfaces.

Requires initialized QGIS/MDAL and netCDF4. Absence is a collection error,
not a skip or a simulated provider pass.
"""
from pathlib import Path

import numpy as np
import pytest
from qgis.core import QgsApplication, QgsMeshLayer, QgsProviderRegistry

from pytuflow import NCMesh
from pytuflow._outputs.pymesh.mesh_geom.qgismesh_geom import (
    QgisMeshGeometry, _face_centroid,
)
from pytuflow._outputs.pymesh.transform import Transform2D
from tests.test_numerical_fv_reader import _write_fv

RTOL = ATOL = 1e-12


@pytest.fixture(scope="module")
def qapp():
    app = QgsApplication.instance()
    if app is None:
        app = QgsApplication([], False)
        app.initQgis()
    assert "mdal" in QgsProviderRegistry.instance().providerList()
    yield app  # Do not exitQgis() while providers might still be retained.


@pytest.fixture
def mixed_mesh(qapp, tmp_path: Path) -> QgisMeshGeometry:
    path = tmp_path / "irregular.2dm"
    path.write_text(
        "MESH2D\n"
        "E3T 1 1 2 3 1\n"
        "E4Q 2 4 5 6 7 1\n"
        "ND 1 0 0 1\nND 2 2 0 2\nND 3 0 2 3\n"
        "ND 4 10 0 0\nND 5 14 0 0\n"
        "ND 6 13 2 0\nND 7 10 2 0\n",
        encoding="ascii",
    )
    layer = QgsMeshLayer(str(path), "irregular", "mdal")
    assert layer.isValid(), "MDAL must load the generated triangle/quad 2DM"
    assert layer.dataProvider().faceCount() == 2
    geom = QgisMeshGeometry(path)
    geom.lyr = layer
    geom.load()
    return geom


def test_independent_triangle_and_irregular_quad_centroids():
    triangle = [[0., 0., 1.], [2., 0., 2.], [0., 2., 3.]]
    # Trapezoid (x=10..14), unlike vertex mean it has a nontrivial centroid.
    quad = [[10., 0., 0.], [14., 0., 0.], [13., 2., 0.], [10., 2., 0.]]
    for coords, wanted in [
        (triangle, [2 / 3, 2 / 3, 2]),
        (quad, [10 + 37 / 21, 20 / 21, 0]),
    ]:
        actual = _face_centroid(np.array(coords))
        np.testing.assert_allclose(actual, wanted, rtol=RTOL, atol=ATOL)
        np.testing.assert_allclose(_face_centroid(np.array(coords)[::-1]), wanted, rtol=RTOL, atol=ATOL)
        offset = np.array([600000., 7500000., 0.])
        np.testing.assert_allclose(_face_centroid(np.array(coords) + offset), actual + offset, atol=1e-9)
    assert not np.isclose(_face_centroid(np.array(quad))[0], np.mean(np.array(quad)[:, 0]))


@pytest.mark.parametrize("bad", [
    np.array([[0., 0., 0.], [1., 1., 0.], [2., 2., 0.]]),
    np.array([[0., 0., 0.], [np.nan, 1., 0.], [2., 0., 0.]]),
])
def test_invalid_face_geometry_rejected(bad):
    with pytest.raises(ValueError):
        _face_centroid(bad)


def test_face_positions_preserve_shape_and_native_face_order(mixed_mesh):
    geom = mixed_mesh
    expected_xy = [[2 / 3, 2 / 3], [10 + 37 / 21, 20 / 21]]
    all_faces = geom.cell_position(slice(None))
    assert all_faces.shape == (2, 3)
    np.testing.assert_allclose(all_faces[:, :2], expected_xy, rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(geom.cell_position(1)[:, :2], [expected_xy[1]], rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(geom.cell_position([1, 0, 1])[:, :2],
                               [expected_xy[1], expected_xy[0], expected_xy[1]], rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(geom.cell_position(np.array([1, 0]))[:, :2], expected_xy[::-1], rtol=RTOL, atol=ATOL)
    assert geom.cell_position([]).shape == (0, 3)
    assert geom.cell_position(slice(0, 0)).shape == (0, 3)
    np.testing.assert_allclose(geom.cell_position(slice(None, None, -1))[:, :2],
                               expected_xy[::-1], rtol=RTOL, atol=ATOL)
    # Native mesh vertices may be 2-D or 3-D. Unknown Z is explicitly NaN;
    # when MDAL supplies it, Z is the area-weighted native mesh elevation.
    geom.init_spatial_index()
    if all(geom._mesh.vertex(v).is3D() for v in geom._mesh.face(0)):
        np.testing.assert_allclose(all_faces[0, 2], 2, rtol=RTOL, atol=ATOL)
    else:
        assert np.isnan(all_faces[0, 2])
    # Cached positions must remain stable across repeated calls.
    np.testing.assert_allclose(geom.cell_position([1, 0]), all_faces[::-1], equal_nan=True)


def test_local_scope_applies_explicit_transform(mixed_mesh):
    geom = mixed_mesh
    native = geom.cell_position(slice(None))
    geom.trans = Transform2D(translate=[123., -456.])
    local = geom.cell_position(slice(None), scope="local")
    np.testing.assert_allclose(local[:, :2], native[:, :2] + [123., -456.], rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(local[:, 2], native[:, 2], equal_nan=True)
    np.testing.assert_allclose(geom.cell_position(slice(None), scope="global"), native, equal_nan=True)


def test_face_cache_reuses_native_mesh_and_returns_independent_arrays(mixed_mesh, monkeypatch):
    from pytuflow._outputs.pymesh.mesh_geom import qgismesh_geom

    geom = mixed_mesh
    original = qgismesh_geom._face_centroid
    calls = []

    def counted(vertices):
        calls.append(vertices.copy())
        return original(vertices)

    monkeypatch.setattr(qgismesh_geom, "_face_centroid", counted)
    first = geom.cell_position([1, 0, 1])
    native_mesh, spatial_index = geom._mesh, geom._si
    assert len(calls) == 2
    first[:] = -999
    again = geom.cell_position([0, 1])
    assert len(calls) == 2
    assert geom._mesh is native_mesh and geom._si is spatial_index
    np.testing.assert_allclose(again[:, :2], [[2 / 3, 2 / 3], [10 + 37 / 21, 20 / 21]],
                               rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("bad", [-1, 2, [0, 2]])
def test_out_of_range_faces_fail_explicitly(mixed_mesh, bad):
    with pytest.raises(IndexError):
        mixed_mesh.cell_position(bad)


@pytest.mark.parametrize("bad", [0.5, True, False, np.bool_(True), np.bool_(False), [True], [False], [0, 1.2]])
def test_noninteger_face_ids_fail_explicitly(mixed_mesh, bad):
    with pytest.raises(TypeError):
        mixed_mesh.cell_position(bad)


def test_bad_scope_fails(mixed_mesh):
    with pytest.raises(ValueError, match="scope"):
        mixed_mesh.cell_position(0, scope="unknown")


@pytest.fixture
def fv(qapp, tmp_path):
    path = tmp_path / "public-surfaces.nc"
    _write_fv(path)
    lyr = QgsMeshLayer(str(path), "fv", "mdal")
    assert lyr.isValid() and lyr.dataProvider().faceCount() == 4
    return path


@pytest.mark.parametrize("driver", [
    "qgis geometry data extractor",
    "qgis geometry netcdf4",
    "qgis geometry h5py",
])
@pytest.mark.parametrize("data_type,columns,first", [
    ("salinity", ["value"], [15.]),
    ("tracer", ["value"], [10.]),
    ("velocity", ["value-x", "value-y"], [3., 4.]),
])
def test_public_fv_3d_surface_real_qgis_geometry(fv, driver, data_type, columns, first):
    result = NCMesh(fv, driver=driver)
    frame = result.surface(data_type, 0., averaging_method="sigma&0&1", to_vertex=False)
    assert frame.shape == (4, 2 + len(columns) + 1)
    np.testing.assert_allclose(frame[["x", "y"]], [[0.5, 0.5], [2.5, 0.5],
                                                 [4.5, 0.5], [6.5, 0.5]], atol=ATOL)
    np.testing.assert_array_equal(frame["active"], [True, True, True, False])
    np.testing.assert_allclose(frame.loc[0, columns], first, rtol=RTOL, atol=ATOL)
    assert frame.loc[1, columns].isna().all()
    np.testing.assert_allclose(frame.loc[2, columns], [0.] * len(columns), atol=ATOL)
    np.testing.assert_allclose(frame.loc[3, columns], [0.] * len(columns), atol=ATOL)


@pytest.mark.parametrize("driver", [
    "qgis geometry data extractor",
    "qgis geometry netcdf4",
    "qgis geometry h5py",
])
def test_public_2d_face_surface_real_qgis_geometry(fv, driver):
    result = NCMesh(fv, driver=driver)
    frame = result.surface("water surface elevation", 0., to_vertex=False)
    assert frame.shape == (4, 4)
    np.testing.assert_allclose(frame[["x", "y"]], [[0.5, 0.5], [2.5, 0.5],
                                                 [4.5, 0.5], [6.5, 0.5]], atol=ATOL)
    np.testing.assert_array_equal(frame["active"], [True, True, True, False])
    np.testing.assert_allclose(frame["value"], [0., 0., 0., 0.], atol=ATOL)
