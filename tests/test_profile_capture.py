"""Evidence-retention contracts; no PyTUFLOW/GIS/solver dependencies."""

import cProfile
import importlib.util
import json
import pstats
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from .profile_capture import capture_profile


def _leaf() -> int:
    return sum(range(10))


def _caller() -> int:
    return _leaf()


def test_complete_capture_preserves_result_and_all_tables(tmp_path: Path) -> None:
    destination = tmp_path / 'capture'
    value, profile = capture_profile(_caller, output_dir=destination, provenance={'revision': 'example'})
    assert value == 45
    assert isinstance(profile, cProfile.Profile)
    assert {p.name for p in destination.iterdir()} == {
        'profile.pstats', 'metadata.json', 'self.txt', 'cumulative.txt', 'callers.txt', 'callees.txt',
    }
    metadata = json.loads((destination / 'metadata.json').read_text())
    assert metadata['reports_complete'] is True
    assert metadata['action_returned'] is True
    assert metadata['accepted_for_benchmark'] is False
    assert metadata['provenance'] == {'revision': 'example'}
    raw = pstats.Stats(str(destination / 'profile.pstats'))
    leaf = next(key for key in raw.stats if key[2] == '_leaf')
    assert any(key[2] == '_caller' for key in raw.stats[leaf][4])
    for name in ('self.txt', 'cumulative.txt', 'callers.txt', 'callees.txt'):
        text = (destination / name).read_text(encoding='utf-8')
        assert '_leaf' in text and '_caller' in text
    assert sys.getprofile() is None


@pytest.mark.parametrize('exception', [ValueError('private detail'), KeyboardInterrupt(), SystemExit(7)])
def test_failed_action_retains_profile_without_masking_exception(tmp_path: Path, exception: BaseException) -> None:
    destination = tmp_path / 'failed'

    def fail() -> None:
        _leaf()
        raise exception

    with pytest.raises(type(exception)) as caught:
        capture_profile(fail, output_dir=destination)
    assert caught.value is exception
    metadata = json.loads((destination / 'metadata.json').read_text())
    assert metadata['reports_complete'] is True
    assert metadata['action_returned'] is False
    assert metadata['accepted_for_benchmark'] is False
    assert metadata['exception_type'] == type(exception).__name__
    assert 'private detail' not in json.dumps(metadata)
    assert any(key[2] == '_leaf' for key in pstats.Stats(str(destination / 'profile.pstats')).stats)
    assert sys.getprofile() is None


def test_existing_output_is_preserved_without_running_action(tmp_path: Path) -> None:
    destination = tmp_path / 'existing'
    destination.mkdir()
    marker = destination / 'metadata.json'
    marker.write_text('original')
    with pytest.raises(FileExistsError):
        capture_profile(lambda: pytest.fail('must not run'), output_dir=destination)
    assert marker.read_text() == 'original'


def test_output_within_repository_is_rejected() -> None:
    destination = Path(__file__).absolute().parent / 'must-not-be-created'
    with pytest.raises(ValueError, match='outside'):
        capture_profile(lambda: pytest.fail('must not run'), output_dir=destination)
    assert not destination.exists()


def test_existing_profiler_is_preserved(tmp_path: Path) -> None:
    existing = cProfile.Profile()
    existing.enable()
    try:
        with pytest.raises(RuntimeError, match='existing profiling hook'):
            capture_profile(lambda: pytest.fail('must not run'), output_dir=tmp_path / 'new')
        assert (sys.getprofile() is existing
                or sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) == 'cProfile')
        _leaf()
        assert not (tmp_path / 'new').exists()
    finally:
        existing.disable()


def test_report_failure_preserves_original_action_failure(tmp_path: Path) -> None:
    original = ValueError('original workload failure')

    def fail() -> None:
        raise original

    with patch.object(pstats.Stats, 'print_stats', side_effect=OSError('disk full')):
        with pytest.raises(ValueError) as caught:
            capture_profile(fail, output_dir=tmp_path / 'partial')
    assert caught.value is original
    assert any('retention also failed: OSError' in note for note in original.__notes__)
    assert (tmp_path / 'partial/profile.pstats').is_file()
    assert json.loads((tmp_path / 'partial/metadata.json').read_text())['reports_complete'] is False


def test_report_failure_after_success_is_not_hidden(tmp_path: Path) -> None:
    with patch.object(pstats.Stats, 'print_stats', side_effect=OSError('disk full')):
        with pytest.raises(OSError):
            capture_profile(_leaf, output_dir=tmp_path / 'partial')
    assert (tmp_path / 'partial/profile.pstats').is_file()
    assert sys.getprofile() is None


def test_no_directory_retains_in_memory_profile(tmp_path: Path) -> None:
    value, profile = capture_profile(_caller)
    assert value == 45
    assert any(key[2] == '_leaf' for key in pstats.Stats(profile).stats)
    assert list(tmp_path.iterdir()) == []


def test_returned_iterator_is_rejected_and_explicit_consumption_is_profiled(tmp_path: Path) -> None:
    def items():
        yield _leaf()
        yield _leaf()

    with pytest.raises(TypeError, match='Consume iterator'):
        capture_profile(items, output_dir=tmp_path / 'lazy')
    values, profile = capture_profile(lambda: list(items()))
    assert values == [45, 45]
    row = next(value for key, value in pstats.Stats(profile).stats.items() if key[2] == '_leaf')
    assert row[1] == 2


def test_recursion_primitive_and_total_calls_are_preserved(tmp_path: Path) -> None:
    def recurse(depth: int) -> int:
        return recurse(depth - 1) if depth else 1

    capture_profile(lambda: recurse(3), output_dir=tmp_path / 'recursion')
    raw = pstats.Stats(str(tmp_path / 'recursion/profile.pstats'))
    row = next(value for key, value in raw.stats.items() if key[2] == 'recurse')
    assert row[:2] == (1, 4)


def test_same_basename_functions_are_not_merged(tmp_path: Path) -> None:
    functions = []
    for folder in ('first', 'second'):
        directory = tmp_path / folder
        directory.mkdir()
        source = directory / 'same.py'
        source.write_text('def work():\n    return sum(range(5))\n')
        spec = importlib.util.spec_from_file_location(folder, source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        functions.append(module.work)
    capture_profile(lambda: [fn() for fn in functions], output_dir=tmp_path / 'capture')
    raw = pstats.Stats(str(tmp_path / 'capture/profile.pstats'))
    assert len([key for key in raw.stats if key[2] == 'work']) == 2
    text = (tmp_path / 'capture/self.txt').read_text(encoding='utf-8')
    assert str(tmp_path / 'first/same.py') in text
    assert str(tmp_path / 'second/same.py') in text


def test_invalid_provenance_fails_before_action_or_output(tmp_path: Path) -> None:
    destination = tmp_path / 'invalid'
    with pytest.raises(TypeError):
        capture_profile(lambda: pytest.fail('must not run'), output_dir=destination, provenance={'bad': object()})
    assert not destination.exists()


def test_monitoring_profiler_slot_is_not_replaced(tmp_path: Path) -> None:
    sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, 'other-profiler')
    try:
        with pytest.raises(RuntimeError, match='existing profiling hook'):
            capture_profile(_leaf, output_dir=tmp_path / 'new')
        assert sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) == 'other-profiler'
        assert not (tmp_path / 'new').exists()
    finally:
        sys.monitoring.free_tool_id(sys.monitoring.PROFILER_ID)


def test_classic_profile_hook_is_not_replaced(tmp_path: Path) -> None:
    def hook(frame, event, arg):
        return None

    sys.setprofile(hook)
    try:
        with pytest.raises(RuntimeError, match='existing profiling hook'):
            capture_profile(_leaf, output_dir=tmp_path / 'new')
        assert sys.getprofile() is hook
    finally:
        sys.setprofile(None)


def test_cli_help_does_not_load_benchmark(monkeypatch, capsys) -> None:
    from . import profile_batch_dependencies

    monkeypatch.setitem(sys.modules, 'tests.benchmark_batch_dependencies', None)
    monkeypatch.setattr(sys, 'argv', ['profile_batch_dependencies.py', '--help'])
    with pytest.raises(SystemExit) as stopped:
        profile_batch_dependencies.main()
    assert stopped.value.code == 0
    assert '--output' in capsys.readouterr().out


@pytest.mark.parametrize('arguments', [
    ['--runs', '0'], ['--runs', '-1'], ['--static-inputs', '-1'],
    ['--functions', '0'], ['--runs', 'invalid'],
])
def test_cli_invalid_counts_do_not_load_benchmark(monkeypatch, arguments) -> None:
    from . import profile_batch_dependencies

    monkeypatch.setitem(sys.modules, 'tests.benchmark_batch_dependencies', None)
    monkeypatch.setattr(sys, 'argv', ['profile_batch_dependencies.py', *arguments])
    with pytest.raises(SystemExit) as stopped:
        profile_batch_dependencies.main()
    assert stopped.value.code == 2


def test_cli_retains_existing_benchmark_arguments(tmp_path: Path, monkeypatch, capsys) -> None:
    from types import ModuleType
    from . import profile_batch_dependencies

    calls = []
    benchmark_module = ModuleType('tests.benchmark_batch_dependencies')

    def benchmark(runs, *, trials, static_inputs):
        calls.append((runs, trials, static_inputs))
        return {'parity': 'test-only', 'cached_context_counters': {}}

    benchmark_module.benchmark = benchmark
    monkeypatch.setitem(sys.modules, 'tests.benchmark_batch_dependencies', benchmark_module)
    monkeypatch.setattr(sys, 'argv', [
        'profile_batch_dependencies.py', '--runs', '2', '--static-inputs', '0',
        '--functions', '1', '--output', str(tmp_path / 'cli'),
    ])
    profile_batch_dependencies.main()
    assert calls == [(2, 1, 0)]
    assert (tmp_path / 'cli/profile.pstats').is_file()
    assert 'Exact reference parity: test-only' in capsys.readouterr().out


@pytest.mark.parametrize('invocation', [
    ['tests/profile_batch_dependencies.py', '--help'],
    ['-m', 'tests.profile_batch_dependencies', '--help'],
])
def test_cli_script_and_package_entry_points(invocation) -> None:
    import subprocess

    completed = subprocess.run(
        [sys.executable, *invocation], cwd=Path(__file__).absolute().parents[1],
        capture_output=True, text=True, check=True,
    )
    assert '--output' in completed.stdout
