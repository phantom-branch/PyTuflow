"""Parity and proof boundaries for literal setting-state reuse in batches."""

from pathlib import Path
from types import MethodType
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow._tmf.compiled_control_tree import CompiledControlTree
from pytuflow._tmf.compiled_dependency_plan import CompiledVariablePlan
from pytuflow._tmf.context import Context
from pytuflow._tmf.group_input_reuse import LiteralInputGroupCache
from pytuflow._tmf.inp.setting import SettingInput
from pytuflow._tmf.tfpathlib import TuflowPath


def _source(tmp_path: Path, content: str) -> TCF:
    source = tmp_path / 'settings.tcf'
    source.write_text(content, encoding='utf-8')
    return TCF(source)


def _values_by_run(model, flags, **options):
    original = model.context
    observed = []

    def observe(*args, **kwargs):
        state = original(*args, **kwargs)
        observed.append(tuple(
            (str(inp.uuid), inp.lhs, inp.rhs, inp.value, inp.line_number,
             tuple(str(scope) for scope in inp.scope))
            for inp in state.find_input()
        ))
        return state

    with patch.object(model, 'context', side_effect=observe):
        result = model.collect_batch_dependencies(flags, **options)
    return result, observed


def test_literal_settings_reuse_with_complete_value_and_order_parity(tmp_path: Path) -> None:
    model = _source(
        tmp_path,
        'Tutorial Model == ON\n'
        'Cell Size == 5\n'
        'Set Grid Size == 800, 1000\n'
        'If Scenario == DEV\n'
        '  Set Code == 1\n'
        'Else\n'
        '  Set Code == 0\n'
        'End If\n'
        'Set Variable SCALE == 1.2\n'
        'Viscosity == <<SCALE>>\n',
    )
    flags = tuple(f'-s1 {"DEV" if i % 2 else "EXG"} -e1 TP{i:03d}' for i in range(500))
    graph, observed = _values_by_run(model, flags)
    graph_off, off_values = _values_by_run(model, flags, compile_tree=False)
    uncached, uncached_values = _values_by_run(model, flags, cache_scopes=False)
    assert graph.passed and graph_off.passed and uncached.passed
    assert graph.runs == graph_off.runs == uncached.runs
    assert observed == off_values == uncached_values
    assert graph.contexts_constructed == 500
    assert graph.invariant_projection_reuses == 0
    assert graph.compiled_input_group_candidates == 5
    assert graph.reusable_input_groups == 5
    assert graph.input_runstates_elided == 1995
    assert graph.input_runstates_constructed == graph_off.input_runstates_constructed - 1995
    assert all(len(run.ordered_inputs) == 6 for run in graph.runs)
    assert all(run.file_references == () for run in graph.runs)


@pytest.mark.parametrize('source_text', [
    'Cell Size == \n',
    'Set Variable SIZE == 5\nCell Size == <<SIZE>>\n',
    'Cell Size == <<E1>>\n',
    'Cell Size == _event_SIZE_\n',
    'Set Grid Size == 800 | 1000\n',
    'Start Time == 0\nEnd Time == 3\n',
    'If Event == A\nCell Size == 5\nEnd If\n',
    'Define Output Zone == FIRST\nCell Size == 5\nEnd Define\n',
    'Output Folder == results\n',
    'Spatial Database == layers.gpkg\nCell Size == 5\n',
])
def test_unproven_or_specialised_settings_use_normal_evaluation(tmp_path: Path, source_text: str) -> None:
    model = _source(tmp_path, source_text)
    flags = ('-e1 A', '-e1 B', '-e1 C')
    graph = model.collect_batch_dependencies(flags)
    off = model.collect_batch_dependencies(flags, compile_tree=False)
    assert graph.runs == off.runs
    assert graph.compiled_input_group_candidates == 0
    assert graph.input_runstates_elided == 0


def test_setting_subclasses_cannot_inherit_a_plain_setting_proof(tmp_path: Path) -> None:
    class SpecialisedSetting(SettingInput):
        pass

    model = _source(tmp_path, 'Cell Size == 5\n')
    source = model.find_input()[0]
    assert type(source) is SettingInput
    tree = CompiledControlTree.compile(model, CompiledVariablePlan.from_assignments(()))
    cache = LiteralInputGroupCache(tree)
    ctx = Context('-e1 A', config=model.config)
    ctx.file_resolution = 'deferred'
    assert cache._key(source, ctx) is not None
    source.__class__ = SpecialisedSetting
    assert cache._key(source, ctx) is None
    assert cache.fallback_counts['ineligible_changed_source'] == 1
    graph = model.collect_batch_dependencies(('-e1 A', '-e1 B'))
    assert graph.passed
    assert graph.compiled_input_group_candidates == 0
    assert graph.input_runstates_elided == 0


@pytest.mark.parametrize('source_text', [
    'Tutorial Model == ON\n',
    'Read GIS Code == code.shp\n',
    'Read Grid Zpts == terrain.tif\n',
])
@pytest.mark.parametrize('hook_target', ['instance', 'class'])
def test_custom_context_hooks_are_not_proved_as_builtin_constructors(
    tmp_path: Path, monkeypatch, source_text: str, hook_target: str,
) -> None:
    model = _source(tmp_path, source_text)
    source = model.find_input()[0]
    original = source.context.__func__
    calls = []

    def custom_context(self, **kwargs):
        if self is not source:
            return original(self, **kwargs)
        event = kwargs['context'].E1
        calls.append(event)
        if event == 'B':
            raise ValueError('custom context B')
        return original(self, **kwargs)

    if hook_target == 'instance':
        monkeypatch.setattr(source, 'context', MethodType(custom_context, source))
    else:
        monkeypatch.setattr(type(source), 'context', custom_context)
    flags = ('-e1 A', '-e1 B', '-e1 C')
    graph = model.collect_batch_dependencies(flags)
    assert calls == ['A', 'B', 'C']
    calls.clear()
    off = model.collect_batch_dependencies(flags, compile_tree=False)
    assert calls == ['A', 'B', 'C']
    assert graph.runs == off.runs
    assert graph.runs[1].error == 'ValueError: custom context B'
    assert graph.compiled_input_group_candidates == 0
    assert graph.invariant_projection_reuses == 0
    assert graph.input_runstates_elided == 0


@pytest.mark.parametrize('source_text', [
    'Tutorial Model == ON\n',
    'Read GIS Code == code.shp\n',
    'Read Grid Zpts == terrain.tif\n',
])
@pytest.mark.parametrize('hook_target', ['instance', 'class'])
def test_context_hook_replacement_invalidates_an_existing_group_plan(
    tmp_path: Path, monkeypatch, source_text: str, hook_target: str,
) -> None:
    # A dynamic setting forces per-input evaluation instead of whole-model
    # projection reuse, so this regression exercises the leaf group guard.
    model = _source(tmp_path, source_text + 'Viscosity == <<E1>>\n')
    source = model.find_input()[0]
    original = source.context.__func__
    calls = []

    def custom_context(self, **kwargs):
        if self is not source:
            return original(self, **kwargs)
        event = kwargs['context'].E1
        calls.append(event)
        if event == 'B':
            raise ValueError('custom context B')
        return original(self, **kwargs)

    def flags(patcher):
        yield '-e1 A'
        if hook_target == 'instance':
            patcher.setattr(source, 'context', MethodType(custom_context, source))
        else:
            patcher.setattr(type(source), 'context', custom_context)
        yield '-e1 B'
        yield '-e1 C'

    with monkeypatch.context() as patcher:
        graph = model.collect_batch_dependencies(flags(patcher))
    assert calls == ['B', 'C']
    calls.clear()
    with monkeypatch.context() as patcher:
        off = model.collect_batch_dependencies(flags(patcher), compile_tree=False)
    assert calls == ['B', 'C']
    assert graph.runs == off.runs
    assert graph.runs[1].error == 'ValueError: custom context B'
    assert graph.compiled_input_group_candidates == 1
    assert graph.input_runstates_elided == 0
    assert dict(graph.input_group_fallbacks)['ineligible_changed_source'] == 2


def test_runtime_event_markers_do_not_certify_literal_looking_settings(tmp_path: Path) -> None:
    model = _source(tmp_path, 'Tutorial Model == ON\n')
    tree = CompiledControlTree.compile(model, CompiledVariablePlan.from_assignments(()))
    cache = LiteralInputGroupCache(tree)
    ctx = Context('-e1 A', config=model.config)
    ctx.file_resolution = 'deferred'
    # TEF event substitution may use ordinary words, not only ~tokens~.
    with patch.object(ctx.event_db, 'event_variables', return_value=('ON',)):
        assert cache._key(model.find_input()[0], ctx) is None
    assert cache.fallback_counts['ineligible_event_expression'] == 1


def test_conditional_setting_states_and_seeds_are_independently_mutable(tmp_path: Path) -> None:
    model = _source(tmp_path, 'If Scenario == DEV\nCell Size == 5\nEnd If\n')
    source = model.find_input()[0]
    original = model.context
    built = []

    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        current = result.find_input()[0]
        assert current.value == 5
        assert current._command.define_blocks is not source.command().define_blocks
        assert current._command.define_blocks[0] is not source.command().define_blocks[0]
        assert current._rs._scope[0].names == ['DEV']
        assert current._rs.cf == []
        assert current._rs._files == []
        assert current._rs._file_to_scope == {}
        if built:
            previous = built[-1]
            assert current._rs is not previous._rs
            assert current._command is not previous._command
            assert current._command.config is not previous._command.config
            assert current._command._expander is not previous._command._expander
            assert current._rs.cf is not previous._rs.cf
            assert current._rs._scope[0] is not previous._rs._scope[0]
            previous._command.value_orig = '999'
            previous._command.config.variables = {'UNUSED': 'leak'}
            previous._command.define_blocks[0].name = 'LEAK'
            previous._rs._scope[0].names.append('LEAK')
            previous._rs.cf.append('leaked child')
            previous._rs._files.append('leaked file')
            previous._rs._file_to_scope['leak'] = 'leak'
        built.append(current)
        return result

    flags = tuple(f'-s1 DEV -e1 {event}' for event in ('A', 'B', 'C', 'D'))
    with patch.object(model, 'context', side_effect=observe):
        graph = model.collect_batch_dependencies(flags)
    assert graph.passed
    assert graph.input_runstates_elided == 3
    assert source.rhs == '5'
    assert source.command().define_blocks[0].name == 'DEV'
    assert graph.runs == model.collect_batch_dependencies(flags, compile_tree=False).runs


def test_failed_run_does_not_certify_setting_state(tmp_path: Path) -> None:
    model = _source(
        tmp_path,
        'Tutorial Model == ON\nIf Scenario == BAD\nPause == stop\nEnd If\n',
    )
    flags = ('-s1 BAD -e1 A', '-s1 GOOD -e1 B', '-s1 GOOD -e1 C')
    graph = model.collect_batch_dependencies(flags)
    off = model.collect_batch_dependencies(flags, compile_tree=False)
    assert not graph.passed
    assert graph.runs == off.runs
    assert graph.runs[0].error
    assert graph.runs[0].ordered_inputs == ()
    assert graph.reusable_input_groups == 1
    assert graph.input_runstates_constructed == 2
    assert graph.input_runstates_elided == 1


def test_changed_setting_source_cannot_reuse_an_earlier_plan(tmp_path: Path) -> None:
    model = _source(tmp_path, 'Tutorial Model == ON\n')
    source = model.find_input()[0]

    def flags():
        yield '-e1 A'
        source.rhs = 'OFF'
        yield '-e1 B'
        yield '-e1 C'

    graph, observed = _values_by_run(model, flags())
    assert graph.passed
    assert [values[0][3] for values in observed] == ['ON', 'OFF', 'OFF']
    assert graph.input_runstates_elided == 0
    assert dict(graph.input_group_fallbacks)['ineligible_changed_source'] == 2
    assert source.rhs == 'OFF'


def test_setting_reuse_performs_no_post_parse_filesystem_probes(tmp_path: Path) -> None:
    model = _source(tmp_path, 'Tutorial Model == ON\nCell Size == 5\n')
    flags = ('-e1 A', '-e1 B', '-e1 C')
    with (
        patch.object(Path, 'open', side_effect=AssertionError('open after parse')),
        patch.object(Path, 'stat', side_effect=AssertionError('stat after parse')),
        patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob after parse')),
    ):
        graph = model.collect_batch_dependencies(flags)
        off = model.collect_batch_dependencies(flags, compile_tree=False)
    assert graph.passed and off.passed
    assert graph.runs == off.runs
    assert graph.input_runstates_elided == 4
