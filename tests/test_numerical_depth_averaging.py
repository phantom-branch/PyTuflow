"""Analytical numerical regressions for the imported PyTUFLOW averaging code.

The reference integrates a piecewise constant profile with exact rational
arithmetic.  It does not call the implementation or reproduce its vectorised
layer-overlap calculation.  Double-precision results use 1e-12 relative and
absolute tolerance: these small profiles need only a few arithmetic operations,
so looser tolerances could hide a materially incorrect layer contribution.
"""

from fractions import Fraction
from math import isnan

import numpy as np
import pytest

from pytuflow._outputs.pymesh.depth_averaging import get_method_func
from pytuflow._outputs.pymesh.depth_averaging.depth_averaging import (
    depth,
    elevation,
    multi_level,
    sigma,
    single_level,
)


RTOL = 1e-12
ATOL = 1e-12


def _fraction(value: float) -> Fraction:
    return Fraction(str(value))


def _analytical_average(
    boundaries: list[float],
    values: list[float],
    elevations: tuple[float, float],
) -> float:
    """Integrate exact antiderivatives of constant-valued layer rectangles.

    Two independent primitives accumulate value and valid vertical measure
    below a requested elevation.  Their differences give the integral over
    the requested interval.  Missing layer values contribute to neither.
    """
    rectangles = []
    for top, bottom, value in zip(boundaries, boundaries[1:], values):
        if isnan(top) or isnan(bottom) or isnan(value) or top <= bottom:
            continue
        rectangles.append((_fraction(bottom), _fraction(top), _fraction(value)))

    def primitive(at: Fraction, weighted: bool) -> Fraction:
        total = Fraction(0)
        for bottom, top, value in rectangles:
            if at <= bottom:
                continue
            if at >= top:
                area = top - bottom
            else:
                area = at - bottom
            total += area * value if weighted else area
        return total

    low, high = sorted(_fraction(value) for value in elevations)
    measure = primitive(high, False) - primitive(low, False)
    if not measure:
        return np.nan
    return float((primitive(high, True) - primitive(low, True)) / measure)


def _assert_average(actual: np.ndarray, expected: list[float]) -> None:
    assert actual.shape == (len(expected),)
    np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL, equal_nan=True)


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ((0.0, 0.5), 10.0),
        ((0.2, 0.8), 10.0),
        ((0.0, 1.0), 10.0),
        ((0.0, 1.5), 40.0 / 3.0),
    ],
)
@pytest.mark.parametrize("as_row", [False, True], ids=["one-dimensional", "row"])
def test_first_layer_reported_regressions(bounds, expected, as_row):
    zlevels = np.array([0.0, -1.0, -2.0])
    values = np.array([10.0, 20.0])
    if as_row:
        zlevels = zlevels[None, :]
        values = values[None, :]
    _assert_average(depth(list(bounds), zlevels, values, True), [expected])
    method = get_method_func(f"depth&{bounds[0]}&{bounds[1]}")
    _assert_average(method(zlevels, values), [expected])


@pytest.mark.parametrize(
    ("elevations", "expected"),
    [
        ((5.0, 4.5), 2.0),
        ((3.75, 2.25), 8.0),
        ((0.5, -1.5), 20.0),
        ((4.5, -0.5), 11.0),  # (0.5 * 2 + 3 * 8 + 1.5 * 20) / 5
        ((5.0, -2.0), 86.0 / 7.0),
        ((8.0, 6.0), np.nan),
    ],
)
def test_independent_integral_known_areas(elevations, expected):
    actual = _analytical_average([5.0, 4.0, 1.0, -2.0], [2.0, 8.0, 20.0], elevations)
    np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL, equal_nan=True)


@pytest.mark.parametrize("from_top", [True, False], ids=["depth", "height"])
@pytest.mark.parametrize(
    "bounds",
    [
        (0.0, 0.5),  # first layer
        (0.2, 0.8),
        (1.25, 2.75),  # interior layer from the surface
        (4.5, 6.5),  # final layer from the surface
        (0.5, 5.5),  # partial first/interior/final contributions
        (1.0, 4.0),  # exact layer boundaries
        (4.0, 7.0),
        (0.0, 7.0),
        (0.5, 1.5),
        (-1.0, 0.5),  # clipped at the surface/bed
        (6.0, 10.0),
        (-10.0, 10.0),
        (8.0, 10.0),  # wholly outside the water column
        (-3.0, -1.0),
        (0.0, 0.0),  # zero-width intervals have no averaging measure
        (1.0, 1.0),
        (7.0, 7.0),
        (5.5, 0.5),  # reversed request
    ],
)
def test_nonuniform_depth_against_exact_integral(bounds, from_top):
    boundaries = [5.0, 4.0, 1.0, -2.0]
    values = [2.0, 8.0, 20.0]
    elevations = tuple(5.0 - value if from_top else -2.0 + value for value in bounds)
    expected = _analytical_average(boundaries, values, elevations)
    actual = depth(list(bounds), np.array(boundaries), np.array(values), from_top)
    _assert_average(actual, [expected])


@pytest.mark.parametrize(
    "bounds",
    [
        (5.0, 4.5),
        (4.8, 4.2),
        (3.75, 2.25),
        (0.5, -1.5),
        (4.5, -0.5),
        (5.0, -2.0),
        (-0.5, 4.5),
        (6.0, 4.5),
        (-1.0, -5.0),
        (10.0, -10.0),
        (8.0, 6.0),
        (-3.0, -5.0),
        (4.5, 4.5),
        (4.0, 4.0),
    ],
)
def test_elevation_against_exact_integral(bounds):
    boundaries = [5.0, 4.0, 1.0, -2.0]
    values = [2.0, 8.0, 20.0]
    expected = _analytical_average(boundaries, values, bounds)
    _assert_average(elevation(list(bounds), np.array(boundaries), np.array(values)), [expected])


@pytest.mark.parametrize("bounds", [(0.0, 0.5), (0.2, 0.8), (0.5, 5.5), (0.0, 7.0), (5.5, 0.5)])
def test_depth_elevation_height_sigma_physical_equivalence(bounds):
    zlevels = np.array([5.0, 4.0, 1.0, -2.0])
    values = np.array([2.0, 8.0, 20.0])
    elevations = (5.0 - bounds[0], 5.0 - bounds[1])
    expected = _analytical_average(zlevels.tolist(), values.tolist(), elevations)
    heights = [7.0 - value for value in bounds]
    _assert_average(depth(list(bounds), zlevels, values, True), [expected])
    _assert_average(depth(heights, zlevels, values, False), [expected])
    _assert_average(elevation(list(elevations), zlevels, values), [expected])
    _assert_average(sigma([height / 7.0 for height in heights], zlevels, values), [expected])


@pytest.mark.parametrize("from_top", [True, False])
def test_same_depth_pair_broadcasts_across_exactly_two_columns(from_top):
    zlevels = np.array([[0.0, -1.0, -2.0], [5.0, 4.0, 3.0]])
    values = np.array([[10.0, 20.0], [30.0, 60.0]])
    expected = [40.0 / 3.0, 40.0] if from_top else [50.0 / 3.0, 50.0]
    _assert_average(depth([0.0, 1.5], zlevels, values, from_top), expected)


@pytest.mark.parametrize("from_top", [True, False])
def test_independent_depth_ranges_per_column(from_top):
    zlevels = np.array([[5.0, 4.0, 1.0, -2.0], [5.0, 3.0, 0.0, -2.0]])
    values = np.array([[2.0, 8.0, 20.0], [1.0, 5.0, 11.0]])
    bounds = np.array([[0.25, 0.75], [1.0, 6.0]])
    expected = []
    for boundaries, row_values, interval in zip(zlevels, values, bounds):
        elevations = tuple(5.0 - value if from_top else -2.0 + value for value in interval)
        expected.append(_analytical_average(boundaries.tolist(), row_values.tolist(), elevations))
    _assert_average(depth(bounds, zlevels, values, from_top), expected)


@pytest.mark.parametrize("from_top", [True, False])
@pytest.mark.parametrize("datum", [0.0, 1e6, 1e9, 1e16])
def test_relative_depth_weights_are_invariant_to_vertical_datum(from_top, datum):
    # The request covers 1.8 m of the first layer and 0.1 m of the second.
    # Translating the elevations must not round the fractional depth request.
    zlevels = np.array([datum, datum - 2.0, datum - 4.0])
    values = np.array([10.0, 20.0])
    expected = 200.0 / 19.0 if from_top else 370.0 / 19.0
    _assert_average(depth([0.2, 2.1], zlevels, values, from_top), [expected])


@pytest.mark.parametrize(
    "uri",
    [
        "depth&0&0.5", "height&0&0.5", "elevation&4.5&3.5", "sigma&0.2&0.8",
        "singlelevel?dir=top&1", "singlelevel?dir=bottom&1",
        "multilevel?dir=top&1&1", "multilevel?dir=bottom&1&1",
    ],
)
def test_single_layer_column(uri):
    _assert_average(get_method_func(uri)(np.array([5.0, 3.0]), np.array([7.0])), [7.0])


@pytest.mark.parametrize(
    "uri",
    [
        "depth&0&2", "height&0&2", "elevation&0&-2", "sigma&0&1",
        "multilevel?dir=top&1&2", "multilevel?dir=bottom&1&2",
    ],
)
@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([10.0, np.nan], 10.0),
        ([np.nan, 20.0], 20.0),
        ([10.0, 0.0], 5.0),
        ([0.0, np.nan], 0.0),
        ([np.nan, np.nan], np.nan),
    ],
)
def test_missing_layers_exclude_both_value_and_thickness(uri, values, expected):
    _assert_average(get_method_func(uri)(np.array([0.0, -1.0, -2.0]), np.array(values)), [expected])


@pytest.mark.parametrize(
    "uri",
    [
        "depth&0&2", "height&0&2", "elevation&0&-2", "sigma&0&1",
        "multilevel?dir=top&1&2", "multilevel?dir=bottom&1&2",
    ],
)
@pytest.mark.parametrize("all_missing", [False, True])
def test_masked_values_have_same_meaning_as_nan(uri, all_missing):
    values = np.ma.array([10.0, 999.0], mask=[all_missing, True])
    expected = np.nan if all_missing else 10.0
    _assert_average(get_method_func(uri)(np.array([0.0, -1.0, -2.0]), values), [expected])


@pytest.mark.parametrize(
    "uri",
    [
        "depth&0&2", "height&0&2", "elevation&0&-2", "sigma&0&1",
        "multilevel?dir=top&1&2", "multilevel?dir=bottom&1&2",
    ],
)
@pytest.mark.parametrize("all_missing", [False, True])
def test_masked_geometry_cannot_contribute_an_unbounded_layer(uri, all_missing):
    # Without the bottom boundary, only the upper layer has a known thickness;
    # the second observation cannot be included merely because its value exists.
    zlevels = np.ma.array([0.0, -1.0, -2.0], mask=[all_missing, all_missing, True])
    values = np.array([10.0, 1000.0])
    # A missing bed makes height and sigma indeterminate. Surface-relative
    # depth, absolute elevation and ordinals can still use the bounded layer.
    expected = np.nan if all_missing or uri.startswith(("height", "sigma")) else 10.0
    _assert_average(get_method_func(uri)(zlevels, values), [expected])


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("sigma&0&1", 12.0 / 5.0),
        ("depth&1.25&3.5", 10.0 / 3.0),
        ("multilevel?dir=top&1&3", 4.0 / 3.0),
        ("singlelevel?dir=top&3", np.nan),
    ],
)
def test_qgis_documented_missing_layer_fixture(uri, expected):
    # QGIS 4.0.1 testqgsmesh3daveraging.cpp uses this profile in its sigma,
    # depth ("25to45"), multilevel ("1to3") and single-level ("3") cases:
    # https://github.com/qgis/QGIS/blob/1ccf690c2e0b8126253bcac2997398deac4ea150/tests/src/core/testqgsmesh3daveraging.cpp
    # The missing third volume retains its position, not its averaging measure.
    zlevels = np.array([-1.0, -2.0, -2.5, -4.0, -5.0])
    values = np.array([1.0, 2.0, np.nan, 4.0])
    _assert_average(get_method_func(uri)(zlevels, values), [expected])


@pytest.mark.parametrize("from_top", [True, False])
def test_single_level_position_is_not_renumbered_by_missing_data(from_top):
    zlevels = np.array([3.0, 2.0, 1.0, 0.0])
    values = np.array([np.nan, 20.0, 30.0]) if from_top else np.array([30.0, 20.0, np.nan])
    _assert_average(single_level(1, zlevels, values, from_top), [np.nan])
    _assert_average(single_level(2, zlevels, values, from_top), [20.0])
    _assert_average(multi_level([1, 2], zlevels, values, from_top), [20.0])


@pytest.mark.parametrize("from_top", [True, False])
@pytest.mark.parametrize("levels", [[2, 3], [3, 2], [2, 20], [4, 20]])
def test_multilevel_order_and_column_clipping(from_top, levels):
    zlevels = np.array([5.0, 4.0, 1.0, -2.0])
    values = np.array([2.0, 8.0, 20.0])
    if levels[0] == 4:
        expected = np.nan
    else:
        expected = 14.0 if from_top else 6.5
    _assert_average(multi_level(levels, zlevels, values, from_top), [expected])


@pytest.mark.parametrize(
    "uri",
    [
        "depth&0&10", "height&0&10", "elevation&10&-10", "sigma&0&1",
        "multilevel?dir=top&1&3", "multilevel?dir=bottom&1&3",
    ],
)
def test_padded_short_dry_and_all_missing_columns(uri):
    zlevels = np.array([
        [0.0, -1.0, -2.0, np.nan],
        [4.0, 3.0, np.nan, np.nan],
        [0.0, 0.0, 0.0, np.nan],
        [np.nan, np.nan, np.nan, np.nan],
    ])
    values = np.array([
        [10.0, 20.0, np.nan],
        [30.0, np.nan, np.nan],
        [10.0, 20.0, np.nan],
        [10.0, 20.0, 30.0],
    ])
    _assert_average(get_method_func(uri, layer_counts=np.array([2, 1, 2, 3]))(zlevels, values), [15.0, 30.0, np.nan, np.nan])


@pytest.mark.parametrize("from_top", [True, False])
def test_geometry_padding_does_not_renumber_a_missing_real_layer(from_top):
    zlevels = np.array([np.nan, 3.0, 2.0, 0.0, np.nan])
    values = np.array([np.nan, np.nan, 40.0, np.nan])
    expected_first = np.nan if from_top else 40.0
    expected_second = 40.0 if from_top else np.nan
    # Leading padding is ambiguous with a missing physical boundary/value;
    # carry its known extent rather than deriving it from valid geometry.
    _assert_average(single_level(1, zlevels, values, from_top, layer_start=1, layer_counts=2), [expected_first])
    _assert_average(single_level(2, zlevels, values, from_top, layer_start=1, layer_counts=2), [expected_second])


@pytest.mark.parametrize("uri", ["depth&0.2&1.5", "height&0.2&1.5", "elevation&-0.2&-1.5", "sigma&0.1&0.75"])
def test_averaging_preserves_caller_arrays(uri):
    zlevels = np.array([[0.0, -1.0, -2.0]])
    values = np.array([[10.0, np.nan]])
    original_zlevels = zlevels.copy()
    original_values = values.copy()
    get_method_func(uri)(zlevels, values)
    np.testing.assert_array_equal(zlevels, original_zlevels)
    np.testing.assert_array_equal(values, original_values)


@pytest.mark.parametrize("from_top", [True, False])
@pytest.mark.parametrize("masked", [False, True])
@pytest.mark.parametrize("missing_observation", [False, True])
def test_missing_physical_boundary_does_not_renumber_ordinals(from_top, masked, missing_observation):
    z = np.array([0., -1., -2.])
    v = np.array([10., 20.])
    boundary, layer = (0, 0) if from_top else (-1, -1)
    if masked:
        z = np.ma.array(z, mask=[from_top, False, not from_top])
    else:
        z[boundary] = np.nan
    if missing_observation:
        v[layer] = np.nan
    # Direct-call default columns are top-aligned; no known boundary/value may
    # cause the second physical layer to become ordinal one.
    _assert_average(single_level(1, z, v, from_top), [np.nan])
    _assert_average(single_level(2, z, v, from_top), [20. if from_top else 10.])
    _assert_average(single_level(1, z, v, from_top, layer_counts=2), [np.nan])
    _assert_average(single_level(2, z, v, from_top, layer_counts=2), [20. if from_top else 10.])


@pytest.mark.parametrize("from_top", [True, False])
def test_explicit_column_counts_keep_padding_separate_from_missing_boundaries(from_top):
    z = np.array([[np.nan, -1., -2., np.nan], [0., -1., np.nan, np.nan]])
    v = np.array([[np.nan, 20., np.nan], [30., np.nan, np.nan]])
    expected = [np.nan, 30.] if from_top else [20., 30.]
    _assert_average(single_level(1, z, v, from_top, layer_counts=np.array([2, 1])), expected)


# Prescribed geometric expectations; no production overlap/anchor calculation.
ENDPOINT_REQUESTS = [
    ("surface", "depth&0&0.5", np.nan),
    ("surface", "height&0&0.5", 20.),
    ("surface", "elevation&-2&0", 20.),
    ("surface", "sigma&0&1", np.nan),
    ("bed", "height&0&0.5", np.nan),
    ("bed", "depth&0&0.5", 10.),
    ("bed", "elevation&-2&0", 10.),
    ("bed", "sigma&0&1", np.nan),
]


@pytest.mark.parametrize("missing,uri,expected", ENDPOINT_REQUESTS)
@pytest.mark.parametrize("masked", [False, True])
@pytest.mark.parametrize("missing_observation", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_missing_endpoint_requests_keep_physical_origins(missing, uri, expected, masked, missing_observation, reverse):
    z = np.array([0., -1., -2.])
    mask = [missing == "surface", False, missing == "bed"]
    z = np.ma.array(z, mask=mask) if masked else np.where(mask, np.nan, z)
    v = np.array([10., 20.])
    if missing_observation:
        # Remove the only fully bounded observation as well.
        v[1 if missing == "surface" else 0] = np.nan
        expected = np.nan
    if reverse:
        method, a, b = uri.split("&")
        uri = f"{method}&{b}&{a}"
    _assert_average(get_method_func(uri)(z, v), [expected])


@pytest.mark.parametrize("uri,expected", [
    ("depth&0&0.5", [10., np.nan, 10., np.nan, 10.]),
    ("height&0&0.5", [20., 20., np.nan, np.nan, 10.]),
    ("sigma&0&1", [15., np.nan, np.nan, np.nan, 10.]),
    ("elevation&-2&0", [15., 20., 10., np.nan, 10.]),
    ("multilevel?dir=bottom&1&1", [20., 20., np.nan, np.nan, 10.]),
])
def test_explicit_extent_controls_endpoints_and_excludes_finite_padding(uri, expected):
    z = np.array([[999., 0., -1., -2., -999.],
                  [999., np.nan, -1., -2., -999.],
                  [999., 0., -1., np.nan, -999.],
                  [999., 0., -1., -2., -999.],
                  [999., 0., -1., -2., -999.]])
    v = np.tile([999., 10., 20., 999.], (5, 1))
    original = z.copy(), v.copy()
    _assert_average(get_method_func(uri, layer_counts=np.array([2, 2, 2, 0, 1]), layer_start=1)(z, v), expected)
    np.testing.assert_array_equal(z, original[0])
    np.testing.assert_array_equal(v, original[1])


@pytest.mark.parametrize("uri", ["depth&0&4", "height&4&0", "sigma&1&0", "elevation&-4&0"])
@pytest.mark.parametrize("masked", [False, True])
def test_interior_missing_geometry_preserves_known_physical_endpoints(uri, masked):
    z = np.array([0., -1., -2., -3., -4.])
    z = np.ma.array(z, mask=[False, False, True, False, False]) if masked else np.where(np.arange(5) == 2, np.nan, z)
    # Only the first and last rectangles are bounded; their equal areas give 25.
    _assert_average(get_method_func(uri)(z, np.array([10., 20., 30., 40.])), [25.])


@pytest.mark.parametrize("uri", ["depth&0&1", "height&0&1", "sigma&0&1", "elevation&-2&0"])
def test_empty_physical_column_has_no_contribution(uri):
    _assert_average(get_method_func(uri)(np.array([0.]), np.array([])), [np.nan])
    _assert_average(get_method_func(uri, layer_counts=0)(np.array([999., 0., -1.]), np.array([999., 10.])), [np.nan])


@pytest.mark.parametrize("start,count", [(-1, 1), (0, -1), (0, 3), (0.5, 1), (0, 1.5)])
@pytest.mark.parametrize("uri", ["depth&0&1", "height&0&1", "sigma&0&1", "elevation&-2&0"])
def test_invalid_physical_extent_is_explicit(uri, start, count):
    with pytest.raises(ValueError, match="physical layer"):
        get_method_func(uri, layer_start=start, layer_counts=count)(np.array([0., -1., -2.]), np.array([10., 20.]))
