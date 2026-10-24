"""Designated live-provider lane: missing QGIS/MDAL is a collection/failure error.

Calls the installed QGIS averaging method on genuine MDAL volume blocks.
Run explicitly in an initialized QGIS Python environment; no fake modules/skips.
"""
from pathlib import Path

import numpy as np
import pytest
from netCDF4 import Dataset
from qgis.core import QgsApplication, QgsMeshDatasetIndex, QgsMeshLayer

from pytuflow._outputs.helpers.averaging_method import AveragingMethod
from pytuflow._outputs.pymesh.depth_averaging import get_method_func
from tests.test_numerical_depth_averaging import _analytical_average, ENDPOINT_REQUESTS
from tests.test_numerical_fv_reader import _write_fv, _read
from pytuflow import NCMesh

RTOL = ATOL = 1e-12


@pytest.fixture(scope="module")
def qapp():
    app = QgsApplication.instance()
    if app is None:
        app = QgsApplication([], False)
        app.initQgis()
    from qgis.core import QgsProviderRegistry
    assert "mdal" in QgsProviderRegistry.instance().providerList()
    yield app
    # Existing suite retains the application until process exit.


def _profile(path, boundaries, values):
    """One square FV cell, Float64 data, explicit NaN fill, physical layers."""
    n = len(boundaries) - 1
    vector = np.ndim(values) == 2
    with Dataset(path, "w") as nc:
        nc.spherical = "false"
        nc.Type = "Cell-centred TUFLOWFV output"
        for name, size in {"Time": 1, "NumCells2D": 1, "NumCells3D": n,
                           "NumVert2D": 4, "MaxNumCellVert": 4,
                           "NumLayerFaces3D": n + 1}.items():
            nc.createDimension(name, size)
        def write(name, dims, data, integer=False, long_name=None):
            v = nc.createVariable(name, "i4" if integer else "f8", dims,
                                  **({} if integer else {"fill_value": np.nan}))
            v.long_name = long_name or name
            v[:] = data
            return v
        write("ResTime", ("Time",), [0]).units = "hours"
        for name, data in {"cell_Nvert": [4], "NL": [n], "idx3": [1]}.items():
            write(name, ("NumCells2D",), data, True)
        write("idx2", ("NumCells3D",), [1] * n, True)
        write("cell_node", ("NumCells2D", "MaxNumCellVert"), [[1, 2, 3, 4]], True)
        for name, data in {"node_X": [0, 1, 1, 0], "node_Y": [0, 0, 1, 1],
                           "node_Zb": [boundaries[-1]] * 4}.items():
            write(name, ("NumVert2D",), data)
        for name, data in {"cell_X": [.5], "cell_Y": [.5], "cell_Zb": [boundaries[-1]], "cell_A": [1]}.items():
            write(name, ("NumCells2D",), data)
        write("layerface_Z", ("Time", "NumLayerFaces3D"), [boundaries])
        write("stat", ("Time", "NumCells2D"), [[1]], True)
        write("H", ("Time", "NumCells2D"), [[boundaries[0]]], long_name="water surface elevation")
        if vector:
            for i, axis in enumerate("xy"):
                write("V_" + axis, ("Time", "NumCells3D"), [np.asarray(values)[:, i]], long_name=axis + "_velocity")
        else:
            write("SAL", ("Time", "NumCells3D"), [values], long_name="salinity")


def _block(path, name, boundaries, values):
    layer = QgsMeshLayer(str(path), "analytical", "mdal")
    assert layer.isValid(), str(path)
    provider = layer.dataProvider()
    assert provider.faceCount() >= 1
    groups = {provider.datasetGroupMetadata(g).name(): g for g in range(provider.datasetGroupCount())}
    assert name in groups, groups
    index = QgsMeshDatasetIndex(groups[name], 0)
    metadata = provider.datasetGroupMetadata(groups[name])
    block = provider.dataset3dValues(index, 0, 1)
    assert block.isValid()
    assert block.verticalLevelsCount() == [len(boundaries) - 1]
    assert block.faceToVolumeIndex() == [0]
    assert block.isVector() == (np.ndim(values) == 2)
    assert metadata.isScalar() != block.isVector()
    np.testing.assert_allclose(block.verticalLevels(), boundaries, rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(block.values(), np.ravel(values), rtol=RTOL, atol=ATOL, equal_nan=True)
    return layer, block  # retain provider lifetime through calculate


# Elevation endpoints are specified independently of production URI conversion.
CASES = [
    ("depth&0&0.5", (0, -.5)), ("depth&0.2&0.8", (-.2, -.8)),
    ("depth&0&1", (0, -1)), ("depth&0&1.5", (0, -1.5)),
    ("depth&0.25&1.75", (-.25, -1.75)), ("depth&0&9", (0, -9)),
    ("depth&3&4", (-3, -4)), ("depth&0.5&0.5", (-.5, -.5)),
    ("height&0.5&2", (-1.5, 0)), ("elevation&-1.5&0", (-1.5, 0)),
    ("sigma&0.25&1", (-1.5, 0)),
    ("multilevel?dir=top&1&2", (0, -2)),
    ("multilevel?dir=bottom&1&1", (-1, -2)),
    ("singlelevel?dir=top&1", (0, -1)),
]


@pytest.mark.parametrize("uri,elevations", CASES)
@pytest.mark.parametrize("values", [[10., 20.], [10., np.nan], [10., 0.], [np.nan, np.nan], [np.nan, 20.]],
                         ids=["valid", "missing-final", "zero", "all-missing", "missing-first"])
def test_analytical_python_qgis(qapp, tmp_path, uri, elevations, values):
    boundaries = [0., -1., -2.]
    path = tmp_path / "profile.nc"
    _profile(path, boundaries, values)
    layer, block = _block(path, "salinity", boundaries, values)
    expected = _analytical_average(boundaries, values, elevations)
    python = get_method_func(uri)(np.array([boundaries]), np.array([values]))
    result = AveragingMethod(uri).to_qgis().calculate(block)
    assert result.isValid()
    np.testing.assert_allclose(python, expected, rtol=RTOL, atol=ATOL, equal_nan=True)
    np.testing.assert_allclose(result.values(), expected, rtol=RTOL, atol=ATOL, equal_nan=True)


@pytest.mark.parametrize("uri,elevations,expected", [
    ("sigma&0&1", (-1, -5), 2.4),
    ("multilevel?dir=top&1&3", (-1, -4), 4/3),
    ("depth&1.25&3.5", (-2.25, -4.5), 10/3),
    ("depth&0.2&0.8", (-1.2, -1.8), 1.),
    ("depth&0.75&2.75", (-1.75, -3.75), 5/3),
    ("height&0.25&0.75", (-4.75, -4.25), 4.),
])
def test_nonuniform_reference(qapp, tmp_path, uri, elevations, expected):
    z, v = [-1., -2., -2.5, -4., -5.], [1., 2., np.nan, 4.]
    path = tmp_path / "nonuniform.nc"
    _profile(path, z, v)
    layer, block = _block(path, "salinity", z, v)
    np.testing.assert_allclose(_analytical_average(z, v, elevations), expected, rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(get_method_func(uri)(np.array([z]), np.array([v])), expected, rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(AveragingMethod(uri).to_qgis().calculate(block).values(), expected, rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("values,expected", [
    ([[3, 4], [6, np.nan]], [3, 4]),
    ([[np.nan, 4], [6, np.nan]], [np.nan, np.nan]),
    ([[0, 0], [0, 0]], [0, 0]),
    ([[3, 4], [6, 8]], [4.5, 6]),
])
def test_vector_components_before_magnitude(qapp, tmp_path, values, expected):
    z = [0., -1., -2.]
    path = tmp_path / "vector.nc"
    _profile(path, z, values)
    layer, block = _block(path, "velocity", z, values)
    qgis = AveragingMethod("sigma&0&1").to_qgis().calculate(block).values()
    v = np.array(values, dtype=float)
    v[~np.isfinite(v).all(axis=1)] = np.nan
    python = [get_method_func("sigma&0&1")(np.array([z]), v[:, i][None, :])[0] for i in range(2)]
    for result in [python, qgis]:
        np.testing.assert_allclose(result, expected, rtol=RTOL, atol=ATOL, equal_nan=True)
        np.testing.assert_allclose(np.linalg.norm(result), np.linalg.norm(expected), rtol=RTOL, atol=ATOL, equal_nan=True)


@pytest.mark.parametrize("access", ["point", "time_series", "section"])
def test_provider_reader_single_layer_interval(qapp, tmp_path, access):
    path = tmp_path / "single.nc"
    _write_fv(path, single_layer=True)
    reader = NCMesh(path, driver="qgis geometry data extractor")
    np.testing.assert_allclose(_read(reader, access, "salinity", "depth&0.2&0.8"), 10., rtol=RTOL, atol=ATOL)
    assert np.isnan(_read(reader, access, "salinity", "depth&2&3")).all()


@pytest.mark.parametrize("name", ["salinity", "temperature", "velocity"])
def test_public_fv_volume_dataset(qapp, name):
    path = Path("tests/nc_mesh/EST000_3D_001.nc")
    layer = QgsMeshLayer(str(path), "public-fv", "mdal")
    assert layer.isValid()
    p = layer.dataProvider()
    groups = {p.datasetGroupMetadata(g).name(): g for g in range(p.datasetGroupCount())}
    block = p.dataset3dValues(QgsMeshDatasetIndex(groups[name], 0), 0, 1)
    assert block.isValid()
    z = np.array(block.verticalLevels())
    v = np.array(block.values()).reshape(-1, 2 if block.isVector() else 1)
    v[~np.isfinite(v).all(axis=1)] = np.nan
    expected = [_analytical_average(z.tolist(), v[:, i].tolist(), (z[0], z[-1])) for i in range(v.shape[1])]
    python = [get_method_func("sigma&0&1")(z[None, :], v[:, i][None, :])[0] for i in range(v.shape[1])]
    qgis = AveragingMethod("sigma&0&1").to_qgis().calculate(block).values()
    # Source data is Float32; retain public-fixture precision.
    np.testing.assert_allclose(python, expected, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(qgis, expected, rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize("uri", ["depth&1.5&0", "elevation&0&-1.5"])
def test_reversed_bounds(qapp, tmp_path, uri):
    z, v = [0., -1., -2.], [10., 20.]
    path = tmp_path / "reversed.nc"
    _profile(path, z, v)
    layer, block = _block(path, "salinity", z, v)
    expected = _analytical_average(z, v, (0, -1.5))
    for result in [get_method_func(uri)(np.array([z]), np.array([v])),
                   AveragingMethod(uri).to_qgis().calculate(block).values()]:
        np.testing.assert_allclose(result, expected, rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("uri,qgis_expected", [("depth&0&0.0000001", np.nan), ("depth&0&0.000002", 10.)])
def test_provider_thickness_threshold(qapp, tmp_path, uri, qgis_expected):
    z, v = [0., -1., -2.], [10., 20.]
    path = tmp_path / "threshold.nc"
    _profile(path, z, v)
    layer, block = _block(path, "salinity", z, v)
    np.testing.assert_allclose(AveragingMethod(uri).to_qgis().calculate(block).values(), qgis_expected, equal_nan=True)
    np.testing.assert_allclose(get_method_func(uri)(np.array([z]), np.array([v])), 10., rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("uri", ["sigma&-0.1&1", "sigma&0&1.1"])
def test_invalid_sigma_provider_difference(qapp, tmp_path, uri):
    z, v = [0., -1., -2.], [10., 20.]
    path = tmp_path / "invalid-sigma.nc"
    _profile(path, z, v)
    layer, block = _block(path, "salinity", z, v)
    assert not AveragingMethod(uri).to_qgis().calculate(block).isValid()
    np.testing.assert_allclose(get_method_func(uri)(np.array([z]), np.array([v])), 15., rtol=RTOL, atol=ATOL)


def test_zero_thickness_ordinal_provider_difference(qapp, tmp_path):
    z, v = [0., 0., -1.], [10., 20.]
    path = tmp_path / "zero-layer.nc"
    _profile(path, z, v)
    layer, block = _block(path, "salinity", z, v)
    uri = "singlelevel?dir=top&1"
    np.testing.assert_allclose(AveragingMethod(uri).to_qgis().calculate(block).values(), 10., rtol=RTOL, atol=ATOL)
    assert np.isnan(get_method_func(uri)(np.array([z]), np.array([v]))).all()


@pytest.mark.parametrize("dtype,expected", [
    ("tracer", [10., np.nan, 0., 0.]),
    ("velocity", [[3., 4.], [np.nan, np.nan], [0., 0.], [0., 0.]]),
])
def test_extractor_preserves_missing_layers_and_components(qapp, tmp_path, dtype, expected):
    path = tmp_path / "missing.nc"
    _write_fv(path)
    reader = NCMesh(path, driver="qgis geometry data extractor")
    data, active = reader._driver.cell_data(dtype, 0, "sigma&0&1")
    np.testing.assert_array_equal(active, [True, True, True, False])
    np.testing.assert_allclose(data[:, 0, :] if dtype == "velocity" else data, expected, rtol=RTOL, atol=ATOL, equal_nan=True)
    # Public point and magnitude paths must preserve the same vector validity.
    for access in ["point", "time_series", "section"]:
        wanted = ([3., 4.] if access == "point" else 5.) if dtype == "velocity" else 10.
        np.testing.assert_allclose(_read(reader, access, dtype, "sigma&0&1"), wanted, rtol=RTOL, atol=ATOL)
        assert np.isnan(_read(reader, access, dtype, "sigma&0&1", cell=1)).all()




def test_provider_metadata_extrema_are_magnitudes(qapp, tmp_path):
    path = tmp_path / "extrema.nc"
    _profile(path, [0., -1., -2.], [[3., 4.], [6., 8.]])
    reader = NCMesh(path, driver="qgis geometry data extractor")
    # Preserve inherited provider metadata semantics even for split requests.
    for split in [False, True]:
        assert reader._driver.minimum("velocity", split_vector_components=split) == 5.
        assert reader._driver.maximum("velocity", split_vector_components=split) == 10.


def test_unnormalised_finite_sentinel_is_not_missing(qapp, tmp_path):
    z, v = [0., -1., -2.], [10., -999.]
    path = tmp_path / "finite-sentinel.nc"
    _profile(path, z, v)
    layer, block = _block(path, "salinity", z, v)
    # Without source missing metadata a finite sentinel remains an observation.
    expected = _analytical_average(z, v, (0, -2))
    for result in [get_method_func("sigma&0&1")(np.array([z]), np.array([v])),
                   AveragingMethod("sigma&0&1").to_qgis().calculate(block).values()]:
        np.testing.assert_allclose(result, expected, rtol=RTOL, atol=ATOL)


def test_ragged_provider_columns_trim_only_padding(qapp, tmp_path):
    path = tmp_path / "ragged.nc"
    _write_fv(path)
    with Dataset(path, "a") as nc:
        nc["NL"][:] = [1, 2, 1, 2]
        nc["idx3"][:] = [1, 2, 4, 5]
        nc["idx2"][:] = [1, 2, 2, 3, 4, 4, 4, 4]
        nc["layerface_Z"][:] = [[0, -2, 0, -1, -2, 0, -2, 0, -1, -2, np.nan, np.nan]] * 2
        nc["Tracer"][:] = [[10, np.nan, 20, 0, 99, 99, np.nan, np.nan]] * 2
    reader = NCMesh(path, driver="qgis geometry data extractor")
    np.testing.assert_allclose(reader._driver.data("tracer", (0, slice(None))),
                               [10, np.nan, 20, 0, 99, 99], equal_nan=True)
    data, active = reader._driver.cell_data("tracer", 0, "sigma&0&1")
    np.testing.assert_allclose(data, [10, 20, 0, 0], rtol=RTOL, atol=ATOL)
    np.testing.assert_array_equal(active, [True, True, True, False])


@pytest.mark.parametrize("engine", ["netcdf4", "h5py", "qgis geometry data extractor"])
@pytest.mark.parametrize("access", ["point", "time_series", "section", "cell_data"])
@pytest.mark.parametrize("missing_observation", [False, True])
def test_reader_physical_count_survives_missing_surface(qapp, tmp_path, engine, access, missing_observation):
    path = tmp_path / "missing-boundary.nc"
    _write_fv(path)
    with Dataset(path, "a") as nc:
        z = nc["layerface_Z"][:]
        z[:, 0] = np.nan
        nc["layerface_Z"][:] = z
        if missing_observation:
            values = nc["SAL"][:]
            values[:, 0] = np.nan
            nc["SAL"][:] = values
    reader = NCMesh(path, driver=engine)
    if engine == "qgis geometry data extractor":
        # The genuine provider block must retain the missing physical boundary.
        p = reader._driver.extractors[0].lyr.dataProvider()
        groups = {p.datasetGroupMetadata(g).name(): g for g in range(p.datasetGroupCount())}
        block = p.dataset3dValues(QgsMeshDatasetIndex(groups["salinity"], 0), 0, 1)
        assert block.isValid() and block.verticalLevelsCount() == [2]
        assert np.isnan(block.verticalLevels()[0])
    def read(level):
        uri = f"singlelevel?dir=top&{level}"
        if access == "cell_data":
            return reader._driver.cell_data("salinity", 0, uri)[0][0]
        return _read(reader, access, "salinity", uri)
    assert np.isnan(read(1)).all()
    np.testing.assert_allclose(read(2), 20., rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("missing,uri,expected", ENDPOINT_REQUESTS)
@pytest.mark.parametrize("missing_observation", [False, True])
def test_missing_endpoints_actual_qgis_calculation(qapp, tmp_path, request, missing, uri, expected, missing_observation):
    z = [np.nan, -1., -2.] if missing == "surface" else [0., -1., np.nan]
    v = [10., 20.]
    if missing_observation:
        v[1 if missing == "surface" else 0] = np.nan
        expected = np.nan
    path = tmp_path / "physical-endpoint.nc"
    _profile(path, z, v)
    layer, block = _block(path, "salinity", z, v)
    qgis = AveragingMethod(uri).to_qgis().calculate(block)
    assert qgis.isValid()
    python = get_method_func(uri, layer_counts=2)(np.array(z), np.array(v))
    np.testing.assert_allclose(python, expected, rtol=RTOL, atol=ATOL, equal_nan=True)
    # Installed QGIS 4.2.3 rejects the whole face if either outer endpoint is
    # missing, even when the known-origin Python request has a bounded integral.
    assert np.isnan(qgis.values()).all()
    request.node.user_properties.extend([
        ("physical_boundaries", str(block.verticalLevels())),
        ("physical_layer_counts", str(block.verticalLevelsCount())),
        ("raw_values", str(block.values())),
        ("analytical_expected", str(expected)),
        ("python_result", str(python.tolist())),
        ("qgis_result", str(qgis.values())),
    ])


@pytest.mark.parametrize("missing,uri,expected", ENDPOINT_REQUESTS)
@pytest.mark.parametrize("access", ["point", "time_series", "section", "cell_data"])
def test_missing_endpoint_qgis_python_reader(qapp, tmp_path, missing, uri, expected, access):
    path = tmp_path / "reader-endpoint.nc"
    _write_fv(path)
    with Dataset(path, "a") as nc:
        z = nc["layerface_Z"][:]
        z[:, 0 if missing == "surface" else 2] = np.nan
        nc["layerface_Z"][:] = z
    reader = NCMesh(path, driver="qgis geometry data extractor")
    if access == "cell_data":
        values, active = reader._driver.cell_data("salinity", 0, uri)
        assert active[0]
        actual = values[0]
    else:
        actual = _read(reader, access, "salinity", uri)
    np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL, equal_nan=True)
