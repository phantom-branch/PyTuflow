"""Analytical FV checks through real public readers and generated NetCDF data.

The fixture is four disconnected unit-square cells, each with one or two layers.
Expected values are prescribed constants, independent of the averaging code.
"""

from pathlib import Path

import numpy as np
import pytest
from netCDF4 import Dataset

from pytuflow import NCMesh


def _write_fv(path: Path, *, single_layer: bool = False) -> None:
    layers = 1 if single_layer else 2
    with Dataset(path, "w", format="NETCDF4") as nc:
        nc.spherical = "false"
        nc.Type = "Cell-centred TUFLOWFV output"
        for name, size in {
            "Time": 2,
            "NumCells2D": 4,
            "NumCells3D": 4 * layers,
            "NumVert2D": 16,
            "MaxNumCellVert": 4,
            "NumLayerFaces3D": 4 * (layers + 1),
        }.items():
            nc.createDimension(name, size)

        def write(name, dimensions, data, *, long_name=None, integer=False):
            kwargs = {} if integer else {"fill_value": np.nan}
            variable = nc.createVariable(name, "i4" if integer else "f8", dimensions, **kwargs)
            variable.long_name = long_name or name
            variable[:] = data
            return variable

        time = write("ResTime", ("Time",), [0.0, 1.0])
        time.units = "hours"
        write("cell_Nvert", ("NumCells2D",), [4] * 4, integer=True)
        write("cell_node", ("NumCells2D", "MaxNumCellVert"), np.arange(1, 17).reshape(4, 4), integer=True)
        write("NL", ("NumCells2D",), [layers] * 4, integer=True)
        write("idx2", ("NumCells3D",), np.repeat(np.arange(1, 5), layers), integer=True)
        write("idx3", ("NumCells2D",), np.arange(0, 4 * layers, layers) + 1, integer=True)
        write("cell_X", ("NumCells2D",), np.arange(4) * 2 + 0.5)
        write("cell_Y", ("NumCells2D",), [0.5] * 4)
        write("cell_Zb", ("NumCells2D",), [-layers] * 4)
        write("cell_A", ("NumCells2D",), [1.0] * 4)
        write("node_X", ("NumVert2D",), (np.arange(4)[:, None] * 2 + [0, 1, 1, 0]).ravel())
        write("node_Y", ("NumVert2D",), np.tile([0, 0, 1, 1], 4))
        write("node_Zb", ("NumVert2D",), [-layers] * 16)
        write("layerface_Z", ("Time", "NumLayerFaces3D"), np.tile(-np.arange(layers + 1), (2, 4)))
        write("stat", ("Time", "NumCells2D"), [[1, 1, 1, 0]] * 2, integer=True)
        write("H", ("Time", "NumCells2D"), np.zeros((2, 4)), long_name="water surface elevation")

        # Cell 0 distinguishes missing data from a physical zero; cell 1 has no
        # jointly valid vector layer; cell 2 is zero; cell 3 is explicitly dry.
        profiles = {
            "SAL": ("salinity", [[10, 20], [np.nan, np.nan], [0, 0], [99, 99]]),
            "Tracer": ("tracer", [[10, np.nan], [np.nan, np.nan], [0, 0], [99, 99]]),
            "V_x": ("x_velocity", [[3, 6], [np.nan, 9], [0, 0], [90, 90]]),
            "V_y": ("y_velocity", [[4, np.nan], [8, np.nan], [0, 0], [90, 90]]),
        }
        for name, (long_name, profile) in profiles.items():
            values = np.asarray(profile, dtype=float)[:, :layers].ravel()
            write(name, ("Time", "NumCells3D"), np.tile(values, (2, 1)), long_name=long_name)


@pytest.fixture(params=["netcdf4", "h5py"])
def fv_reader(tmp_path: Path, request: pytest.FixtureRequest) -> NCMesh:
    path = tmp_path / "analytical_fv.nc"
    _write_fv(path)
    return NCMesh(path, driver=request.param)


def _read(result: NCMesh, access: str, data_type: str, averaging: str, cell: int = 0) -> np.ndarray:
    point = (2 * cell + 0.5, 0.5)
    if access == "point":
        return np.asarray(result.data_point(point, data_type, 0.0, averaging_method=averaging))
    if access == "time_series":
        return result.time_series(point, data_type, averaging_method=averaging).to_numpy()
    if access == "section":
        line = [(2 * cell + 0.2, 0.5), (2 * cell + 0.8, 0.5)]
        return result.section(line, data_type, 0.0, averaging_method=averaging).iloc[:, -1].to_numpy()
    frame = result.surface(data_type, 0.0, averaging_method=averaging)
    columns = ["value-x", "value-y"] if data_type == "velocity" else ["value"]
    return frame.loc[cell, columns].to_numpy(dtype=float)


@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
@pytest.mark.parametrize(
    ("averaging", "expected"),
    [("depth&0&0.5", 10.0), ("depth&0.2&0.8", 10.0), ("depth&0&1", 10.0), ("depth&0&1.5", 40.0 / 3.0)],
)
def test_first_layer_intervals_through_public_reader(fv_reader, access, averaging, expected):
    np.testing.assert_allclose(_read(fv_reader, access, "salinity", averaging), expected, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
@pytest.mark.parametrize("averaging", ["sigma&0&1", "depth&0&2", "height&0&2", "elevation&0&-2", "multilevel?dir=top&1&2"])
def test_missing_scalar_layers_do_not_dilute_valid_data(fv_reader, access, averaging):
    np.testing.assert_allclose(_read(fv_reader, access, "tracer", averaging), 10.0, rtol=1e-12, atol=1e-12)
    assert np.isnan(_read(fv_reader, access, "tracer", averaging, cell=1)).all()
    np.testing.assert_array_equal(_read(fv_reader, access, "tracer", averaging, cell=2), 0.0)


@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
def test_vector_layer_requires_both_components(fv_reader, access):
    expected = [3.0, 4.0] if access in {"point", "surface"} else 5.0
    np.testing.assert_allclose(_read(fv_reader, access, "velocity", "sigma&0&1"), expected, rtol=1e-12, atol=1e-12)
    assert np.isnan(_read(fv_reader, access, "velocity", "sigma&0&1", cell=1)).all()
    np.testing.assert_array_equal(_read(fv_reader, access, "velocity", "sigma&0&1", cell=2), 0.0)


@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
@pytest.mark.parametrize("data_type", ["tracer", "velocity"])
def test_masked_reader_values_are_missing_not_underlying_numbers(fv_reader, monkeypatch, access, data_type):
    # Exercise the actual public reader with an extractor returning a MaskedArray.
    # Its masked entries deliberately contain finite nonzero backing data.
    original_data = fv_reader._driver.data

    def masked_data(dtype, index):
        values = original_data(dtype, index)
        if dtype in {"Tracer", "V_y"}:
            missing = np.isnan(values)
            return np.ma.array(np.where(missing, 123.0, values), mask=missing)
        return values

    monkeypatch.setattr(fv_reader._driver, "data", masked_data)
    if data_type == "tracer":
        expected = 10.0
    else:
        expected = [3.0, 4.0] if access in {"point", "surface"} else 5.0
    np.testing.assert_allclose(_read(fv_reader, access, data_type, "sigma&0&1"), expected, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("data_type", ["tracer", "velocity"])
def test_depth_averages_on_vertices_preserve_missing_values_and_dry_mask(fv_reader, data_type):
    frame = fv_reader.surface(data_type, 0.0, to_vertex=True)
    np.testing.assert_array_equal(frame["active"], np.repeat([True, True, True, False], 4))
    columns = ["value-x", "value-y"] if data_type == "velocity" else ["value"]
    expected = np.tile([3.0, 4.0] if data_type == "velocity" else [10.0], (4, 1))
    np.testing.assert_allclose(frame.loc[:3, columns], expected, rtol=1e-12, atol=1e-12)
    assert frame.loc[4:7, columns].isna().all().all()
    np.testing.assert_array_equal(frame.loc[8:, columns], 0.0)


@pytest.mark.parametrize("data_type", ["tracer", "velocity"])
def test_public_dry_mask_remains_separate_from_missing_data(fv_reader, data_type):
    frame = fv_reader.surface(data_type, 0.0)
    np.testing.assert_array_equal(frame["active"], [True, True, True, False])
    columns = ["value-x", "value-y"] if data_type == "velocity" else ["value"]
    assert frame.loc[1, columns].isna().all()  # wet, with missing results
    np.testing.assert_array_equal(frame.loc[3, columns].to_numpy(dtype=float), 0.0)  # inactive placeholders
    for access in ["point", "time_series", "section"]:
        assert np.isnan(_read(fv_reader, access, data_type, "sigma&0&1", cell=3)).all()


@pytest.mark.parametrize("engine", ["netcdf4", "h5py"])
@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
def test_single_layer_reader_honours_requested_interval(tmp_path, engine, access):
    path = tmp_path / "single_layer_fv.nc"
    _write_fv(path, single_layer=True)
    reader = NCMesh(path, driver=engine)
    np.testing.assert_allclose(_read(reader, access, "salinity", "sigma&0&1"), 10.0)
    np.testing.assert_allclose(_read(reader, access, "salinity", "depth&0.2&0.8"), 10.0)
    assert np.isnan(_read(reader, access, "salinity", "depth&2&3")).all()


@pytest.mark.parametrize("engine", ["netcdf4", "h5py"])
@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
@pytest.mark.parametrize("missing,averaging,expected", [
    ("surface", "depth&0&0.5", np.nan),
    ("surface", "height&0&0.5", 20.),
    ("surface", "elevation&-2&0", 20.),
    ("surface", "sigma&0&1", np.nan),
    ("bed", "height&0&0.5", np.nan),
    ("bed", "depth&0&0.5", 10.),
    ("bed", "elevation&-2&0", 10.),
    ("bed", "sigma&0&1", np.nan),
])
@pytest.mark.parametrize("missing_observation", [False, True])
def test_missing_endpoint_public_reader(tmp_path, engine, access, missing, averaging, expected, missing_observation):
    path = tmp_path / "missing_endpoint.nc"
    _write_fv(path)
    with Dataset(path, "a") as nc:
        z = nc["layerface_Z"][:]
        z[:, 0 if missing == "surface" else 2] = np.nan
        nc["layerface_Z"][:] = z
        if missing_observation:
            v = nc["SAL"][:]
            v[:, 1 if missing == "surface" else 0] = np.nan
            nc["SAL"][:] = v
            expected = np.nan
    reader = NCMesh(path, driver=engine)
    np.testing.assert_allclose(_read(reader, access, "salinity", averaging), expected,
                               rtol=1e-12, atol=1e-12, equal_nan=True)


@pytest.mark.parametrize("engine", ["netcdf4", "h5py"])
@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
@pytest.mark.parametrize("missing", ["surface", "bed"])
def test_endpoint_single_layer_has_no_bounded_contribution(tmp_path, engine, access, missing):
    path = tmp_path / "single_endpoint.nc"
    _write_fv(path, single_layer=True)
    with Dataset(path, "a") as nc:
        z = nc["layerface_Z"][:]
        z[:, 0 if missing == "surface" else 1] = np.nan
        nc["layerface_Z"][:] = z
    reader = NCMesh(path, driver=engine)
    for uri in ["depth&0&0.5", "height&0&0.5", "elevation&-1&0", "sigma&0&1"]:
        assert np.isnan(_read(reader, access, "salinity", uri)).all()


@pytest.mark.parametrize("engine", ["netcdf4", "h5py"])
@pytest.mark.parametrize("access", ["point", "time_series", "section", "surface"])
def test_ragged_reader_endpoint_extent(tmp_path, engine, access):
    path = tmp_path / "ragged_endpoints.nc"
    _write_fv(path)
    with Dataset(path, "a") as nc:
        nc["NL"][:] = [1, 2, 1, 2]
        nc["idx3"][:] = [1, 2, 4, 5]
        nc["idx2"][:] = [1, 2, 2, 3, 4, 4, 4, 4]
        nc["layerface_Z"][:] = [[0, -2, 0, -1, np.nan, 0, -2, 0, -1, -2, np.nan, np.nan]] * 2
        nc["SAL"][:] = [[10, 30, 40, 0, 99, 99, np.nan, np.nan]] * 2
    reader = NCMesh(path, driver=engine)
    for uri, expected in [("depth&0&0.5", 30.), ("height&0&0.5", np.nan),
                          ("sigma&0&1", np.nan), ("elevation&-2&0", 30.)]:
        # The shorter first cell ends at its actual bed, before artificial padding.
        np.testing.assert_allclose(_read(reader, access, "salinity", uri, cell=0), 10., rtol=1e-12, atol=1e-12)
        # The second cell's missing physical bed is not the same as padding.
        np.testing.assert_allclose(_read(reader, access, "salinity", uri, cell=1), expected,
                                   rtol=1e-12, atol=1e-12, equal_nan=True)
