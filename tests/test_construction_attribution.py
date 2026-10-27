"""Deterministic accounting and failure contracts; no PyTUFLOW dependency."""

import cProfile
import sys
from types import SimpleNamespace

import pytest

from .construction_attribution import Attribution, Target


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def advance(self, value):
        self.now += value


def cells(capture):
    return {(row['operation'], row['control_file_kind']): row for row in capture.snapshot()['cells']}


def test_nested_owners_partition_elapsed_without_double_counting():
    clock = Clock()
    class Root: pass
    class Child: pass
    def inner(owner):
        clock.advance(7)
    def outer(owner):
        clock.advance(3)
        inner(Child())
        clock.advance(5)
    capture = Attribution([
        (outer.__code__, Target('construct', 'owner')),
        (inner.__code__, Target('construct', 'owner')),
    ], {Root: 'TCF', Child: 'TGC'}, clock=clock)
    capture.run(lambda: outer(Root()))
    rows = cells(capture)
    assert rows['construct', 'TCF']['exclusive_ns'] == 8
    assert rows['construct', 'TCF']['inclusive_span_ns'] == 15
    assert rows['construct', 'TGC']['exclusive_ns'] == 7
    assert sum(row['exclusive_ns'] for row in rows.values()) == 15
    assert capture.snapshot()['wall_elapsed_ns'] == 15


def test_recursive_same_category_counts_work_once():
    clock = Clock()
    def recurse(n):
        clock.advance(1)
        if n:
            recurse(n - 1)
    capture = Attribution([(recurse.__code__, Target('recursive'))], {}, clock=clock)
    capture.run(lambda: recurse(3))
    row = cells(capture)['recursive', 'UNATTRIBUTED']
    assert row['exclusive_ns'] == 4
    assert row['inclusive_span_ns'] == 10
    assert row['activation_segments'] == 4


def test_generator_yield_excludes_consumer_work_and_handles_close():
    clock = Clock()
    def generate():
        try:
            clock.advance(2)
            yield 1
            clock.advance(3)
            yield 2
        finally:
            clock.advance(5)
    def consume():
        iterator = generate()
        assert next(iterator) == 1
        clock.advance(100)
        assert next(iterator) == 2
        clock.advance(200)
        iterator.close()
    capture = Attribution([(generate.__code__, Target('source_projection'))], {}, clock=clock)
    capture.run(consume)
    rows = cells(capture)
    assert rows['source_projection', 'UNATTRIBUTED']['exclusive_ns'] == 10
    assert rows['source_projection', 'UNATTRIBUTED']['generator_activation_segments'] == 3
    assert rows['unattributed', 'UNATTRIBUTED']['exclusive_ns'] == 300


@pytest.mark.parametrize('failure', [ValueError('original'), KeyboardInterrupt(), SystemExit(7)])
def test_failure_retains_partial_accounting_and_original_exception(failure):
    clock = Clock()
    def fail():
        clock.advance(11)
        raise failure
    capture = Attribution([(fail.__code__, Target('construction'))], {}, clock=clock)
    with pytest.raises(type(failure)) as caught:
        capture.run(fail)
    assert caught.value is failure
    assert sys.getprofile() is None
    assert not capture.snapshot()['completed']
    assert cells(capture)['construction', 'UNATTRIBUTED']['exclusive_ns'] == 11


def test_unregistered_work_belongs_to_nearest_registered_boundary():
    clock = Clock()
    def helper(): clock.advance(8)
    def outer(): helper()
    capture = Attribution([(outer.__code__, Target('scope'))], {}, clock=clock)
    capture.run(outer)
    assert cells(capture)['scope', 'UNATTRIBUTED']['exclusive_ns'] == 8


def test_unknown_owner_does_not_invoke_custom_hash_or_attribute_hooks():
    class Meta(type):
        def __hash__(self): raise AssertionError('metaclass hash called')
    class Unknown(metaclass=Meta):
        def __getattribute__(self, name): raise AssertionError('getter called')
    def work(owner): return 1
    capture = Attribution([(work.__code__, Target('scope', 'owner'))], {})
    assert capture.run(lambda: work(Unknown())) == 1
    assert ('scope', 'UNATTRIBUTED') in cells(capture)


def test_code_objects_with_same_text_remain_distinct():
    clock = Clock()
    left, right = {}, {}
    for namespace, filename in ((left, '/one/same.py'), (right, '/two/same.py')):
        exec(compile('def work():\n    clock.advance(3)\n', filename, 'exec'), {'clock': clock}, namespace)
    capture = Attribution([
        (left['work'].__code__, Target('left')),
        (right['work'].__code__, Target('right')),
    ], {}, clock=clock)
    capture.run(lambda: (left['work'](), right['work']()))
    assert cells(capture)['left', 'UNATTRIBUTED']['exclusive_ns'] == 3
    assert cells(capture)['right', 'UNATTRIBUTED']['exclusive_ns'] == 3


def test_existing_classic_profiler_is_not_replaced():
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        before = sys.getprofile()
        with pytest.raises(RuntimeError, match='profile'):
            Attribution([], {}).run(lambda: pytest.fail('action ran'))
        assert sys.getprofile() is before
    finally:
        profiler.disable()


def test_existing_monitoring_profiler_is_not_replaced(monkeypatch):
    monkeypatch.setattr(sys, 'monitoring', SimpleNamespace(PROFILER_ID=2, get_tool=lambda _: 'owner'))
    with pytest.raises(RuntimeError, match='already owned'):
        Attribution([], {}).run(lambda: pytest.fail('action ran'))


def test_replaced_hook_is_retained_but_capture_fails():
    replacement = lambda *args: None
    capture = Attribution([], {})
    try:
        with pytest.raises(RuntimeError, match='replaced or disabled'):
            capture.run(lambda: sys.setprofile(replacement))
        assert sys.getprofile() is replacement
        assert not capture.snapshot()['completed']
    finally:
        sys.setprofile(None)


def test_changed_hook_does_not_replace_original_failure():
    failure = ValueError('original')
    def action():
        sys.setprofile(None)
        raise failure
    capture = Attribution([], {})
    with pytest.raises(ValueError) as caught:
        capture.run(action)
    assert caught.value is failure
    assert capture.snapshot()['diagnostic_error'] is not None


def test_lazy_return_rejected_and_single_use_enforced():
    capture = Attribution([], {})
    with pytest.raises(TypeError, match='Consume lazy'):
        capture.run(lambda: iter([1]))
    assert not capture.snapshot()['completed']
    with pytest.raises(RuntimeError, match='fresh Attribution'):
        capture.run(lambda: 1)


def test_snapshot_requires_finished_capture_and_returns_independent_cells():
    capture = Attribution([], {})
    with pytest.raises(RuntimeError, match='finished'):
        capture.snapshot()
    assert capture.run(lambda: 42) == 42
    first = capture.snapshot()
    first['cells'].clear()
    assert capture.snapshot()['cells']
    assert capture.snapshot()['accepted_for_benchmark'] is False


def test_unknown_child_owner_does_not_charge_known_parent():
    clock = Clock()
    class Root: pass
    def child(owner): clock.advance(7)
    def root(owner):
        clock.advance(2)
        child(object())
    capture = Attribution([
        (root.__code__, Target('evaluate', 'owner')),
        (child.__code__, Target('evaluate', 'owner')),
    ], {Root: 'TCF'}, clock=clock)
    capture.run(lambda: root(Root()))
    assert cells(capture)['evaluate', 'TCF']['exclusive_ns'] == 2
    assert cells(capture)['evaluate', 'UNATTRIBUTED']['exclusive_ns'] == 7
