"""Batch construction avoids repeated UUID scans without changing edit history."""

from pathlib import Path
from types import MethodType, SimpleNamespace
from uuid import UUID, uuid4

import pytest

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import BatchContext
from pytuflow._tmf.cf.cf_run_state import _batch_append_context_methods
from pytuflow._tmf.inp.gis import GisInput
from pytuflow._tmf.inp.inp_build_state import InputBuildState
from pytuflow._tmf.inp.inputs import Inputs, _ContextAppendRecorder
from pytuflow._tmf.inp.setting import SettingInput


class _InputProbe:
    def __init__(
        self, owner: object, identifier: UUID, *, visible: bool = True, block: str = ''
    ) -> None:
        self.parent = owner
        self.identifier = identifier
        self.visible = visible
        self.block = block
        self.uuid_reads = 0

    @property
    def uuid(self) -> UUID:
        self.uuid_reads += 1
        return self.identifier

    def __bool__(self) -> bool:
        return self.visible

    def is_start_block(self) -> bool:
        return self.block == 'start'

    def is_end_block(self) -> bool:
        return self.block == 'end'


def _owner() -> SimpleNamespace:
    return SimpleNamespace(inputs=Inputs())


def test_append_recorder_retains_first_uuid_and_hidden_positions() -> None:
    """Duplicate identifiers select the first visible and first hidden match."""
    owner = _owner()
    recorder = _ContextAppendRecorder(owner.inputs)
    first, hidden, other = uuid4(), uuid4(), uuid4()
    inputs = [
        _InputProbe(owner, first),
        _InputProbe(owner, hidden, visible=False),
        _InputProbe(owner, hidden),
        _InputProbe(owner, first),
        _InputProbe(owner, other, visible=False),
        _InputProbe(owner, uuid4(), block='start'),
        _InputProbe(owner, uuid4(), block='end'),
        _InputProbe(owner, first, visible=False),
    ]
    for inp in inputs:
        assert recorder.append(inp)
    assert len(owner.inputs) == 3
    assert len(owner.inputs.inputs(include_hidden=True)) == 6
    assert [pair for _, pair in owner.inputs.iter_indexes()] == [
        (0, 0), (-1, 1), (1, 1), (0, 0), (-1, 4), (0, 0),
    ]


def test_append_uuid_accesses_are_linear_during_one_construction() -> None:
    """The regression is counted work, with no machine-dependent timing gate."""
    count = 500
    ordinary_owner, batch_owner = _owner(), _owner()
    ordinary = [_InputProbe(ordinary_owner, uuid4()) for _ in range(count)]
    batch = [_InputProbe(batch_owner, inp.identifier) for inp in ordinary]
    for inp in ordinary:
        ordinary_owner.inputs.append(inp)
    recorder = _ContextAppendRecorder(batch_owner.inputs)
    for inp in batch:
        assert recorder.append(inp)
    assert sum(inp.uuid_reads for inp in batch) == count
    assert sum(inp.uuid_reads for inp in ordinary) >= count * (count + 1) // 2
    assert batch_owner.inputs._indexes == ordinary_owner.inputs._indexes


def test_append_recorder_falls_back_after_external_structural_change() -> None:
    owner = _owner()
    first = _InputProbe(owner, uuid4())
    inserted = _InputProbe(owner, uuid4())
    duplicate = _InputProbe(owner, first.identifier)
    recorder = _ContextAppendRecorder(owner.inputs)
    assert recorder.append(first)
    owner.inputs.insert(0, inserted)
    assert not recorder.append(duplicate)
    # The first UUID has moved to index one; no cached position may survive.
    assert owner.inputs._indexes[-1] == (1, 1)
    owner.inputs.remove(inserted)
    assert not recorder.append(duplicate)
    assert owner.inputs._indexes[-1] == (0, 0)


def test_public_append_and_copy_keep_live_parent_lookups() -> None:
    owner = _owner()
    first, second, inserted = [_InputProbe(owner, uuid4()) for _ in range(3)]
    owner.inputs.append(first)
    owner.inputs.append(second)
    changes = Inputs()
    changes.append(first)
    snapshot = changes.copy()
    first.identifier = second.identifier
    owner.inputs.insert(0, inserted)
    changes.append(second)
    assert changes._indexes == [(0, 0), (1, 1)]
    assert snapshot._indexes == [(0, 0)]
    # Even direct edits to the publicly returned hidden list remain visible.
    owner.inputs.inputs(include_hidden=True).reverse()
    snapshot.append(second)
    assert snapshot._indexes == [(0, 0), (1, 0)]


@pytest.mark.parametrize('file_resolution', ['eager', 'deferred'])
def test_batch_and_ordinary_contexts_preserve_nested_append_indices(
    tmp_path: Path, file_resolution: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_inputs = []
    original_append = _ContextAppendRecorder.append

    def counted_append(self, inp):
        recorded_inputs.append(inp)
        return original_append(self, inp)

    monkeypatch.setattr(_ContextAppendRecorder, 'append', counted_append)
    (tmp_path / 'geometry.tgc').write_text(
        'Set Code == 2\nSet Code == 3\n', encoding='utf-8'
    )
    source = tmp_path / 'model.tcf'
    source.write_text(
        '! hidden comment\n'
        'Set Code == 0\n'
        'Geometry Control File == geometry.tgc\n'
        'If Scenario == DEV\nSet Code == 1\nElse\nSet Code == 4\nEnd If\n',
        encoding='utf-8',
    )
    model = TCF(source)
    for scenario in ('DEV', 'EXG'):
        recorded_inputs.clear()
        flags = f'-s1 {scenario}'
        batch = model.context(
            context=BatchContext(flags, config=model.config), file_resolution=file_resolution
        )
        ordinary = model.context(flags, file_resolution=file_resolution)
        assert [(inp.uuid, str(inp)) for inp in batch.find_input()] == [
            (inp.uuid, str(inp)) for inp in ordinary.find_input()
        ]
        assert batch.inputs._indexes == ordinary.inputs._indexes == [(0, 0), (1, 1), (2, 2)]
        assert batch.tgc().inputs._indexes == ordinary.tgc().inputs._indexes == [(0, 0), (1, 1)]
        if file_resolution == 'deferred':
            # Retiring the outer recorder before recursion must not disable
            # the new, independent collection built for a leaf control file.
            assert [id(inp) for inp in recorded_inputs] == [
                id(batch.inputs[0]), *[id(inp) for inp in batch.tgc().inputs],
            ]
        else:
            assert not recorded_inputs


def test_custom_constructor_mutation_disables_enclosing_append_recorder(tmp_path: Path) -> None:
    """A nested extension can change an already-created outer input's UUID."""
    (tmp_path / 'geometry.tgc').write_text('Set Code == 2\n', encoding='utf-8')
    source = tmp_path / 'model.tcf'
    source.write_text(
        'Set Code == 0\nGeometry Control File == geometry.tgc\nSet Code == 1\n',
        encoding='utf-8',
    )
    model = TCF(source)
    child = model.tgc().inputs[0]
    original_context = child.context
    outer_identifier = model.inputs[1].uuid

    def custom_context(self, *args, **kwargs):
        parent = kwargs['parent']
        parent.parent.inputs[0].uuid = outer_identifier
        return original_context(*args, **kwargs)

    child.context = MethodType(custom_context, child)
    context = BatchContext('-s1 DEV', config=model.config)
    batch = model.context(context=context, file_resolution='deferred')
    ordinary = model.context('-s1 DEV', file_resolution='deferred')
    assert context._batch_append_indexes_safe is False
    assert batch.inputs._indexes == ordinary.inputs._indexes == [(0, 0), (0, 0), (2, 2)]


def test_nested_control_context_override_keeps_parent_indexes_live(tmp_path: Path) -> None:
    """An enclosing recorder retires before invoking a child control hook."""
    (tmp_path / 'geometry.tgc').write_text('Set Code == 2\n', encoding='utf-8')
    source = tmp_path / 'nested_extension.tcf'
    source.write_text(
        'Set Code == 0\nGeometry Control File == geometry.tgc\nSet Code == 1\n',
        encoding='utf-8',
    )
    model = TCF(source)
    child_control = model.tgc()
    original_context = child_control.context

    def custom_context(self, *args, **kwargs):
        kwargs['parent'].inputs[0].uuid = model.inputs[1].uuid
        return original_context(*args, **kwargs)

    child_control.context = MethodType(custom_context, child_control)
    batch = model.context(
        context=BatchContext('-s1 DEV', config=model.config), file_resolution='deferred'
    )
    ordinary = model.context('-s1 DEV', file_resolution='deferred')
    assert batch.inputs._indexes == ordinary.inputs._indexes == [(0, 0), (0, 0), (2, 2)]


def test_append_guard_does_not_inspect_lazy_gis_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / 'deferred_gis.tcf'
    source.write_text('Set Code == 0\nRead GIS Zpt == points.shp\n', encoding='utf-8')
    model = TCF(source)

    def forbidden_children(self):
        raise AssertionError('Deferred append accounting must not inspect lazy GIS children')

    monkeypatch.setattr(GisInput, 'cf', property(forbidden_children, GisInput.cf.fset))
    batch = model.context(
        context=BatchContext('-s1 DEV', config=model.config), file_resolution='deferred'
    )
    assert batch.inputs._indexes == [(0, 0), (1, 1)]


@pytest.mark.parametrize('scenario', ['DEV', 'EXG'])
@pytest.mark.parametrize('hook_target', ['subclass', 'class'])
def test_custom_context_descriptor_is_read_only_when_constructing_selected_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str, hook_target: str,
) -> None:
    """Trust checks must not invoke inactive or unsupported constructor hooks."""
    context_reads = []

    class ExtendedSetting(SettingInput):
        @property
        def context(self):
            if self is extended:
                if scenario == 'EXG':
                    raise AssertionError('Inactive constructor must not be inspected')
                context_reads.append(self.uuid)
            return MethodType(InputBuildState.context, self)

    source = tmp_path / 'constructor_descriptor.tcf'
    source.write_text(
        'Set Code == 0\nIf Scenario == DEV\nSet Code == 1\nEnd If\nSet Code == 2\n',
        encoding='utf-8',
    )
    model = TCF(source)
    extended = model.find_input(lhs='Set Code')[1]
    if hook_target == 'subclass':
        extended.__class__ = ExtendedSetting
    else:
        monkeypatch.setattr(SettingInput, 'context', ExtendedSetting.context)
    ordinary = model.context(f'-s1 {scenario}', file_resolution='deferred')
    expected_reads = context_reads.copy()
    context_reads.clear()
    batch = model.context(
        context=BatchContext(f'-s1 {scenario}', config=model.config),
        file_resolution='deferred',
    )
    assert context_reads == expected_reads == ([extended.uuid] if scenario == 'DEV' else [])
    assert batch.inputs._indexes == ordinary.inputs._indexes
    assert [(inp.uuid, str(inp)) for inp in batch.find_input()] == [
        (inp.uuid, str(inp)) for inp in ordinary.find_input()
    ]


@pytest.mark.parametrize('input_class', [InputBuildState, SettingInput])
def test_class_constructor_override_before_first_batch_uses_live_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, input_class: type
) -> None:
    """A class-level extension must not become trusted on first cache access."""
    source = tmp_path / 'class_extension.tcf'
    source.write_text('Set Code == 0\nSet Code == 1\n', encoding='utf-8')
    model = TCF(source)
    original_context = input_class.context

    def custom_context(self, *args, **kwargs):
        parent = kwargs['parent']
        if parent.inputs:
            parent.inputs[0].uuid = self.uuid
        return original_context(self, *args, **kwargs)

    monkeypatch.setattr(input_class, 'context', custom_context)
    # Exercise initial table construction even when earlier tests ran batches.
    _batch_append_context_methods.cache_clear()
    try:
        context = BatchContext('-s1 DEV', config=model.config)
        batch = model.context(context=context, file_resolution='deferred')
        ordinary = model.context('-s1 DEV', file_resolution='deferred')
        assert getattr(context, '_batch_append_indexes_safe', True) is False
        assert batch.inputs._indexes == ordinary.inputs._indexes == [(0, 0), (0, 0)]
    finally:
        _batch_append_context_methods.cache_clear()


def test_build_edit_and_undo_after_batch_context_are_unchanged(tmp_path: Path) -> None:
    source = tmp_path / 'editable.tcf'
    source.write_text('Set Code == 1\nSet Code == 2\nSet Code == 3\n', encoding='utf-8')
    model = TCF(source)
    middle = model.inputs[1]
    context = BatchContext('-s1 DEV', config=model.config)
    model.context(context=context, file_resolution='deferred')
    model.remove_input(middle)
    assert [str(inp) for inp in model.inputs] == ['Set Code == 1', 'Set Code == 3']
    model.undo()
    assert [str(inp) for inp in model.inputs] == ['Set Code == 1', 'Set Code == 2', 'Set Code == 3']
    middle = model.inputs[1]
    model.comment_out(middle)
    assert [str(inp) for inp in model.inputs] == ['Set Code == 1', 'Set Code == 3']
    model.undo()
    assert [str(inp) for inp in model.inputs] == ['Set Code == 1', 'Set Code == 2', 'Set Code == 3']
