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


def test_branch_metadata_preserves_else_and_negation(tmp_path: Path):
    model = _source(
        tmp_path,
        'If Scenario == DEV\n'
        '  Read GIS Code == dev.shp\n'
        'Else\n'
        '  Read GIS Code == exg.shp\n'
        'End If\n',
    )
    tree = CompiledControlTree.compile(model, CompiledVariablePlan.from_assignments(()))
    branch_nodes = [node for node in tree.nodes if node.role == 'READ']
    assert len(branch_nodes) == 2
    assert all(node.branch_conditions for node in branch_nodes)
    assert any(
        scope.scope_type == 'SCENARIO'
        for node in branch_nodes for scope in node.branch_conditions
    )
    assert branch_nodes[0].branch_conditions != branch_nodes[1].branch_conditions


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


def test_compile_tree_opt_out_keeps_other_caches_and_provenance(tmp_path: Path):
    model = _source(
        tmp_path,
        'Set Variable ROOT == gis\n'
        'Read GIS Code == <<ROOT>>/code.shp\n'
        'Read Grid Zpts == terrain/static.tif\n',
    )
    flags = tuple(f'-e1 TP{i:03d}' for i in range(25))
    graph = model.collect_batch_dependencies(flags)
    older_cached = model.collect_batch_dependencies(flags, compile_tree=False)
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert graph.passed and older_cached.passed and uncached.passed
    assert graph.compiled_graph_nodes == 3
    assert older_cached.compiled_graph_nodes == 0
    assert older_cached.compiled_read_nodes >= 2
    assert older_cached.commands_cloned > 0
    assert older_cached.contexts_constructed == 25
    assert graph.invariant_projection_reuses == 0
    assert _identities(graph) == _identities(older_cached) == _identities(uncached)


def test_literal_leaf_tree_elides_run_states_for_500_distinct_flags(tmp_path: Path):
    model = _source(
        tmp_path,
        'Read GIS Code == gis/codes.shp\n'
        'Read Grid Zpts == terrain/dem.tif\n',
    )
    flags = tuple(f'-s1 DEV -e1 TP{i:03d}' for i in range(500))
    graph = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, compile_tree=False)
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert graph.passed and baseline.passed and uncached.passed
    assert graph.contexts_constructed == 500
    assert graph.contexts_reused == 0
    assert graph.invariant_projection_reuses == 499
    assert graph.input_runstates_constructed == 2
    assert graph.input_runstates_elided == 998
    assert baseline.input_runstates_elided == 0
    assert baseline.invariant_projection_reuses == 0
    assert baseline.input_runstates_constructed == 1000
    assert graph.graph_node_lookups == 2
    assert _identities(graph) == _identities(baseline) == _identities(uncached)


@pytest.mark.parametrize(
    'source_text',
    [
        'Set Variable ROOT == gis\nRead GIS Code == <<ROOT>>/code.shp\n',
        'Read GIS Code == gis/2d_code_<<E1>>.shp\n',
        'Read GIS Code == gis/code_~e1~.shp\n',
        'Read GIS Code == gis/code_*.shp\n',
        'Read GIS Code == layers.gpkg >> all\n',
        'Read GIS Code == gis/code.shp | 1\n',
        'Read Grid RF == rainfall.nc\n',
        'BC Database == bc.csv\nRead GIS BC == 2d_bc.shp\n',
        'If Scenario == DEV\nRead GIS Code == dev.shp\n'
        'Else\nRead GIS Code == exg.shp\nEnd If\n',
    ],
)
def test_unproven_nodes_do_not_elide_run_states(tmp_path: Path, source_text: str):
    model = _source(tmp_path, source_text)
    flags = ('-s1 DEV -e1 A', '-s1 DEV -e1 B')
    cached = model.collect_batch_dependencies(flags)
    assert cached.input_runstates_elided == 0
    assert cached.invariant_projection_reuses == 0
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert _identities(cached) == _identities(baseline)


def test_failed_first_run_never_seeds_invariant_projection(tmp_path: Path):
    model = _source(tmp_path, 'Read GIS Code == gis/code.shp\n')
    real_context = model.context
    calls = []

    def flaky_context(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('deliberate one-run failure')
        return real_context(*args, **kwargs)

    with patch.object(model, 'context', side_effect=flaky_context):
        result = model.collect_batch_dependencies(('-e1 A', '-e1 B', '-e1 C'))
    assert not result.passed
    assert result.runs[0].error == 'ValueError: deliberate one-run failure'
    assert not result.runs[0].file_references
    assert not result.runs[0].ordered_inputs
    assert result.runs[1].error is None
    assert result.runs[2].error is None
    assert result.invariant_projection_reuses == 1
    assert result.input_runstates_elided == 1
    assert len(calls) == 2


def test_static_graph_rebuilds_and_disables_projection_after_model_edit(tmp_path: Path):
    model = _source(tmp_path, 'Read GIS Code == gis/code.shp\n')
    flags = ('-e1 A', '-e1 B', '-e1 C')
    original = model.collect_batch_dependencies(flags)
    assert original.invariant_projection_reuses == 2
    model.find_input(lhs='read gis code')[0].rhs = 'gis/<<E1>>.shp'
    edited = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert edited.invariant_projection_reuses == 0
    assert edited.input_runstates_elided == 0
    assert _identities(edited) == _identities(baseline)


def test_compiled_read_counter_tracks_active_plan_encounters(tmp_path: Path):
    """Whole-tree node totals must not contaminate same-head plan counts."""
    model = _source(
        tmp_path,
        'If Scenario == DEV\n'
        '  Read GIS Code == gis/dev.shp\n'
        'Else\n'
        '  Read GIS Code == gis/exg.shp\n'
        'End If\n'
        'Read Grid Zpts == terrain/static.tif\n',
    )
    for flags in (
        ('-s1 DEV -e1 A',),
        ('-s1 DEV -e1 A', '-s1 DEV -e1 B'),
        ('-s1 EXG -e1 A',),
        ('-s1 DEV -e1 A', '-s1 EXG -e1 B'),
    ):
        graph = model.collect_batch_dependencies(flags)
        graph_off = model.collect_batch_dependencies(flags, compile_tree=False)
        uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
        assert graph.passed and graph_off.passed and uncached.passed
        assert _identities(graph) == _identities(graph_off) == _identities(uncached)
        assert graph.compiled_graph_nodes == len(model.find_input())
        assert graph.compiled_read_nodes == graph_off.compiled_read_nodes
        if not (any('DEV' in flag for flag in flags)
                and any('EXG' in flag for flag in flags)):
            # For a single active branch, a full-tree total must be larger
            # than the number of encountered plans.
            assert graph.compiled_read_nodes < sum(
                node.role == 'READ'
                for node in CompiledControlTree.compile(
                    model, CompiledVariablePlan.from_assignments(())
                ).nodes
            )
        assert graph_off.compiled_graph_nodes == 0


def test_scenario_literal_tree_reuses_across_500_distinct_events(tmp_path: Path):
    """Scenario-dependent READ streams may be shared only within a scenario."""
    model = _source(
        tmp_path,
        'If Scenario == DEV\n'
        '  Read GIS Code == gis/dev.shp\n'
        'Else\n'
        '  Read GIS Code == gis/exg.shp\n'
        'End If\n'
        'Read Grid Zpts == terrain/dem.tif\n',
    )
    eligibility = CompiledControlTree.compile(
        model, CompiledVariablePlan.from_assignments(())
    )
    assert eligibility.is_scenario_literal_model(model), (
        model.config.scenarios, model.config.variables,
        str(model.config.spatial_database),
        [(node.command_name, node.bypass_reason, node.branch_conditions)
         for node in eligibility.nodes],
    )
    flags = tuple(
        f'-s1 {"DEV" if index % 2 else "EXG"} -e1 TP{index:03d}'
        for index in range(500)
    )
    graph = model.collect_batch_dependencies(flags)
    old_cached = model.collect_batch_dependencies(flags, compile_tree=False)
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert graph.passed and old_cached.passed and uncached.passed
    assert graph.contexts_constructed == 500
    assert graph.contexts_reused == 0
    assert graph.invariant_projection_reuses == 498
    assert graph.input_runstates_constructed == 4
    assert graph.input_runstates_elided == 996
    assert old_cached.input_runstates_elided == 0
    assert _identities(graph) == _identities(old_cached) == _identities(uncached)
    assert 'exg.shp' in {
        ref.path_pattern.name for ref in graph.runs[0].file_references
    }
    assert 'dev.shp' in {
        ref.path_pattern.name for ref in graph.runs[1].file_references
    }


def test_scenario_projection_preserves_exact_selected_slots(tmp_path: Path):
    model = _source(
        tmp_path,
        'If Scenario == DEV\n'
        '  Read GIS Code == gis/dev.shp\n'
        'Else\n'
        '  Read GIS Code == gis/exg.shp\n'
        'End If\n',
    )
    flags = (
        '-s1 EXG -e1 A',
        '-s1 DEV -e1 B',
        '-s1 DEV -e1 C',
        '-s1 EXG -e1 D',
        '-s1 DEV -s2 EXG -e1 E',
        '-s1 DEV -s2 EXG -e1 F',
        '-s1 EXG -s2 DEV -e1 G',
        '-s1 EXG -s2 DEV -e1 H',
    )
    graph = model.collect_batch_dependencies(flags)
    graph_off = model.collect_batch_dependencies(flags, compile_tree=False)
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert graph.passed and graph_off.passed and uncached.passed
    assert graph.invariant_projection_reuses == 4
    assert graph.input_runstates_elided > 0
    assert _identities(graph) == _identities(graph_off) == _identities(uncached)


def test_scenario_projection_failure_does_not_seed_other_branch(tmp_path: Path):
    model = _source(
        tmp_path,
        'If Scenario == DEV\n'
        '  Read GIS Code == dev.shp\n'
        'Else\n'
        '  Read GIS Code == exg.shp\n'
        'End If\n',
    )
    original = model.context
    calls = []

    def fail_dev_first(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('first scenario failed')
        return original(*args, **kwargs)

    flags = ('-s1 DEV -e1 A', '-s1 EXG -e1 A',
             '-s1 DEV -e1 B', '-s1 EXG -e1 B',
             '-s1 DEV -e1 C')
    with patch.object(model, 'context', side_effect=fail_dev_first):
        graph = model.collect_batch_dependencies(flags)
    assert not graph.passed
    assert graph.runs[0].error == 'ValueError: first scenario failed'
    assert graph.runs[0].ordered_inputs == ()
    assert all(run.error is None for run in graph.runs[1:])
    assert len(calls) == 3  # failure, EXG first, DEV first success
    assert graph.invariant_projection_reuses == 2
    baseline = model.collect_batch_dependencies(flags[1:], cache_scopes=False)
    assert _identities(graph)[1:] == _identities(baseline)


@pytest.mark.parametrize('source_text', [
    'If Event == A\nRead GIS Code == a.shp\n'
    'Else\nRead GIS Code == b.shp\nEnd If\n',
    'If Scenario == <<UNKNOWN>>\nRead GIS Code == a.shp\n'
    'End If\n',
    'Set Variable PART == x\n'
    'If Scenario == DEV\nRead GIS Code == dev.shp\nEnd If\n',
    'If Scenario == DEV\nRead GIS Code == gis/<<E1>>.shp\n'
    'Else\nRead GIS Code == exg.shp\nEnd If\n',
    'If Scenario == DEV\nRead GIS BC == bc.shp\nEnd If\n',
])
def test_unproven_scenario_models_never_shortcut(tmp_path: Path, source_text: str):
    model = _source(tmp_path, source_text)
    flags = ('-s1 DEV -e1 A', '-s1 DEV -e1 B')
    compiled = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert compiled.invariant_projection_reuses == 0
    assert compiled.input_runstates_elided == 0
    assert _identities(compiled) == _identities(baseline)
