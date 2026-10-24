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
    reader = NCGrid(make_nc(tmp_path))
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
    assert len(reader._surface_cache["water level"]) <= 4


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
    assert len(reader._surface_cache["water level"]) <= 4


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
    cache = reader._surface_cache["water level"]
    assert len(cache) <= 4
    assert all(x.shape == (3, 3) for x in cache.values())
    assert "water level" not in reader._cached_data
