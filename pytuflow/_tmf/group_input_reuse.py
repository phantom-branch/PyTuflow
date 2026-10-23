"""Conservative, invocation-local reuse of proven independent READ input states.

The ordinary control-file traversal still decides activation, variable ordering,
failures and database side effects.  Only leaf GIS CODE / GRID ZPTS commands
with a proven literal result can skip their expensive InputRunState initialiser.
Known scenario conditions and acyclic variable lineage are part of the proof;
the ordinary evaluator still selects active inputs before asking for reuse. A
successful entire run must certify a prototype before another run can use it.
"""
from __future__ import annotations

from copy import copy
from collections import Counter
from time import perf_counter
from typing import TYPE_CHECKING

from .compiled_control_tree import (
    group_block_signature, group_command_signature, group_configuration_signature, is_literal_group_path,
    snapshot_branches,
)
from .parsers.block import DefineBlock
from .parsers.command import Command
from .settings import from_config

if TYPE_CHECKING:
    from .compiled_control_tree import CompiledControlTree
    from .context import Context


_MAX_TEMPLATES = 10_000


class LiteralInputGroupCache:
    """One batch's proven prototypes, never shared across invocations."""

    def __init__(self, graph: CompiledControlTree):
        self.graph = graph
        self._prototypes: dict[tuple[object, ...], tuple[object, object]] = {}
        # Fixed reason keys, bounded memory even for very large batches.
        self.fallback_counts: Counter[str] = Counter()
        self.key_seconds = 0.0
        self.clone_seconds = 0.0
        self.certification_seconds = 0.0

    def _ineligible(self, reason: str) -> None:
        self.fallback_counts['ineligible'] += 1
        self.fallback_counts[f'ineligible_{reason}'] += 1

    def _key(self, build_input, ctx: Context, node=None) -> tuple[object, ...] | None:
        node = node if node is not None else self.graph.node_for(build_input)
        if node is None or node.input_group is None:
            self._ineligible(node.input_group_bypass_reason if node else 'unindexed')
            return None
        plan = node.input_group
        bound_context = build_input.context
        command = build_input.command()
        if (type(build_input) is not plan.input_type
                or getattr(bound_context, '__func__', None) is not plan.context_method
                or getattr(bound_context, '__self__', None) is not build_input
                or type(command) is not Command
                or str(build_input.uuid) != node.input_uuid
                or command.command != node.command_name
                or build_input.lhs.upper() != node.command_name
                or command.original_text != node.original_text
                or str(command.value_orig) != node.raw_value
                or not build_input.rhs or str(build_input.rhs) != node.raw_value
                or group_command_signature(command) != plan.command_signature
                or group_block_signature(command) != plan.define_blocks
                or snapshot_branches(build_input.scope) != node.branch_conditions
                or group_configuration_signature(build_input.config)
                != plan.configuration_signature):
            self._ineligible('changed_source')
            return None
        if getattr(ctx, 'file_resolution', None) != 'deferred':
            self._ineligible('non_deferred')
            return None

        raw = node.raw_value.strip()
        variables = node.read_dependency.relevant_variables
        relevant_values = tuple((name, ctx.var_map.get(name)) for name in variables)
        if any(not isinstance(value, str) for _, value in relevant_values):
            self._ineligible('unresolved_variable')
            return None
        declarations = ctx.variable_declaration_signature(variables) if variables else ()
        if any(not identifiers for _, identifiers in declarations):
            self._ineligible('inactive_variable_declaration')
            return None

        # Event text can replace arbitrary tokens, not just <<E1>> or ~e1~.
        # Do not accidentally expand coverage to event-dependent source paths
        # through an otherwise ordinary Set Variable declaration.
        expressions = (raw, *(value for _, value in relevant_values))
        if any(
            marker and str(marker).casefold() in expression.casefold()
            for marker in ctx.event_db.event_variables()
            for expression in expressions
        ):
            self._ineligible('event_expression')
            return None
        resolved = ctx.translate(raw)
        if (not isinstance(resolved, str) or not is_literal_group_path(resolved)
                or not ctx.is_resolved(resolved)
                or ctx.translate(resolved) != resolved
                or (not variables and resolved != raw)):
            self._ineligible('unresolved_or_dynamic_path')
            return None

        scenario_signature = ()
        if plan.scenario_dependent:
            # Retain actual slot numbers, including gaps, rather than only
            # scenario membership. An unnumbered S-list is a distinct form.
            if hasattr(ctx, 'S'):
                selected = ctx.S
                if not isinstance(selected, list) or any(
                    not isinstance(value, str) for value in selected
                ):
                    self._ineligible('dynamic_scenario_selection')
                    return None
                scenario_signature = (('S', tuple(value.casefold() for value in selected)),)
            else:
                selected = tuple((f'S{i}', getattr(ctx, f'S{i}'))
                                 for i in range(1, 10) if hasattr(ctx, f'S{i}'))
                if any(not isinstance(value, str) for _, value in selected):
                    self._ineligible('dynamic_scenario_selection')
                    return None
                scenario_signature = tuple((slot, value.casefold()) for slot, value in selected)

        # The group identity includes source/branch/configuration provenance,
        # the actual resolved expression and every relevant active declaration.
        # Unrelated event values cannot fragment a proven constant group.
        return (
            id(build_input), node.original_text, node.input_uuid, node.ordinal,
            plan.command_signature,
            plan.configuration_signature, plan.define_blocks, node.branch_conditions,
            resolved, relevant_values, declarations, scenario_signature,
        )

    @staticmethod
    def _clone_blocks(command):
        if any(type(block) is not DefineBlock
               or block.type not in ('SCENARIO', 'SCENARIO (ELSE)')
               for block in command.define_blocks):
            return None
        return [copy(block) for block in command.define_blocks]

    def prepare_seed(self, state) -> bool:
        """Detach the successful constructor's blocks from parsed build inputs.

        The ordinary constructor assigns a nonempty source block list directly.
        This opt-in boundary prevents a caller-visible seed from mutating the
        graph's build-state branches; eager/ordinary construction is unchanged.
        """
        try:
            blocks = self._clone_blocks(state._command)
            if blocks is None:
                self.fallback_counts['seed_isolation_unsupported'] += 1
                return False
            state._command._define_blocks = blocks
            return True
        except Exception:
            self.fallback_counts['seed_isolation_exception'] += 1
            return False

    @staticmethod
    def _clone(prototype, build_input, ctx: Context, parent):
        """Construct independently mutable wrappers without re-evaluating READ."""
        from .inp.gis import GisInput, GisInputRunState
        from .inp.grid import GridInput
        from .inp.inp_run_state import InputRunState

        if not (
            (type(prototype._rs) is GisInput and type(prototype) is GisInputRunState)
            or (type(prototype._rs) is GridInput and type(prototype) is InputRunState)
        ):
            return None
        result = copy(prototype)
        result.bs = build_input
        result.ctx = ctx
        result.parent = parent
        result.cf = []
        result.config = build_input.config

        config = from_config(build_input.config)
        config.file_resolution = "deferred"
        config.variables = ctx.translate
        command = copy(prototype._command)
        # A conditional seed and every reuse must own both the list and its
        # mutable DefineBlock objects, including writer flags.
        blocks = LiteralInputGroupCache._clone_blocks(prototype._command)
        if blocks is None:
            return None
        command._define_blocks = blocks
        command.config = config
        command._expander = copy(prototype._command._expander)
        command._expander.variables = ctx.translate
        command._expander.database = config.spatial_database
        result._command = command

        state = copy(prototype._rs)
        state.parent = build_input.parent
        state._command = command
        state.config = config
        state._files = []
        state._rhs_files = []
        state._files_loaded = False
        state._has_missing_files = False
        state._file_to_original = {}
        state._file_to_scope = {}
        state._rhs = []
        # Preserve ELSE/negation/known flags exactly. Reconstructing Scope from
        # its display string can lose branch metadata; copy names separately.
        from .scope import GlobalScope, ScenarioScope, ScopeList
        if not prototype._rs._scope or any(
            type(scope) not in (GlobalScope, ScenarioScope) for scope in prototype._rs._scope
        ):
            return None
        state._scope = ScopeList()
        for scope in prototype._rs._scope:
            # Scope.__new__ dispatches by a required type_name, so copy(scope)
            # cannot reconstruct it. Exact approved types have ordinary field
            # dictionaries; allocate that same type without rerunning parsing.
            independent_scope = object.__new__(type(scope))
            independent_scope.__dict__ = scope.__dict__.copy()
            independent_scope.names = list(scope.names)
            state._scope.append(independent_scope)
        state._prev_val = None
        state._attr_idx = 0
        state._attr_idx_found = False
        # Both GIS and GRID descendants may retain mutable lazy-loaded state.
        if hasattr(state, '_cf'):
            state._cf = []
            state._cf_loaded = False
        if type(state) is GridInput:
            # GRID inherits the plain Input.cf list, not GIS's _cf property.
            # Resetting result.cf or state._cf alone leaves this list aliased.
            state.cf = []
            state.multiplier = 1.0
            state.clip_layer = None
        if type(state) is GisInput:
            state._cf = []
            state._cf_loaded = False
            state._geoms = []
        result._rs = state
        if isinstance(result, GisInputRunState):
            result._geoms = []
        return result

    def try_reuse(self, build_input, ctx: Context, parent):
        try:
            # Static proof is compiled once. Most real-model inputs are not
            # candidates, so avoid rebuilding signatures or timing each one.
            node = self.graph.node_for(build_input)
            if node is None or node.input_group is None:
                self._ineligible(node.input_group_bypass_reason if node else 'unindexed')
                return None, None
            started = perf_counter()
            try:
                key = self._key(build_input, ctx, node)
            finally:
                self.key_seconds += perf_counter() - started
            if key is None:
                return None, None
            entry = self._prototypes.get(key)
            if entry is None or entry[0] is not build_input:
                return None, key
            started = perf_counter()
            try:
                result = self._clone(entry[1], build_input, ctx, parent)
            finally:
                self.clone_seconds += perf_counter() - started
            if result is None:
                self.fallback_counts['clone_unsupported'] += 1
                return None, None
            return result, key
        except Exception:
            # The ordinary parser still determines errors, never this cache.
            self.fallback_counts['reuse_exception'] += 1
            return None, None

    def commit(self, pending) -> None:
        """Only fully successful run projections may certify later reuse."""
        for key, build_input, state in pending:
            if key in self._prototypes:
                continue
            if len(self._prototypes) >= _MAX_TEMPLATES:
                self.fallback_counts['capacity'] += 1
                continue
            # The retained exemplar cannot be mutated through the returned
            # projection or its original run tree.
            started = perf_counter()
            try:
                exemplar = self._clone(state, build_input, state.ctx, None)
            except Exception:
                self.fallback_counts['prototype_exception'] += 1
                continue
            finally:
                self.certification_seconds += perf_counter() - started
            if exemplar is None:
                self.fallback_counts['prototype_unsupported'] += 1
                continue
            exemplar.ctx = None
            exemplar.parent = None
            exemplar._command.config.variables = {}
            exemplar._command._expander.variables = {}
            self._prototypes[key] = (build_input, exemplar)

    @property
    def unique_groups(self) -> int:
        return len(self._prototypes)
