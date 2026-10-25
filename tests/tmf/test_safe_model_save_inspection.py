"""Filesystem inspection errors must not be mistaken for absent save targets."""

import errno
from pathlib import Path

import pytest

from pytuflow._tmf.cf import cf_build_state as saves
from pytuflow._tmf.cf.tcf import TCF


def _inventory(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


def _state(model: TCF) -> tuple:
    owners = [model, *(child for inp in model.inputs for child in inp.cf)]
    return tuple((
        id(owner), owner.fpath, owner.dirty, id(owner.config), owner.config.control_file,
        tuple((id(inp), inp.uuid, inp.command().original_text, inp.dirty, inp.trd)
              for inp in owner.inputs.inputs(include_hidden=True)),
        tuple(tuple((id(change), change.uuid, change.change_type) for change in block)
              for block in owner.altered_inputs._updated_inputs),
    ) for owner in owners)


def _use_python_314_exists_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the fault injection meaningful on both supported Python versions."""
    exists = Path.exists

    def suppress_oserror(path, *args, **kwargs):
        try:
            return exists(path, *args, **kwargs)
        except OSError:
            return False

    monkeypatch.setattr(Path, 'exists', suppress_oserror)


def test_backup_staging_stat_error_aborts_before_any_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / 'model_010.tcf'
    child_path = tmp_path / 'grid_003.tgc'
    source.write_bytes(b'Geometry Control File == grid_003.tgc\n')
    child_path.write_bytes(b'Cell Size == 5\n')
    model = TCF(source)
    model.tgc().find_input('Cell Size')[0].rhs = '10'
    before_disk, before_state = _inventory(tmp_path), _state(model)
    stage, stat, replace = saves._stage_bytes, Path.stat, saves.os.replace
    staged = []
    replacements = []
    inspections = []

    def record_stage(destination, data):
        result = stage(destination, data)
        staged.append(Path(destination))
        return result

    def fail_backup_stat(path, *args, **kwargs):
        # Both new outputs are staged, and the next child status check decides
        # whether its original needs a backup. Fail once, as a transient EIO.
        if path == child_path and len(staged) == 2 and not inspections:
            inspections.append(path)
            raise OSError(errno.EIO, 'injected original-backup status failure', str(path))
        return stat(path, *args, **kwargs)

    def record_replace(source, destination):
        replacements.append(Path(destination))
        return replace(source, destination)

    with monkeypatch.context() as patch:
        _use_python_314_exists_semantics(patch)
        patch.setattr(saves, '_stage_bytes', record_stage)
        patch.setattr(Path, 'stat', fail_backup_stat)
        patch.setattr(saves.os, 'replace', record_replace)
        with pytest.raises(OSError, match='injected original-backup status failure') as caught:
            model.write(None)

    assert caught.value.errno == errno.EIO
    assert inspections == [child_path]
    assert not replacements
    assert _inventory(tmp_path) == before_disk
    assert _state(model) == before_state


def test_unknown_new_target_status_cannot_be_reported_as_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / 'model_010.tcf'
    destination = tmp_path / 'model_011.tcf'
    source.write_bytes(b'Hardware == GPU\n')
    model = TCF(source)
    model.find_input('Hardware')[0].rhs = 'CPU'
    before_disk, before_state = _inventory(tmp_path), _state(model)
    replace, unlink, stat = saves.os.replace, Path.unlink, Path.stat
    rollback_started = False
    inspections = []

    def lose_replacement_acknowledgement(staged, target):
        replace(staged, target)
        raise OSError(errno.EIO, 'injected lost replacement acknowledgement', str(target))

    def fail_target_rollback(path, *args, **kwargs):
        nonlocal rollback_started
        if path == destination:
            rollback_started = True
            raise PermissionError(errno.EACCES, 'injected rollback removal failure', str(path))
        return unlink(path, *args, **kwargs)

    def fail_rollback_inspection(path, *args, **kwargs):
        if rollback_started and path == destination:
            inspections.append(path)
            raise OSError(errno.EIO, 'injected rollback status failure', str(path))
        return stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        _use_python_314_exists_semantics(patch)
        patch.setattr(saves.os, 'replace', lose_replacement_acknowledgement)
        patch.setattr(Path, 'unlink', fail_target_rollback)
        patch.setattr(Path, 'stat', fail_rollback_inspection)
        with pytest.raises(saves.ModelSaveError) as caught:
            model.write('auto')

    assert inspections
    assert caught.value.unrestored_paths == (destination,)
    assert caught.value.recovery_paths == {}  # This destination had no original.
    assert 'rollback incomplete' in str(caught.value)
    assert destination.read_bytes() == b'Hardware == CPU\n'
    assert source.read_bytes() == before_disk[source.name]
    assert set(_inventory(tmp_path)) == set(before_disk) | {destination.name}
    assert _state(model) == before_state
