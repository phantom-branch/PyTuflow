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
    assert batch.commands_constructed > 0
    assert batch.compilation_seconds >= 0.0
    assert batch.context_construction_seconds > 0.0
    assert batch.reference_collection_seconds >= 0.0
    assert batch.database_projection_seconds >= 0.0
    assert (batch.compilation_seconds + batch.context_construction_seconds
            + batch.reference_collection_seconds
            + batch.database_projection_seconds) <= batch.elapsed_seconds * 1.01
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


def test_command_construction_counts_are_not_reference_cache_hits(tmp_path):
    model = _make_model(tmp_path)
    flags = tuple(f'-s1 DEV -e1 TP{n:03d}' for n in range(20))
    cached = model.collect_batch_dependencies(flags)
    plain = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and plain.passed
    assert cached.contexts_constructed == 20
    assert cached.cross_run_reference_hits > 0
    # Shared templates skip parser construction but still allocate distinct
    # per-run commands and RunState objects.
    assert cached.commands_constructed >= 1
    assert cached.commands_cloned > 0
    assert cached.unique_command_templates >= 1
    assert cached.commands_constructed + cached.commands_cloned == 40
    # The uncached mode uses the uninstrumented base Context.
    assert plain.commands_constructed == 0
    assert [x.input_references for x in cached.runs] == [
        x.input_references for x in plain.runs
    ]


def test_command_templates_keep_mutable_objects_private(tmp_path):
    source = tmp_path / 'static.tcf'
    source.write_text('Read GIS Code == gis/static.shp\n', encoding='utf-8')
    model = TCF(source)

    first_ctx = BatchContext('-e1 A', config=model.config)
    shared_templates = {}
    first_ctx._shared_command_templates = shared_templates
    first = model.context(context=first_ctx, file_resolution='deferred')
    second_ctx = BatchContext('-e1 B', config=model.config)
    second_ctx._shared_command_templates = shared_templates
    second = model.context(context=second_ctx, file_resolution='deferred')
    first_cmd = first.find_input(lhs='read gis code')[0]._command
    second_cmd = second.find_input(lhs='read gis code')[0]._command
    assert first_cmd is not second_cmd
    assert first_cmd.config is not second_cmd.config
    assert first_cmd._expander is not second_cmd._expander
    assert first_ctx.commands_constructed >= 1
    assert second_ctx.commands_cloned >= 1
    prototype = next(iter(shared_templates.values()))[1]
    assert prototype is not first_cmd
    assert prototype.config is not first_cmd.config
    assert prototype.config.variables == {}
    assert prototype._expander.variables == {}

    second_cmd.config.file_resolution = 'eager'
    second_cmd.value = 'corrupted'
    second_cmd._expander._expanded_value = 'corrupted'
    assert first_cmd.config.file_resolution == 'deferred'
    assert first_cmd.value != 'corrupted'
    assert first_cmd._expander._expanded_value != 'corrupted'
    assert first.find_input(lhs='read gis code')[0].file_references[0].path_pattern.name == 'static.shp'
    # Editing the first run's command must not corrupt the cached prototype
    # used to create any later run.
    first_cmd.value = 'corrupted'
    third_ctx = BatchContext('-e1 C', config=model.config)
    third_ctx._shared_command_templates = shared_templates
    third = model.context(context=third_ctx, file_resolution='deferred')
    assert third_ctx.commands_cloned >= 1
    assert third.find_input(lhs='read gis code')[0].file_references[0].path_pattern.name == 'static.shp'


def test_event_dependent_read_command_bypasses_compiled_template(tmp_path):
    source = tmp_path / 'event.tcf'
    source.write_text('Read GIS Code == gis/<<E1>>.shp\n', encoding='utf-8')
    model = TCF(source)
    flags = tuple(f'-e1 TP{i:03d}' for i in range(12))
    batch = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert batch.passed and baseline.passed
    assert batch.commands_cloned == 0
    assert batch.command_template_bypasses > 0
    assert [r.input_references for r in batch.runs] == [
        r.input_references for r in baseline.runs
    ]


def test_compiled_commands_do_not_probe_disk_after_parse(tmp_path):
    model = _make_model(tmp_path)
    flags = tuple(f'-s1 DEV -e1 TP{i:03d}' for i in range(12))
    with (
        patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')),
        patch.object(Path, 'stat', side_effect=AssertionError('stat')),
        patch.object(Path, 'open', side_effect=AssertionError('open')),
    ):
        batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    assert batch.commands_cloned > 0
    assert batch.unique_command_templates >= 1


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
    # The same fully resolved output from different event contexts is safe
    # to reuse; scenario-derived DEV and EXG paths remain distinct signatures.
    assert cached.cross_run_reference_hits >= 10
    assert cached.cross_run_reference_misses == 2
    assert cached.unique_reference_signatures == 2


def test_variable_derived_gpkg_layers_use_conservative_cache_bypass(tmp_path):
    source = tmp_path / 'layers.tcf'
    source.write_text(
        'IF Scenario == DEV\n'
        '  Set Variable Layer == dev\n'
        'ELSE\n'
        '  Set Variable Layer == exg\n'
        'END IF\n'
        'Read GIS Code == gis/codes.gpkg >> <<Layer>>\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = tuple(
        f'-s1 {"DEV" if n % 2 else "EXG"} -e1 TP{n:03d}'
        for n in range(30)
    )
    cached = model.collect_batch_dependencies(flags)
    plain = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and plain.passed
    # The GeoPackage layer syntax is not proven eligible for this narrow
    # resolved-command cache. Preserve existing per-run layer interpretation.
    assert cached.cross_run_reference_hits == 0
    assert cached.cross_run_reference_bypasses > 0
    assert cached.unique_reference_signatures == 0
    assert [case.input_references for case in cached.runs] == [
        case.input_references for case in plain.runs
    ]
    assert {
        case.file_references[-1].layer_pattern for case in cached.runs
    } == {'dev', 'exg'}


def test_dynamic_event_paths_have_distinct_reference_signatures(tmp_path):
    source = tmp_path / 'event_paths.tcf'
    source.write_text(
        'Read GIS Code == gis/code_<<E1>>.shp\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = tuple(f'-e1 TP{n:03d}' for n in range(30))
    cached = model.collect_batch_dependencies(flags)
    plain = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and plain.passed
    assert cached.cross_run_reference_hits == 0
    assert cached.cross_run_reference_misses == 30
    assert cached.unique_reference_signatures == 30
    # Repeat access to the same input in one run is not a cross-run hit.
    assert cached.within_run_reference_hits > 0
    assert [case.file_references for case in cached.runs] == [
        case.file_references for case in plain.runs
    ]


def test_new_batch_does_not_reuse_previous_model_state(tmp_path):
    source = tmp_path / 'mutable.tcf'
    source.write_text(
        'Set Variable Root == before\n'
        'Read GIS Code == gis/<<Root>>/code.shp\n',
        encoding='utf-8',
    )
    model = TCF(source)
    first = model.collect_batch_dependencies(('-e1 A', '-e1 B'))
    assert first.passed
    assert first.cross_run_reference_hits >= 1
    assert 'before' in first.runs[0].file_references[-1].path_pattern.parts
    source_input = model.find_input(lhs='set variable')[0]
    source_input.rhs = 'after'
    second = model.collect_batch_dependencies(('-e1 A', '-e1 B'))
    baseline = model.collect_batch_dependencies(('-e1 A', '-e1 B'), cache_scopes=False)
    assert second.passed and baseline.passed
    assert second.runs[0].file_references == baseline.runs[0].file_references
    assert 'after' in second.runs[0].file_references[-1].path_pattern.parts


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


def test_batch_preserves_nested_tgc_control_file_provenance(tmp_path):
    geom = tmp_path / 'geometry.tgc'
    geom.write_text('Read GIS Z Shape == gis/2d_zsh.shp\n', encoding='utf-8')
    top = tmp_path / 'model.tcf'
    top.write_text('Geometry Control File == geometry.tgc\n', encoding='utf-8')
    model = TCF(top)
    batch = model.collect_batch_dependencies(('-s1 EXG -e1 10p',))
    assert batch.passed
    case = batch.runs[0]
    nested = [
        item for item in case.input_references
        if item.reference.path_pattern.name == '2d_zsh.shp'
    ]
    assert len(nested) == 1
    assert nested[0].owner_control_file == geom
    assert nested[0].line_number == 1
    assert any(
        item.owner_control_file == top for item in case.input_references
    )
