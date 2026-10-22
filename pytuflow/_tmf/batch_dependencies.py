"""Opt-in, read-only batch projection of parsed TUFLOW control-file contexts.

The batch path uses a fresh Context for every run. It caches only within a
single run, never mutable RunState objects or results from another run. This
is the conservative first stage of batch optimisation; future dependency-plan
compilation can replace the individual contexts after full parity validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING

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
        self.shared_reference_hits = 0
        self.shared_reference_misses = 0
        self.shared_scope_hits = 0
        self.shared_scope_misses = 0
        self._batch_scopes = None
        self._batch_scope_decisions: dict[int, tuple[object, bool]] = {}
        self._batch_translations: dict[str, str] = {}
        self.scope_builds = 0
        self.scope_hits = 0
        self.translation_hits = 0
        self.translation_misses = 0
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

        A context-dependent command must use PyTUFLOW's existing resolver.
        The cache holds the original build-state input to prevent id reuse.
        No mutable command, config or run-state is shared between contexts.
        """
        if not self._batch_active or self._shared_file_references is None:
            return materialised_input.file_references
        rhs = str(build_input.rhs)
        # The tilde and variable forms include TEF/event wildcards. Avoid
        # guessing how they resolve; the standard resolver remains authoritative.
        if not rhs or '<<' in rhs or '~' in rhs or self.translate(rhs) != rhs:
            return materialised_input.file_references
        key = (id(build_input), rhs)
        cached = self._shared_file_references.get(key)
        if cached is not None and cached[0] is build_input:
            self.shared_reference_hits += 1
            return cached[1]
        refs = materialised_input.file_references
        self._shared_file_references[key] = (build_input, refs)
        self.shared_reference_misses += 1
        return refs

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
class BatchDependencyRun:
    """One requested context. An error invalidates its entire reference set."""

    index: int
    flags: str
    file_references: tuple[FileReference, ...]
    database_sources: tuple[DeferredDatabaseSource, ...]
    database_activations: tuple[DeferredDatabaseActivation, ...]
    error: str | None = None


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
    shared_scope_decisions = {} if cache_scopes else None
    shared_file_references = {} if cache_scopes else None
    # Control-file traversal to locate Set Variable declarations was previously
    # repeated for every run. The parsed input objects and their scopes are
    # shared; active-variable values are still computed independently per run.
    variable_inputs = tuple(model.find_input(lhs='set variable', recursive=True)) if cache_scopes else None

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
            ))
            contexts_reused += 1
            continue

        ctx = None
        contexts_constructed += 1
        refs = ()
        sources = ()
        activations = ()
        error = None
        try:
            # Even an invalid flag combination is one failed run, not an
            # uncaught exception that aborts the remaining batch.
            ctx = (BatchContext(flags, config=model.config, variable_inputs=variable_inputs,
                                shared_scope_decisions=shared_scope_decisions)
                   if cache_scopes else Context(flags, config=model.config))
            if isinstance(ctx, BatchContext):
                ctx._shared_file_references = shared_file_references
            run = model.context(context=ctx, file_resolution='deferred')
            refs = tuple(ref for inp in run.find_input() for ref in inp.file_references)
            activations = run.deferred_database_activations()
            # Keep rows attached to the exact declaration UUID. The consumer
            # selects the database active at each boundary/GIS command; simply
            # unioning BC rows would produce false secondary dependencies.
            sources = tuple(
                source
                for activation in activations
                for source in run.deferred_database_sources_for_activation(activation.input_uuid)
            )
        except Exception as exc:
            # Fail closed. Never return the partial references accumulated
            # before an unknown database or malformed control-file failure.
            refs = sources = activations = ()
            error = f'{type(exc).__name__}: {exc}'
        projected = BatchDependencyRun(index, flag_text, refs, sources, activations, error)
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

    if not results:
        raise ValueError('At least one simulation context is required')
    return BatchDependencyResult(
        tuple(results), perf_counter() - started,
        scope_builds, scope_hits, translation_hits, translation_misses,
        contexts_constructed, contexts_reused,
        cross_run_reference_hits, cross_run_reference_misses,
        cross_run_scope_hits, cross_run_scope_misses,
    )
