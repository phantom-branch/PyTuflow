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
    assert not refs[0].requires_attribute_scan


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


def test_nested_control_file_owns_reference_path(tmp_path):
    from pytuflow._tmf.context import Context
    from pytuflow._tmf.inp.gis import GisInput

    owner = tmp_path / 'model' / 'geometry.tgc'
    cfg = TCFConfig(control_file=tmp_path / 'main.tcf', init_from_tcf=False)
    source = GisInput(None, Command('Read GIS Code == ../gis/2d_code.shp',
                                    cfg, parent=owner), load_control_files=False)
    ctx = Context(config=cfg)
    ctx.file_resolution = 'deferred'
    run = source.context(context=ctx)
    # Preserve lexical '..' rather than dereference a possible junction/symlink.
    assert run.file_references[0].path_pattern == owner.parent / '../gis/2d_code.shp'


def test_context_after_parse_has_no_filesystem_or_gis_io(tmp_path):
    """Deferred contexts cannot enumerate, stat or open model dependencies."""
    fpath = tmp_path / 'model.tcf'
    fpath.write_text(
        'Read GIS Code == gis/code_*.gpkg >> 2d_code_*\n'
        'Read GRID Zpts == grids/missing_*.tif\n'
        'BC Database == bc_dbase.csv\n',
        encoding='utf-8',
    )
    tcf = TCF(fpath)  # Parsing is deliberately excluded from the I/O contract.
    forbidden = AssertionError('deferred context unexpectedly touched filesystem')
    with (
        patch.object(TuflowPath, 'glob', side_effect=forbidden),
        patch.object(Path, 'stat', side_effect=forbidden),
        patch.object(Path, 'open', side_effect=forbidden),
        patch.object(Path, 'resolve', side_effect=forbidden),
        patch('os.scandir', side_effect=forbidden),
        patch('sqlite3.connect', side_effect=forbidden),
        patch.object(TuflowPath, 'open_gis', side_effect=forbidden),
        patch.object(TuflowPath, '_gpkg_layers', side_effect=forbidden),
    ):
        run = tcf.context(file_resolution='deferred')
        # Use the exact recursive traversal consumed by downstream preflight.
        refs = tuple(ref for inp in run.find_input() for ref in inp.file_references)
    assert any(ref.requires_layer_scan for ref in refs)
    assert any(ref.requires_directory_scan for ref in refs)
    assert any(ref.requires_database_scan for ref in refs)


def test_deferred_eager_parity_for_literal_existing_path(tmp_path):
    gis = tmp_path / 'gis'
    gis.mkdir()
    (gis / '2d_code.shp').touch()
    fpath = tmp_path / 'model.tcf'
    fpath.write_text('Read GIS Code == gis/2d_code.shp\n', encoding='utf-8')
    tcf = TCF(fpath)
    eager = tcf.context()
    eager_files = {
        str(path) for inp in eager.inputs for path in inp.files
        if str(path).lower().endswith('.shp')
    }
    deferred = tcf.context(file_resolution='deferred')
    deferred_files = {
        str(ref.path_pattern) for inp in deferred.inputs
        for ref in inp.file_references if ref.path_pattern.suffix.lower() == '.shp'
    }
    assert eager_files == deferred_files


def test_nested_tgc_references_preserve_owning_directory(tmp_path):
    model = tmp_path / 'model'
    geom = tmp_path / 'geom'
    model.mkdir()
    geom.mkdir()
    control = model / 'main.tcf'
    tgc = geom / 'geometry.tgc'
    tgc.write_text('Read GIS Code == ../gis/2d_code.shp\n', encoding='utf-8')
    control.write_text('Geometry Control File == ../geom/geometry.tgc\n', encoding='utf-8')
    tcf = TCF(control)
    run = tcf.context(file_resolution='deferred')
    nested = [
        cf for inp in run.inputs for cf in inp.cf if getattr(cf, 'fpath', None) == tgc
    ]
    assert nested, 'Nested TGC run context was not constructed'
    refs = tuple(ref for cf in nested for inp in cf.inputs for ref in inp.file_references)
    assert any('2d_code.shp' in str(ref.path_pattern) for ref in refs)
    # Preserve '..' in the emitted path; compare only its lexical location.
    import os
    assert all(os.path.normpath(ref.base_directory) == os.path.normpath(geom) for ref in refs)


def test_440_synthetic_scenario_contexts_are_probe_free(tmp_path, capsys):
    """A repeated ensemble remains syntactic after the one-time model parse."""
    import time
    import tracemalloc

    tcf_path = tmp_path / 'ensemble.tcf'
    tcf_path.write_text(
        'IF Scenario == DEV\n'
        '    Read GIS Code == gis/2d_code_DEV.shp\n'
        'ELSE\n'
        '    Read GIS Code == gis/2d_code_EXG.shp\n'
        'END IF\n',
        encoding='utf-8',
    )
    tcf = TCF(tcf_path)
    counts = {'glob': 0}
    def no_glob(*args, **kwargs):
        counts['glob'] += 1
        raise AssertionError('Deferred contexts must not expand globs')
    tracemalloc.start()
    start = time.perf_counter()
    with (
        patch.object(TuflowPath, 'glob', side_effect=no_glob),
        patch.object(Path, 'stat', side_effect=AssertionError('stat')),
    ):
        for i in range(440):
            scenario = 'DEV' if i % 2 else 'EXG'
            run = tcf.context(f'-s1 {scenario}', file_resolution='deferred')
            paths = {
                ref.path_pattern.name for inp in run.inputs for ref in inp.file_references
            }
            assert f'2d_code_{scenario}.shp' in paths
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert counts['glob'] == 0
    print(f'440 deferred synthetic contexts: {elapsed:.3f}s, peak={peak / (1024 * 1024):.1f}MiB')


@pytest.mark.parametrize('scenario', ['DEV', 'EXG'])
def test_scenario_specific_eager_deferred_file_parity(tmp_path, scenario):
    gis = tmp_path / 'gis'
    gis.mkdir()
    for name in ('DEV', 'EXG'):
        (gis / f'2d_code_{name}.shp').touch()
    tcf_path = tmp_path / 'model.tcf'
    tcf_path.write_text(
        'IF Scenario == DEV\n'
        '    Read GIS Code == gis/2d_code_DEV.shp\n'
        'ELSE\n'
        '    Read GIS Code == gis/2d_code_EXG.shp\n'
        'END IF\n',
        encoding='utf-8',
    )
    tcf = TCF(tcf_path)
    eager = tcf.context(f'-s1 {scenario}')
    eager_paths = {
        str(file) for inp in eager.inputs for file in inp.files
        if str(file).endswith('.shp')
    }
    deferred = tcf.context(f'-s1 {scenario}', file_resolution='deferred')
    deferred_paths = {
        str(ref.path_pattern) for inp in deferred.inputs
        for ref in inp.file_references if str(ref.path_pattern).endswith('.shp')
    }
    assert eager_paths == deferred_paths
    assert {Path(file).name for file in deferred_paths} == {f'2d_code_{scenario}.shp'}


def test_wildcard_deferred_pattern_materialises_to_eager_dependencies(tmp_path):
    gis = tmp_path / 'gis'
    gis.mkdir()
    expected = {gis / '2d_code_001.shp', gis / '2d_code_002.shp'}
    for source in expected:
        source.touch()
    tcf_path = tmp_path / 'model.tcf'
    tcf_path.write_text('Read GIS Code == gis/2d_code_*.shp\n', encoding='utf-8')
    tcf = TCF(tcf_path)
    eager_paths = {
        Path(file) for inp in tcf.context().inputs for file in inp.files
        if str(file).endswith('.shp')
    }
    run = tcf.context(file_resolution='deferred')
    patterns = [
        ref.path_pattern for inp in run.inputs for ref in inp.file_references
        if ref.path_pattern.suffix.lower() == '.shp'
    ]
    assert len(patterns) == 1
    assert '*' in patterns[0].name
    resolved = set(patterns[0].parent.glob(patterns[0].name))
    assert eager_paths == resolved == expected


def test_event_command_deferred_reconstruction_preserves_event_name(tmp_path):
    from pytuflow._tmf.context import Context
    from pytuflow._tmf.inp.event import EventInput
    from pytuflow._tmf.parsers.command import EventCommand

    cfg = config(tmp_path)
    command = EventCommand('BC Event Source == ~AEP~ | 05.00p', cfg)
    command.event_name = 'Q100'
    original = EventInput(None, command)
    context = Context(config=cfg)
    context.file_resolution = 'deferred'
    run = original.context(context=context)
    assert run._command.event_name == 'Q100'
    assert run.file_references == ()


def test_deferred_gpkg_all_materialises_when_files_requested(tmp_path):
    import sqlite3
    from pytuflow._tmf.inp.gis import GisInput

    gpkg = tmp_path / 'input.gpkg'
    with sqlite3.connect(gpkg) as database:
        database.execute('CREATE TABLE gpkg_contents (table_name TEXT)')
        database.executemany(
            'INSERT INTO gpkg_contents (table_name) VALUES (?)',
            [('2d_code_L',), ('2d_code_P',)],
        )
    cmd = Command('Read GIS Code == input.gpkg >> all', config(tmp_path))
    inp = GisInput(None, cmd, load_control_files=False)
    refs = inp.file_references
    assert len(refs) == 1
    assert refs[0].layer_pattern == 'all'
    files = inp.files
    assert {f.lyrname for f in files} == {'2d_code_L', '2d_code_P'}


@pytest.mark.parametrize(
    ('event', 'expected_source'),
    [('Q100', '100yr_001.csv'), ('QPMF', 'PMFyr_001.csv')],
)
def test_event_file_and_bc_sources_remain_event_specific(tmp_path, event, expected_source):
    """A TEF's BC Event Source is an assignment, not a required file."""
    tcf_path = tmp_path / 'model.tcf'
    tef_path = tmp_path / 'events.tef'
    bc_path = tmp_path / 'bc_dbase.csv'
    tcf_path.write_text(
        'Event File == events.tef\nBC Database == bc_dbase.csv\n', encoding='utf-8',
    )
    tef_path.write_text(
        'Define Event == Q100\n'
        '    BC Event Source == _event_ | 100yr\n'
        'End Define\n'
        'Define Event == QPMF\n'
        '    BC Event Source == _event_ | PMFyr\n'
        'End Define\n',
        encoding='utf-8',
    )
    bc_path.write_text(
        'Name,Source,Column 1,Column 2,Add Col 1,Mult Col 2,Add Col 2,Column 3,Column 4\n'
        'FC01,_event__001.csv,inflow_time_hr,inflow,,,,,\n',
        encoding='utf-8',
    )
    tcf = TCF(tcf_path)
    with patch.object(TuflowPath, 'glob', side_effect=AssertionError('no glob')):
        run = tcf.context(f'-e1 {event}', file_resolution='deferred')
        references = [
            ref for inp in run.find_input() for ref in inp.file_references
        ]
    assert any(ref.path_pattern.name == 'bc_dbase.csv' for ref in references)
    assert not any('BC Event Source' in ref.origin for ref in references)
    # Eager mode still exposes a loaded database; deferred uses cached rows.
    assert tcf.context(f'-e1 {event}').bc_dbase().df.loc['FC01']['Source'] == expected_source
    sources = run.deferred_database_sources()
    assert len(sources) == 1
    assert sources[0].database_kind == 'bc'
    assert sources[0].entry_name == 'FC01'
    assert sources[0].database_path == bc_path
    assert sources[0].path_pattern == tmp_path / expected_source


    database_inputs = run.find_input(lhs='BC Database')
    assert len(database_inputs) == 1
    secondary = database_inputs[0].database_source_references
    assert {ref.path_pattern.name for ref in secondary} == {expected_source}
    assert all(ref.origin.startswith('bc database row') for ref in secondary)


@pytest.mark.parametrize('mode', ['eager', 'deferred'])
def test_multipart_material_file_materialises_without_treating_multiplier_as_path(tmp_path, mode):
    from pytuflow._tmf.inp.mat import MatDatabaseInput

    material = tmp_path / 'materials.csv'
    material.write_text('Material, Manning\\n1,0.03\\n', encoding='utf-8')
    cfg = config(tmp_path)
    cfg.file_resolution = mode
    command = Command('Read Materials File == materials.csv | 0.8', cfg)
    input_ = MatDatabaseInput(None, command, load_control_files=False)
    assert input_.multiplier == pytest.approx(0.8)
    assert input_.files == [material]
    assert not input_.has_missing_files


def test_deferred_material_database_reports_source_without_rechecking_disk(tmp_path):
    tcf_path = tmp_path / 'model.tcf'
    materials = tmp_path / 'materials.csv'
    tcf_path.write_text('Read Materials File == materials.csv | 0.8\n', encoding='utf-8')
    materials.write_text('Material ID,Manning\'s n\n1,0.03\n', encoding='utf-8')
    model = TCF(tcf_path)
    with (
        patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')),
        patch.object(Path, 'stat', side_effect=AssertionError('stat')),
        patch.object(Path, 'open', side_effect=AssertionError('open')),
    ):
        run = model.context(file_resolution='deferred')
        mat_input = run.find_input(lhs='Read Materials File')[0]
        refs = mat_input.file_references
        secondary = mat_input.database_source_references
    assert len(refs) == 1
    assert refs[0].database_kind == 'materials'
    assert secondary == ()


def test_deferred_material_database_without_secondary_sources(tmp_path):
    """The material CSV is a primary file, not a perpetual unresolved scan."""
    tcf_path = tmp_path / 'model.tcf'
    mat_path = tmp_path / 'materials.csv'
    tcf_path.write_text('Read Materials File == materials.csv | 0.8\n', encoding='utf-8')
    mat_path.write_text(
        "Material ID,Manning's n,Rainfall Losses,Land Use Hazard ID,SRF,Fraction Impervious\n"
        '1,0.03,0,0,0,0\n',
        encoding='utf-8',
    )
    run = TCF(tcf_path).context(file_resolution='deferred')
    assert run.deferred_database_sources() == ()
    assert run.mat_file().loaded
