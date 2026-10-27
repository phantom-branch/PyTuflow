"""Bounded orchestration contracts using explicit controlled parser stand-ins."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from .profile_construction_attribution import compare, load_runs, operation


class Model:
    def __init__(self, *, mismatch=False, failed=False):
        self.calls = []
        self.mismatch = mismatch
        self.failed = failed

    def collect_batch_dependencies(self, runs, *, cache_scopes, compile_tree):
        self.calls.append((runs, cache_scopes, compile_tree))
        values = tuple((i, tuple(row.items()), 'complete-public-fields') for i, row in enumerate(runs))
        if self.mismatch and compile_tree:
            values = values[:-1] + (('changed-command-provenance',),)
        return SimpleNamespace(passed=not self.failed, runs=values)


def test_four_calls_preserve_flags_caches_order_duplicates_and_complete_parity():
    model = Model()
    runs = [{'s1': 'DEV', 'e1': 'A'}, {'e1': 'A', 's1': 'DEV'}] * 3
    saved = {}
    report = compare(model, runs, [], {}, on_capture=lambda name, value: saved.update({name: value}))
    assert len(model.calls) == 4
    assert [g for _, _, g in model.calls] == [False, False, True, True]
    assert all(rows is runs and caches for rows, caches, _ in model.calls)
    assert report['public_projection_parity'] is True
    assert report['accepted_for_benchmark'] is False
    assert report['physical_preflight_performed'] is False
    assert len(saved) == 2
    for capture in saved.values():
        assert capture['completed']
        assert sum(row['exclusive_ns'] for row in capture['cells']) == capture['wall_elapsed_ns']


def test_equal_counts_with_changed_provenance_do_not_pass():
    with pytest.raises(RuntimeError, match='public run projections differ'):
        compare(Model(mismatch=True), [{'e1': 'A'}], [], {})


def test_failed_projection_stops_before_further_calls():
    model = Model(failed=True)
    with pytest.raises(RuntimeError, match='Incomplete or failed'):
        compare(model, [{'e1': 'A'}], [], {})
    assert len(model.calls) == 1


def test_observed_exception_is_retained_when_report_write_also_fails():
    failure = ValueError('parser failure')
    class Failing(Model):
        def collect_batch_dependencies(self, runs, **options):
            if self.calls:
                raise failure
            return super().collect_batch_dependencies(runs, **options)
    def cannot_write(*args): raise OSError('disk failure')
    with pytest.raises(ValueError) as caught:
        compare(Failing(), [{'e1': 'A'}], [], {}, on_capture=cannot_write)
    assert caught.value is failure
    assert 'Attribution report failed: OSError' in failure.__notes__
    assert sys.getprofile() is None


def test_report_write_error_after_success_is_not_hidden():
    def cannot_write(*args): raise OSError('disk failure')
    with pytest.raises(OSError, match='disk failure'):
        compare(Model(), [{'e1': 'A'}], [], {}, on_capture=cannot_write)


@pytest.mark.parametrize('rows', [[], [{}] * 7])
def test_direct_api_rejects_empty_or_full_workload(rows):
    model = Model()
    with pytest.raises(ValueError, match='six contexts'):
        compare(model, rows, [], {})
    assert model.calls == []


@pytest.mark.parametrize('value', [[], [{}], [{'e1': 1}], [{'solver': 'run'}],
                                  [{'e1': ''}], [{'e1': 'A'}] * 7, {'e1': 'A'}])
def test_invalid_run_lists_are_rejected(tmp_path, value):
    path = tmp_path / 'runs.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError):
        load_runs(path)


def test_run_list_preserves_order_and_duplicate_rows(tmp_path):
    path = tmp_path / 'runs.json'
    value = [{'s1': 'EXG', 'e1': 'A'}, {'e1': 'B'}, {'s1': 'EXG', 'e1': 'A'}]
    path.write_text(json.dumps(value), encoding='utf-8')
    assert load_runs(path) == value


def test_projection_dataclasses_are_not_mislabelled_as_context_construction():
    assert operation('batch_dependencies', '__init__', 'BatchContext.__init__') == 'context_bootstrap'
    assert operation('batch_dependencies', '__init__', 'BatchDependencyRun.__init__') == 'batch_projection'
    assert operation('cf.tcf', 'deferred_database_sources_for_activation', 'TCF.deferred_database_sources_for_activation') == 'database_source_projection'
    assert operation('parsers.command', '__init__', 'Command.__init__') == 'command_construction'
    assert operation('parsers.block', '__init__', 'DefineBlock.__init__') == 'parser_processing'


@pytest.mark.parametrize('as_module', [False, True])
def test_help_does_not_require_gis_imports(as_module):
    root = Path(__file__).absolute().parents[1]
    args = ['-m', 'tests.profile_construction_attribution'] if as_module else ['tests/profile_construction_attribution.py']
    result = subprocess.run([sys.executable, *args, '--help'], cwd=root, text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert '--runs-json' in result.stdout
