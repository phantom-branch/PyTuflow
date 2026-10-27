"""Regressions reproduced on the first attribution implementation."""

from types import SimpleNamespace

import pytest

from .construction_attribution import Attribution
from .profile_construction_attribution import compare


def test_unconsumed_async_generator_is_not_reported_as_completed():
    async def generate():
        yield 1
    capture = Attribution([], {})
    with pytest.raises(TypeError, match='Consume lazy'):
        capture.run(generate)
    assert not capture.snapshot()['completed']


def test_outer_handled_exception_does_not_hide_a_new_reporting_failure():
    class Model:
        def collect_batch_dependencies(self, runs, **options):
            return SimpleNamespace(passed=True, runs=tuple(range(len(runs))))
    def cannot_write(*args):
        raise OSError('report failure')
    try:
        raise LookupError('unrelated outer exception')
    except LookupError:
        with pytest.raises(OSError, match='report failure'):
            compare(Model(), [{'e1': 'A'}], [], {}, on_capture=cannot_write)
