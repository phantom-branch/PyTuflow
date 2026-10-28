"""Conservative immutable variable DAG and batch READ template regressions."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pytuflow import TCF
from pytuflow._tmf.compiled_dependency_plan import CompiledVariablePlan


def _plan(*definitions: tuple[str, str]) -> CompiledVariablePlan:
    return CompiledVariablePlan.from_assignments(
        tuple((object(), definition) for definition in definitions)
    )


def test_compiled_transitive_variable_closure_is_immutable():
    plan = _plan(
        ('BASE', 'geometry'),
        ('ROOT', '<<BASE>>/model'),
        ('OTHER', 'unused'),
    )
    read = plan.compile_read('<<ROOT>>/codes.shp')
    assert read.reusable
    assert read.direct_variables == ('ROOT',)
    assert read.relevant_variables == ('BASE', 'ROOT')
    assert plan.reusable_variables == {'BASE', 'ROOT', 'OTHER'}
    with pytest.raises(FrozenInstanceError):
        read.reusable = False


@pytest.mark.parametrize(
    ('definitions', 'expression'),
    [
        ((('A', '<<B>>'), ('B', '<<A>>')), '<<A>>/code.shp'),
        ((('A', '<<UNKNOWN>>'),), '<<A>>/code.shp'),
        ((('ROOT', '<<E1>>'),), '<<ROOT>>/code.shp'),
        ((('ROOT', 'folder/~e1~'),), '<<ROOT>>/code.shp'),
        ((('ROOT', 'model.gpkg >> all'),), '<<ROOT>>'),
        ((('ROOT', 'geometry'),), 'geometry/<<BROKEN/path.shp'),
        ((('ROOT', 'geometry'),), 'model.gpkg >> <<ROOT>>'),
    ],
)
def test_unsafe_dependency_graphs_are_not_reused(definitions, expression):
    plan = _plan(*definitions)
    assert not plan.compile_read(expression).reusable


def test_multiple_scoped_declarations_conservatively_join_lineage():
    plan = _plan(
        ('ROOT', 'geometry'),
        ('ROOT', '<<ALT>>'),
        ('ALT', 'alternate'),
    )
    read = plan.compile_read('<<ROOT>>/code.shp')
    assert read.reusable
    assert read.relevant_variables == ('ALT', 'ROOT')
    unsafe = _plan(('ROOT', 'geometry'), ('ROOT', '<<NOT_DECLARED>>'))
    assert not unsafe.compile_read('<<ROOT>>/code.shp').reusable


def test_variable_derived_read_reuses_command_template_across_events(tmp_path: Path):
    source = tmp_path / 'transitive.tcf'
    source.write_text(
        'Set Variable BASE == gis\n'
        'Set Variable ROOT == <<BASE>>/terrain\n'
        'Read GIS Code == <<ROOT>>/codes.shp\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = tuple(f'-s1 DEV -e1 TP{n:03d}' for n in range(30))
    cached = model.collect_batch_dependencies(flags, compile_tree=False)
    graph = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and graph.passed and baseline.passed
    assert cached.compiled_variable_nodes == 2
    assert cached.compiled_read_nodes >= 1
    assert cached.variable_template_clones >= 29
    assert graph.variable_template_clones == cached.variable_template_clones
    assert graph.input_group_state_reuses == 0
    assert graph.runs == cached.runs
    assert cached.contexts_constructed == 30
    assert cached.contexts_reused == 0
    assert [item.input_references for item in cached.runs] == [
        item.input_references for item in baseline.runs
    ]
    assert all(
        item.file_references[-1].path_pattern.name == 'codes.shp'
        for item in cached.runs
    )


def test_transitive_scenario_variable_changes_do_not_collide(tmp_path: Path):
    source = tmp_path / 'scenario.tcf'
    source.write_text(
        'IF Scenario == DEV\n'
        '  Set Variable BASE == dev\n'
        'ELSE\n'
        '  Set Variable BASE == exg\n'
        'END IF\n'
        'Set Variable ROOT == <<BASE>>/gis\n'
        'Read GIS Code == <<ROOT>>/codes.shp\n',
        encoding='utf-8',
    )
    model = TCF(source)
    flags = tuple(
        f'-s1 {"DEV" if n % 2 else "EXG"} -e1 TP{n:03d}'
        for n in range(30)
    )
    cached = model.collect_batch_dependencies(flags, compile_tree=False)
    graph = model.collect_batch_dependencies(flags)
    baseline = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert cached.passed and graph.passed and baseline.passed
    assert cached.variable_template_clones >= 28
    assert graph.variable_template_clones == cached.variable_template_clones
    assert graph.input_group_state_reuses == 0
    assert graph.runs == cached.runs
    assert cached.unique_command_templates >= 2
    assert cached.runs == baseline.runs
    assert [item.input_references for item in cached.runs] == [
        item.input_references for item in baseline.runs
    ]
    assert [
        item.file_references[-1].path_pattern.parent.name for item in cached.runs
    ] == ['gis'] * 30
    assert {
        item.file_references[-1].path_pattern.parent.parent.name
        for item in cached.runs
    } == {'dev', 'exg'}
