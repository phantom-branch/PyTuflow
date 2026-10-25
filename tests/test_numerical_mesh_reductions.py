"""Analytical regressions for the real PyMesh min/max entry points.

Only the extraction boundary is replaced: the imported PyMesh dispatch, masks,
reductions, return shapes and cache are exercised normally. Expected values are
fixed scalar extrema and 3-4-5 / 6-8-10 triangles, independent of production code.
"""

from pathlib import Path
from unittest.mock import Mock

import h5py
import numpy as np
import pytest

from pytuflow._outputs.pymesh import PyDataExtractor, PyMesh, PyXMDF


def _mesh(
    monkeypatch: pytest.MonkeyPatch,
    values: np.ndarray,
    active: np.ndarray,
    *,
    vector: bool,
    on_vertex: bool,
    stored: tuple[float | tuple[float, float], float | tuple[float, float]] | None = None,
) -> tuple[PyMesh, Mock, Mock, Mock, str]:
    """Provide a small extractor payload without bypassing PyMesh itself."""
    mesh = PyMesh()
    mesh.geom.data_type = ''
    data_type = 'vector velocity' if vector else 'water level'
    extractor = Mock(spec=PyDataExtractor)
    extractor.data_types.return_value = [data_type]
    extractor.is_3d.return_value = False
    extractor.is_vector.return_value = vector
    extractor.on_vertex.return_value = on_vertex
    if stored is None:
        extractor.minimum.side_effect = NotImplementedError
        extractor.maximum.side_effect = NotImplementedError
    else:
        extractor.minimum.return_value, extractor.maximum.return_value = stored
    mesh.extractors = [extractor]
    vertex_data = Mock(return_value=(values, active))
    cell_data = Mock(return_value=(values, active))
    monkeypatch.setattr(mesh, 'vertex_data', vertex_data)
    monkeypatch.setattr(mesh, 'cell_data', cell_data)
    return mesh, extractor, vertex_data, cell_data, data_type


def _payload(values: list[float] | list[list[float]], temporal: bool, vector: bool) -> tuple[np.ndarray, np.ndarray]:
    data = np.asarray(values, dtype=float)
    if temporal:
        # Two-dimensional scalar or three-dimensional vector time series.
        data = data.reshape((-1, 1, 2) if vector else (-1, 1))
    active = np.ones(data.shape[:-1] if vector else data.shape, dtype=bool)
    return data, active


@pytest.mark.parametrize('on_vertex', [False, True], ids=['cells', 'vertices'])
@pytest.mark.parametrize('temporal', [False, True], ids=['static', 'temporal'])
def test_vector_magnitude_fallback(monkeypatch, on_vertex, temporal):
    """The reported defect: scalar minimum magnitude must not be indexed."""
    data, active = _payload([[3, 4], [6, 8]], temporal, vector=True)
    mesh, _, vertex_data, cell_data, dtype = _mesh(
        monkeypatch, data, active, vector=True, on_vertex=on_vertex,
    )
    minimum = mesh.minimum(dtype)
    maximum = mesh.maximum(dtype)
    assert minimum == 5.0
    assert maximum == 10.0
    assert type(minimum) is float
    assert type(maximum) is float
    used, unused = (vertex_data, cell_data) if on_vertex else (cell_data, vertex_data)
    assert used.call_count == 2
    unused.assert_not_called()


@pytest.mark.parametrize('on_vertex', [False, True], ids=['cells', 'vertices'])
@pytest.mark.parametrize('temporal', [False, True], ids=['static', 'temporal'])
def test_split_components_are_independent_extrema(monkeypatch, on_vertex, temporal):
    # The two component minima occur in different vectors; these tuples are
    # component extrema, not the vector selected by minimum/maximum magnitude.
    data, active = _payload([[3, 4], [-6, 8]], temporal, vector=True)
    mesh, _, _, _, dtype = _mesh(monkeypatch, data, active, vector=True, on_vertex=on_vertex)
    minimum = mesh.minimum(dtype, split_vector_components=True)
    maximum = mesh.maximum(dtype, split_vector_components=True)
    assert minimum == (-6.0, 4.0)
    assert maximum == (3.0, 8.0)
    assert isinstance(minimum, tuple)
    assert isinstance(maximum, tuple)
    assert all(type(value) is float for value in (*minimum, *maximum))
    # Separate cache entries must preserve the scalar magnitude contract.
    assert mesh.minimum(dtype) == 5.0
    assert mesh.maximum(dtype) == 10.0


@pytest.mark.parametrize('on_vertex', [False, True], ids=['cells', 'vertices'])
@pytest.mark.parametrize('temporal', [False, True], ids=['static', 'temporal'])
@pytest.mark.parametrize('split', [False, True])
def test_scalar_extrema_keep_scalar_shape(monkeypatch, on_vertex, temporal, split):
    data, active = _payload([10, -2, 0], temporal, vector=False)
    mesh, extractor, _, _, dtype = _mesh(monkeypatch, data, active, vector=False, on_vertex=on_vertex)
    minimum = mesh.minimum(dtype, split_vector_components=split)
    maximum = mesh.maximum(dtype, split_vector_components=split)
    assert minimum == -2.0
    assert maximum == 10.0
    assert type(minimum) is float
    assert type(maximum) is float
    extractor.minimum.assert_called_once_with(dtype, None, False)
    extractor.maximum.assert_called_once_with(dtype, None, False)


@pytest.mark.parametrize('on_vertex', [False, True], ids=['cells', 'vertices'])
@pytest.mark.parametrize('temporal', [False, True], ids=['static', 'temporal'])
@pytest.mark.parametrize('vector,split,expected', [
    (False, False, (0.0, 5.0)),
    (True, False, (0.0, 5.0)),
    (True, True, ((0.0, 0.0), (3.0, 4.0))),
], ids=['scalar', 'magnitude', 'components'])
def test_inactive_values_are_excluded_but_physical_zero_is_retained(
    monkeypatch, on_vertex, temporal, vector, split, expected,
):
    values = [[0, 0], [600, 800], [3, 4]] if vector else [0, 1000, 5]
    data, active = _payload(values, temporal, vector)
    active.reshape(-1)[1] = False
    mesh, _, _, _, dtype = _mesh(monkeypatch, data, active, vector=vector, on_vertex=on_vertex)
    assert mesh.minimum(dtype, split_vector_components=split) == expected[0]
    assert mesh.maximum(dtype, split_vector_components=split) == expected[1]


@pytest.mark.parametrize('on_vertex', [False, True], ids=['cells', 'vertices'])
@pytest.mark.parametrize('vector,split', [(False, False), (True, False), (True, True)],
                         ids=['scalar', 'magnitude', 'components'])
@pytest.mark.parametrize('operation', ['minimum', 'maximum'])
def test_all_inactive_fallback_preserves_empty_reduction_error(
    monkeypatch, on_vertex, vector, split, operation,
):
    # Neither existing fallback defines an extremum over an empty wet domain.
    # Preserve ValueError rather than introducing a fabricated zero or sentinel.
    data, active = _payload([[3, 4], [6, 8]] if vector else [5, 10], False, vector)
    active[:] = False
    mesh, _, _, _, dtype = _mesh(monkeypatch, data, active, vector=vector, on_vertex=on_vertex)
    with pytest.raises(ValueError, match='zero-size array'):
        getattr(mesh, operation)(dtype, split_vector_components=split)


@pytest.mark.parametrize('on_vertex', [False, True], ids=['cells', 'vertices'])
@pytest.mark.parametrize('vector,split,expected', [
    (False, False, (5.0, 10.0)),
    (True, False, (5.0, 10.0)),
    (True, True, ((3.0, 4.0), (6.0, 8.0))),
], ids=['scalar', 'magnitude', 'components'])
def test_stored_and_fallback_extrema_agree(monkeypatch, on_vertex, vector, split, expected):
    data, active = _payload([[3, 4], [6, 8]] if vector else [5, 10], True, vector)
    fallback, _, _, _, dtype = _mesh(monkeypatch, data, active, vector=vector, on_vertex=on_vertex)
    stored, extractor, vertex_data, cell_data, _ = _mesh(
        monkeypatch, data, active, vector=vector, on_vertex=on_vertex, stored=expected,
    )
    for operation, value in zip(('minimum', 'maximum'), expected):
        assert getattr(fallback, operation)(dtype, split_vector_components=split) == value
        assert getattr(stored, operation)(dtype, split_vector_components=split) == value
        # Calling again proves the scalar and component cache keys stay valid.
        assert getattr(stored, operation)(dtype, split_vector_components=split) == value
        getattr(extractor, operation).assert_called_once_with(dtype, None, split)
    vertex_data.assert_not_called()
    cell_data.assert_not_called()


@pytest.mark.parametrize('on_vertex', [False, True], ids=['cells', 'vertices'])
@pytest.mark.parametrize('vector,split', [(False, False), (True, False), (True, True)],
                         ids=['scalar', 'magnitude', 'components'])
def test_active_missing_data_is_not_silently_replaced_by_zero(monkeypatch, on_vertex, vector, split):
    # PyMesh's existing extrema propagate an active NaN. Averaging has a separate
    # layer-validity contract; this repair does not redefine extrema policy.
    data, active = _payload([[np.nan, np.nan], [3, 4]] if vector else [np.nan, 5], False, vector)
    mesh, _, _, _, dtype = _mesh(monkeypatch, data, active, vector=vector, on_vertex=on_vertex)
    assert np.isnan(mesh.minimum(dtype, split_vector_components=split)).all()
    assert np.isnan(mesh.maximum(dtype, split_vector_components=split)).all()


@pytest.fixture
def analytical_xmdf(tmp_path: Path) -> Path:
    """One quad, four vertices and two timesteps with exact 3-4-5 vectors."""
    path = tmp_path / 'analytical.xmdf'
    path.with_suffix('.2dm').write_text(
        'MESH2D\nNO_MOVE_EQ9_CENTER_NODE\n'
        'ND 1 0 0 0\nND 2 1 0 0\nND 3 1 1 0\nND 4 0 1 0\n'
        'E4Q 1 1 2 3 4 1\n', encoding='utf-8',
    )
    with h5py.File(path, 'w') as handle:
        handle.create_dataset('File Type', data=[np.bytes_('XMDF')])
        handle.create_dataset('File Version', data=[1.0])
        for name, values, kind in (
            ('Water Level', [[5.0] * 4, [10.0] * 4], 'SCALAR'),
            ('Vector Velocity', [[[3.0, 4.0]] * 4, [[6.0, 8.0]] * 4], 'VECTOR'),
        ):
            group = handle.create_group(f'analytical/Temporal/{name}')
            group.attrs['Grouptype'] = np.bytes_(f'DATASET {kind}')
            group.attrs['TimeUnits'] = np.bytes_('Hours')
            group.create_dataset('Times', data=[0.0, 1.0])
            group.create_dataset('Active', data=[[1], [1]])
            group.create_dataset('Values', data=values)
            group.create_dataset('Mins', data=[5.0, 10.0])
            group.create_dataset('Maxs', data=[5.0, 10.0])
    return path


@pytest.mark.parametrize('dtype,split,expected', [
    ('Water Level', False, (5.0, 10.0)),
    ('Vector Velocity', False, (5.0, 10.0)),
    ('Vector Velocity', True, ((3.0, 4.0), (6.0, 8.0))),
], ids=['scalar', 'magnitude', 'components'])
def test_real_xmdf_reader_stored_and_fallback_contract(
    analytical_xmdf, monkeypatch, dtype, split, expected,
):
    # Geometry, active-cell-to-vertex mapping and data reads use the real
    # PyVista/HDF5 path. Only the optional metadata shortcut is disabled below.
    mesh = PyXMDF(analytical_xmdf, geom_driver='python', engine='h5py')
    extractor = mesh.extractors[0]
    if split:
        # XMDF stores magnitude extrema, so component requests deliberately
        # use PyMesh's fallback even before the shortcut is disabled.
        with pytest.raises(NotImplementedError):
            extractor.minimum(dtype, None, True)
        with pytest.raises(NotImplementedError):
            extractor.maximum(dtype, None, True)
    for operation, value in zip(('minimum', 'maximum'), expected):
        assert getattr(mesh, operation)(dtype, split_vector_components=split) == value

    mesh.clear_cache()
    monkeypatch.setattr(extractor, 'minimum', Mock(side_effect=NotImplementedError))
    monkeypatch.setattr(extractor, 'maximum', Mock(side_effect=NotImplementedError))
    for operation, value in zip(('minimum', 'maximum'), expected):
        assert getattr(mesh, operation)(dtype, split_vector_components=split) == value
