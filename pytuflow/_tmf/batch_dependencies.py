"""Opt-in, read-only batch projection of parsed TUFLOW control-file contexts.

The batch path uses a fresh Context for each distinct run. Its compiled tree
identifies independently reusable inputs and the variables and branches that
govern them. Private prototypes supply fresh, independently mutable run states;
immutable dependency projections are shared within this invocation only.
"""

from __future__ import annotations

from collections.abc import Callable, Sized
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import MethodType
from typing import TYPE_CHECKING

from .dependency_records import BatchDependencyRun, BatchInputCommand, BatchInputReference
from .compiled_control_tree import CompiledControlTree
from .compiled_dependency_plan import CompiledVariablePlan
from .group_input_reuse import LiteralInputGroupCache
from .context import Context, _CONTEXT_APPEND_ATTRIBUTES, _CONTEXT_APPEND_MRO
from .event import EventDatabase, _EVENT_DATABASE_APPEND_ATTRIBUTES, _EVENT_DATABASE_APPEND_MRO
from .scope import (
    GlobalScope, ScenarioScope, ScopeList, _SCOPE_APPEND_DEFINITIONS,
    _SCOPE_APPEND_INSTANCE_ATTRIBUTES, _SCOPE_LIST_APPEND_ATTRIBUTES,
)
from .tfpathlib import TuflowPath

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .file_reference import DeferredDatabaseActivation, DeferredDatabaseSource, FileReference
    from .cf.tcf import TCF


class BatchContext(Context):
    """Per-run memoisation for repeated scope checks and variable translation.

    Every context owns its caches. Loading variables, events or new run flags
    invalidates them. During event loading caching is disabled because TEF
    variables may become visible successively while evaluating event scopes.
    """

    def __init__(self, run_flags: str | dict[str, str] = (), *, config=None,
                 variable_inputs=None, shared_scope_decisions=None):
        self._batch_active = False
        # Build-state inputs are immutable during this single synchronous batch.
        # Only their traversal is shared; scopes and values stay per-run.
        self._batch_variable_inputs = variable_inputs
        # Share only decisions depending exclusively on scenario membership.
        # No event, TEF or user-defined variable scopes can enter this cache.
        self._shared_scope_decisions = shared_scope_decisions
        self._shared_file_references = None
        self._shared_command_templates = None
        self._shared_read_plans = None
        self._batch_variable_plan: CompiledVariablePlan | None = None
        self._batch_compiled_tree: CompiledControlTree | None = None
        self._batch_input_group_cache: LiteralInputGroupCache | None = None
        self._batch_pending_input_groups: list[tuple[tuple[object, ...], object, object]] = []
        self.graph_input_state_reuses = 0
        self._batch_input_states_constructed = 0
        self.input_state_construction_seconds = 0.0
        self.graph_node_lookups = 0
        self.graph_node_fallbacks = 0
        self._active_declaration_cache: dict[str, tuple[str, ...]] = {}
        self._batch_run_index: int | None = None
        self.shared_reference_hits = 0
        self.within_run_reference_hits = 0
        self.shared_reference_misses = 0
        self.shared_reference_bypasses = 0
        self.shared_scope_hits = 0
        self.shared_scope_misses = 0
        self._batch_scopes = None
        self._batch_scope_decisions: dict[int, tuple[object, bool]] = {}
        self._batch_translations: dict[str, str] = {}
        self.scope_builds = 0
        self.scope_hits = 0
        self.translation_hits = 0
        self.translation_misses = 0
        self.commands_constructed = 0
        self.commands_cloned = 0
        self.command_template_bypasses = 0
        self.variable_template_clones = 0
        self.command_plan_hits = 0
        super().__init__(run_flags, config=config)
        self._batch_active = True

    def _invalidate(self) -> None:
        self._batch_scopes = None
        self._batch_scope_decisions.clear()
        self._batch_translations.clear()
        self._active_declaration_cache.clear()

    def load_context_from_dict(self, context: dict) -> None:
        was_active = self._batch_active
        self._batch_active = False
        self._invalidate()
        try:
            super().load_context_from_dict(context)
        finally:
            self._invalidate()
            self._batch_active = was_active

    def load_variables(self, var_map) -> None:
        self._invalidate()
        super().load_variables(var_map)
        self._invalidate()

    def load_events(self, event_db) -> None:
        was_active = self._batch_active
        self._batch_active = False
        self._invalidate()
        try:
            super().load_events(event_db)
        finally:
            self._invalidate()
            self._batch_active = was_active

    @property
    def available_scopes(self) -> ScopeList:
        if not self._batch_active:
            return super().available_scopes
        if self._batch_scopes is None:
            self._batch_scopes = super().available_scopes
            self.scope_builds += 1
        else:
            self.scope_hits += 1
        return self._batch_scopes

    def in_context_by_scope(self, req_scope: ScopeList) -> bool:
        if not self._batch_active:
            return super().in_context_by_scope(req_scope)
        # Build-state scope objects are stable throughout one synchronous run.
        # Retain the identity itself to prevent id reuse/collisions.
        cached = self._batch_scope_decisions.get(id(req_scope))
        if cached is not None and cached[0] is req_scope:
            return cached[1]
        shareable = (self._shared_scope_decisions is not None and req_scope
                     and all(isinstance(scope, (ScenarioScope, GlobalScope))
                             for scope in req_scope))
        shared_key = None
        if shareable:
            # TUFLOW tests scenario membership regardless of the flag slot.
            # An event-only change cannot alter a pure scenario decision.
            # Retain the scope object to protect against id reuse.
            shared_key = (id(req_scope), tuple(self._create_list('S')))
            shared = self._shared_scope_decisions.get(shared_key)
            if shared is not None and shared[0] is req_scope:
                self.shared_scope_hits += 1
                self._batch_scope_decisions[id(req_scope)] = (req_scope, shared[1])
                return shared[1]
            self.shared_scope_misses += 1
        active = super().in_context_by_scope(req_scope)
        self._batch_scope_decisions[id(req_scope)] = (req_scope, active)
        if shared_key is not None:
            self._shared_scope_decisions[shared_key] = (req_scope, active)
        return active

    def cached_file_references(self, build_input, materialised_input):
        """Reuse literal immutable references from this batch's parsed TCF.

        Reuse is permitted only for fully resolved, equivalent commands.
        Any uncertain expansion uses PyTUFLOW's existing resolver. The cache
        retains the build-state input to prevent id reuse; no mutable command,
        config or run-state is shared between contexts.
        """
        if not self._batch_active or self._shared_file_references is None:
            return materialised_input.file_references
        rhs = str(build_input.rhs)
        # Construct the signature from the *resolved* command, not from the
        # complete run flags. Unrelated events can then reuse the same input
        # even if an upstream Set Variable produced the path. This requires
        # the same parsed input identity and all settings used by deferred
        # command/path classification. Context-dependent or incompletely
        # expanded commands bypass the cache rather than sharing partial work.
        from .parsers.command import Command

        cmd = materialised_input.command()
        resolved = self.translate(rhs)
        if (not rhs or '~' in rhs or type(cmd) is not Command
                or cmd.define_blocks or not isinstance(resolved, str)
                or '<<' in resolved or '>>' in resolved
                or '<<' in str(cmd.value) or '~' in str(cmd.value)
                or self.translate(str(cmd.value)) != str(cmd.value)):
            self.shared_reference_bypasses += 1
            return materialised_input.file_references

        config = cmd.config
        key = (
            id(build_input), cmd.original_text, str(cmd.value),
            str(cmd.parent), cmd.part_index, cmd.part_count,
            str(config.control_file), str(config.root_folder),
            str(config.spatial_database), str(config.gis_format),
            str(config.grid_format), tuple(map(str, config.wildcards)),
        )
        cached = self._shared_file_references.get(key)
        if cached is not None and cached[0] is build_input:
            if cached[2] == self._batch_run_index:
                self.within_run_reference_hits += 1
            else:
                self.shared_reference_hits += 1
            return cached[1]
        refs = materialised_input.file_references
        if not refs:
            # Set Variable, output and other non-source commands have no
            # physical input references; do not count or store empty entries.
            return refs
        if len(self._shared_file_references) >= 10_000:
            # Bound memory growth for exceptionally large or highly dynamic
            # batches. Correctness takes precedence over cache retention.
            self.shared_reference_bypasses += 1
            return refs
        self._shared_file_references[key] = (
            build_input, refs, self._batch_run_index,
        )
        self.shared_reference_misses += 1
        return refs

    def variable_declaration_signature(self, names: tuple[str, ...]):
        """Identify active, *ordered* declarations feeding a reusable READ.

        Matching final values alone does not prove equivalent variable
        provenance when several scoped Set Variable commands can win.  Keep
        the identity of every active declaration, in build traversal order.
        """
        assignments = getattr(self, '_batch_variable_assignments', None)
        if not assignments or not names:
            return ()
        required = frozenset(names)
        missing = required.difference(self._active_declaration_cache)
        if missing:
            found = {name: [] for name in missing}
            for inp, (name, _) in assignments:
                key = str(name).upper()
                if key in found and self.in_context_by_scope(inp.scope):
                    found[key].append(str(inp.uuid))
            self._active_declaration_cache.update(
                (name, tuple(values)) for name, values in found.items()
            )
        return tuple((name, self._active_declaration_cache[name]) for name in sorted(required))

    def batch_command(self, build_input, source_command, command_text, run_config):
        """Produce an independent command, avoiding repeated safe literal parsing.

        Only plain GIS/GRID READ commands with literal RHS and no DEFINE/event
        constructs may use this optimisation. Per-run mutable command/config/
        expander objects are *never* shared; the cached prototype is not
        returned to callers. Other inputs retain the normal constructor.
        """
        from .parsers.command import Command
        from .settings import from_config

        eligible_read = (
            self._batch_active
            and self._shared_command_templates is not None
            and self._shared_read_plans is not None
            and self._batch_variable_plan is not None
            and type(source_command) is Command
            and source_command.command is not None
            and source_command.command.startswith(('READ GIS ', 'READ GRID '))
            and not source_command.define_blocks
            and bool(source_command.value_orig)
        )
        plan = None
        if eligible_read:
            # The compiled tree is an immutable snapshot of ALL parsed inputs,
            # including inactive branches.  Validate source identity/text
            # before using its precompiled transitive READ dependencies.
            if self._batch_compiled_tree is not None:
                node = self._batch_compiled_tree.node_for(build_input)
                if node is not None and node.original_text == source_command.original_text:
                    self.graph_node_lookups += 1
                    if node.role == 'READ':
                        # The original compiled_read_nodes metric counts
                        # plans *encountered by active runs*, including
                        # conservative bypasses.  Precompiling inactive
                        # branches must not inflate that counter; separate
                        # compiled_graph_* fields describe the whole tree.
                        key = id(build_input)
                        saved = self._shared_read_plans.get(key)
                        if saved is None or saved[0] is not build_input:
                            if len(self._shared_read_plans) < 10_000:
                                self._shared_read_plans[key] = (
                                    build_input, str(source_command.value_orig),
                                    node.read_dependency,
                                )
                        if node.bypass_reason is None:
                            plan = node.read_dependency
                            self.command_plan_hits += 1
                else:
                    # In-batch model mutation or unindexed inputs must use
                    # the original constructor and resolver, never stale data.
                    self.graph_node_fallbacks += 1
            else:
                # Compatibility with standalone BatchContext use (no tree).
                raw_expression = str(source_command.value_orig)
                key = id(build_input)
                saved = self._shared_read_plans.get(key)
                if saved is not None and saved[0] is build_input and saved[1] == raw_expression:
                    plan = saved[2]
                    self.command_plan_hits += 1
                else:
                    plan = self._batch_variable_plan.compile_read(raw_expression)
                    if key in self._shared_read_plans or len(self._shared_read_plans) < 10_000:
                        self._shared_read_plans[key] = (build_input, raw_expression, plan)

        # The existing context resolver remains authoritative. We never
        # reuse an expression with unresolved tokens, special layer syntax,
        # or a context-dependent second expansion. A relevant-variable
        # signature also distinguishes different transitive assignments even
        # when unrelated event flags vary.
        relevant_values = ()
        if plan is not None and plan.reusable and plan.relevant_variables:
            if all(
                isinstance(self.var_map.get(name), str)
                for name in plan.relevant_variables
            ):
                relevant_values = tuple(
                    (name, self.var_map[name]) for name in plan.relevant_variables
                )
            else:
                plan = None
        eligible = (
            plan is not None and plan.reusable
            and '<<' not in command_text
            and '>>' not in command_text
            and '~' not in command_text
            # A TEF replacement can expose another event token even when
            # there are no <<variables>> in the original READ. The command
            # constructor performs a further translation; copying a cached
            # prototype before that translation would retain the previous
            # event's expanded path. Require a stable second pass for *all*
            # templates, not only those with direct variables.
            and self.translate(command_text) == command_text
        )
        if eligible:
            # The same parsed input provides a frozen configuration snapshot
            # for each batch. Include all settings used by path classification,
            # not just the run flags; preserve the original input identity.
            signature = (
                id(build_input),
                command_text,
                str(source_command.parent),
                source_command.part_index,
                source_command.line_number,
                str(run_config.control_file),
                str(run_config.spatial_database),
                str(run_config.root_folder),
                str(run_config.gis_format),
                str(run_config.grid_format),
                tuple(map(str, run_config.wildcards)),
                relevant_values,
                self.variable_declaration_signature(plan.relevant_variables),
            )
            entry = self._shared_command_templates.get(signature)
            if entry is not None and entry[0] is build_input:
                prototype = entry[1]
                fresh = copy(prototype)
                fresh.config = from_config(run_config)
                fresh._define_blocks = []
                # The cached expander holds its last expansion. Give each
                # run an independent copy, rebound to its own settings.
                fresh._expander = copy(prototype._expander)
                fresh._expander.variables = fresh.config.variables
                fresh._expander.database = fresh.config.spatial_database
                self.commands_cloned += 1
                if plan.direct_variables:
                    self.variable_template_clones += 1
                return fresh

        from .parsers.command import EventCommand
        if isinstance(source_command, EventCommand):
            command = EventCommand(
                command_text, run_config, source_command.parent, source_command.part_index,
            )
            command.event_name = source_command.event_name
        else:
            command = source_command.__class__(
                command_text, run_config, source_command.parent,
                source_command.part_index, source_command.line_number,
            )
        self.commands_constructed += 1
        if eligible:
            if len(self._shared_command_templates) < 10_000:
                # Do not retain the first run's mutable command or the bound
                # Context.translate method. Keep a neutral private prototype
                # which cannot be changed through any returned RunState.
                prototype = copy(command)
                prototype.config = from_config(command.config)
                prototype.config.variables = {}
                prototype._expander = copy(command._expander)
                prototype._expander.variables = {}
                self._shared_command_templates[signature] = (build_input, prototype)
            else:
                self.command_template_bypasses += 1
        else:
            self.command_template_bypasses += 1
        return command

    def batch_input_state(self, build_input, parent):
        """Return a fresh state; skip construction only for a certified group."""
        cache = self._batch_input_group_cache if self._batch_active else None
        if cache is not None:
            reused, key = cache.try_reuse(build_input, self, parent)
            if reused is not None:
                self.graph_input_state_reuses += 1
                return reused
        else:
            key = None
        # Count constructor attempts here, including those that raise.
        self._batch_input_states_constructed += 1
        construction_started = perf_counter()
        try:
            state = build_input.context(context=self, parent=parent)
        finally:
            self.input_state_construction_seconds += perf_counter() - construction_started
        if key is not None and cache.prepare_seed(state):
            self._batch_pending_input_groups.append((key, build_input, state))
        return state

    def commit_input_groups(self) -> None:
        """Publish templates only after the *entire* run has passed."""
        if self._batch_input_group_cache is not None:
            self._batch_input_group_cache.commit(self._batch_pending_input_groups)
        self._batch_pending_input_groups.clear()

    def translate(self, item):
        if not self._batch_active or not isinstance(item, (str, TuflowPath)):
            return super().translate(item)
        key = str(item)
        if key in self._batch_translations:
            self.translation_hits += 1
            return self._batch_translations[key]
        translated = super().translate(item)
        self.translation_misses += 1
        self._batch_translations[key] = translated
        return translated


# Retain the entire raw callback surface, including the inherited methods
# invoked through super(). New/replaced class descriptors are unsupported too.
_BATCH_CONTEXT_APPEND_ATTRIBUTES = tuple(BatchContext.__dict__.items())
_BATCH_CONTEXT_APPEND_MRO = BatchContext.__mro__
_APPEND_CONTEXT_INSTANCE_ATTRIBUTES = tuple({
    **dict(_CONTEXT_APPEND_ATTRIBUTES),
    **dict(_BATCH_CONTEXT_APPEND_ATTRIBUTES),
}.items())


def _raw_class_attribute(cls: type, name: str):
    """Return an unbound class attribute without executing any descriptor."""
    for owner in type.__getattribute__(cls, '__mro__'):
        namespace = type.__getattribute__(owner, '__dict__')
        if name in namespace:
            return namespace[name]
    return None


def _original_instance_callbacks(instance, namespace: dict, originals) -> bool:
    # An assigned dict subclass can override even membership/index lookup.
    # Custom keys can also execute equality hooks during a plain lookup.
    # Inspect only ordinary storage so proving dispatch cannot run callbacks.
    if type(namespace) is not dict or any(type(key) is not str for key in namespace):
        return False
    for name, original in originals:
        if name not in namespace:
            continue
        replacement = namespace[name]
        if (type(replacement) is not MethodType
                or replacement.__func__ is not original
                or replacement.__self__ is not instance):
            return False
    return True


def _batch_append_context_is_trusted(context) -> bool:
    """Prove context dispatch is built in before retaining UUID positions.

    Scope selection, translation, command/reference creation and resolution
    all dispatch through this context. A custom callback anywhere in that
    chain can edit previous parent inputs. Inspect raw dictionaries only;
    proving a property or a constructor must never execute it an extra time.
    """
    if type(context) is not BatchContext:
        return False
    for cls, mro, originals in (
        (Context, _CONTEXT_APPEND_MRO, _CONTEXT_APPEND_ATTRIBUTES),
        (BatchContext, _BATCH_CONTEXT_APPEND_MRO, _BATCH_CONTEXT_APPEND_ATTRIBUTES),
        *_SCOPE_APPEND_DEFINITIONS,
    ):
        namespace = type.__getattribute__(cls, '__dict__')
        if (type.__getattribute__(cls, '__mro__') != mro
                or len(namespace) != len(originals)
                or any(name not in namespace or namespace[name] is not original
                       for name, original in originals)):
            return False
    namespace = object.__getattribute__(context, '__dict__')
    if not _original_instance_callbacks(context, namespace, _APPEND_CONTEXT_INSTANCE_ATTRIBUTES):
        return False
    # Do not retrieve context.event_db: an extension could make it a property.
    # The unchanged class surface above proves this raw instance slot is used.
    event_db = namespace.get('event_db')
    if (type(event_db) is not EventDatabase
            or type.__getattribute__(EventDatabase, '__mro__') != _EVENT_DATABASE_APPEND_MRO
            or any(_raw_class_attribute(EventDatabase, name) is not original
                   for name, original in _EVENT_DATABASE_APPEND_ATTRIBUTES)):
        return False
    event_namespace = object.__getattribute__(event_db, '__dict__')
    return _original_instance_callbacks(event_db, event_namespace, _EVENT_DATABASE_APPEND_ATTRIBUTES)


def _batch_append_scope_is_trusted(scopes) -> bool:
    """Inspect scope data after the context proof checked raw class definitions.

    Public setters preserve ScopeList/Scope subclasses and their callbacks.
    Do not invoke membership, iteration overrides, getters or comparisons to
    decide whether those objects are safe for the private append recorder.
    """
    if scopes is None:
        return True
    if type(scopes) is not ScopeList:
        return False
    namespace = object.__getattribute__(scopes, '__dict__')
    if not _original_instance_callbacks(scopes, namespace, _SCOPE_LIST_APPEND_ATTRIBUTES):
        return False
    for scope in list.__iter__(scopes):
        originals = next((attributes for cls, attributes in _SCOPE_APPEND_INSTANCE_ATTRIBUTES
                          if type(scope) is cls), None)
        if originals is None:
            return False
        namespace = object.__getattribute__(scope, '__dict__')
        if not _original_instance_callbacks(scope, namespace, originals):
            return False
        names = namespace.get('names')
        if (type(names) is not list
                or any(type(name) is not str for name in names)
                or type(namespace.get('type')) is not str
                or (namespace.get('var') is not None and type(namespace['var']) is not str)
                or any(type(namespace.get(flag)) is not bool
                       for flag in ('known', '_neg', '_else'))):
            return False
    return True


def _batch_append_input_scope_is_trusted(inp, known_input_types) -> bool:
    """Prove the normal scope getter will read the inspected raw instance slot."""
    from .abc.bld_state import BuildState, _BUILD_STATE_SCOPE, _BUILD_STATE_DICTIONARY
    from .inp.inp_build_state import _INPUT_BUILD_SCOPE

    cls = type(inp)
    if not any(cls is known_type for known_type in known_input_types):
        return False
    if (_raw_class_attribute(cls, 'scope') is not _INPUT_BUILD_SCOPE
            or type.__getattribute__(BuildState, '__dict__').get('scope') is not _BUILD_STATE_SCOPE
            or _raw_class_attribute(cls, '__getattribute__') is not object.__getattribute__
            or _raw_class_attribute(cls, '__getattr__') is not None
            or _raw_class_attribute(cls, '__dict__') is not _BUILD_STATE_DICTIONARY
            or _raw_class_attribute(cls, '_scope') is not None):
        return False
    namespace = object.__getattribute__(inp, '__dict__')
    return (type(namespace) is dict and all(type(key) is str for key in namespace)
            and '_scope' in namespace
            and _batch_append_scope_is_trusted(namespace['_scope']))


def _plain_scope_value(value) -> bool:
    return type(value) is str or (
        type(value) is list and all(type(item) is str for item in value)
    )


def _batch_append_scope_sources_are_trusted(namespace: dict, known_input_types) -> bool:
    """Check stable scope-producing data once before a fresh recorder exists.

    Context flags and variable/event maps build available scopes. Public event
    entries also participate in resolution through nested items(). Compiled
    READs may also inspect other declarations' scopes while constructing an
    input. Validate those sources once, without evaluating any scope, under
    the batch's existing stable-source contract.
    """
    for prefix in ('S', 'E'):
        for slot in (prefix, *(f'{prefix}{i}' for i in range(1, 10))):
            if slot in namespace and not _plain_scope_value(namespace[slot]):
                return False
    for attribute in ('var_map', 'event_variables'):
        values = namespace.get(attribute)
        if (type(values) is not dict
                or any(type(key) is not str or not _plain_scope_value(value)
                       for key, value in values.items())):
            return False
    # Canonical event_variables() calls each public event entry's items().
    # Bypass virtual access while proving those nested mappings and values.
    for name, values in dict.items(namespace['event_db']):
        if (type(name) is not str or type(values) is not dict
                or any(type(key) is not str or not _plain_scope_value(value)
                       for key, value in values.items())):
            return False
    if not _batch_append_scope_is_trusted(namespace.get('_batch_scopes')):
        return False
    assignments = namespace.get('_batch_variable_assignments')
    if assignments is None:
        return True
    if type(assignments) is not tuple:
        return False
    for assignment in assignments:
        if type(assignment) is not tuple or len(assignment) != 2:
            return False
        inp, declaration = assignment
        if (type(declaration) is not tuple or len(declaration) != 2
                or any(type(value) is not str for value in declaration)
                or not _batch_append_input_scope_is_trusted(inp, known_input_types)):
            return False
    return True


@dataclass(frozen=True, slots=True)
class BatchDependencyResult:
    """All runs and explicit timings/counters for a single already-parsed TCF."""

    runs: tuple[BatchDependencyRun, ...]
    elapsed_seconds: float
    scope_builds: int
    scope_hits: int
    translation_hits: int
    translation_misses: int
    contexts_constructed: int
    contexts_reused: int
    cross_run_reference_hits: int
    cross_run_reference_misses: int
    cross_run_scope_hits: int
    cross_run_scope_misses: int
    cross_run_reference_bypasses: int = 0
    unique_reference_signatures: int = 0
    within_run_reference_hits: int = 0
    commands_constructed: int = 0
    compilation_seconds: float = 0.0
    context_construction_seconds: float = 0.0
    reference_collection_seconds: float = 0.0
    database_projection_seconds: float = 0.0
    commands_cloned: int = 0
    command_template_bypasses: int = 0
    unique_command_templates: int = 0
    compiled_variable_nodes: int = 0
    compiled_read_nodes: int = 0
    command_plan_hits: int = 0
    variable_template_clones: int = 0
    compiled_graph_nodes: int = 0
    compiled_graph_eligible_reads: int = 0
    compiled_graph_bypassed_reads: int = 0
    graph_node_lookups: int = 0
    graph_node_fallbacks: int = 0
    input_runstates_elided: int = 0
    input_runstates_constructed: int = 0
    invariant_projection_reuses: int = 0
    reusable_input_groups: int = 0
    input_group_fallbacks: tuple[tuple[str, int], ...] = ()
    compiled_input_group_candidates: int = 0
    input_group_bypass_reasons: tuple[tuple[str, int], ...] = ()
    input_group_cache_bypass_reason: str | None = None
    input_group_state_reuses: int = 0
    failed_run_input_runstates_constructed: int = 0
    failed_run_input_runstates_elided: int = 0
    input_group_key_seconds: float = 0.0
    input_group_clone_seconds: float = 0.0
    input_group_certification_seconds: float = 0.0
    input_state_construction_seconds: float | None = None

    @property
    def passed(self) -> bool:
        return bool(self.runs) and all(run.error is None for run in self.runs)


def collect_batch_dependencies(
    model: TCF,
    run_flags: Iterable[str | dict[str, str]],
    *,
    cache_scopes: bool = True,
    compile_tree: bool = True,
    on_run: Callable[[BatchDependencyRun], None] | None = None,
) -> BatchDependencyResult:
    """Collect **syntactic** dependencies without inspecting physical inputs.

    The caller must still bulk materialise wildcard paths, GIS attributes,
    database/table links and raster metadata, and check every unique input.
    Unsupported or malformed contexts are returned as explicit per-run errors;
    their partial references must never be accepted. The optional on_run
    callback receives each COMPLETE immutable per-run projection in order,
    after the run is recorded and before the next run starts. It is intended
    for bounded, read-only consumers; callback exceptions propagate and abort
    the batch rather than being disguised as parser errors. The callback must
    not modify parsed model inputs or shared batch state. With compile_tree=False,
    the original per-batch caches remain on, isolating the graph's contribution.
    """
    started = perf_counter()
    # Cross-context prototypes can reuse a literal source filename under the
    # original translation semantics. A custom Context.translate hook may
    # change that filename with run flags absent from its compiled variables.
    # Do not certify or share projections when translation is overridden.
    # Keep ordinary per-run Context evaluation as the authoritative fallback.
    if cache_scopes and Context.translate is not dict(_CONTEXT_APPEND_ATTRIBUTES)["translate"]:
        cache_scopes = False
    # Do not consume or look ahead in generators: callers can stream flags
    # after examining an earlier projection. Only use an advertised length.
    requested_count = len(run_flags) if isinstance(run_flags, Sized) else None
    if requested_count == 0:
        raise ValueError('At least one simulation context is required')
    results: list[BatchDependencyRun] = []
    seen_flags: dict[str, BatchDependencyRun] = {}
    contexts_constructed = contexts_reused = 0
    scope_builds = scope_hits = translation_hits = translation_misses = 0
    cross_run_scope_hits = cross_run_scope_misses = 0
    cross_run_reference_hits = cross_run_reference_misses = 0
    cross_run_reference_bypasses = 0
    within_run_reference_hits = 0
    commands_constructed = 0
    commands_cloned = 0
    command_template_bypasses = 0
    command_plan_hits = 0
    variable_template_clones = 0
    graph_node_lookups = 0
    graph_node_fallbacks = 0
    input_runstates_constructed = input_runstates_elided = 0
    input_group_state_reuses = 0
    failed_run_input_runstates_constructed = 0
    failed_run_input_runstates_elided = 0
    input_state_construction_seconds = 0.0
    invariant_projection_reuses = 0
    invariant_projection: BatchDependencyRun | None = None
    scenario_projections: dict[tuple[str, ...], BatchDependencyRun] = {}
    context_construction_seconds = 0.0
    reference_collection_seconds = 0.0
    database_projection_seconds = 0.0
    shared_scope_decisions = {} if cache_scopes else None
    shared_file_references = {} if cache_scopes else None
    shared_command_templates = {} if cache_scopes else None
    shared_read_plans = {} if cache_scopes else None
    # Control-file traversal to locate Set Variable declarations was previously
    # repeated for every run. The parsed input objects and their scopes are
    # shared; active-variable values are still computed independently per run.
    variable_inputs = tuple(model.find_input(lhs='set variable', recursive=True)) if cache_scopes else None
    # parse_variable() reads the original, parsed build-state command, not
    # per-run substitutions. Compile the immutable name/value templates once
    # and continue applying scenario scope checks for every individual run.
    variable_assignments = None
    if variable_inputs is not None:
        try:
            variable_assignments = tuple(
                (inp, inp.command().parse_variable()) for inp in variable_inputs
            )
        except Exception:
            # Keep the original per-context failure semantics for malformed
            # declarations instead of failing the entire batch up front.
            variable_assignments = None

    variable_plan = CompiledVariablePlan.from_assignments(variable_assignments) if cache_scopes else None
    # Same-revision P3 differential baseline: opt out of the graph only,
    # retaining all pre-existing per-batch scope/reference/command caches.
    # Uncached mode remains cache_scopes=False, regardless of compile_tree.
    compiled_tree = (CompiledControlTree.compile(model, variable_plan)
                     if compile_tree and variable_plan is not None else None)
    # Only completely literal, scope-free, variable-free, BC-free leaf READs
    # are certified equivalent across *distinct* flags. Never infer a
    # shortcut from identical FileReference outputs of partial evaluations.
    can_reuse_invariant_projection = (
        compiled_tree is not None and compiled_tree.is_invariant_literal_model(model)
    )
    # A scenario-only READ tree can be reused for different events, but only
    # when the complete selected scenario-slot sequence matches exactly.
    can_reuse_scenario_projection = (
        compiled_tree is not None
        and not can_reuse_invariant_projection
        and compiled_tree.is_scenario_literal_model(model)
    )
    # Compilation remains visible even when there is no useful group cache.
    # In particular a one-run public model must not clone private prototypes
    # which can never be used. Unknown-length iterators stay fully streaming.
    input_group_cache_bypass_reason = None
    if compiled_tree is None:
        input_group_cache_bypass_reason = 'graph-disabled'
    elif compiled_tree.reusable_input_group_nodes == 0:
        input_group_cache_bypass_reason = 'no-candidates'
    elif requested_count == 1:
        input_group_cache_bypass_reason = 'single-run'
    elif can_reuse_invariant_projection:
        input_group_cache_bypass_reason = 'whole-model-projection'
    input_groups = (LiteralInputGroupCache(compiled_tree)
                    if input_group_cache_bypass_reason is None else None)
    compilation_seconds = perf_counter() - started

    for index, flags in enumerate(run_flags):
        flag_text = flags if isinstance(flags, str) else ' '.join(
            f'-{key.lstrip("-")} {value}' for key, value in flags.items()
        )
        if cache_scopes and flag_text in seen_flags:
            # Identical *complete* flags have the same immutable dependency
            # projection within this one read-only batch. Keep their individual
            # run indices; never merge results for merely similar flag sets.
            previous = seen_flags[flag_text]
            projected = BatchDependencyRun(
                index, flag_text, previous.file_references, previous.database_sources,
                previous.database_activations, previous.error,
                previous.input_references,
                previous.ordered_inputs,
            )
            results.append(projected)
            contexts_reused += 1
            if on_run is not None:
                on_run(projected)
            continue

        ctx = None
        contexts_constructed += 1
        refs = ()
        sources = ()
        activations = ()
        input_refs = ()
        ordered_inputs = ()
        error = None
        reused_projection: BatchDependencyRun | None = None
        try:
            # Even an invalid flag combination is one failed run, not an
            # uncaught exception that aborts the remaining batch.
            ctx = (BatchContext(flags, config=model.config, variable_inputs=variable_inputs,
                                shared_scope_decisions=shared_scope_decisions)
                   if cache_scopes else Context(flags, config=model.config))
            # Count attempts on the uncached differential as well. Ordinary
            # standalone eager/deferred contexts have no instrumentation.
            if not isinstance(ctx, BatchContext):
                ctx._batch_input_states_constructed = 0
            if isinstance(ctx, BatchContext):
                ctx._shared_file_references = shared_file_references
                ctx._shared_command_templates = shared_command_templates
                ctx._shared_read_plans = shared_read_plans
                ctx._batch_variable_plan = variable_plan
                ctx._batch_compiled_tree = compiled_tree
                ctx._batch_input_group_cache = input_groups
                ctx._batch_run_index = index
                ctx._batch_variable_assignments = variable_assignments
            scenario_key = None
            if can_reuse_scenario_projection:
                selected = ctx._create_list('S')
                if all(isinstance(value, str) for value in selected):
                    # Context evaluation is case-insensitive for scenario
                    # membership. Preserve slot ordering conservatively;
                    # event differences are irrelevant to scenario-only READs.
                    scenario_key = tuple(value.casefold() for value in selected)
            prior = (invariant_projection if can_reuse_invariant_projection
                     else scenario_projections.get(scenario_key)
                     if scenario_key is not None else None)
            if prior is not None:
                # Context has already validated this run's flags. Reuse only
                # a fully successful immutable projection of the same proven
                # scenario signature; no mutable RunState crosses runs.
                projected = BatchDependencyRun(
                    index, flag_text, prior.file_references,
                    prior.database_sources, prior.database_activations,
                    None, prior.input_references, prior.ordered_inputs,
                )
                results.append(projected)
                if cache_scopes:
                    seen_flags[flag_text] = projected
                invariant_projection_reuses += 1
                input_runstates_elided += len(projected.ordered_inputs)
                reused_projection = projected
            else:
                context_started = perf_counter()
                try:
                    run = model.context(context=ctx, file_resolution='deferred')
                finally:
                    # Failed runs can have performed substantial construction.
                    context_construction_seconds += perf_counter() - context_started
                references_started = perf_counter()
                # Retain input UUID + command order for downstream active-database
                # selection; merely flattening paths would lose provenance.
                # Traverse active commands once for ordered ownership. In
                # particular, commands without FileReference must not disappear:
                # consumers need the original ordinals for database activation.
                active_inputs = tuple(run.find_input())
                # Count attempts on both successful and failed contexts below.
                ordered_inputs = tuple(
                    BatchInputCommand(
                        input_uuid=str(inp.uuid),
                        command_index=sequence,
                        owner_control_file=inp._command.parent,
                        line_number=inp.line_number,
                        command_name=str(inp.lhs),
                        command_text=str(inp._command.original_text),
                        reference_count=len(inp.file_references),
                    )
                    for sequence, inp in enumerate(active_inputs)
                )
                input_refs = tuple(
                    BatchInputReference(
                        input_uuid=descriptor.input_uuid,
                        command_index=descriptor.command_index,
                        owner_control_file=descriptor.owner_control_file,
                        line_number=descriptor.line_number,
                        reference=ref,
                    )
                    for descriptor, inp in zip(ordered_inputs, active_inputs, strict=True)
                    for ref in inp.file_references
                )
                refs = tuple(item.reference for item in input_refs)
                reference_collection_seconds += perf_counter() - references_started
                database_started = perf_counter()
                activations = run.deferred_database_activations()
                # Keep rows attached to the exact declaration UUID. The consumer
                # selects the database active at each boundary/GIS command; simply
                # unioning BC rows would produce false secondary dependencies.
                sources = tuple(
                    source
                    for activation in activations
                    for source in run.deferred_database_sources_for_activation(activation.input_uuid)
                )
                database_projection_seconds += perf_counter() - database_started
                # Do not let a failed/partial projection seed a reusable group.
                if isinstance(ctx, BatchContext):
                    ctx.commit_input_groups()
        except Exception as exc:
            # Fail closed. Never return the partial references accumulated
            # before an unknown database or malformed control-file failure.
            refs = sources = activations = input_refs = ordered_inputs = ()
            error = f'{type(exc).__name__}: {exc}'
        # Reuse callbacks must execute outside the parser exception handler:
        # consumer errors are not parser failures or extra projected runs.
        if reused_projection is not None:
            if on_run is not None:
                on_run(reused_projection)
            continue
        projected = BatchDependencyRun(
            index, flag_text, refs, sources, activations, error, input_refs,
            ordered_inputs,
        )
        results.append(projected)
        if cache_scopes:
            seen_flags[flag_text] = projected
        if error is None:
            if can_reuse_invariant_projection and invariant_projection is None:
                # A failed first run must never certify a reusable projection.
                invariant_projection = projected
            elif (can_reuse_scenario_projection and scenario_key is not None
                  and scenario_key not in scenario_projections
                  and len(scenario_projections) < 10_000):
                scenario_projections[scenario_key] = projected
        if ctx is not None:
            input_runstates_constructed += ctx._batch_input_states_constructed
            if error is not None:
                failed_run_input_runstates_constructed += ctx._batch_input_states_constructed
        if isinstance(ctx, BatchContext):
            input_state_construction_seconds += ctx.input_state_construction_seconds
            input_runstates_elided += ctx.graph_input_state_reuses
            input_group_state_reuses += ctx.graph_input_state_reuses
            if error is not None:
                failed_run_input_runstates_elided += ctx.graph_input_state_reuses
            scope_builds += ctx.scope_builds
            scope_hits += ctx.scope_hits
            translation_hits += ctx.translation_hits
            translation_misses += ctx.translation_misses
            cross_run_scope_hits += ctx.shared_scope_hits
            cross_run_scope_misses += ctx.shared_scope_misses
            cross_run_reference_hits += ctx.shared_reference_hits
            cross_run_reference_misses += ctx.shared_reference_misses
            cross_run_reference_bypasses += ctx.shared_reference_bypasses
            within_run_reference_hits += ctx.within_run_reference_hits
            commands_constructed += ctx.commands_constructed
            commands_cloned += ctx.commands_cloned
            command_template_bypasses += ctx.command_template_bypasses
            command_plan_hits += ctx.command_plan_hits
            variable_template_clones += ctx.variable_template_clones
            graph_node_lookups += ctx.graph_node_lookups
            graph_node_fallbacks += ctx.graph_node_fallbacks
        if on_run is not None:
            on_run(projected)

    if not results:
        raise ValueError('At least one simulation context is required')
    return BatchDependencyResult(
        tuple(results), perf_counter() - started,
        scope_builds, scope_hits, translation_hits, translation_misses,
        contexts_constructed, contexts_reused,
        cross_run_reference_hits, cross_run_reference_misses,
        cross_run_scope_hits, cross_run_scope_misses,
        cross_run_reference_bypasses,
        len(shared_file_references) if shared_file_references is not None else 0,
        within_run_reference_hits,
        commands_constructed,
        compilation_seconds,
        context_construction_seconds,
        reference_collection_seconds,
        database_projection_seconds,
        commands_cloned,
        command_template_bypasses,
        len(shared_command_templates) if shared_command_templates is not None else 0,
        len(variable_plan.dependencies) if variable_plan is not None else 0,
        # Same semantics with or without precompilation: unique READ plans
        # encountered by evaluated (active) commands, not every graph node.
        len(shared_read_plans) if shared_read_plans is not None else 0,
        command_plan_hits,
        variable_template_clones,
        compiled_graph_nodes=len(compiled_tree.nodes) if compiled_tree is not None else 0,
        compiled_graph_eligible_reads=compiled_tree.eligible_read_nodes if compiled_tree is not None else 0,
        compiled_graph_bypassed_reads=compiled_tree.bypassed_read_nodes if compiled_tree is not None else 0,
        graph_node_lookups=graph_node_lookups,
        graph_node_fallbacks=graph_node_fallbacks,
        input_runstates_elided=input_runstates_elided,
        input_runstates_constructed=input_runstates_constructed,
        invariant_projection_reuses=invariant_projection_reuses,
        reusable_input_groups=input_groups.unique_groups if input_groups is not None else 0,
        input_group_fallbacks=(tuple(sorted(input_groups.fallback_counts.items()))
                               if input_groups is not None else ()),
        compiled_input_group_candidates=(compiled_tree.reusable_input_group_nodes
                                         if compiled_tree is not None else 0),
        input_group_bypass_reasons=(compiled_tree.input_group_bypass_reasons
                                   if compiled_tree is not None else ()),
        input_group_cache_bypass_reason=input_group_cache_bypass_reason,
        input_group_state_reuses=input_group_state_reuses,
        failed_run_input_runstates_constructed=failed_run_input_runstates_constructed,
        failed_run_input_runstates_elided=failed_run_input_runstates_elided,
        # Diagnostic costs overlap other phases; certification happens after
        # database projection. Do not add these to elapsed time or sum them
        # with the top-level phases as independent end-to-end costs.
        input_group_key_seconds=input_groups.key_seconds if input_groups is not None else 0.0,
        input_group_clone_seconds=input_groups.clone_seconds if input_groups is not None else 0.0,
        input_group_certification_seconds=(input_groups.certification_seconds
                                           if input_groups is not None else 0.0),
        input_state_construction_seconds=(input_state_construction_seconds
                                          if cache_scopes else None),
    )
