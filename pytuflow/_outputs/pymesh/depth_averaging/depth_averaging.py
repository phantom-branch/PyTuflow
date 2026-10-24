"""Layer-thickness averages for the Python FV mesh reader.

NaN and masked result values are absent observations, not physical zero. Their
overlap is excluded from both the weighted sum and contributing thickness,
matching the supported QGIS averaging provider. No positive valid overlap gives
NaN. See agent_workstreams/W8_numerical_result_reductions.md for policy evidence
and the deliberately retained provider differences.
"""

import numpy as np


def _profiles(zlevels: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalise scalar profiles without discarding a source missing-data mask."""
    zlevels = np.atleast_2d(np.ma.asarray(zlevels, dtype=float).filled(np.nan))
    values = np.atleast_2d(np.ma.asarray(values, dtype=float).filled(np.nan))
    if zlevels.ndim != 2 or values.ndim != 2 or zlevels.shape[1] != values.shape[1] + 1:
        raise ValueError("profiles require one more layer boundary than values per row")
    rows = max(zlevels.shape[0], values.shape[0])
    zlevels = np.broadcast_to(zlevels, (rows, zlevels.shape[1]))
    values = np.broadcast_to(values, (rows, values.shape[1]))
    return zlevels, values


def _pairs(ranges: np.ndarray | list[float], rows: int, name: str) -> np.ndarray:
    ranges = np.asarray(ranges, dtype=float)
    if ranges.ndim == 1:
        ranges = ranges.reshape(1, -1)
    if ranges.ndim != 2 or ranges.shape[1] != 2:
        raise ValueError(f"{name} must contain exactly two values per row")
    return np.broadcast_to(ranges, (rows, 2))


def _column_limits(zlevels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Find surface/bed through padding, without all-NaN reduction warnings."""
    valid = ~np.isnan(zlevels)
    top = np.max(zlevels, axis=1, where=valid, initial=-np.inf)
    bottom = np.min(zlevels, axis=1, where=valid, initial=np.inf)
    top[~valid.any(axis=1)] = np.nan
    bottom[~valid.any(axis=1)] = np.nan
    return top, bottom


def _overlap(zlevels: np.ndarray, top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
    """Physical intersection of each layer with one requested vertical interval."""
    layer_top = np.maximum(zlevels[:, :-1], zlevels[:, 1:])
    layer_bottom = np.minimum(zlevels[:, :-1], zlevels[:, 1:])
    return np.maximum(
        np.minimum(layer_top, top[:, None]) - np.maximum(layer_bottom, bottom[:, None]),
        0.,
    )


def _weighted_average(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    valid = ~np.isnan(values) & (weights > 0)
    weights = np.where(valid, weights, 0.)
    products = np.zeros(values.shape, dtype=float)
    np.multiply(values, weights, out=products, where=valid)
    numerator = products.sum(axis=1)
    denominator = weights.sum(axis=1)
    result = np.full(numerator.shape, np.nan)
    np.divide(numerator, denominator, out=result, where=denominator > 0)
    return result


def multi_level(levels: list[int] | np.ndarray, zlevels: np.ndarray, values: np.ndarray, from_top: bool,
                *, layer_counts=None, layer_start=0) -> np.ndarray:
    """Average selected physical layer ordinals, excluding missing observations."""
    zlevels, values = _profiles(zlevels, values)
    rows, boundary_count = zlevels.shape
    levels = np.sort(_pairs(levels, rows, "levels"), axis=1)
    if values.shape[1] == 0:
        return np.full(rows, np.nan)

    valid_layers = ~np.isnan(zlevels[:, :-1]) & ~np.isnan(zlevels[:, 1:])
    thickness = np.where(valid_layers, np.abs(np.diff(zlevels, axis=1)), 0.)
    # Readers know physical extents independently of missing observations and
    # boundaries. Direct callers default to the full supplied physical column;
    # padding requires explicit extents because NaNs alone cannot identify it.
    start = np.broadcast_to(np.asarray(layer_start), (rows,))
    if layer_counts is None:
        layer_counts = boundary_count - 1 - start
    counts = np.broadcast_to(np.asarray(layer_counts), (rows,))
    physical_cols = np.arange(boundary_count - 1)[None, :]
    physical = (physical_cols >= start[:, None]) & (physical_cols < (start + counts)[:, None])
    cols = physical_cols - start[:, None] if from_top else (start + counts - 1)[:, None] - physical_cols
    idx1 = np.clip(levels[:, 0] - 1, 0, boundary_count - 1)
    idx2 = np.clip(levels[:, 1] - 1, 0, boundary_count - 1)
    selected = physical & (cols >= idx1[:, None]) & (cols <= idx2[:, None])
    return _weighted_average(values, np.where(selected, thickness, 0.))


def single_level(level: int, zlevels: np.ndarray, values: np.ndarray, from_top: bool,
                 *, layer_counts=None, layer_start=0) -> np.ndarray:
    return multi_level([level, level], zlevels, values, from_top,
                       layer_counts=layer_counts, layer_start=layer_start)


def depth(dist: np.ndarray | list[float], zlevels: np.ndarray, values: np.ndarray, from_top: bool) -> np.ndarray:
    """Average over depth below surface or height above bed, clipped to the column.

    A pair is shared by all rows, including a two-row input. Explicit (N, 2)
    arrays select a different interval per row. A single endpoint, or (N, 1)
    endpoints, selects from zero; the legacy length-N endpoint form is retained
    when it cannot be confused with a shared pair.
    """
    zlevels, values = _profiles(zlevels, values)
    rows = zlevels.shape[0]
    dist = np.asarray(dist, dtype=float)
    if dist.size == 1:
        dist = np.array([[0., dist.item()]])
    elif dist.ndim == 1 and dist.size != 2 and dist.size == rows:
        dist = np.column_stack((np.zeros(rows), dist))
    elif dist.ndim == 2 and dist.shape[1] == 1:
        dist = np.column_stack((np.zeros(dist.shape[0]), dist[:, 0]))
    dist = np.sort(_pairs(dist, rows, "dist"), axis=1)
    top, bottom = _column_limits(zlevels)
    # Intersect in relative coordinates so small requested depths retain their
    # precision even when the absolute elevation datum is large.
    if from_top:
        zlevels = zlevels - top[:, None]
        interval_top = -dist[:, 0]
        interval_bottom = -dist[:, 1]
    else:
        zlevels = zlevels - bottom[:, None]
        interval_top = dist[:, 1]
        interval_bottom = dist[:, 0]
    return _weighted_average(values, _overlap(zlevels, interval_top, interval_bottom))


def elevation(elev: list[float], zlevels: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Average the physical overlap with an absolute elevation interval."""
    zlevels, values = _profiles(zlevels, values)
    elev = np.sort(_pairs(elev, zlevels.shape[0], "elev"), axis=1)
    return _weighted_average(values, _overlap(zlevels, elev[:, 1], elev[:, 0]))


def sigma(fracs: list[float], zlevels: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Average fractional column heights: zero is the bed and one the surface."""
    zlevels, values = _profiles(zlevels, values)
    fracs = _pairs(fracs, zlevels.shape[0], "fracs")
    top, bottom = _column_limits(zlevels)
    depths = (top - bottom)[:, None] * fracs
    return depth(depths, zlevels, values, from_top=False)
