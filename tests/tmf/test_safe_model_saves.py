"""Real-package save contracts using generated, disposable control-file trees."""

import errno
import os
import subprocess
from pathlib import Path, PureWindowsPath

import pytest

from pytuflow._tmf.cf import cf_build_state as saves
from pytuflow._tmf.cf.cf_build_state import ControlFileBuildState
from pytuflow._tmf.cf.tcf import TCF


def _inventory(directory: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(directory): path.read_bytes()
        for path in directory.rglob('*')
        if path.is_file()
    }


def _model(directory: Path) -> TCF:
    (directory / 'model_010.tcf').write_bytes(
        b'! parent\nHardware == GPU\nRead File == forcing_002.trd\n'
        b'Geometry Control File == grid_003.tgc\n'
        b'BC Control File == boundary_004.tbc\n'
    )
    (directory / 'forcing_002.trd').write_bytes(b'! include\nTimestep == 1\n')
    (directory / 'grid_003.tgc').write_bytes(b'! geometry\nCell Size == 5\n')
    (directory / 'boundary_004.tbc').write_bytes(b'! boundary\nTimestep == 2\n')
    return TCF(directory / 'model_010.tcf')


def _children(model: TCF) -> list[ControlFileBuildState]:
    return [child for inp in model.inputs for child in inp.cf]


def _edit_all(model: TCF) -> None:
    model.find_input('Hardware')[0].rhs = 'CPU'
    model.find_input('Cell Size')[0].rhs = '10'
    _children(model)[1].find_input('Timestep')[0].rhs = '3'
    include = next(inp for inp in model.inputs if inp.trd is not None)
    include.comment = '! included edit'


def _state(model: TCF) -> tuple:
    """Snapshot observable live identities and save-relevant mutable state."""
    result = []
    for cf in [model, *_children(model)]:
        inputs = cf.inputs.inputs(include_hidden=True)
        result.append((
            id(cf), cf.fpath, cf.loaded, cf.dirty, id(cf.parent),
            id(cf.config), cf.config.control_file, cf.config.tcf,
            id(cf.inputs), cf.inputs._iter_idx,
            tuple((
                id(inp), inp.uuid, id(inp.parent), inp.dirty,
                inp.command().original_text, inp.rhs, str(inp.scope),
                inp.trd, id(inp.trd_input),
                id(inp.config), inp.config.control_file, inp.config.tcf,
                tuple(id(child) for child in inp.cf),
                tuple(getattr(inp, '_cf_loaded_paths', ())),
                inp._files_loaded, tuple(inp._files), tuple(inp._rhs_files),
            ) for inp in inputs),
            id(cf.altered_inputs),
            tuple(tuple((id(change), change.uuid, change.change_type)
                        for change in block)
                  for block in cf.altered_inputs._updated_inputs),
        ))
    return tuple(result)


def test_legacy_comment_round_trip_does_not_truncate_real_tcf(tmp_path):
    path = tmp_path / 'legacy_001.tcf'
    original = b'! legacy byte: \x81\nHardware == GPU\n'
    path.write_bytes(original)
    model = TCF(path)

    model.write('inplace')

    assert path.read_bytes() == original


def test_legacy_comment_round_trip_does_not_truncate_real_trd(tmp_path):
    path = tmp_path / 'legacy_001.tcf'
    include = tmp_path / 'legacy_001.trd'
    original = b'! legacy byte: \x81\nTimestep == 1\n'
    path.write_bytes(b'Read File == legacy_001.trd\n')
    include.write_bytes(original)
    model = TCF(path)
    model.find_input('Timestep')[0].dirty = True

    model.write('inplace')

    assert include.read_bytes() == original
    assert path.read_bytes() == b'Read File == legacy_001.trd\n'


def test_parent_serialisation_failure_preserves_children_and_live_state(tmp_path, monkeypatch):
    model = _model(tmp_path)
    _edit_all(model)
    before_disk = _inventory(tmp_path)
    before_state = _state(model)
    real_write = ControlFileBuildState._write

    def fail_parent(stream, inputs):
        if any('! parent' in inp.command().original_text
               for inp in inputs.inputs(include_hidden=True)):
            stream.write('partial serialisation\n')
            raise RuntimeError('injected parent serialisation failure')
        real_write(stream, inputs)

    monkeypatch.setattr(ControlFileBuildState, '_write', staticmethod(fail_parent))
    with pytest.raises(RuntimeError, match='injected parent serialisation failure'):
        model.write('inplace')

    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


@pytest.mark.parametrize('include_file', [False, True], ids=['tcf', 'trd'])
@pytest.mark.parametrize('edited', [False, True], ids=['unchanged', 'edited'])
@pytest.mark.parametrize('newline', [b'\n', b'\r\n'], ids=['lf', 'crlf'])
@pytest.mark.parametrize('final_newline', [False, True], ids=['no-final-newline', 'final-newline'])
@pytest.mark.parametrize('bom', [b'', b'\xef\xbb\xbf'], ids=['no-bom', 'bom'])
@pytest.mark.parametrize('legacy', [False, True], ids=['utf8', 'legacy-byte'])
def test_source_text_contract(tmp_path, include_file, edited, newline, final_newline, bom, legacy):
    path = tmp_path / 'text_001.tcf'
    target = tmp_path / 'text_001.trd' if include_file else path
    header = b'! caf\xc3\xa9' + (b' legacy \x81' if legacy else b'')
    original = bom + header + newline + b'Hardware == GPU'
    if final_newline:
        original += newline
    target.write_bytes(original)
    parent_bytes = b'! untouched parent\r\nRead File == text_001.trd\r\n'
    if include_file:
        path.write_bytes(parent_bytes)
    model = TCF(path)
    inp = model.find_input('Hardware')[0]
    owner_before = inp.trd
    identity_before = (id(inp), inp.uuid)
    if edited:
        # The comment setter preserves flattened-TRD ownership. Its formatting
        # behaviour belongs to W2; this test checks the save text contract.
        inp.comment = '! edit caf\u00e9'

    assert model.write('inplace') is model

    actual = target.read_bytes()
    assert actual.startswith(bom + header + newline)
    assert actual.count(b'\xef\xbb\xbf') == bool(bom)
    assert actual.endswith(newline) is final_newline
    if newline == b'\r\n':
        assert b'\n' not in actual.replace(b'\r\n', b'')
    else:
        assert b'\r' not in actual
    if edited:
        assert b'! edit caf\xc3\xa9' in actual
    else:
        assert actual == original
    assert inp.trd == owner_before
    assert (id(inp), inp.uuid) == identity_before
    if include_file:
        assert path.read_bytes() == parent_bytes
        assert b'Hardware' not in path.read_bytes()


def test_bom_on_first_command_is_not_part_of_command_name(tmp_path):
    path = tmp_path / 'bom.tcf'
    path.write_bytes(b'\xef\xbb\xbfHardware == GPU\r\n')
    model = TCF(path)
    inp = model.find_input('Hardware')[0]
    assert inp.lhs == 'Hardware'
    inp.rhs = 'CPU'

    model.write('inplace')

    assert path.read_bytes() == b'\xef\xbb\xbfHardware == CPU\r\n'


def test_new_control_file_is_utf8_lf_without_bom(tmp_path):
    path = tmp_path / 'new.tcf'
    model = TCF(path)
    model.append_input('! caf\u00e9')
    model.append_input('Hardware == CPU')

    model.write()

    assert model.fpath == path
    assert path.read_bytes() == b'! caf\xc3\xa9\nHardware == CPU\n'
    assert model.loaded
    assert not model.dirty


@pytest.mark.parametrize('marker', ['! geometry', '! boundary', '! include'])
@pytest.mark.parametrize('increment', ['auto', 'inplace', None])
def test_child_or_trd_serialisation_failure_is_non_destructive(tmp_path, monkeypatch, marker, increment):
    model = _model(tmp_path)
    _edit_all(model)
    before_disk, before_state = _inventory(tmp_path), _state(model)
    real_write = ControlFileBuildState._write

    def fail_selected(stream, inputs):
        if any(marker in inp.command().original_text
               for inp in inputs.inputs(include_hidden=True)):
            stream.write('partial render\n')
            raise RuntimeError('injected serialisation failure')
        real_write(stream, inputs)

    monkeypatch.setattr(ControlFileBuildState, '_write', staticmethod(fail_selected))
    with pytest.raises(RuntimeError, match='injected serialisation failure'):
        model.write(increment)

    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


@pytest.mark.parametrize('child', [False, True], ids=['parent', 'child'])
def test_unencodable_new_text_fails_before_any_replacement(tmp_path, child):
    model = _model(tmp_path)
    _edit_all(model)
    target = _children(model)[0] if child else model
    target.append_input('! invalid non-byte surrogate \ud800')
    before_disk, before_state = _inventory(tmp_path), _state(model)

    with pytest.raises(UnicodeEncodeError):
        model.write('inplace')

    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_all_outputs_are_staged_before_replacing_files_or_changing_live_state(tmp_path, monkeypatch):
    model = _model(tmp_path)
    _edit_all(model)
    before_disk, before_state = _inventory(tmp_path), _state(model)
    expected = {tmp_path / relative for relative in before_disk}
    stage = saves._stage_bytes
    replace = saves.os.replace
    staged = set()
    replaced = []

    def inspect_stage(destination, data):
        assert _state(model) == before_state
        for relative, original in before_disk.items():
            assert (tmp_path / relative).read_bytes() == original
        result = stage(destination, data)
        assert result.parent == Path(destination).parent
        assert result.read_bytes() == data
        staged.add(Path(destination))
        return result

    def inspect_replace(source, destination):
        assert expected <= staged
        assert _state(model) == before_state
        replaced.append(Path(destination))
        return replace(source, destination)

    monkeypatch.setattr(saves, '_stage_bytes', inspect_stage)
    monkeypatch.setattr(saves.os, 'replace', inspect_replace)
    model.write(None)

    assert set(replaced) == expected
    assert len(replaced) == len(expected)
    assert set(_inventory(tmp_path)) == set(before_disk)
    assert not model.dirty


@pytest.mark.parametrize('error', [PermissionError, OSError], ids=['permission', 'disk-full'])
def test_staging_failure_preserves_all_originals_and_live_state(tmp_path, monkeypatch, error):
    model = _model(tmp_path)
    _edit_all(model)
    before_disk, before_state = _inventory(tmp_path), _state(model)
    stage = saves._stage_bytes
    calls = []

    def fail_second(destination, data):
        calls.append(destination)
        if len(calls) == 2:
            code = errno.EACCES if error is PermissionError else errno.ENOSPC
            raise error(code, 'injected staging failure', str(destination))
        return stage(destination, data)

    monkeypatch.setattr(saves, '_stage_bytes', fail_second)
    with pytest.raises(error, match='injected staging failure'):
        model.write('inplace')

    assert len(calls) == 2
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


@pytest.mark.parametrize('operation', ['write', 'flush', 'fsync'])
def test_partial_staging_io_failure_removes_temporary_file(tmp_path, monkeypatch, operation):
    model = _model(tmp_path)
    _edit_all(model)
    before_disk, before_state = _inventory(tmp_path), _state(model)
    fdopen = saves.os.fdopen
    failed = False

    class FailingStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, data):
            nonlocal failed
            if operation == 'write' and not failed:
                self.stream.write(data[:max(1, len(data) // 2)])
                failed = True
                raise OSError(errno.ENOSPC, 'injected partial staging failure')
            return self.stream.write(data)

        def flush(self):
            nonlocal failed
            self.stream.flush()
            if operation == 'flush' and not failed:
                failed = True
                raise OSError(errno.ENOSPC, 'injected partial staging failure')

        def fileno(self):
            return self.stream.fileno()

    def patched_fdopen(*args, **kwargs):
        return FailingStream(fdopen(*args, **kwargs))

    def fail_fsync(fd):
        nonlocal failed
        failed = True
        raise OSError(errno.ENOSPC, 'injected partial staging failure')

    monkeypatch.setattr(saves.os, 'fdopen', patched_fdopen)
    if operation == 'fsync':
        monkeypatch.setattr(saves.os, 'fsync', fail_fsync)
    with pytest.raises(OSError, match='injected partial staging failure'):
        model.write('inplace')

    assert failed
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


@pytest.mark.parametrize('increment', [None, 'auto'])
def test_mid_commit_failure_rolls_back_existing_and_new_destinations(tmp_path, monkeypatch, increment):
    model = _model(tmp_path)
    _edit_all(model)
    # Auto-increment must also recover a pre-existing destination, rather than
    # assuming every incremented file is new and deleting its original bytes.
    if increment == 'auto':
        (tmp_path / 'grid_011.tgc').write_bytes(b'pre-existing destination\n')
    before_disk, before_state = _inventory(tmp_path), _state(model)
    replace = saves.os.replace
    attempts = []

    def fail_second(source, destination):
        attempts.append(Path(destination))
        if len(attempts) == 2:
            raise PermissionError(errno.EACCES, 'injected replacement failure', str(destination))
        return replace(source, destination)

    monkeypatch.setattr(saves.os, 'replace', fail_second)
    with pytest.raises(saves.ModelSaveError) as raised:
        model.write(increment)

    assert raised.value.failed_destination == attempts[1]
    assert raised.value.replaced_paths == (attempts[0],)
    assert raised.value.unrestored_paths == ()
    assert raised.value.recovery_paths == {}
    assert isinstance(raised.value.__cause__, PermissionError)
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_rollback_failure_reports_original_backup_and_keeps_live_edits(tmp_path, monkeypatch):
    model = _model(tmp_path)
    _edit_all(model)
    before_disk, before_state = _inventory(tmp_path), _state(model)
    replace = saves.os.replace
    attempts = []

    def fail_commit_and_rollback(source, destination):
        attempts.append(Path(destination))
        if len(attempts) >= 2:
            raise PermissionError(errno.EACCES, 'injected commit/rollback failure', str(destination))
        return replace(source, destination)

    monkeypatch.setattr(saves.os, 'replace', fail_commit_and_rollback)
    with pytest.raises(saves.ModelSaveError) as raised:
        model.write(None)

    error = raised.value
    assert error.failed_destination == attempts[1]
    assert error.replaced_paths == (attempts[0],)
    assert error.unrestored_paths == (attempts[0],)
    assert set(error.recovery_paths) == {attempts[0]}
    recovery = error.recovery_paths[attempts[0]]
    assert recovery.is_file()
    assert recovery.read_bytes() == before_disk[attempts[0].relative_to(tmp_path)]
    assert attempts[0].read_bytes() != recovery.read_bytes()
    assert str(attempts[0]) in str(error)
    assert str(recovery) in str(error)
    assert _state(model) == before_state
    for relative, original in before_disk.items():
        if tmp_path / relative != attempts[0]:
            assert (tmp_path / relative).read_bytes() == original
    expected_paths = set(before_disk) | {recovery.relative_to(tmp_path)}
    assert set(_inventory(tmp_path)) == expected_paths


def test_recovery_diagnostic_displays_native_windows_paths():
    destination = PureWindowsPath('C:/models/grid_003.tgc')
    recovery = PureWindowsPath('C:/models/.grid_003.tgc.pytuflow-backup.tmp')

    error = saves.ModelSaveError(destination, (destination,), (destination,),
                                 {destination: recovery})

    assert str(destination) in str(error)
    assert str(recovery) in str(error)


def test_backup_inspection_error_retains_recovery_copy_and_continues_rollback(tmp_path, monkeypatch):
    model = _model(tmp_path)
    _edit_all(model)
    before_disk, before_state = _inventory(tmp_path), _state(model)
    replace, path_stat = saves.os.replace, Path.stat
    attempts = []
    unavailable_backup = None
    inspections = 0

    def fail_commit_and_one_rollback(source, destination):
        nonlocal unavailable_backup
        attempts.append(Path(destination))
        if len(attempts) == 3:
            raise PermissionError(errno.EACCES, 'injected replacement failure', str(destination))
        if len(attempts) == 4:
            unavailable_backup = Path(source)
            raise PermissionError(errno.EACCES, 'injected rollback failure', str(destination))
        return replace(source, destination)

    def fail_backup_inspection(path, *args, **kwargs):
        nonlocal inspections
        if path == unavailable_backup:
            inspections += 1
            raise OSError(errno.EIO, 'injected backup inspection failure', str(path))
        return path_stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(saves.os, 'replace', fail_commit_and_one_rollback)
        patch.setattr(Path, 'stat', fail_backup_inspection)
        with pytest.raises(saves.ModelSaveError) as raised:
            model.write(None)

    error = raised.value
    assert inspections
    assert error.failed_destination == attempts[2]
    assert error.replaced_paths == tuple(attempts[:2])
    assert error.unrestored_paths == (attempts[1],)
    assert error.recovery_paths == {attempts[1]: unavailable_backup}
    assert unavailable_backup.read_bytes() == before_disk[attempts[1].relative_to(tmp_path)]
    assert isinstance(error.__cause__, PermissionError)
    assert any('backup inspection' in note for note in error.__cause__.__notes__)
    assert _state(model) == before_state
    for relative, original in before_disk.items():
        if tmp_path / relative != attempts[1]:
            assert (tmp_path / relative).read_bytes() == original
    assert set(_inventory(tmp_path)) == set(before_disk) | {unavailable_backup.relative_to(tmp_path)}


@pytest.mark.parametrize(('increment', 'root_name', 'child_suffix'), [
    ('auto', 'model_011.tcf', '011'),
    ('025', 'model_025.tcf', '025'),
    ('review', 'model_review.tcf', '001'),
    ('inplace', 'model_010.tcf', '010'),
    (None, 'model_010.tcf', None),
])
def test_increment_modes_preserve_ownership_and_child_identity(tmp_path, increment, root_name, child_suffix):
    model = _model(tmp_path)
    _edit_all(model)
    original_disk = _inventory(tmp_path)
    children = _children(model)
    all_inputs = [inp for cf in [model, *children] for inp in cf.inputs.inputs(include_hidden=True)]
    identities = [(id(inp), inp.uuid) for inp in all_inputs]
    include_inputs = [inp for inp in model.inputs.inputs(include_hidden=True) if inp.trd is not None]
    old_history = tuple(tuple(block) for block in model.altered_inputs._updated_inputs)

    assert model.write(increment) is model

    names = (
        [f'grid_{child_suffix}.tgc', f'boundary_{child_suffix}.tbc', f'forcing_{child_suffix}.trd']
        if child_suffix is not None else ['grid_003.tgc', 'boundary_004.tbc', 'forcing_002.trd']
    )
    assert model.fpath == tmp_path / root_name
    assert [(id(inp), inp.uuid) for inp in all_inputs] == identities
    assert all(a is b for a, b in zip(_children(model), children))
    assert [child.fpath for child in children] == [tmp_path / name for name in names[:2]]
    assert all(inp.trd == tmp_path / names[2] for inp in include_inputs)
    root_bytes = model.fpath.read_bytes()
    for name in names:
        assert name.encode() in root_bytes
        assert (tmp_path / name).is_file()
    assert b'Hardware == CPU' in root_bytes
    assert b'Timestep' not in root_bytes
    assert b'! included edit' in (tmp_path / names[2]).read_bytes()
    assert not any(cf.dirty for cf in [model, *children])
    assert not any(inp.dirty for inp in all_inputs)
    assert not model.altered_inputs._updated_inputs[-1]
    assert tuple(tuple(block) for block in model.altered_inputs._updated_inputs[:len(old_history)]) == old_history
    for inp in model.inputs:
        if inp.cf:
            assert tuple(inp._cf_loaded_paths) == tuple(child.fpath for child in inp.cf)
            assert tuple(inp.files) == tuple(child.fpath for child in inp.cf)
    destinations = {Path(root_name), *(Path(name) for name in names)}
    for path, original in original_disk.items():
        if path not in destinations:
            assert (tmp_path / path).read_bytes() == original


def test_second_save_reuses_clean_children_and_persists_new_edit(tmp_path):
    model = _model(tmp_path)
    _edit_all(model)
    model.write('auto')
    first_children = _children(model)
    first_names = [child.fpath for child in first_children]
    include_path = next(inp.trd for inp in model.inputs if inp.trd is not None)
    saved_dependencies = {path: path.read_bytes() for path in [*first_names, include_path]}
    model.find_input('Hardware')[0].rhs = 'GPU'

    model.write('auto')

    assert model.fpath.name == 'model_012.tcf'
    assert [child.fpath for child in _children(model)] == first_names
    assert all(a is b for a, b in zip(_children(model), first_children))
    assert next(inp.trd for inp in model.inputs if inp.trd is not None) == include_path
    for path, original in saved_dependencies.items():
        assert path.read_bytes() == original
    assert b'Hardware == GPU' in model.fpath.read_bytes()
    assert b'grid_011.tgc' in model.fpath.read_bytes()
    assert not (tmp_path / 'grid_012.tgc').exists()
    assert not (tmp_path / 'forcing_012.trd').exists()
    assert not model.dirty


@pytest.mark.parametrize('alias', [False, True], ids=['same-path', 'hardlink'])
def test_distinct_owners_of_one_destination_are_rejected_before_staging(tmp_path, monkeypatch, alias):
    first = tmp_path / 'shared_001.tgc'
    first.write_bytes(b'Cell Size == 5\n')
    other = tmp_path / 'alias_001.tgc' if alias else first
    if alias:
        os.link(first, other)
    path = tmp_path / 'model_001.tcf'
    path.write_text(
        f'Geometry Control File == {first.name}\nGeometry Control File == {other.name}\n',
        encoding='utf-8', newline='\n',
    )
    model = TCF(path)
    children = _children(model)
    assert len(children) == 2 and children[0] is not children[1]
    children[0].find_input('Cell Size')[0].rhs = '10'
    children[1].find_input('Cell Size')[0].rhs = '20'
    before_disk, before_state = _inventory(tmp_path), _state(model)
    staged = []

    def forbidden_stage(destination, data):
        staged.append(destination)
        raise AssertionError('duplicate plan reached staging')

    monkeypatch.setattr(saves, '_stage_bytes', forbidden_stage)
    with pytest.raises(ValueError, match='(?i)(duplicate|destination|same|owner)'):
        model.write(None)

    assert not staged
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_one_shared_child_object_is_written_once(tmp_path, monkeypatch):
    child_path = tmp_path / 'shared_001.tgc'
    child_path.write_bytes(b'Cell Size == 5\n')
    path = tmp_path / 'model_001.tcf'
    path.write_bytes(
        b'Geometry Control File == shared_001.tgc\n'
        b'Geometry Control File == shared_001.tgc\n'
    )
    model = TCF(path)
    references = [inp for inp in model.inputs if inp.cf]
    shared = references[0].cf[0]
    references[1].cf[0] = shared
    shared.find_input('Cell Size')[0].rhs = '10'
    real_replace = saves.os.replace
    replacements = []

    def record_replace(source, destination):
        replacements.append(Path(destination))
        return real_replace(source, destination)

    monkeypatch.setattr(saves.os, 'replace', record_replace)
    model.write(None)

    assert replacements.count(child_path) == 1
    assert all(inp.cf[0] is shared for inp in references)
    assert child_path.read_bytes() == b'Cell Size == 10\n'


@pytest.mark.parametrize('increment', [None, 'auto'])
def test_lost_replace_acknowledgement_recovers_the_attempted_destination(tmp_path, monkeypatch, increment):
    path = tmp_path / 'model_001.tcf'
    path.write_bytes(b'Hardware == GPU\n')
    model = TCF(path)
    model.find_input('Hardware')[0].rhs = 'CPU'
    before_disk, before_state = _inventory(tmp_path), _state(model)
    replace = saves.os.replace
    calls = []

    def replace_then_raise(source, destination):
        calls.append(Path(destination))
        replace(source, destination)
        if len(calls) == 1:
            raise OSError('lost replacement acknowledgement')

    monkeypatch.setattr(saves.os, 'replace', replace_then_raise)
    with pytest.raises(saves.ModelSaveError) as raised:
        model.write(increment)

    assert raised.value.replaced_paths == (calls[0],)
    assert raised.value.unrestored_paths == ()
    assert raised.value.recovery_paths == {}
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_staging_open_failure_closes_descriptor_and_removes_temporary(tmp_path, monkeypatch):
    path = tmp_path / 'model_001.tcf'
    path.write_bytes(b'Hardware == GPU\n')
    model = TCF(path)
    before_disk, before_state = _inventory(tmp_path), _state(model)
    descriptors = []

    def fail_open(fd, *args, **kwargs):
        descriptors.append(fd)
        raise OSError('injected fdopen failure')

    monkeypatch.setattr(saves.os, 'fdopen', fail_open)
    with pytest.raises(OSError, match='injected fdopen failure'):
        model.write(None)

    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_saving_retains_event_database_inputs_in_command_configs(tmp_path):
    path = tmp_path / 'events_001.tcf'
    path.write_bytes(b'BC Event Text == ~event~\nBC Event Name == one\nHardware == GPU\n')
    model = TCF(path)
    original = [tuple(inp.config.event_db.inputs) for inp in model.inputs]
    assert any(original)

    model.write(None)

    assert [tuple(inp.config.event_db.inputs) for inp in model.inputs] == original


def test_lost_rollback_acknowledgement_does_not_report_a_consumed_backup(tmp_path, monkeypatch):
    path = tmp_path / 'model_001.tcf'
    path.write_bytes(b'Hardware == GPU\n')
    model = TCF(path)
    model.find_input('Hardware')[0].rhs = 'CPU'
    before_disk, before_state = _inventory(tmp_path), _state(model)
    replace = saves.os.replace

    def replace_then_raise(source, destination):
        replace(source, destination)
        raise OSError('lost acknowledgement')

    monkeypatch.setattr(saves.os, 'replace', replace_then_raise)
    with pytest.raises(saves.ModelSaveError) as raised:
        model.write(None)

    assert raised.value.unrestored_paths == ()
    assert raised.value.recovery_paths == {}
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


@pytest.mark.parametrize('layout', ['empty', 'missing', 'repeated', 'scoped'])
@pytest.mark.parametrize('edited', [False, True])
def test_unrepresentable_include_layouts_are_preserved_or_rejected(tmp_path, layout, edited):
    path = tmp_path / 'model_001.tcf'
    include = tmp_path / 'settings.trd'
    if layout != 'missing':
        include.write_bytes(b'' if layout == 'empty' else b'Timestep == 1\n')
    directive = b'Read File == settings.trd\n'
    if layout == 'repeated':
        directive *= 2
    elif layout == 'scoped':
        directive = b'If Scenario == DEV\n    Read File == settings.trd\nEnd If\n'
    path.write_bytes(directive + b'Hardware == GPU\n')
    model = TCF(path)
    if edited:
        model.find_input('Hardware')[0].rhs = 'CPU'
    before_disk, before_state = _inventory(tmp_path), _state(model)

    if edited:
        with pytest.raises(ValueError, match='flattened include writer'):
            model.write(None)
        assert _state(model) == before_state
    else:
        model.write(None)

    assert _inventory(tmp_path) == before_disk


def test_repeated_include_edit_is_rejected_even_when_parent_reference_is_unchanged(tmp_path):
    path = tmp_path / 'model_001.tcf'
    (tmp_path / 'settings.trd').write_bytes(b'Timestep == 1\n')
    path.write_bytes(b'Read File == settings.trd\nRead File == settings.trd\n')
    model = TCF(path)
    model.find_input('Timestep')[0].rhs = '2'
    before_disk, before_state = _inventory(tmp_path), _state(model)

    with pytest.raises(ValueError, match='flattened include writer'):
        model.write(None)

    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_new_destinations_through_directory_alias_are_rejected(tmp_path):
    directory = tmp_path / 'geometry'
    alias = tmp_path / 'alias'
    directory.mkdir()
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(directory)],
                       check=True, capture_output=True)
    else:
        alias.symlink_to(directory, target_is_directory=True)
    for suffix in ('003', '004'):
        (directory / f'grid_{suffix}.tgc').write_bytes(b'Cell Size == 5\n')
    path = tmp_path / 'model_010.tcf'
    path.write_bytes(b'Geometry Control File == geometry/grid_003.tgc\n'
                     b'Geometry Control File == geometry/grid_004.tgc\n')
    model = TCF(path)
    first, second = _children(model)
    second.fpath = alias / 'grid_004.tgc'
    first.find_input('Cell Size')[0].rhs = '10'
    second.find_input('Cell Size')[0].rhs = '20'
    before_disk, before_state = _inventory(tmp_path), _state(model)

    with pytest.raises(ValueError, match='Duplicate physical save destination'):
        model.write('auto')

    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state
    assert not (directory / 'grid_011.tgc').exists()
