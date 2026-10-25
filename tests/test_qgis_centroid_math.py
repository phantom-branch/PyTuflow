"""Standalone geometry maths tests; QGIS provider integration has its own lane."""
import numpy as np
import pytest

from pytuflow._outputs.pymesh.mesh_geom.qgismesh_geom import _face_centroid


def test_triangle_centroid_and_native_z():
    triangle = np.array([[0., 0., 1.], [2., 0., 2.], [0., 2., 3.]])
    np.testing.assert_allclose(_face_centroid(triangle), [2/3, 2/3, 2.], rtol=0, atol=1e-12)


def test_irregular_quad_area_centroid_not_vertex_average():
    quad = np.array([[10., 0., 0.], [14., 0., 0.], [13., 2., 0.], [10., 2., 0.]])
    np.testing.assert_allclose(_face_centroid(quad), [10 + 37/21, 20/21, 0.], rtol=0, atol=1e-12)
    assert not np.isclose(_face_centroid(quad)[0], quad[:, 0].mean())


@pytest.mark.parametrize("flip", [False, True])
def test_offset_and_winding_independent(flip):
    quad = np.array([[10., 0., 0.], [14., 0., 0.], [13., 2., 0.], [10., 2., 0.]])
    if flip:
        quad = quad[::-1]
    offset = [650000., 7450000., 12.]
    np.testing.assert_allclose(_face_centroid(quad + offset), _face_centroid(quad) + offset,
                               rtol=0, atol=1e-9)


def test_unknown_native_elevation_remains_nan():
    tri = np.array([[0., 0., np.nan], [2., 0., 2.], [0., 2., 3.]])
    result = _face_centroid(tri)
    np.testing.assert_allclose(result[:2], [2/3, 2/3], rtol=0, atol=1e-12)
    assert np.isnan(result[2])


@pytest.mark.parametrize("coords", [
    [[0., 0., 0.], [1., 1., 0.], [2., 2., 0.]],
    [[0., 0., 0.], [np.nan, 1., 0.], [2., 0., 0.]],
])
def test_invalid_geometry_fails(coords):
    with pytest.raises(ValueError):
        _face_centroid(np.array(coords))
