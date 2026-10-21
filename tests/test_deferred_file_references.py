"""Focused tests for syntax-only TUFLOW input references."""
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow._tmf.file_reference import make_file_reference
from pytuflow._tmf.parsers.command import Command
from pytuflow._tmf.settings import TCFConfig
from pytuflow._tmf.tfpathlib import TuflowPath


def config(tmp_path: Path) -> TCFConfig:
    return TCFConfig(control_file=tmp_path / 'model.tcf', init_from_tcf=False,
                     file_resolution='deferred')


def test_glob_and_layer_patterns_are_immutable(tmp_path):
    with patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')):
        cmd = Command('Read GIS Mat == gis/model_*.gpkg >> 2d_mat_*', config(tmp_path))
        ref = make_file_reference(next(cmd.parts()))
    assert ref.path_pattern.name == 'model_*.gpkg'
    assert ref.layer_pattern == '2d_mat_*'
    assert ref.requires_directory_scan
    assert ref.requires_layer_scan
    with pytest.raises(FrozenInstanceError):
        ref.origin = 'different'


def test_gpkg_all_does_not_open_database(tmp_path):
    with patch.object(Path, 'exists', side_effect=AssertionError('stat')):
        cmd = Command('Read GIS Code == gis/model.gpkg >> all', config(tmp_path))
    assert '>> all' in cmd.value_expanded_path


def test_bc_event_source_is_not_a_file(tmp_path):
    cmd = Command('BC Event Source == ~AEP~ | 05.00p', config(tmp_path))
    assert not cmd.is_value_a_file()


def test_deferred_context_does_not_glob_missing_input(tmp_path):
    fpath = tmp_path / 'model.tcf'
    fpath.write_text('Read GIS Code == gis/missing.shp\n', encoding='utf-8')
    tcf = TCF(fpath)
    with patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')):
        run = tcf.context(file_resolution='deferred')
        refs = [ref for inp in run.inputs for ref in inp.file_references]
    assert refs
    assert refs[0].path_pattern.name == 'missing.shp'
    assert refs[0].requires_attribute_scan


def test_invalid_mode_rejected(tmp_path):
    fpath = tmp_path / 'model.tcf'
    fpath.write_text('Read GIS Code == gis/missing.shp\n', encoding='utf-8')
    with pytest.raises(ValueError, match='file_resolution'):
        TCF(fpath).context(file_resolution='unknown')


def test_literal_relative_input_reference_from_eager_config(tmp_path):
    from pytuflow._tmf.inp.file import FileInput

    cmd = Command('Read File == subdir/extra.trd',
                  TCFConfig(control_file=tmp_path / 'model.tcf', init_from_tcf=False))
    inp = FileInput(None, cmd, load_control_files=False)
    with patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')):
        ref = inp.file_references[0]
    assert ref.path_pattern == tmp_path / 'subdir' / 'extra.trd'
    assert not ref.requires_directory_scan
    assert not ref.requires_layer_scan


def test_variable_substitution_without_glob(tmp_path):
    cfg = config(tmp_path)
    cfg.variables = {'TEST': 'DEV'}
    with patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')):
        cmd = Command('Read GIS Code == gis/code_<<TEST>>.shp', cfg)
        ref = make_file_reference(next(cmd.parts()))
    assert ref.path_pattern.name == 'code_DEV.shp'
    assert not ref.unresolved_variables


def test_unresolved_variable_is_preserved_in_reference(tmp_path):
    cmd = Command('Read GIS Mat == gis/mat_<<MISSING>>.gpkg >> 2d_mat_*', config(tmp_path))
    ref = make_file_reference(next(cmd.parts()))
    assert ref.unresolved_variables == ('<<MISSING>>',)
    assert ref.layer_pattern == '2d_mat_*'
    assert ref.requires_directory_scan


def test_non_source_commands_excluded(tmp_path):
    from pytuflow._tmf.inp.file import FileInput
    cmd = Command('Write GIS == checks/debug.gpkg', config(tmp_path))
    inp = FileInput(None, cmd, load_control_files=False)
    assert inp.file_references == ()


def test_database_reference_requests_deferred_inspection(tmp_path):
    cmd = Command('BC Database == bc_dbase.csv', config(tmp_path))
    ref = make_file_reference(next(cmd.parts()))
    assert ref.path_pattern.name == 'bc_dbase.csv'
    assert ref.requires_database_scan
    assert not ref.requires_layer_scan


def test_plain_gis_file_does_not_require_attribute_scan(tmp_path):
    cmd = Command('Read GIS Code == gis/2d_code_001.shp', config(tmp_path))
    ref = make_file_reference(next(cmd.parts()))
    assert not ref.requires_attribute_scan
    assert not ref.requires_database_scan


def test_1d_gis_file_marks_attribute_dependencies(tmp_path):
    cmd = Command('Read GIS Network == gis/1d_nwk_001.shp', config(tmp_path))
    ref = make_file_reference(next(cmd.parts()))
    assert ref.requires_attribute_scan
