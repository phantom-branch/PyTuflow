"""W10: provider-independent contract for existing corner-angle interpolation.

Real QGIS/MDAL public surfaces are exercised separately. These cases verify
the same weighting rule on mixed faces, masked observations and wet/dry changes.
"""
import numpy as np
import pytest

from pytuflow._outputs.pymesh.mesh_geom.qgismesh_geom import _angle_weights
from pytuflow._outputs.pymesh.cell_data_mixin import _qgis_cell_to_vertex


@pytest.fixture
def geometry():
    # CCW triangle 0-1-2, rectangle 1-4-5-3; shared corner is node 1.
    # Triangle angle at node 1 is pi/4; rectangle angle is pi/2.
    vertices = np.array([[0., 0., np.nan], [2., 0., np.nan],
                         [0., 2., np.nan], [2., 2., np.nan],
                         [4., 0., np.nan], [4., 2., np.nan],
                         [9., 9., np.nan]])
    nodes = np.array([[0, 1, 2, 2], [1, 4, 5, 3]])
    weights = _angle_weights(vertices, nodes, np.array([True, False]))
    return nodes, weights, vertices.shape[0]


def test_mixed_triangle_quad_shared_vertex_angle_reference(geometry):
    nodes, weights, count = geometry
    np.testing.assert_allclose(weights[0, 3], 0.)
    assert weights.shape == (2, 4)
    np.testing.assert_allclose(
        np.bincount(nodes.ravel(), weights=weights.ravel(), minlength=count)[:6], 1.,
        rtol=1e-12, atol=1e-12,
    )
    np.testing.assert_allclose(weights[0, 1], 1 / 3, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(weights[1, 0], 2 / 3, rtol=1e-12, atol=1e-12)


def test_two_valid_cells_angle_weight_shared_value(geometry):
    nodes, weights, count = geometry
    value, wet = _qgis_cell_to_vertex(np.array([3., 9.]), [True, True], nodes, weights, count)
    np.testing.assert_allclose(value[:6], [3., 7., 3., 9., 9., 9.], rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(wet, [True] * 6 + [False])
    assert value[6] == 0.


def test_missing_wet_cell_is_excluded_without_nan_poisoning(geometry):
    nodes, weights, count = geometry
    values, wet = _qgis_cell_to_vertex([3., np.nan], [True, True], nodes, weights, count)
    np.testing.assert_allclose(values[[0, 1, 2]], 3.)
    assert np.isnan(values[[3, 4, 5]]).all()
    np.testing.assert_array_equal(wet, [True] * 6 + [False])


def test_masked_vector_requires_joint_validity(geometry):
    nodes, weights, count = geometry
    data = np.ma.array([[3., 4.], [99., 9.]], mask=[[False, False], [False, True]])
    values, wet = _qgis_cell_to_vertex(data, [True, True], nodes, weights, count)
    np.testing.assert_allclose(values[[0, 1, 2]], [[3., 4.]] * 3)
    assert np.isnan(values[[3, 4, 5]]).all()
    assert values.shape == (count, 2)
    assert wet.shape == (count,)


def test_actual_zero_valid_and_dry_cells_remain_distinct(geometry):
    nodes, weights, count = geometry
    values, wet = _qgis_cell_to_vertex([0., 9.], [True, False], nodes, weights, count)
    np.testing.assert_allclose(values[[0, 1, 2]], 0.)
    np.testing.assert_allclose(values[[3, 4, 5, 6]], 0.)
    np.testing.assert_array_equal(wet, [True, True, True, False, False, False, False])


def test_wet_and_validity_change_between_time_steps(geometry):
    nodes, weights, count = geometry
    data = np.array([[3., 9.], [np.nan, 9.]])
    values, wet = _qgis_cell_to_vertex(data, [[True, True], [True, False]], nodes, weights, count)
    assert values.shape == (2, count) and wet.shape == (2, count)
    np.testing.assert_allclose(values[0, 1], 7.)
    assert np.isnan(values[1, [0, 1, 2]]).all()
    np.testing.assert_allclose(values[1, [3, 4, 5]], 0.)
    np.testing.assert_array_equal(wet[1], [True, True, True, False, False, False, False])


def test_vector_preserves_single_frame_shape(geometry):
    nodes, weights, count = geometry
    values, wet = _qgis_cell_to_vertex(np.array([[[3., 4.]], [[9., 12.]]]),
                                      [True, True], nodes, weights, count)
    assert values.shape == (count, 1, 2)
    np.testing.assert_allclose(values[1, 0], [7., 28/3], rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(wet[:6], [True] * 6)


@pytest.mark.parametrize("wet", [[True], [[True, False, True]]])
def test_invalid_face_mask_dimensions_are_rejected(geometry, wet):
    nodes, weights, count = geometry
    with pytest.raises(ValueError):
        _qgis_cell_to_vertex(np.array([3., 9.]), wet, nodes, weights, count)
