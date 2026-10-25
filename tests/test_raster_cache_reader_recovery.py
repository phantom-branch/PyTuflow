"""Bounded Grid/NCGrid surface cache and exception-safe reader ownership."""

from collections import OrderedDict

import numpy as np
import pytest
from netCDF4 import Dataset

from pytuflow import Grid, NCGrid


def make_nc(tmp_path, count=12):
    path = tmp_path / "cache.nc"
    with Dataset(path, "w") as nc:
        for axis in ("x", "y"):
            nc.createDimension(axis, 3)
            coord = nc.createVariable(axis, "f8", (axis,))
            coord.axis = axis.upper()
            coord[:] = [0.5, 1.5, 2.5]
        nc.createDimension("time", count)
        time = nc.createVariable("time", "f8", ("time",))
        time.units = "hours since 2000-01-01 00:00:00"
        time[:] = np.arange(count)
        water = nc.createVariable("water_level", "f8", ("time", "y", "x"))
        water[:] = np.arange(count * 9, dtype=float).reshape(count, 3, 3)
        nc.createDimension("static_time", 1)
        level = nc.createVariable("maximum_water_level", "f8", ("static_time", "y", "x"))
        level[:] = 100.
        bed = nc.createVariable("bed_level", "f8", ("y", "x"))
        bed[:] = -5.
    return path


def expected(index):
    return np.arange(index * 9, (index + 1) * 9, dtype=float).reshape(3, 3)


@pytest.mark.parametrize("count", [2, 12, 120])
def test_one_surface_does_not_preallocate_time_cube(tmp_path, count):
    reader = NCGrid(make_nc(tmp_path, count))
    np.testing.assert_array_equal(reader.surface("water level", 0)["value"].to_numpy().reshape(3, 3), expected(0))
    cache = reader._surface_cache["water level"]
    assert isinstance(cache, OrderedDict)
    assert list(cache) == [0]
    assert cache[0].shape == (3, 3)
    assert "water level" not in reader._cached_data
    assert sum(x.nbytes for x in cache.values()) == 9 * 8


def test_lru_hits_and_evicts_in_access_order(tmp_path, monkeypatch):
    reader = NCGrid(make_nc(tmp_path), memory_budget_bytes=4 * 9 * 8)
    original = reader._value
    reads = []

    def record(dtype, idx):
        reads.append(idx)
        return original(dtype, idx)

    monkeypatch.setattr(reader, "_value", record)
    with reader._open():
        for idx in [0, 1, 2, 3]:
            np.testing.assert_array_equal(reader._surface("water level", idx), expected(idx))
        reader._surface("water level", 0)
        assert reads == [0, 1, 2, 3]
        reader._surface("water level", 4)
        assert reads == [0, 1, 2, 3, 4]
    assert list(reader._surface_cache["water level"]) == [2, 3, 0, 4]
    assert reader._surface_cache_bytes <= reader.memory_budget_bytes


@pytest.mark.parametrize("selector,indexes", [
    ([5, 1, 5, 0], [5, 1, 5, 0]),
    (np.array([3, 0, 3]), [3, 0, 3]),
    (slice(None), list(range(12))),
    (slice(0, 0), []),
    (slice(5, 0, -2), [5, 3, 1]),
    (slice(None, None, -1), list(range(11, -1, -1))),
    (slice(0, 5, 2), [0, 2, 4]),
    (np.array([True, False] * 6), [0, 2, 4, 6, 8, 10]),
])
def test_selectors_preserve_order_repetition_and_shape(tmp_path, selector, indexes):
    reader = NCGrid(make_nc(tmp_path))
    with reader._open():
        observed = reader._surface("water level", selector)
    if len(indexes) == 0:
        assert observed.shape == (0, 3, 3)
    else:
        reference = np.stack([expected(i) for i in indexes])
        if len(indexes) == 1:
            reference = reference[0]
        np.testing.assert_array_equal(observed, reference)
    assert reader._surface_cache_bytes <= reader.memory_budget_bytes


@pytest.mark.parametrize("bad", [[12], [-13], np.array([1.5]), [[1, 2]]])
def test_invalid_time_selectors_raise(tmp_path, bad):
    reader = NCGrid(make_nc(tmp_path))
    with reader._open(), pytest.raises(IndexError):
        reader._surface("water level", bad)


def test_static_grid_uses_one_slice_and_repeated_reads(tmp_path, monkeypatch):
    reader = NCGrid(make_nc(tmp_path))
    original = reader._value
    reads = []

    def record(dtype, idx):
        reads.append(idx)
        return original(dtype, idx)

    monkeypatch.setattr(reader, "_value", record)
    with reader._open():
        for i in range(3):
            surface = reader._surface("bed level", -1)
            np.testing.assert_array_equal(surface, np.full((3, 3), -5.))
    assert len(reads) == 1
    assert list(reader._surface_cache["bed level"]) == [None]


def test_explicit_load_into_memory_keeps_all_timesteps(tmp_path):
    reader = NCGrid(make_nc(tmp_path))
    reader.surface("water level", 1)
    assert reader._surface_cache["water level"]
    reader.load_into_memory("water level")
    assert reader._cached_data["water level"].shape == (12, 3, 3)
    assert "water level" not in reader._surface_cache
    with reader._open():
        np.testing.assert_array_equal(reader._surface("water level", [10, 0, 10]), np.stack([
            expected(10), expected(0), expected(10)
        ]))


def test_memory_grid_point_and_time_series_use_resident_data():
    data = np.stack([np.full((2, 2), i + 1., dtype=float) for i in range(3)])
    reader = Grid({
        "dx": 1., "ncol": 2, "nrow": 2,
        "data_type": "water level", "timesteps": [0., 1., 2.],
        "data": data,
    })
    assert reader.data_point((0.5, 0.5), "water level", 1.0) == 2.
    series = reader.time_series((0.5, 0.5), "water level")
    np.testing.assert_array_equal(series.iloc[:, 0].to_numpy(), [1., 2., 3.])


def test_failure_closes_owned_reader_and_retry_succeeds(tmp_path, monkeypatch):
    reader = NCGrid(make_nc(tmp_path))
    original = reader._value
    failure = RuntimeError("synthetic extraction failure")
    seen = []

    def fail_once(dtype, idx):
        if not seen:
            seen.append(True)
            raise failure
        return original(dtype, idx)

    monkeypatch.setattr(reader, "_value", fail_once)
    with pytest.raises(RuntimeError, match="synthetic extraction failure"):
        reader.surface("water level", 0.)
    assert reader._nc is None
    assert reader.data_point((0.5, 0.5), "water level", 0.) == 0.
    assert reader._nc is None


def test_nested_context_keeps_outer_reader_alive(tmp_path):
    reader = NCGrid(make_nc(tmp_path))
    with reader._open() as outer:
        with reader._open() as inner:
            assert inner is outer
            assert reader._nc is outer
        assert outer.isopen()
        assert reader._nc is outer
        with pytest.raises(RuntimeError, match="nested"):
            with reader._open():
                raise RuntimeError("nested")
        assert outer.isopen()
    assert reader._nc is None
    assert not outer.isopen()


def test_explicit_reader_survives_nested_failure_until_close(tmp_path):
    reader = NCGrid(make_nc(tmp_path))
    reader.open_reader()
    handle = reader._nc
    reader.open_reader()
    assert reader._nc is handle
    with pytest.raises(ValueError, match="error"):
        with reader._open() as borrowed:
            assert borrowed is handle
            raise ValueError("error")
    assert reader._nc is handle
    assert handle.isopen()
    reader.close()
    reader.close()
    assert reader._nc is None
    assert not handle.isopen()
    reader.surface("water level", 0.)
    assert reader._nc is None


def test_lru_returns_independent_copies(tmp_path):
    reader = NCGrid(make_nc(tmp_path))
    with reader._open():
        data = reader._surface("water level", 0)
        data[:] = -1000.
        assert reader._surface("water level", 0)[0, 0] == 0.

def test_reductions_stream_time_slices_without_allocating_cube(tmp_path):
    reader = NCGrid(make_nc(tmp_path, 120))
    assert reader.maximum("water level") == 1079.
    assert reader.minimum("water level") == 0.
    assert reader._surface_cache_bytes == 0
    assert "water level" not in reader._cached_data

@pytest.mark.parametrize("temporal", [False, True])
def test_resident_masked_grid_preserves_missing_cells_and_extrema(temporal):
    surface = np.ma.array(
        [[1., 999.], [2., 3.]],
        mask=[[False, True], [False, False]],
    )
    data = np.ma.stack([surface, surface + 1]) if temporal else surface
    metadata = {"dx": 1., "nrow": 2, "ncol": 2,
                "data_type": "water level", "data": data}
    if temporal:
        metadata["timesteps"] = [0., 1.]
    grid = Grid(metadata)
    with_masks = grid._surface("water level", [1, 0, 1] if temporal else -1)
    assert np.ma.isMaskedArray(with_masks)
    assert np.ma.getmaskarray(with_masks).any()
    assert grid.maximum("water level") == (4. if temporal else 3.)
    assert grid.minimum("water level") == 1.


@pytest.mark.parametrize("budget", [0, -1, 1.5, True])
def test_memory_budget_must_be_positive_integer(tmp_path, budget):
    with pytest.raises(ValueError, match="memory_budget_bytes"):
        NCGrid(make_nc(tmp_path), memory_budget_bytes=budget)


def test_aggregate_lru_eviction_across_variables(tmp_path):
    reader = NCGrid(make_nc(tmp_path), memory_budget_bytes=3 * 9 * 8)
    with reader._open():
        reader._surface("water level", 0)
        reader._surface("water level", 1)
        reader._surface("bed level", -1)
        assert reader._surface_cache_bytes == 3 * 9 * 8
        reader._surface("water level", 0)  # refresh oldest
        assert reader._surface_cache_bytes <= reader.memory_budget_bytes
        assert ("water level", 1) not in reader._surface_lru
        assert ("bed level", None) in reader._surface_lru
        assert ("water level", 0) in reader._surface_lru
        reader._surface("water level", 2)
        assert ("bed level", None) not in reader._surface_lru
        assert reader._surface_cache_bytes <= reader.memory_budget_bytes


def test_large_slice_returned_without_retention(tmp_path):
    reader = NCGrid(make_nc(tmp_path), memory_budget_bytes=8)
    with reader._open():
        np.testing.assert_array_equal(reader._surface("water level", 0), expected(0))
        assert reader._surface_cache_bytes == 0
        assert not reader._surface_lru


def test_configured_capacity_not_limited_to_four_slices(tmp_path):
    reader = NCGrid(make_nc(tmp_path), memory_budget_bytes=12 * 9 * 8)
    with reader._open():
        for i in range(12):
            reader._surface("water level", i)
    assert len(reader._surface_cache["water level"]) == 12
    assert reader._surface_cache_bytes == 12 * 9 * 8


def test_reductions_batch_into_contiguous_reads_and_do_not_retain(tmp_path, monkeypatch):
    reader = NCGrid(make_nc(tmp_path, 40), memory_budget_bytes=3 * 4 * 9 * 8)
    original = reader._value
    selections = []

    def spy(dtype, idx):
        selections.append(idx)
        return original(dtype, idx)

    monkeypatch.setattr(reader, "_value", spy)
    # Existing lazy surfaces cannot add to working block allocation.
    reader.surface("water level", 0)
    assert reader._surface_cache_bytes
    selections.clear()
    assert reader.maximum("water level") == 359.
    assert reader.minimum("water level") == 0.
    assert len(selections) < 80
    assert len(selections) >= 2
    assert all(isinstance(index, slice) for index in selections)
    assert all(0 <= index.start < index.stop <= 40 for index in selections)
    assert max(index.stop - index.start for index in selections) <= 4
    assert reader._surface_cache_bytes == 0


def test_cache_hit_reuses_time_count_metadata(tmp_path, monkeypatch):
    reader = NCGrid(make_nc(tmp_path, 12))
    orig_times = reader.times
    calls = []

    def time_spy(*args, **kwargs):
        calls.append((args, kwargs))
        return orig_times(*args, **kwargs)

    monkeypatch.setattr(reader, "times", time_spy)
    with reader._open():
        for _ in range(5):
            reader._surface("water level", 0)
    assert len(calls) <= 1


def test_mask_bytes_are_charged_across_shared_cache(tmp_path, monkeypatch):
    reader = NCGrid(make_nc(tmp_path), memory_budget_bytes=2 * (9 * 8 + 9))
    original = reader._value

    def masked(dtype, idx):
        value = original(dtype, idx)
        if dtype == "water level":
            mask = np.zeros((3, 3), dtype=bool)
            mask[0, 0] = True
            return np.ma.array(value, mask=mask)
        return value

    monkeypatch.setattr(reader, "_value", masked)
    with reader._open():
        one = reader._surface("water level", 0)
        assert np.ma.isMaskedArray(one)
        assert np.ma.is_masked(one[0, 0])
        assert reader._surface_cache_bytes == 9 * 8 + 9
        reader._surface("water level", 1)
        assert reader._surface_cache_bytes == 2 * (9 * 8 + 9)
        reader._surface("water level", 2)
        assert reader._surface_cache_bytes == 2 * (9 * 8 + 9)
