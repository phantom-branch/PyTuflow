"""Compiled control tree and distinct-context, per-run parity regressions.

Synthetic models here are correctness fixtures, NOT performance benchmarks.
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow._tmf.compiled_control_tree import CompiledControlTree
from pytuflow._tmf.compiled_dependency_plan import CompiledVariablePlan
from pytuflow._tmf.tfpathlib import TuflowPath


def _source(tmp_path: Path, content: str) -> TCF:
    file = tmp_path / 'graph.tcf'
    file.write_text(content, encoding='utf-8')
    return TCF(file)


def _identities(batch):
    return tuple(
        (run.error, run.ordered_inputs, run.input_references,
         run.file_references, run.database_activations, run.database_sources)
        for run in batch.runs
    )


def test_tree_is_ordered_and_immutable_with_explicit_bypass(tmp_path: Path):
    model = _source(
        tmp_path,
        'Set Variable ROOT == gis\n'
        'Read GIS Code == <<ROOT>>/code.shp\n'
        'Read GIS Code == layers.gpkg >> all\n'
        'BC Database == bc.csv\n',
    )
    assignments = tuple(
        (inp, inp.command().parse_variable())
        for inp in model.find_input(lhs='set variable')
    )
    plan = CompiledVariablePlan.from_assignments(assignments)
    tree = CompiledControlTree.compile(model, plan)

    assert tuple(node.ordinal for node in tree.nodes) == tuple(range(len(tree.nodes)))
    assert len(tree.nodes) == len(model.find_input())
    assert all(node.input_uuid and node.line_number > 0 for node in tree.nodes)
    assert all(node.owner_control_file is not None for node in tree.nodes)
    assert any(node.role == 'VARIABLE' for node in tree.nodes)
    assert any(node.role == 'BC_ACTIVATION' for node in tree.nodes)
    reads = [node for node in tree.nodes if node.role == 'READ']
    assert len(reads) == 2
    assert reads[0].read_dependency.relevant_variables == ('ROOT',)
    assert reads[0].bypass_reason is None
    assert reads[1].bypass_reason == 'unproven-expression-or-variable-lineage'
    assert tree.eligible_read_nodes == 1
    assert tree.bypassed_read_nodes == 1
    with pytest.raises(FrozenInstanceError):
        reads[0].role = 'SETTING'
    with pytest.raises(TypeError):
        tree._by_identity[123] = ('bad', reads[0])
    assert tree.node_for(object()) is None


def test_500_distinct_events_have_complete_per_run_parity(tmp_path: Path):
    model = _source(
        tmp_path,
        'If Scenario == DEV\n'
        '  Set Variable ROOT == dev\n'
        'Else\n'
        '  Set Variable ROOT == exg\n'
        'End If\n'
        'Read GIS Code == gis/<<ROOT>>/code.shp\n'
        'Read Grid Zpts == terrain/base.tif\n',
    )
    flags = tuple(
        f'-s1 {"DEV" if i % 2 else "EXG"} -e1 TP{i:03d}'
        for i in range(500)
    )
    cached = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and baseline.passed
    assert cached.contexts_constructed == 500
    assert cached.contexts_reused == 0
    assert cached.compiled_graph_nodes == len(model.find_input())
    assert cached.compiled_graph_eligible_reads == 2
    assert cached.graph_node_lookups >= 1000
    assert cached.commands_cloned >= 900
    assert cached.input_runstates_elided == 0
    assert _identities(cached) == _identities(baseline)


def test_scoped_declarations_with_same_values_do_not_alias(tmp_path: Path):
    model = _source(
        tmp_path,
        'If Scenario == DEV\n'
        '  Set Variable BASE == gis\n'
        'Else\n'
        '  Set Variable BASE == gis\n'
        'End If\n'
        'Read GIS Code == <<BASE>>/code.shp\n',
    )
    flags = tuple(
        f'-s1 {"DEV" if i % 2 else "EXG"} -e1 TP{i:03d}'
        for i in range(20)
    )
    cached = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and baseline.passed
    assert cached.unique_command_templates == 2
    assert _identities(cached) == _identities(baseline)


def test_dynamic_sources_bypass_graph_templates_and_fail_closed(tmp_path: Path):
    model = _source(
        tmp_path,
        'Read GIS Code == gis/<<E1>>/code.shp\n'
        'Pause == stop\n',
    )
    flags = tuple(f'-e1 TP{i:03d}' for i in range(5))
    result = model.collect_batch_dependencies(flags)
    assert not result.passed
    assert result.compiled_graph_bypassed_reads == 1
    for run in result.runs:
        assert run.error is not None
        assert not run.file_references
        assert not run.ordered_inputs
        assert not run.input_references
        assert not run.database_activations


def test_new_invocation_recompiles_after_parsed_input_changes(tmp_path: Path):
    model = _source(tmp_path, 'Read GIS Code == gis/old.shp\n')
    first = model.collect_batch_dependencies(('-e1 A', '-e1 B'))
    assert first.passed
    model.find_input(lhs='read gis code')[0].rhs = 'gis/new.shp'
    second = model.collect_batch_dependencies(('-e1 A', '-e1 B'))
    assert second.passed
    assert first.runs[0].file_references[0].path_pattern.name == 'old.shp'
    assert second.runs[0].file_references[0].path_pattern.name == 'new.shp'
    assert second.compiled_graph_nodes == first.compiled_graph_nodes
    assert _identities(second) == _identities(
        model.collect_batch_dependencies(('-e1 A', '-e1 B'), cache_scopes=False)
    )


def test_compiled_tree_does_not_probe_resources_after_parse(tmp_path: Path):
    model = _source(
        tmp_path,
        'Set Variable ROOT == gis\nRead GIS Code == <<ROOT>>/code.shp\n',
    )
    with (
        patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')),
        patch.object(Path, 'stat', side_effect=AssertionError('stat')),
        patch.object(Path, 'open', side_effect=AssertionError('open')),
    ):
        batch = model.collect_batch_dependencies(('-e1 A', '-e1 B'))
    assert batch.passed
    assert batch.compiled_graph_nodes >= 2
