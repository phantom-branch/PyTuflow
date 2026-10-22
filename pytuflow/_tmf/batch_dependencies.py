"""Opt-in, read-only batch projection of parsed TUFLOW control-file contexts.

The batch path uses a fresh Context for each distinct run. It caches
immutable references keyed by resolved command and relevant configuration
within a single synchronous batch, never mutable RunState objects. The full
immutable cross-run dependency graph remains future work.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from .compiled_dependency_plan import CompiledVariablePlan
from .context import Context
from .scope import GlobalScope, ScenarioScope
from .tfpathlib import TuflowPath

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .file_reference import DeferredDatabaseActivation, DeferredDatabaseSource, FileReference
    from .scope import ScopeList
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
            # Compile only once per parsed input. Retain the original input
            # identity to prevent an id() collision. The snapshot is scoped
            # to one batch; a new batch rebuilds this graph after model edits.
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
            and (not plan.direct_variables
                 or self.translate(command_text) == command_text)
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


@dataclass(frozen=True, slots=True)
class BatchInputReference:
    """One dependency with stable input identity and owning command position."""

    input_uuid: str
    command_index: int
    owner_control_file: Path | None
    line_number: int
    reference: FileReference


@dataclass(frozen=True, slots=True)
class BatchDependencyRun:
    """One requested context. An error invalidates its entire reference set."""

    index: int
    flags: str
    file_references: tuple[FileReference, ...]
    database_sources: tuple[DeferredDatabaseSource, ...]
    database_activations: tuple[DeferredDatabaseActivation, ...]
    error: str | None = None
    input_references: tuple[BatchInputReference, ...] = ()


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

    @property
    def passed(self) -> bool:
        return bool(self.runs) and all(run.error is None for run in self.runs)


def collect_batch_dependencies(
    model: TCF,
    run_flags: Iterable[str | dict[str, str]],
    *,
    cache_scopes: bool = True,
) -> BatchDependencyResult:
    """Collect **syntactic** dependencies without inspecting physical inputs.

    The caller must still bulk materialise wildcard paths, GIS attributes,
    database/table links and raster metadata, and check every unique input.
    Unsupported or malformed contexts are returned as explicit per-run errors;
    their partial references must never be accepted.
    """
    started = perf_counter()
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
            results.append(BatchDependencyRun(
                index, flag_text, previous.file_references, previous.database_sources,
                previous.database_activations, previous.error,
                previous.input_references,
            ))
            contexts_reused += 1
            continue

        ctx = None
        contexts_constructed += 1
        refs = ()
        sources = ()
        activations = ()
        input_refs = ()
        error = None
        try:
            # Even an invalid flag combination is one failed run, not an
            # uncaught exception that aborts the remaining batch.
            ctx = (BatchContext(flags, config=model.config, variable_inputs=variable_inputs,
                                shared_scope_decisions=shared_scope_decisions)
                   if cache_scopes else Context(flags, config=model.config))
            if isinstance(ctx, BatchContext):
                ctx._shared_file_references = shared_file_references
                ctx._shared_command_templates = shared_command_templates
                ctx._shared_read_plans = shared_read_plans
                ctx._batch_variable_plan = variable_plan
                ctx._batch_run_index = index
                ctx._batch_variable_assignments = variable_assignments
            context_started = perf_counter()
            run = model.context(context=ctx, file_resolution='deferred')
            context_construction_seconds += perf_counter() - context_started
            references_started = perf_counter()
            # Retain input UUID + command order for downstream active-database
            # selection; merely flattening paths would lose provenance.
            input_refs = tuple(
                BatchInputReference(
                    input_uuid=str(inp.uuid),
                    command_index=sequence,
                    owner_control_file=inp._command.parent,
                    line_number=inp.line_number,
                    reference=ref,
                )
                for sequence, inp in enumerate(run.find_input())
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
        except Exception as exc:
            # Fail closed. Never return the partial references accumulated
            # before an unknown database or malformed control-file failure.
            refs = sources = activations = input_refs = ()
            error = f'{type(exc).__name__}: {exc}'
        projected = BatchDependencyRun(
            index, flag_text, refs, sources, activations, error, input_refs,
        )
        results.append(projected)
        if cache_scopes:
            seen_flags[flag_text] = projected
        if isinstance(ctx, BatchContext):
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
        len(shared_read_plans) if shared_read_plans is not None else 0,
        command_plan_hits,
        variable_template_clones,
    )
