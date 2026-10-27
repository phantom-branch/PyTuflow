"""Real installed-parser checks; syntactic projections only, never native acceptance."""

from pathlib import Path

import pytest

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import BatchContext
from pytuflow._tmf.parsers.command import Command

from .construction_attribution import Attribution
from .profile_construction_attribution import compare, parser_targets


def test_six_context_graph_differential_preserves_complete_results(tmp_path: Path) -> None:
    source = tmp_path / 'model.tcf'
    source.write_text('Geometry Control File == child.tgc\n'
                      'Cell Size == 5\nViscosity == <<E1>>\n', encoding='utf-8')
    (tmp_path / 'child.tgc').write_text('Set Code == 0\nRead GRID Zpts == terrain.tif\n', encoding='utf-8')
    model = TCF(source)
    originals = BatchContext.translate, BatchContext.batch_input_state, Command.__init__
    targets, owners = parser_targets()
    runs = [{'e1': f'TEST{i:02d}', 's1': 'EXG'} for i in range(6)]
    report = compare(model, runs, targets, owners)
    assert report['completed'] and report['public_projection_parity']
    assert not report['accepted_for_benchmark'] and not report['physical_preflight_performed']
    assert originals == (BatchContext.translate, BatchContext.batch_input_state, Command.__init__)
    for capture in report['captures'].values():
        rows = capture['cells']
        assert sum(row['exclusive_ns'] for row in rows) == capture['wall_elapsed_ns']
        kinds = {row['control_file_kind'] for row in rows if row['activation_segments']}
        assert {'TCF', 'TGC'} <= kinds
        operations = {row['operation'] for row in rows if row['activation_segments']}
        assert {'context_bootstrap', 'translation', 'command_construction', 'configuration_copy'} <= operations


def test_failure_projection_parity_remains_visible_under_observation(tmp_path: Path) -> None:
    source = tmp_path / 'model.tcf'
    source.write_text('If Scenario == BAD\nPause == diagnostic failure\nEnd If\n', encoding='utf-8')
    model = TCF(source)
    targets, owners = parser_targets()
    runs = [{'s1': 'GOOD'}, {'s1': 'BAD'}, {'s1': 'GOOD'}]
    plain = model.collect_batch_dependencies(runs, compile_tree=True)
    capture = Attribution(targets, owners)
    observed = capture.run(lambda: model.collect_batch_dependencies(runs, compile_tree=True))
    assert plain.runs == observed.runs
    assert not observed.passed and observed.runs[1].error
    # The callable returned normally; its semantic failure is a distinct fact.
    assert capture.snapshot()['completed']
    with pytest.raises(RuntimeError, match='Incomplete or failed'):
        compare(model, runs, targets, owners)
