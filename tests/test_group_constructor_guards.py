"""Constructor hooks retain their per-run semantics across graph shortcuts."""

from pathlib import Path
from types import MethodType

import pytest

from pytuflow import TCF
from pytuflow._tmf.compiled_control_tree import CompiledControlTree
from pytuflow._tmf.compiled_dependency_plan import CompiledVariablePlan


_READS = ('Read GIS Code == code.shp', 'Read Grid Zpts == terrain.tif')


def _model(tmp_path: Path, read: str, shape: str = 'mixed') -> TCF:
    if shape == 'mixed':
        text = f'Set Code == 0\n{read}\n'
    elif shape == 'scenario':
        text = f'If Scenario == DEV\n{read}\nEnd If\n'
    else:
        text = f'{read}\n'
    source = tmp_path / 'constructor_guard.tcf'
    source.write_text(text, encoding='utf-8')
    return TCF(source)


def _install_hook(patcher, source, hook_target: str, hook) -> None:
    if hook_target == 'instance':
        patcher.setattr(source, 'context', MethodType(hook, source))
    else:
        patcher.setattr(type(source), 'context', hook)


@pytest.mark.parametrize('read', _READS)
@pytest.mark.parametrize('hook_target', ['instance', 'class'])
@pytest.mark.parametrize('shape', ['mixed', 'literal', 'scenario'])
def test_preinstalled_context_hooks_cannot_be_skipped_by_graph_shortcuts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, read: str, hook_target: str, shape: str,
) -> None:
    model = _model(tmp_path, read, shape)
    source = model.find_input()[-1]
    original = source.context.__func__
    calls = []

    def custom_context(self, **kwargs):
        if self is not source:
            return original(self, **kwargs)
        event = kwargs['context'].E1
        calls.append(event)
        if event == 'B':
            raise ValueError('source context rejected B')
        return original(self, **kwargs)

    _install_hook(monkeypatch, source, hook_target, custom_context)
    flags = tuple(f'-s1 DEV -e1 {event}' for event in ('A', 'B', 'C'))
    graph = model.collect_batch_dependencies(flags)
    assert calls == ['A', 'B', 'C']
    calls.clear()
    baseline = model.collect_batch_dependencies(flags, compile_tree=False)
    assert calls == ['A', 'B', 'C']
    assert graph.runs == baseline.runs
    assert graph.runs[1].error == 'ValueError: source context rejected B'
    assert graph.compiled_input_group_candidates == 0
    assert graph.invariant_projection_reuses == 0
    assert graph.input_runstates_elided == 0
    assert dict(graph.input_group_bypass_reasons)['custom_context'] == 1


@pytest.mark.parametrize('read', _READS)
@pytest.mark.parametrize('hook_target', ['instance', 'class'])
def test_replacing_a_context_hook_invalidates_an_existing_leaf_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, read: str, hook_target: str,
) -> None:
    # The extra non-READ command excludes whole-model projection reuse. This
    # checks the leaf cache's existing live-source contract during iteration;
    # whole-projection/exact-flag mutation invalidation is a separate scope.
    model = _model(tmp_path, read)
    source = model.find_input()[-1]
    original = source.context.__func__
    calls = []

    def custom_context(self, **kwargs):
        if self is not source:
            return original(self, **kwargs)
        event = kwargs['context'].E1
        calls.append(event)
        if event == 'B':
            raise ValueError('source context rejected B')
        return original(self, **kwargs)

    def flags(patcher):
        yield '-e1 A'
        _install_hook(patcher, source, hook_target, custom_context)
        yield '-e1 B'
        yield '-e1 C'

    with monkeypatch.context() as patcher:
        graph = model.collect_batch_dependencies(flags(patcher))
    assert calls == ['B', 'C']
    calls.clear()
    with monkeypatch.context() as patcher:
        baseline = model.collect_batch_dependencies(flags(patcher), compile_tree=False)
    assert calls == ['B', 'C']
    assert graph.runs == baseline.runs
    assert graph.runs[1].error == 'ValueError: source context rejected B'
    assert graph.compiled_input_group_candidates == 1
    assert graph.invariant_projection_reuses == 0
    assert graph.input_runstates_elided == 0
    assert dict(graph.input_group_fallbacks)['ineligible_changed_source'] == 2


@pytest.mark.parametrize('read', _READS)
def test_a_builtin_context_bound_to_another_source_is_not_a_valid_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, read: str,
) -> None:
    model = _model(tmp_path, f'{read}\n{read.replace("== ", "== other_")}')
    source, other = model.find_input()[-2:]
    variables = CompiledVariablePlan.from_assignments(())
    tree = CompiledControlTree.compile(model, variables)
    assert tree.node_for(source).input_group is not None
    with monkeypatch.context() as patcher:
        patcher.setattr(source, 'context', other.context)
        rebound_tree = CompiledControlTree.compile(model, variables)
    assert rebound_tree.node_for(source).input_group is None
    assert rebound_tree.node_for(source).input_group_bypass_reason == 'custom_context'

    def flags(patcher):
        yield '-e1 A'
        patcher.setattr(source, 'context', other.context)
        yield '-e1 B'

    with monkeypatch.context() as patcher:
        graph = model.collect_batch_dependencies(flags(patcher))
    with monkeypatch.context() as patcher:
        baseline = model.collect_batch_dependencies(flags(patcher), compile_tree=False)
    assert graph.passed and baseline.passed
    assert graph.runs == baseline.runs
    assert dict(graph.input_group_fallbacks)['ineligible_changed_source'] == 1
