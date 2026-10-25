"""Invocation-local immutable dependency fragments for file-existence batches.

Evaluate each section only for distinct effective substitutions and branch
decisions. Mutable InputRunState objects are discarded after projection, never
shared. The ordinary evaluator remains authoritative for command semantics.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any, cast

from .batch_dependencies import (
    BatchContext,
    BatchDependencyRun,
    BatchInputCommand,
    BatchInputReference,
)
from .context import Context
from .file_reference import (
    DeferredDatabaseActivation,
    DeferredDatabaseSource,
    FileReference,
)

_TOKEN = re.compile(r"<<([^<>]+)>>")
_LIMIT = 10000


def _variable_name(token: str) -> str:
    name = token.upper()
    if re.fullmatch(r"~[SE]~", name):
        name = name[:-1] + "1~"
    return name.strip("~") if name.startswith(("~S", "~E")) else name


@dataclass(frozen=True, slots=True)
class CompiledExpression:
    """Literal/token operations; complex TEF replacement uses Context semantics."""

    text: str
    operations: tuple[tuple[bool, str], ...]
    variables: tuple[str, ...]

    @classmethod
    def compile(cls, text: str) -> CompiledExpression:
        operations: list[tuple[bool, str]] = []
        names: set[str] = set()
        end = 0
        for match in _TOKEN.finditer(text):
            operations.append((False, text[end : match.start()]))
            operations.append((True, match.group(0)))
            names.add(_variable_name(match.group(1)))
            end = match.end()
        operations.append((False, text[end:]))
        return cls(text, tuple(operations), tuple(sorted(names)))

    def bindings(self, ctx: Any) -> tuple[object, ...]:
        # Follow actual variable values transitively, including scoped Set
        # Variable declarations. Cycles terminate; Context decides errors.
        pending = list(self.variables)
        found: dict[str, object] = {}
        while pending:
            name = pending.pop()
            if name in found:
                continue
            value = ctx.var_map.get(name)
            found[name] = value if isinstance(value, (str, int, float, type(None))) else repr(value)
            if isinstance(value, str):
                pending.extend(_variable_name(m.group(1)) for m in _TOKEN.finditer(value))
        # TEF tokens are arbitrary strings and replacements can introduce other
        # tokens or <<variables>>. Retain ordered complete event bindings when
        # they can participate; do not assume tokens have ~ delimiters.
        has_events = bool(ctx.event_variables) and (
            bool(self.variables) or any(str(key).casefold() in self.text.casefold() for key in ctx.event_variables)
        )
        events = tuple((key, str(value)) for key, value in ctx.event_variables.items()) if has_events else ()
        if events:
            # Event values may introduce variables absent from the expression.
            # The complete variable map is conservative for this complex case.
            return tuple(sorted((str(k), repr(v)) for k, v in ctx.var_map.items())), events
        return tuple(sorted(found.items())), events

    def evaluate(self, ctx: Any) -> Any:
        # Only use the token join when no replacement can trigger a subsequent
        # replacement, numeric coercion, or arbitrary TEF substitution.
        if not ctx.event_variables and all(
            isinstance(ctx.var_map.get(name), str) and "<<" not in ctx.var_map[name] and ">>" not in ctx.var_map[name]
            for name in self.variables
        ):
            return "".join(
                str(ctx.var_map[_variable_name(value[2:-2])]) if token else value for token, value in self.operations
            )
        return Context.translate(ctx, self.text)


class ExpressionPool:
    """Compile expressions once and share evaluations by effective bindings."""

    def __init__(self) -> None:
        self.plans: dict[str, CompiledExpression] = {}
        self.values: dict[tuple[str, tuple[object, ...]], Any] = {}
        self.evaluations = 0
        self.reuses = 0

    def translate(self, ctx: Any, text: Any) -> Any:
        from .tfpathlib import TuflowPath

        if not isinstance(text, (str, TuflowPath)):
            return text
        text = str(text)
        plan = self.plans.get(text)
        if plan is None:
            plan = CompiledExpression.compile(text)
            if len(self.plans) < _LIMIT:
                self.plans[text] = plan
        key = text, plan.bindings(ctx)
        if key in self.values:
            self.reuses += 1
            return self.values[key]
        value = plan.evaluate(ctx)
        self.evaluations += 1
        if len(self.values) < _LIMIT:
            self.values[key] = value
        return value


class _FragmentContext(BatchContext):
    _batch_variable_assignments: tuple[tuple[Any, tuple[str, str]], ...]

    def __init__(self, flags: Any, config: Any, expressions: ExpressionPool) -> None:
        self.expressions = expressions
        cast(Any, super()).__init__(flags, config=config)
        self.file_resolution = "deferred"

    def translate(self, item: Any) -> Any:
        return self.expressions.translate(self, item)


@dataclass(frozen=True, slots=True)
class DependencyFragment:
    """Shared values with relative command ordinals and no mutable run owner."""

    commands: tuple[BatchInputCommand, ...] = ()
    references: tuple[BatchInputReference, ...] = ()
    sources: tuple[DeferredDatabaseSource, ...] = ()
    activations: tuple[DeferredDatabaseActivation, ...] = ()


def _join(fragments: Iterable[DependencyFragment]) -> DependencyFragment:
    commands: list[BatchInputCommand] = []
    refs: list[BatchInputReference] = []
    sources: list[DeferredDatabaseSource] = []
    activations: list[DeferredDatabaseActivation] = []
    for fragment in fragments:
        offset = len(commands)
        commands.extend(replace(item, command_index=item.command_index + offset) for item in fragment.commands)
        refs.extend(replace(item, command_index=item.command_index + offset) for item in fragment.references)
        sources.extend(fragment.sources)
        activations.extend(replace(item, sequence=item.sequence + offset) for item in fragment.activations)
    return DependencyFragment(tuple(commands), tuple(refs), tuple(sources), tuple(activations))


@dataclass(frozen=True, slots=True)
class FragmentBatchResult:
    runs: tuple[BatchDependencyRun, ...]
    fragments: tuple[DependencyFragment, ...]
    fragment_evaluations: int
    fragment_reuses: int
    expression_evaluations: int
    expression_reuses: int
    fallback_runs: int
    fallback_reason: str | None
    elapsed_seconds: float

    @property
    def passed(self) -> bool:
        return bool(self.runs) and all(run.error is None for run in self.runs)


class _Plan:
    def __init__(self, model: Any) -> None:
        from .inp.cf import ControlFileInput
        from .inp.comment import CommentInput
        from .inp.db import DatabaseInput
        from .inp.file import FileInput
        from .inp.folder import FolderInput
        from .inp.gis import GisInput
        from .inp.grid import GridInput
        from .inp.mat import MatDatabaseInput
        from .inp.setting import SettingInput
        from .inp.time_inp import TimeInput
        from .inp.tin import TinInput
        from .inp.trd import TuflowReadFileInput
        from .parsers.command import Command, EventCommand

        self.model = model
        self.expressions = ExpressionPool()
        self.cache: dict[tuple[int, tuple[object, ...]], DependencyFragment] = {}
        self.pending: dict[tuple[int, tuple[object, ...]], DependencyFragment] = {}
        self.evaluations = 0
        self.reuses = 0
        self.expressions_by_input: dict[int, tuple[str, ...]] = {}
        self.scopes_by_input: dict[int, tuple[Any, ...]] = {}
        self.children: dict[int, tuple[Any, ...]] = {}
        self.allowed = {
            ControlFileInput,
            DatabaseInput,
            FileInput,
            FolderInput,
            GisInput,
            GridInput,
            SettingInput,
            CommentInput,
            TimeInput,
            TinInput,
            TuflowReadFileInput,
            MatDatabaseInput,
        }
        self.command_types = {Command, EventCommand}
        self.roots = tuple(model.inputs)
        self.assignments = tuple(
            (inp, inp.command().parse_variable()) for inp in model.find_input(lhs="set variable", recursive=True)
        )
        for inp in self.roots:
            self._compile(inp, set())

    def _compile(self, inp: Any, ancestors: set[int]) -> None:
        from .inp.cf import ControlFileInput
        from .inp.db import DatabaseInput

        if id(inp) in ancestors:
            raise NotImplementedError("Cyclic control-file inclusion")
        if type(inp) not in self.allowed or type(inp.command()) not in self.command_types:
            raise NotImplementedError(f"Unsupported fragment input: {type(inp).__name__}")
        if str(inp.lhs).upper().startswith("AD "):
            raise NotImplementedError("AD database ownership requires the ordinary evaluator")
        # Custom input hooks can mutate shared context/source state; never cache
        # them as pure evaluations. Only the original built-in methods qualify.
        from .cf.cf_run_state import _batch_append_context_methods

        methods: Any = _batch_append_context_methods()
        method = methods.get(type(inp))
        if getattr(inp.context, "__func__", None) is not method:
            raise NotImplementedError("Custom input context hook")
        expressions = [str(inp.rhs or "")]
        scopes = [inp.scope]
        children: tuple[Any, ...] = tuple(cast(Any, inp).cf) if type(inp) is ControlFileInput else ()
        self.children[id(inp)] = children
        for child in children:
            for sub in child.inputs:
                self._compile(sub, ancestors | {id(inp)})
                expressions.extend(self.expressions_by_input[id(sub)])
                scopes.extend(self.scopes_by_input[id(sub)])
        if isinstance(inp, DatabaseInput):
            # Dataframes are already loaded source listings. This reads no
            # physical data; include all cells conservatively for row selection.
            for database in cast(Any, inp).cf:
                frame = getattr(database, "_df", None)
                if frame is not None:
                    expressions.extend(str(value) for row in frame.itertuples(index=True, name=None) for value in row)
        self.expressions_by_input[id(inp)] = tuple(dict.fromkeys(expressions))
        self.scopes_by_input[id(inp)] = tuple(scopes)

    def _key(self, inp: Any, ctx: Any) -> tuple[int, tuple[object, ...]]:
        # Equality is based on effective values, not entire flag dictionaries.
        # This covers transitive variables and TEF changes without guessing that
        # E/S flags alone describe a file's dependencies.
        values: list[tuple[str, tuple[object, ...]]] = []
        for text in self.expressions_by_input[id(inp)]:
            expression = self.expressions.plans.get(text)
            if expression is None:
                expression = CompiledExpression.compile(text)
                if len(self.expressions.plans) < _LIMIT:
                    self.expressions.plans[text] = expression
            try:
                value = str(ctx.translate(text))
                # Deep unresolved substitution chains must retain their bindings:
                # a subsequent constructor translation may expand another level.
                binding = expression.bindings(ctx) if "<<" in value else ()
                values.append((value, binding))
            except (ValueError, TypeError):
                # Inactive commands must not fail merely while forming a key.
                # Their ordinary evaluation, if selected, determines the error.
                values.append((text, expression.bindings(ctx)))
        scopes = tuple(ctx.in_context_by_scope(scope) for scope in self.scopes_by_input[id(inp)])
        return id(inp), (tuple(values), scopes)

    def evaluate(self, inp: Any, ctx: Any) -> DependencyFragment:
        from .cf.tcf_run_state import TCFRunState
        from .inp.cf import ControlFileInput, select_deferred_children
        from .inp.inp_run_state import InputRunState

        key = self._key(inp, ctx)
        prior = self.cache.get(key, self.pending.get(key))
        if prior is not None:
            self.reuses += 1
            return prior
        self.evaluations += 1
        if not ctx.in_context_by_scope(inp.scope):
            result = DependencyFragment()
        else:
            if str(inp.lhs).upper() == "PAUSE":
                raise ValueError(f"Pause command encountered: {inp.rhs}")
            # Includes are projected without constructing their mutable child
            # tree. Leaves use their existing evaluator once per signature.
            state = (
                cast(Any, InputRunState)(inp, ctx, None)
                if type(inp) is ControlFileInput
                else inp.context(context=ctx, parent=None)
            )
            refs: tuple[FileReference, ...] = tuple(state.file_references)
            descriptor = BatchInputCommand(
                str(state.uuid),
                0,
                state._command.parent,
                state.line_number,
                str(state.lhs),
                str(state._command.original_text),
                len(refs),
            )
            records = tuple(
                BatchInputReference(
                    descriptor.input_uuid, 0, descriptor.owner_control_file, descriptor.line_number, ref
                )
                for ref in refs
            )
            activations: list[DeferredDatabaseActivation] = []
            sources: list[DeferredDatabaseSource] = []
            for ref in refs:
                if ref.requires_database_scan:
                    if (
                        ref.unresolved_variables
                        or ref.requires_directory_scan
                        or ref.database_kind in (None, "unknown")
                    ):
                        raise ValueError(f"Cannot establish database activation: {ref.path_pattern}")
                    activations.append(
                        DeferredDatabaseActivation(
                            0,
                            descriptor.input_uuid,
                            ref.database_kind,
                            ref.path_pattern,
                            ref.origin,
                            descriptor.owner_control_file,
                            descriptor.line_number,
                        )
                    )
                    sources.extend(cast(Any, TCFRunState)._deferred_sources_for_input(state, ref.database_kind, ref))
            result = DependencyFragment((descriptor,), records, tuple(sources), tuple(activations))
            if type(inp) is ControlFileInput:
                children = select_deferred_children(inp, refs)
                result = _join((result, *(self.evaluate(sub, ctx) for child in children for sub in child.inputs)))
        if len(self.cache) + len(self.pending) < _LIMIT:
            self.pending[key] = result
        return result


def collect_file_dependencies(model: Any, run_flags: Iterable[str | dict[str, str]]) -> FragmentBatchResult:
    """Project file dependencies with shared immutable subtree evaluations.

    Source models must remain read-only throughout this synchronous call. No
    callbacks expose mutable parser state. Unsupported source types use the
    ordinary batch evaluator; a failed run publishes no partial fragments.
    """
    from .batch_dependencies import collect_batch_dependencies
    from .cf.cf_run_state import prepare_run_context

    started = perf_counter()
    try:
        plan = _Plan(model)
    except Exception as exc:  # noqa: BLE001 - incomplete compilation uses the authoritative evaluator
        fallback = collect_batch_dependencies(model, run_flags)
        return FragmentBatchResult(
            fallback.runs, (), 0, 0, 0, 0, len(fallback.runs), str(exc), perf_counter() - started
        )
    results: list[BatchDependencyRun] = []
    for index, flags in enumerate(run_flags):
        text = (
            flags if isinstance(flags, str) else " ".join(f"-{key.lstrip('-')} {value}" for key, value in flags.items())
        )
        try:
            ctx = _FragmentContext(flags, model.config, plan.expressions)
            ctx._batch_variable_assignments = plan.assignments
            prepare_run_context(model, ctx)
            fragment = _join(plan.evaluate(inp, ctx) for inp in plan.roots)
            # Match the ordinary activation contract, including duplicate UUID
            # rejection; references alone are not proof of correct ownership.
            uuids = [command.input_uuid for command in fragment.commands]
            if any(uuids.count(item.input_uuid) != 1 for item in fragment.activations):
                raise ValueError("Ambiguous database activation ownership")
            results.append(
                BatchDependencyRun(
                    index,
                    text,
                    tuple(item.reference for item in fragment.references),
                    fragment.sources,
                    fragment.activations,
                    None,
                    fragment.references,
                    fragment.commands,
                )
            )
            plan.cache.update(plan.pending)
        except Exception as exc:  # noqa: BLE001 - invalidate the complete run on parser failures
            results.append(BatchDependencyRun(index, text, (), (), (), f"{type(exc).__name__}: {exc}"))
        finally:
            plan.pending.clear()
    if not results:
        raise ValueError("At least one simulation context is required")
    return FragmentBatchResult(
        tuple(results),
        tuple(plan.cache.values()),
        plan.evaluations,
        plan.reuses,
        plan.expressions.evaluations,
        plan.expressions.reuses,
        0,
        None,
        perf_counter() - started,
    )
