"""Batch construction avoids repeated UUID scans without changing edit history."""

from pathlib import Path
from types import MethodType, SimpleNamespace
from uuid import UUID, uuid4

import pytest

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import BatchContext, _batch_append_context_is_trusted
from pytuflow._tmf.cf.cf_run_state import ControlFileRunState, _batch_append_context_methods
from pytuflow._tmf.context import Context
from pytuflow._tmf.event import EventDatabase
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


@pytest.mark.parametrize('hook_target', ['instance', 'class', 'descriptor'])
def test_custom_batch_factory_keeps_live_append_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hook_target: str,
) -> None:
    """The invoked factory can mutate prior UUIDs without changing list lengths."""
    source = tmp_path / 'factory_extension.tcf'
    source.write_text(
        'Set Code == 0\nIf Scenario == OMIT\nSet Code == 2\nEnd If\nSet Code == 1\n',
        encoding='utf-8',
    )
    model = TCF(source)
    original_factory = BatchContext.batch_input_state
    calls, descriptor_reads = [], []

    def custom_factory(self, build_input, parent):
        calls.append(build_input.uuid)
        state = original_factory(self, build_input, parent)
        if parent.inputs:
            parent.inputs[0].uuid = state.uuid
        return state

    def factory_descriptor(self):
        descriptor_reads.append(self)
        return MethodType(custom_factory, self)

    if hook_target == 'class':
        monkeypatch.setattr(BatchContext, 'batch_input_state', custom_factory)
    elif hook_target == 'descriptor':
        monkeypatch.setattr(BatchContext, 'batch_input_state', property(factory_descriptor))

    results = []
    for recorder_enabled in (False, True):
        context = BatchContext('-s1 DEV', config=model.config)
        if not recorder_enabled:
            # Reference uses the unchanged public Inputs.append implementation.
            context._batch_append_indexes_safe = False
        if hook_target == 'instance':
            context.batch_input_state = MethodType(custom_factory, context)
        calls.clear()
        descriptor_reads.clear()
        result = model.context(context=context, file_resolution='deferred')
        results.append(result)
        assert calls == [model.inputs[0].uuid, model.inputs[-1].uuid]
        assert descriptor_reads == ([context, context] if hook_target == 'descriptor' else [])

    ordinary, optimised = results
    assert optimised.inputs._indexes == ordinary.inputs._indexes == [(0, 0), (0, 0)]
    assert [(inp.uuid, str(inp)) for inp in optimised.find_input()] == [
        (inp.uuid, str(inp)) for inp in ordinary.find_input()
    ]


def test_factory_descriptor_retires_recorder_even_when_returning_canonical_method(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Descriptor side effects happen before bound-method identity is known."""
    source = tmp_path / 'canonical_factory_descriptor.tcf'
    source.write_text('Set Code == 0\nSet Code == 1\n', encoding='utf-8')
    model = TCF(source)
    original_factory = BatchContext.batch_input_state
    original_resolve = ControlFileRunState._resolve_scope_in_context
    active_parents = {}
    descriptor_reads = []

    def capture_parent(self):
        active_parents[id(self.ctx)] = self
        return original_resolve(self)

    def factory_descriptor(self):
        descriptor_reads.append(self)
        parent = active_parents[id(self)]
        if parent.inputs:
            parent.inputs[0].uuid = model.inputs[-1].uuid
        return MethodType(original_factory, self)

    monkeypatch.setattr(ControlFileRunState, '_resolve_scope_in_context', capture_parent)
    monkeypatch.setattr(BatchContext, 'batch_input_state', property(factory_descriptor))
    histories = []
    for recorder_enabled in (False, True):
        context = BatchContext('-s1 DEV', config=model.config)
        if not recorder_enabled:
            context._batch_append_indexes_safe = False
        descriptor_reads.clear()
        result = model.context(context=context, file_resolution='deferred')
        histories.append(result.inputs._indexes)
        assert descriptor_reads == [context, context]
    assert histories == [[(0, 0), (0, 0)], [(0, 0), (0, 0)]]


@pytest.mark.parametrize('factory_owner', ['same', 'other'])
def test_append_recorder_requires_canonical_factory_bound_to_current_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory_owner: str,
) -> None:
    """An original function bound to another context is still an extension."""
    source = tmp_path / 'factory_owner.tcf'
    source.write_text('Set Code == 0\nSet Code == 1\n', encoding='utf-8')
    model = TCF(source)
    context = BatchContext('-s1 DEV', config=model.config)
    other = BatchContext('-s1 DEV', config=model.config)
    other.file_resolution = 'deferred'
    if factory_owner == 'other':
        context.batch_input_state = other.batch_input_state
    recorded_inputs = []
    original_append = _ContextAppendRecorder.append

    def counted_append(self, inp):
        recorded_inputs.append(inp.uuid)
        return original_append(self, inp)

    monkeypatch.setattr(_ContextAppendRecorder, 'append', counted_append)
    result = model.context(context=context, file_resolution='deferred')
    assert result.inputs._indexes == [(0, 0), (1, 1)]
    assert all(inp.ctx is (other if factory_owner == 'other' else context) for inp in result.inputs)
    assert recorded_inputs == (
        [inp.uuid for inp in result.inputs] if factory_owner == 'same' else []
    )


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


def _capture_context_parents(monkeypatch: pytest.MonkeyPatch) -> dict[int, ControlFileRunState]:
    parents = {}
    original = ControlFileRunState._resolve_scope_in_context

    def capture_parent(self):
        parents[id(self.ctx)] = self
        return original(self)

    monkeypatch.setattr(ControlFileRunState, '_resolve_scope_in_context', capture_parent)
    return parents


@pytest.mark.parametrize(('hook_target', 'callback'), [
    ('instance', 'translate'),
    ('instance', 'batch_command'),
    ('instance', 'in_context_by_scope'),
    ('instance', 'is_resolved'),
    ('instance', 'cached_file_references'),
    ('instance', '_create_list'),
    ('base', 'translate'),
    ('base', 'in_context_by_scope'),
])
def test_constructor_callback_mutations_preserve_live_append_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hook_target: str, callback: str,
) -> None:
    """Canonical constructors can invoke extensions that edit earlier inputs."""
    source = tmp_path / 'callback_extension.tcf'
    source.write_text(
        'Set Code == 0\nIf Scenario == OMIT\nSet Code == 2\nEnd If\nSet Code == 1\n',
        encoding='utf-8',
    )
    model = TCF(source)
    parents = _capture_context_parents(monkeypatch)
    original = getattr(Context if hook_target == 'base' else BatchContext, callback)
    calls, mutations = [], []

    def custom_callback(self, *args, **kwargs):
        calls.append(self)
        parent = parents.get(id(self))
        if parent is not None and parent.inputs:
            parent.inputs[0].uuid = model.inputs[-1].uuid
            mutations.append(parent.inputs[0].uuid)
        return original(self, *args, **kwargs)

    if hook_target == 'base':
        monkeypatch.setattr(Context, callback, custom_callback)
    results, call_counts = [], []
    for recorder_enabled in (False, True):
        context = BatchContext('-s1 DEV', config=model.config)
        if not recorder_enabled:
            context._batch_append_indexes_safe = False
        if hook_target == 'instance':
            setattr(context, callback, MethodType(custom_callback, context))
        calls.clear()
        mutations.clear()
        result = model.context(context=context, file_resolution='deferred')
        results.append(result)
        assert mutations
        call_counts.append((len(calls), len(mutations)))

    ordinary, optimised = results
    assert call_counts[0] == call_counts[1]
    assert optimised.inputs._indexes == ordinary.inputs._indexes == [(0, 0), (0, 0)]
    assert [(inp.uuid, str(inp)) for inp in optimised.find_input()] == [
        (inp.uuid, str(inp)) for inp in ordinary.find_input()
    ]


@pytest.mark.parametrize(('owner', 'callback'), [
    (BatchContext, 'translate'),
    (BatchContext, 'available_scopes'),
    (Context, 'available_scopes'),
])
def test_context_callback_descriptors_are_not_read_by_append_trust_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner: type, callback: str,
) -> None:
    """A getter returning canonical behaviour can itself mutate earlier UUIDs."""
    source = tmp_path / 'callback_descriptor.tcf'
    source.write_text(
        'Set Code == 0\nIf Scenario == OMIT\nSet Code == 2\nEnd If\nSet Code == 1\n',
        encoding='utf-8',
    )
    model = TCF(source)
    parents = _capture_context_parents(monkeypatch)
    original = owner.__dict__[callback]
    descriptor_reads, mutations = [], []

    def descriptor(self):
        descriptor_reads.append(self)
        parent = parents.get(id(self))
        if parent is not None and parent.inputs:
            parent.inputs[0].uuid = model.inputs[-1].uuid
            mutations.append(parent.inputs[0].uuid)
        return original.__get__(self, type(self))

    monkeypatch.setattr(owner, callback, property(descriptor))
    histories, read_counts = [], []
    for recorder_enabled in (False, True):
        context = BatchContext('-s1 DEV', config=model.config)
        if not recorder_enabled:
            context._batch_append_indexes_safe = False
        descriptor_reads.clear()
        mutations.clear()
        result = model.context(context=context, file_resolution='deferred')
        histories.append(result.inputs._indexes)
        assert mutations
        read_counts.append(len(descriptor_reads))

    assert read_counts[0] == read_counts[1]
    assert histories == [[(0, 0), (0, 0)], [(0, 0), (0, 0)]]


def test_unused_callback_descriptor_is_not_evaluated_for_an_inactive_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / 'inactive_callback.tcf'
    source.write_text(
        'Set Code == 0\nIf Scenario == OMIT\nRead GIS Code == code.shp\nEnd If\nSet Code == 1\n',
        encoding='utf-8',
    )
    model = TCF(source)

    def forbidden_signature(self):
        raise AssertionError('An inactive READ does not require a declaration-signature callback')

    monkeypatch.setattr(BatchContext, 'variable_declaration_signature', property(forbidden_signature))
    histories = []
    for recorder_enabled in (False, True):
        context = BatchContext('-s1 DEV', config=model.config)
        if not recorder_enabled:
            context._batch_append_indexes_safe = False
        result = model.context(context=context, file_resolution='deferred')
        histories.append(result.inputs._indexes)
    assert histories == [[(0, 0), (1, 1)], [(0, 0), (1, 1)]]


def test_late_scope_callback_retires_recorder_before_an_inactive_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An initially canonical context can acquire a callback between appends."""
    source = tmp_path / 'late_scope_callback.tcf'
    source.write_text(
        'Set Code == 0\nIf Scenario == OMIT\nSet Code == 2\nEnd If\nSet Code == 1\n',
        encoding='utf-8',
    )
    model = TCF(source)
    parents = _capture_context_parents(monkeypatch)
    original_scope = BatchContext.in_context_by_scope
    original_append = Inputs.append
    original_record = _ContextAppendRecorder.append
    scope_safety, recorded_inputs = [], []

    def custom_scope(self, required):
        active = original_scope(self, required)
        if not active:
            scope_safety.append(getattr(self, '_batch_append_indexes_safe', True))
            parents[id(self)].inputs[0].uuid = model.inputs[-1].uuid
        return active

    def install_callback(inp):
        if inp.bs is model.inputs[0]:
            inp.ctx.in_context_by_scope = MethodType(custom_scope, inp.ctx)

    def append(self, inp):
        original_append(self, inp)
        install_callback(inp)

    def record(self, inp):
        recorded_inputs.append(inp.uuid)
        accepted = original_record(self, inp)
        install_callback(inp)
        return accepted

    monkeypatch.setattr(Inputs, 'append', append)
    monkeypatch.setattr(_ContextAppendRecorder, 'append', record)
    histories = []
    for recorder_enabled in (False, True):
        context = BatchContext('-s1 DEV', config=model.config)
        if not recorder_enabled:
            context._batch_append_indexes_safe = False
        scope_safety.clear()
        recorded_inputs.clear()
        result = model.context(context=context, file_resolution='deferred')
        histories.append(result.inputs._indexes)
        assert scope_safety == [False]
        assert recorded_inputs == ([model.inputs[0].uuid] if recorder_enabled else [])
    assert histories == [[(0, 0), (0, 0)], [(0, 0), (0, 0)]]


@pytest.mark.parametrize('callback_owner', ['same', 'other'])
def test_canonical_translate_rebinding_requires_the_current_context_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, callback_owner: str,
) -> None:
    source = tmp_path / 'translate_owner.tcf'
    source.write_text('Set Code == 0\nSet Code == 1\n', encoding='utf-8')
    model = TCF(source)
    context = BatchContext('-s1 DEV', config=model.config)
    other = BatchContext('-s1 EXG', config=model.config)
    context.translate = MethodType(BatchContext.translate, context if callback_owner == 'same' else other)
    original_append = _ContextAppendRecorder.append
    recorded_inputs = []

    def counted_append(self, inp):
        recorded_inputs.append(inp.uuid)
        return original_append(self, inp)

    monkeypatch.setattr(_ContextAppendRecorder, 'append', counted_append)
    result = model.context(context=context, file_resolution='deferred')
    assert result.inputs._indexes == [(0, 0), (1, 1)]
    assert recorded_inputs == (
        [inp.uuid for inp in result.inputs] if callback_owner == 'same' else []
    )


def test_compiled_command_signature_callback_keeps_prior_uuid_lookups_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The normal command cache invokes the signature callback even for literals."""
    source = tmp_path / 'signature_callback.tcf'
    source.write_text('Set Code == 0\nRead GIS Code == code.shp\n', encoding='utf-8')
    model = TCF(source)
    parents = _capture_context_parents(monkeypatch)
    original_signature = BatchContext.variable_declaration_signature
    original_context = model.context
    runs, signatures = [], []

    def custom_signature(self, names):
        parent = parents[id(self)]
        assert parent.inputs
        parent.inputs[0].uuid = model.inputs[-1].uuid
        signatures.append(names)
        return original_signature(self, names)

    def build_context(*args, **kwargs):
        if not recorder_enabled:
            kwargs['context']._batch_append_indexes_safe = False
        result = original_context(*args, **kwargs)
        runs.append(result)
        return result

    monkeypatch.setattr(BatchContext, 'variable_declaration_signature', custom_signature)
    monkeypatch.setattr(model, 'context', build_context)
    projections = []
    for recorder_enabled in (False, True):
        signatures.clear()
        result = model.collect_batch_dependencies(('-s1 DEV',), compile_tree=False)
        assert result.passed
        assert signatures == [()]
        projections.append(result.runs)
    assert [run.inputs._indexes for run in runs] == [[(0, 0), (0, 0)], [(0, 0), (0, 0)]]
    assert projections[0] == projections[1]


@pytest.mark.parametrize('callback', ['event_variables', 'items'])
def test_event_database_callback_mutation_uses_live_append_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, callback: str,
) -> None:
    source = tmp_path / 'event_callback.tcf'
    source.write_text('Set Code == 0\nSet Code == 1\n', encoding='utf-8')
    model = TCF(source)
    parents = _capture_context_parents(monkeypatch)
    original = getattr(EventDatabase, callback)
    histories, call_counts = [], []
    calls = []

    def custom_callback(self):
        calls.append(self)
        parent = parents.get(id(context))
        if parent is not None and parent.inputs:
            parent.inputs[0].uuid = model.inputs[-1].uuid
        return original(self)

    for recorder_enabled in (False, True):
        context = BatchContext('-s1 DEV', config=model.config)
        if not recorder_enabled:
            context._batch_append_indexes_safe = False
        setattr(context.event_db, callback, MethodType(custom_callback, context.event_db))
        calls.clear()
        result = model.context(context=context, file_resolution='deferred')
        histories.append(result.inputs._indexes)
        call_counts.append(len(calls))
    assert call_counts[0] == call_counts[1] > 0
    assert histories == [[(0, 0), (0, 0)], [(0, 0), (0, 0)]]


def test_canonical_event_database_keeps_append_recorder_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / 'canonical_event.tcf'
    source.write_text('Set Code == 0\nSet Code == ~code~\n', encoding='utf-8')
    model = TCF(source)
    model.config.event_db['RUN'] = {'~code~': '1'}
    context = BatchContext('-e1 RUN', config=model.config)
    original_append = _ContextAppendRecorder.append
    recorded_inputs = []

    def counted_append(self, inp):
        recorded_inputs.append(inp.uuid)
        return original_append(self, inp)

    monkeypatch.setattr(_ContextAppendRecorder, 'append', counted_append)
    result = model.context(context=context, file_resolution='deferred')
    assert [str(inp) for inp in result.inputs] == ['Set Code == 0', 'Set Code == 1']
    assert result.inputs._indexes == [(0, 0), (1, 1)]
    assert recorded_inputs == [inp.uuid for inp in result.inputs]


@pytest.mark.parametrize('namespace_owner', ['context', 'event'])
def test_append_trust_rejects_custom_namespaces_without_invoking_mapping_hooks(
    namespace_owner: str,
) -> None:
    class CustomNamespace(dict):
        def __contains__(self, key):
            raise AssertionError('Trust proof must not invoke custom namespace membership')

        def __getitem__(self, key):
            raise AssertionError('Trust proof must not invoke custom namespace indexing')

        def get(self, key, default=None):
            raise AssertionError('Trust proof must not invoke custom namespace get')

    context = BatchContext('-s1 DEV')
    assert _batch_append_context_is_trusted(context) is True
    owner = context if namespace_owner == 'context' else context.event_db
    original = owner.__dict__
    try:
        owner.__dict__ = CustomNamespace(original)
        assert _batch_append_context_is_trusted(context) is False
    finally:
        owner.__dict__ = original
