"""Save ownership, database and FV regressions using disposable package inputs."""

from pathlib import Path

import pandas as pd
import pytest

from pytuflow._tmf.cf import cf_build_state as saves
from pytuflow._tmf.cf.fvc import FVC
from pytuflow._tmf.cf.tcf import TCF
from pytuflow._tmf.db.mat import MatDatabaseTMF
from pytuflow._tmf.inp.inp_build_state import InputBuildState


def _inventory(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


def _state(model) -> tuple:
    """Record live ownership, scopes, caches and pending history without materialising files."""
    result = []
    pending = [model]
    visited = set()
    while pending:
        owner = pending.pop()
        if id(owner) in visited:
            continue
        visited.add(id(owner))
        inputs = owner.inputs.inputs(include_hidden=True) if hasattr(owner, 'inputs') else []
        result.append((
            id(owner), owner.fpath, owner.loaded, owner.dirty, id(owner.parent),
            id(owner.config), owner.config.control_file, owner.config.tcf,
            tuple((id(change), change.uuid, change.change_type)
                  for block in owner.altered_inputs._updated_inputs for change in block),
            tuple(len(block) for block in owner.altered_inputs._updated_inputs),
            tuple((
                id(inp), inp.uuid, inp.dirty, id(inp.parent),
                inp.command().original_text, inp.trd, id(inp.trd_input),
                tuple((id(scope), repr(scope)) for scope in inp.scope),
                tuple(id(child) for child in inp.cf),
                tuple(getattr(inp, '_cf_loaded_paths', ())),
                tuple(getattr(inp, '_database_loaded_paths', ())),
            ) for inp in inputs),
        ))
        pending.extend(child for inp in inputs for child in inp.cf)
    return tuple(result)


def _geometry_model(directory: Path) -> TCF:
    (directory / 'model_010.tcf').write_bytes(b'Geometry Control File == grid_003.tgc\n')
    (directory / 'grid_003.tgc').write_bytes(b'Cell Size == 5\n')
    return TCF(directory / 'model_010.tcf')


def _database_model(directory: Path, extension: str) -> TCF:
    (directory / 'model_010.tcf').write_bytes(
        f'Read Materials File == materials_003.{extension}\n'.encode('ascii')
    )
    prefix = '! ' if extension == 'tmf' else ''
    (directory / f'materials_003.{extension}').write_bytes(
        f"{prefix}Material ID,Manning's n\n1,0.03\n".encode('ascii')
    )
    return TCF(directory / 'model_010.tcf')


def _fv_model(directory: Path) -> FVC:
    path = directory / 'model_010.fvc'
    path.write_bytes(
        b'Material == 1\n'
        b'    Bottom Roughness == 0.05\n'
        b'End Material\n'
    )
    return FVC(path)


@pytest.mark.parametrize('increment', ['auto', None], ids=['rename', 'overwrite'])
def test_rhs_edits_remain_in_their_trd_across_repeated_saves(tmp_path: Path, increment) -> None:
    path = tmp_path / 'model_010.tcf'
    path.write_bytes(b'Hardware == GPU\nRead File == forcing_002.trd\n')
    original_include = tmp_path / 'forcing_002.trd'
    original_include.write_bytes(b'! include ownership\nTimestep == 1\n')
    model = TCF(path)
    inp = model.find_input('Timestep')[0]
    identity = id(inp)

    for sequence, value in enumerate(('2', '3'), start=11):
        inp.rhs = value
        model.write(increment)
        include = tmp_path / (f'forcing_{sequence:03d}.trd' if increment else 'forcing_002.trd')
        assert model.find_input('Timestep')[0] is inp
        assert id(inp) == identity
        assert inp.trd == include
        assert f'Timestep == {value}'.encode('ascii') in include.read_bytes()
        assert b'Timestep' not in model.fpath.read_bytes()
        assert f'Read File == {include.name}'.encode('ascii') in model.fpath.read_bytes()
        reloaded = TCF(model.fpath)
        assert reloaded.find_input('Timestep')[0].trd == include
        assert str(reloaded.find_input('Timestep')[0].rhs) == value

    if increment:
        assert original_include.read_bytes() == b'! include ownership\nTimestep == 1\n'
        assert b'Timestep == 2' in (tmp_path / 'forcing_011.trd').read_bytes()


@pytest.mark.parametrize('mode', ['eager', 'deferred'])
def test_context_after_renamed_save_uses_same_child_and_updated_reference(tmp_path: Path, mode: str) -> None:
    model = _geometry_model(tmp_path)
    ref = model.find_input('Geometry Control File')[0]
    child = ref.cf[0]
    child.find_input('Cell Size')[0].rhs = '10'

    model.write('auto')

    destination = tmp_path / 'grid_011.tgc'
    assert ref.cf[0] is child
    assert child.fpath == destination
    assert ref.files == [destination]
    assert ref._cf_loaded_paths == [destination]
    context = model.context(file_resolution=mode)
    contextual_ref = context.find_input('Geometry Control File')[0]
    assert contextual_ref.files == [destination]
    assert contextual_ref.file_references[0].path_pattern == destination
    assert context.find_input('Cell Size')[0].value == 10.0
    assert child.parent is model
    assert child.config.tcf == model.fpath


@pytest.mark.parametrize('extension', ['csv', 'tmf'])
def test_database_save_retains_identity_data_and_special_header(tmp_path: Path, extension: str) -> None:
    model = _database_model(tmp_path, extension)
    ref = model.find_input('Read Materials File')[0]
    database = ref.cf[0]
    database.df.loc[1, "Manning's n"] = 0.06
    expected = database._df.copy(deep=True)
    dataframe_id = id(database._df)

    model.write('auto')

    destination = tmp_path / f'materials_011.{extension}'
    assert ref.cf[0] is database
    assert database.fpath == destination
    assert ref.files == [destination]
    assert ref._database_loaded_paths == [destination]
    assert id(database._df) == dataframe_id
    pd.testing.assert_frame_equal(database._df, expected)
    assert database._df.index.name == 'Material ID'
    expected_header = b"! Material ID,Manning's n" if extension == 'tmf' else b"Material ID,Manning's n"
    assert destination.read_bytes().splitlines()[0] == expected_header
    assert TCF(model.fpath).mat_file().value(1) == pytest.approx(0.06)
    assert database.loaded
    assert not database.dirty
    assert not model.dirty


@pytest.mark.parametrize('extension', ['csv', 'tmf'])
@pytest.mark.parametrize('failure', ['stage', 'replace'])
def test_database_failure_preserves_disk_dataframe_and_pending_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extension: str, failure: str,
) -> None:
    model = _database_model(tmp_path, extension)
    database = model.mat_file()
    database.df.loc[1, "Manning's n"] = 0.06
    before_disk, before_state = _inventory(tmp_path), _state(model)
    before_df = database._df.copy(deep=True)
    dataframe_ids = (id(database._df), id(database._df_wrapped))
    stage = saves._stage_bytes
    replace = saves.os.replace
    staged_databases = []

    def fail_stage(destination, data):
        if Path(destination).suffix == f'.{extension}':
            staged_databases.append(Path(destination))
        if failure == 'stage' and Path(destination).suffix == '.tcf':
            assert staged_databases, 'database must be staged before this injected failure'
            raise PermissionError('injected parent stage failure after database serialisation')
        return stage(destination, data)

    def fail_replace(source, destination):
        if Path(destination).suffix == '.tcf':
            raise PermissionError('injected parent replacement failure after database replacement')
        return replace(source, destination)

    monkeypatch.setattr(saves, '_stage_bytes', fail_stage)
    if failure == 'stage':
        expected_error = PermissionError
    else:
        monkeypatch.setattr(saves.os, 'replace', fail_replace)
        expected_error = saves.ModelSaveError
    with pytest.raises(expected_error) as caught:
        model.write(None)

    assert staged_databases
    if failure == 'replace':
        assert caught.value.replaced_paths == (database.fpath,)
        assert caught.value.unrestored_paths == ()
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state
    assert (id(database._df), id(database._df_wrapped)) == dataframe_ids
    pd.testing.assert_frame_equal(database._df, before_df)
    pd.testing.assert_frame_equal(database._df_wrapped, before_df, check_frame_type=False)
    assert database._df.index.name == 'Material ID'
    assert database.dirty


def test_tmf_database_serialisation_failure_cannot_mutate_live_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _database_model(tmp_path, 'tmf')
    database = model.mat_file()
    assert isinstance(database, MatDatabaseTMF)
    database.df.loc[1, "Manning's n"] = 0.06
    before_disk, before_state = _inventory(tmp_path), _state(model)
    before_df = database._df.copy(deep=True)
    calls = []

    def fail_csv(frame, *args, **kwargs):
        calls.append(frame.index.name)
        assert frame is not database._df
        raise OSError('injected material serialisation failure')

    monkeypatch.setattr(pd.DataFrame, 'to_csv', fail_csv)
    with pytest.raises(OSError, match='injected material serialisation failure'):
        model.write(None)

    assert calls == ['! Material ID']
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state
    pd.testing.assert_frame_equal(database._df, before_df)
    assert database._df.index.name == 'Material ID'


def test_fv_inline_block_save_preserves_live_scopes_and_child_identity(tmp_path: Path) -> None:
    model = _fv_model(tmp_path)
    block_ref = model.find_input('Material')[0]
    block = block_ref.cf[0]
    roughness = model.find_input('Bottom Roughness')[0]
    roughness.rhs = '0.07'
    scopes = tuple((id(scope), repr(scope)) for scope in roughness.scope)

    model.write('auto')

    assert model.fpath.name == 'model_011.fvc'
    assert block_ref.cf[0] is block
    assert block.fpath == model.fpath
    assert tuple((id(scope), repr(scope)) for scope in roughness.scope) == scopes
    assert b'Bottom Roughness == 0.07' in model.fpath.read_bytes()
    reloaded = FVC(model.fpath)
    assert float(reloaded.find_input('Bottom Roughness')[0].rhs) == pytest.approx(0.07)
    assert len(reloaded.find_input('Material')) == 1
    assert len(_inventory(tmp_path)) == 2


def test_fv_inline_block_render_failure_does_not_leave_live_scope_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _fv_model(tmp_path)
    model.find_input('Bottom Roughness')[0].rhs = '0.07'
    before_disk, before_state = _inventory(tmp_path), _state(model)
    write = InputBuildState.write
    seen_scopes = []

    def fail_roughness(inp, stream, writer):
        if inp.lhs == 'Bottom Roughness':
            seen_scopes.extend(repr(scope) for scope in inp.scope)
            raise RuntimeError('injected inline block failure')
        return write(inp, stream, writer)

    monkeypatch.setattr(InputBuildState, 'write', fail_roughness)
    with pytest.raises(RuntimeError, match='injected inline block failure'):
        model.write('auto')

    assert any('_BlockScope' in scope for scope in seen_scopes)
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


@pytest.mark.parametrize('external_target', ['parent', 'child'])
def test_external_source_edit_is_rejected_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, external_target: str,
) -> None:
    model = _geometry_model(tmp_path)
    child = model.tgc()
    child.find_input('Cell Size')[0].rhs = '10'
    target = model.fpath if external_target == 'parent' else child.fpath
    target.write_bytes(target.read_bytes() + b'! external editor\n')
    before_disk, before_state = _inventory(tmp_path), _state(model)

    def forbidden_stage(*args):
        pytest.fail('externally changed source reached staging')

    monkeypatch.setattr(saves, '_stage_bytes', forbidden_stage)
    with pytest.raises(ValueError, match='Source changed on disk'):
        model.write(None)

    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_incremented_child_cannot_overwrite_another_loaded_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / 'model_010.tcf').write_bytes(
        b'Geometry Control File == grid_010.tgc\nGeometry Control File == grid_011.tgc\n'
    )
    (tmp_path / 'grid_010.tgc').write_bytes(b'Cell Size == 5\n')
    (tmp_path / 'grid_011.tgc').write_bytes(b'Cell Size == 7\n')
    model = TCF(tmp_path / 'model_010.tcf')
    model.find_input('Geometry Control File')[0].cf[0].find_input('Cell Size')[0].rhs = '10'
    before_disk, before_state = _inventory(tmp_path), _state(model)

    def forbidden_stage(*args):
        pytest.fail('source collision reached staging')

    monkeypatch.setattr(saves, '_stage_bytes', forbidden_stage)
    with pytest.raises(ValueError, match='overwrite another source'):
        model.write('auto')

    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state
