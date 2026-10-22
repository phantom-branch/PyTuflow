"""Tests for opt-in batch dependency discovery and safe per-run memoisation."""

from pathlib import Path
from unittest.mock import patch

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import BatchContext, collect_batch_dependencies
from pytuflow._tmf.context import Context
from pytuflow._tmf.tfpathlib import TuflowPath


def _make_model(tmp_path: Path) -> TCF:
    source = tmp_path / 'shared.tcf'
    source.write_text(
        'IF Scenario == DEV\n'
        '    Read GIS Code == gis/2d_code_DEV.shp\n'
        'ELSE\n'
        '    Read GIS Code == gis/2d_code_EXG.shp\n'
        'END IF\n'
        'Read Grid Zpts == grids/terrain_*.tif\n',
        encoding='utf-8',
    )
    return TCF(source)


def test_batch_matches_individual_deferred_contexts(tmp_path):
    model = _make_model(tmp_path)
    flags = ('-s1 EXG', '-s1 DEV', '-s1 EXG')
    batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    assert len(batch.runs) == len(flags)
    for case, options in zip(batch.runs, flags, strict=True):
        old = model.context(options, file_resolution='deferred')
        expected = tuple(ref for inp in old.find_input() for ref in inp.file_references)
        assert case.file_references == expected
        assert case.database_sources == old.deferred_database_sources()
        assert case.database_activations == old.deferred_database_activations()


def test_batch_cached_and_uncached_have_identical_references(tmp_path):
    model = _make_model(tmp_path)
    flags = ('-s1 EXG', '-s1 DEV') * 5
    cached = collect_batch_dependencies(model, flags)
    plain = collect_batch_dependencies(model, flags, cache_scopes=False)
    assert cached.passed and plain.passed
    assert tuple((x.file_references, x.database_sources, x.database_activations, x.error)
                 for x in cached.runs) == tuple(
        (x.file_references, x.database_sources, x.database_activations, x.error)
        for x in plain.runs
    )
    assert cached.scope_hits > 0
    assert cached.translation_hits > 0


def test_batch_invalidates_cache_when_loading_new_variables(tmp_path):
    model = _make_model(tmp_path)
    ctx = BatchContext('-s1 DEV', config=model.config)
    first = ctx.translate('gis/<<TEST>>.shp')
    assert first == 'gis/<<TEST>>.shp'
    assert ctx.translate('gis/<<TEST>>.shp') == first
    assert ctx.translation_hits > 0
    ctx.load_variables({'TEST': 'one'})
    assert ctx.translate('gis/<<TEST>>.shp') == 'gis/one.shp'
    ctx.load_variables({'TEST': 'two'})
    assert ctx.translate('gis/<<TEST>>.shp') == 'gis/two.shp'


def test_batch_after_parse_makes_no_input_probes(tmp_path):
    model = _make_model(tmp_path)
    with (
        patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')),
        patch.object(Path, 'stat', side_effect=AssertionError('stat')),
        patch.object(Path, 'open', side_effect=AssertionError('open')),
    ):
        batch = model.collect_batch_dependencies(('-s1 EXG', '-s1 DEV'))
    assert batch.passed
    assert all(run.file_references for run in batch.runs)


def test_batch_500_contexts_keep_correct_per_run_dependencies(tmp_path):
    model = _make_model(tmp_path)
    flags = tuple('-s1 DEV' if n % 2 else '-s1 EXG' for n in range(500))
    batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    assert len(batch.runs) == 500
    assert batch.scope_hits > 0
    # Literal duplicate contexts can share the exact same immutable projection.
    assert batch.contexts_constructed == 2
    assert batch.contexts_reused == 498
    for case, flag in zip(batch.runs, flags, strict=True):
        scenario = flag.split()[-1]
        paths = {ref.path_pattern.name for ref in case.file_references}
        assert f'2d_code_{scenario}.shp' in paths
        assert 'terrain_*.tif' in paths


def test_single_context_default_stays_eager(tmp_path):
    model = _make_model(tmp_path)
    default = model.context('-s1 DEV')
    assert default.ctx.file_resolution == 'eager'
    assert not isinstance(default.ctx, BatchContext)


def test_batch_context_rejects_invalid_parse_without_making_partial_pass(tmp_path):
    model = _make_model(tmp_path)
    result = model.collect_batch_dependencies(('-s1 DEV', '-s1 DEV -s1 EXG'))
    assert result.runs[0].error is None
    assert result.runs[1].error is not None
    assert not result.passed
    assert result.runs[1].file_references == ()


def test_duplicate_runs_keep_separate_provenance(tmp_path):
    model = _make_model(tmp_path)
    batch = model.collect_batch_dependencies(('-s1 DEV', '-s1 DEV', '-s1 EXG'))
    assert batch.passed
    assert (batch.contexts_constructed, batch.contexts_reused) == (2, 1)
    assert [case.index for case in batch.runs] == [0, 1, 2]
    assert batch.runs[0].file_references == batch.runs[1].file_references
    plain = model.collect_batch_dependencies(('-s1 DEV', '-s1 DEV', '-s1 EXG'), cache_scopes=False)
    assert plain.contexts_constructed == 3
    assert plain.contexts_reused == 0


def test_empty_batch_is_rejected(tmp_path):
    import pytest

    model = _make_model(tmp_path)
    with pytest.raises(ValueError, match='At least one'):
        model.collect_batch_dependencies(())


def test_distinct_event_flags_do_not_collide_in_cache(tmp_path):
    source = tmp_path / 'event_model.tcf'
    source.write_text('Read GIS Code == gis/code_<<E1>>.shp\n', encoding='utf-8')
    model = TCF(source)
    flags = tuple(f'-e1 TEST{i:03d}' for i in range(50))
    batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    assert (batch.contexts_constructed, batch.contexts_reused) == (50, 0)
    for i, run in enumerate(batch.runs):
        assert {ref.path_pattern.name for ref in run.file_references} == {
            f'code_TEST{i:03d}.shp',
        }


def test_batch_reuses_variable_declaration_scan_not_variable_values(tmp_path):
    source = tmp_path / 'variable_model.tcf'
    source.write_text(
        'IF Scenario == DEV\n'
        '    Set Variable InputDir == dev\n'
        'ELSE\n'
        '    Set Variable InputDir == exg\n'
        'END IF\n'
        'Read GIS Code == gis/<<InputDir>>/2d_code.shp\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = tuple('-s1 DEV' if i % 2 else '-s1 EXG' for i in range(12))
    # Use six distinct secondary flags to force contexts beyond the
    # whole-run exact-flag cache, while retaining independent variable scope.
    flags = tuple(f'{flag} -e1 TEST{i:02d}' for i, flag in enumerate(flags))
    with patch.object(model, 'find_input', wraps=model.find_input) as finder:
        batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    declaration_reads = [
        call for call in finder.call_args_list
        if call.kwargs.get('lhs', '').casefold() == 'set variable'
    ]
    assert len(declaration_reads) == 1
    assert batch.contexts_constructed == len(flags)
    for i, case in enumerate(batch.runs):
        expected = 'dev' if i % 2 else 'exg'
        assert any(expected in ref.path_pattern.parts for ref in case.file_references)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert baseline.passed
    assert [
        item.file_references for item in baseline.runs
    ] == [
        item.file_references for item in batch.runs
    ]


def test_cross_run_scenario_scope_cache_preserves_distinct_events(tmp_path):
    model = _make_model(tmp_path)
    flags = tuple(
        f'-s1 {"DEV" if index % 2 else "EXG"} -e1 TEST{index:03d}'
        for index in range(50)
    )
    batch = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert batch.passed and baseline.passed
    assert batch.contexts_constructed == 50
    assert batch.contexts_reused == 0
    assert batch.cross_run_scope_hits > 0
    assert [(run.file_references, run.database_sources, run.database_activations)
            for run in batch.runs] == [
        (run.file_references, run.database_sources, run.database_activations)
        for run in baseline.runs
    ]


def test_cross_run_scope_cache_never_reuses_event_conditions(tmp_path):
    source = tmp_path / 'events.tcf'
    source.write_text(
        'IF Event == EVENT000\n'
        '  Read GIS Code == gis/code_EVENT000.shp\n'
        'ELSE\n'
        '  Read GIS Code == gis/code_other.shp\n'
        'END IF\n'
        'IF Scenario == DEV\n'
        '  Read GIS Mat == gis/2d_mat_DEV.shp\n'
        'END IF\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = ('-s1 DEV -e1 EVENT000', '-s1 DEV -e1 EVENT001',
             '-s1 DEV -e1 EVENT002', '-s1 DEV -e1 EVENT000')
    cached = model.collect_batch_dependencies(flags)
    plain = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and plain.passed
    assert cached.cross_run_scope_hits > 0
    assert [run.file_references for run in cached.runs] == [
        run.file_references for run in plain.runs
    ]
    names = [{ref.path_pattern.name for ref in run.file_references} for run in cached.runs]
    assert 'code_EVENT000.shp' in names[0]
    assert 'code_other.shp' in names[1]
    assert 'code_other.shp' in names[2]
    assert 'code_EVENT000.shp' in names[3]


def test_static_references_shared_across_distinct_event_flags(tmp_path):
    source = tmp_path / 'static_dynamic.tcf'
    source.write_text(
        'Read GIS Code == gis/static_code.shp\n'
        'Read GIS Code == gis/event_<<E1>>.shp\n'
        'Read Grid Zpts == terrain/static_*.tif\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = tuple(f'-e1 TP{i:03d}' for i in range(40))
    shared = model.collect_batch_dependencies(flags)
    plain = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert shared.passed and plain.passed
    assert shared.contexts_constructed == 40
    assert shared.contexts_reused == 0
    assert shared.cross_run_reference_hits > 0
    assert shared.cross_run_reference_misses > 0
    assert [case.file_references for case in shared.runs] == [
        case.file_references for case in plain.runs
    ]
    for i, case in enumerate(shared.runs):
        names = {ref.path_pattern.name for ref in case.file_references}
        assert names == {'static_code.shp', 'static_*.tif', f'event_TP{i:03d}.shp'}


def test_variable_derived_paths_never_share_static_reference_cache(tmp_path):
    source = tmp_path / 'scenario_variable.tcf'
    source.write_text(
        'IF Scenario == DEV\n'
        '  Set Variable Root == geometry/DEV\n'
        'ELSE\n'
        '  Set Variable Root == geometry/EXG\n'
        'END IF\n'
        'Read GIS Code == <<Root>>/2d_code.shp\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = tuple(f'-s1 {"DEV" if i % 2 else "EXG"} -e1 TP{i:02d}' for i in range(12))
    cached = model.collect_batch_dependencies(flags)
    plain = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and plain.passed
    assert [run.file_references for run in cached.runs] == [
        run.file_references for run in plain.runs
    ]
    # Only the variable-derived READ exists: never reuse it as literal static.
    assert cached.cross_run_reference_hits == 0


def test_variable_templates_parsed_once_but_scopes_evaluated_per_run(tmp_path):
    source = tmp_path / 'compiled_variables.tcf'
    source.write_text(
        'IF Scenario == DEV\n'
        '  Set Variable InputFolder == dev\n'
        'ELSE\n'
        '  Set Variable InputFolder == exg\n'
        'END IF\n'
        'Read GIS Code == gis/<<InputFolder>>/code.shp\n',
        encoding='utf-8',
    )
    model = TCF(source)
    definitions = model.find_input(lhs='set variable', recursive=True)
    assert len(definitions) == 2
    from contextlib import ExitStack

    flags = tuple(f'-s1 {"DEV" if i % 2 else "EXG"} -e1 TP{i:03d}' for i in range(30))
    with ExitStack() as stack:
        spies = [
            stack.enter_context(
                patch.object(item.command(), 'parse_variable', wraps=item.command().parse_variable)
            )
            for item in definitions
        ]
        batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    assert all(spy.call_count == 1 for spy in spies)
    assert batch.contexts_constructed == 30
    for i, case in enumerate(batch.runs):
        folder = 'dev' if i % 2 else 'exg'
        assert any(folder in ref.path_pattern.parts for ref in case.file_references)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert [case.file_references for case in batch.runs] == [
        case.file_references for case in baseline.runs
    ]


def test_batch_input_references_preserve_uuid_command_order_and_owner(tmp_path):
    source = tmp_path / 'provenance.tcf'
    source.write_text(
        'Read GIS Code == gis/same.shp\n'
        'Read GIS Code == gis/same.shp\n'
        'Read Grid Zpts == grids/terrain.tif\n',
        encoding='utf-8',
    )
    model = TCF(source)
    first, second = model.collect_batch_dependencies(('-e1 A', '-e1 B')).runs
    assert first.error is None and second.error is None
    assert first.input_references == second.input_references
    assert tuple(item.reference for item in first.input_references) == first.file_references
    assert len(first.input_references) == 3
    assert len({item.input_uuid for item in first.input_references}) == 3
    assert [item.command_index for item in first.input_references] == sorted(
        item.command_index for item in first.input_references
    )
    assert all(item.owner_control_file == source for item in first.input_references)
    assert [item.line_number for item in first.input_references] == [1, 2, 3]


def test_invalid_batch_context_discards_input_provenance(tmp_path):
    model = _make_model(tmp_path)
    failed = model.collect_batch_dependencies(('-s1 DEV -s1 EXG',)).runs[0]
    assert failed.error is not None
    assert failed.input_references == ()
    assert failed.file_references == ()
