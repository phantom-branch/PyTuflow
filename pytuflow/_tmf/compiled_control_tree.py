"""Invocation-local, immutable projection of the parsed control-file input tree.

This is a *syntactic* graph.  It never opens files or constructs run states.
Runtime Context and the existing resolver remain authoritative for scope,
activation, substitutions and command ordering.  Immutable nodes are not
proof that a mutable InputRunState can be reused across simulations.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

from .compiled_dependency_plan import CompiledReadDependency, CompiledVariablePlan


_GROUP_COMMANDS = frozenset({'READ GIS CODE', 'READ GRID ZPTS'})
_GROUP_SUFFIXES = frozenset({'.shp', '.tif', '.asc', '.flt'})
_SCENARIO_BLOCKS = frozenset({'SCENARIO', 'SCENARIO (ELSE)'})
_GROUP_VARIABLE = re.compile(r'<<[A-Za-z_][A-Za-z0-9_-]*>>')


def group_configuration_signature(config) -> tuple[object, ...]:
    """Settings affecting the supported deferred leaf READs, without I/O."""
    return (
        str(config.tcf), str(config.control_file), str(config.root_folder),
        str(config.spatial_database), str(config.gis_format),
        str(config.grid_format), tuple(map(str, config.wildcards)),
        str(config.check_file_prefix_1d), str(config.check_file_prefix_2d),
    )


def group_block_signature(command) -> tuple[tuple[str, str], ...]:
    return tuple((str(block.type), str(block.name)) for block in command.define_blocks)


def group_command_signature(command) -> tuple[object, ...]:
    return (
        str(command.parent), command.part_index, command.part_count,
        command.line_number,
    )


def is_literal_group_path(value: str) -> bool:
    """A single explicit supported file, without late-bound selector syntax."""
    return bool(
        value and '_event_' not in value.casefold()
        and not any(token in value for token in '<>~*?|#$%')
        and Path(value).suffix.lower() in _GROUP_SUFFIXES
    )


@dataclass(frozen=True, slots=True)
class CompiledBranchDependency:
    """Snapshot of an ordered scope/branch, including ELSE and negation."""

    scope_type: str
    names: tuple[str, ...]
    variable: str | None
    negated: bool
    else_branch: bool
    known: bool


def snapshot_branches(scopes) -> tuple[CompiledBranchDependency, ...]:
    return tuple(
        CompiledBranchDependency(
            scope_type=str(scope.type).upper(),
            names=tuple(map(str, scope.names)),
            variable=str(scope.var) if scope.var is not None else None,
            negated=scope.is_neg(),
            else_branch=bool(getattr(scope, '_else', False)),
            known=bool(scope.known),
        )
        for scope in scopes
    )


@dataclass(frozen=True, slots=True)
class CompiledInputGroupPlan:
    """Static proof for one leaf; resolved values are still checked per run."""

    configuration_signature: tuple[object, ...]
    command_signature: tuple[object, ...]
    define_blocks: tuple[tuple[str, str], ...]
    scenario_dependent: bool
    input_type: type
    context_method: object


def _compile_input_group(inp, command, role, read, branches):
    """Classify every input once, keeping uncertain inputs on the normal path."""
    from .inp.gis import GisInput, _GIS_INPUT_CONTEXT
    from .inp.grid import GridInput
    from .inp.inp_build_state import _INPUT_BUILD_CONTEXT
    from .parsers.block import DefineBlock
    from .parsers.command import Command
    from .scope import GlobalScope, ScenarioScope

    if role != 'READ':
        return None, 'non_read'
    if type(command) is not Command:
        return None, 'specialised_command'
    if command.command not in _GROUP_COMMANDS:
        return None, 'unsupported_command'
    if type(inp) not in (GisInput, GridInput):
        return None, 'unsupported_input'
    context_method = _GIS_INPUT_CONTEXT if type(inp) is GisInput else _INPUT_BUILD_CONTEXT
    bound_context = inp.context
    if (getattr(bound_context, '__func__', None) is not context_method
            or getattr(bound_context, '__self__', None) is not inp):
        return None, 'custom_context'
    if any(type(block) is not DefineBlock or block.type not in _SCENARIO_BLOCKS
           for block in command.define_blocks):
        return None, 'conditional_or_define'
    if not branches or any(type(scope) not in (GlobalScope, ScenarioScope)
                           for scope in inp.scope):
        return None, 'conditional_or_define'
    if any(
        branch.scope_type not in ('GLOBAL', *_SCENARIO_BLOCKS)
        or (branch.scope_type != 'GLOBAL' and (
            not branch.known or branch.variable is not None or not branch.names
            or any(not name or any(token in name for token in '<>~*?$%')
                   for name in branch.names)
        ))
        for branch in branches
    ):
        return None, 'dynamic_scope'
    raw = str(command.value_orig or '').strip()
    if not raw:
        return None, 'empty_read'
    if read is None or not read.reusable:
        return None, 'unproven_variable_lineage'
    # Allow only variables whose complete lineage was compiled. The resolved
    # value must pass the stricter literal-path test for each individual run.
    literal_parts = _GROUP_VARIABLE.sub('', raw)
    if ('_event_' in literal_parts.casefold()
            or any(token in literal_parts for token in '<>~*?|#$%')):
        return None, 'dynamic_path'
    if not read.relevant_variables and not is_literal_group_path(raw):
        return None, 'unsupported_path'
    if str(inp.config.spatial_database) not in ('', '.', 'None'):
        return None, 'spatial_database'
    return CompiledInputGroupPlan(
        group_configuration_signature(inp.config),
        group_command_signature(command),
        group_block_signature(command),
        any(branch.scope_type != 'GLOBAL' for branch in branches),
        type(inp),
        context_method,
    ), None


if TYPE_CHECKING:
    from .cf.tcf import TCF


@dataclass(frozen=True, slots=True)
class CompiledControlNode:
    """One parsed input in traversal order, including reference-free commands."""

    input_uuid: str
    ordinal: int
    owner_control_file: Path | None
    line_number: int
    command_name: str
    original_text: str
    raw_value: str | None
    scope: tuple[str, ...]
    branch_conditions: tuple[CompiledBranchDependency, ...]
    role: str
    read_dependency: CompiledReadDependency | None
    bypass_reason: str | None
    input_group: CompiledInputGroupPlan | None
    input_group_bypass_reason: str | None


@dataclass(frozen=True, slots=True)
class CompiledControlTree:
    """Frozen nodes plus a read-only, invocation-local identity index.

    The index retains build inputs only to guard against Python id reuse.
    It is deliberately not a module-global or persistent cache.  A new batch
    invocation compiles a fresh tree and observes changes to BuildState.
    """

    nodes: tuple[CompiledControlNode, ...]
    _by_identity: Mapping[int, tuple[object, CompiledControlNode]]

    @classmethod
    def compile(cls, model: TCF, variables: CompiledVariablePlan) -> CompiledControlTree:
        from .parsers.command import Command

        nodes: list[CompiledControlNode] = []
        by_identity: dict[int, tuple[object, CompiledControlNode]] = {}
        for ordinal, inp in enumerate(model.find_input(recursive=True)):
            command = inp.command()
            name = str(command.command or '').upper()
            role = 'INPUT'
            if name.startswith(('READ GIS ', 'READ GRID ')):
                role = 'READ'
            elif name.startswith('SET VARIABLE'):
                role = 'VARIABLE'
            elif name in ('BC DATABASE', 'AD BC DATABASE', 'BC EVENT SOURCE'):
                role = 'BC_ACTIVATION'
            elif name in ('EVENT FILE', 'BC EVENT FILE'):
                role = 'EVENT'
            elif command.is_control_file():
                role = 'CONTROL_FILE'
            elif name.startswith(('SPATIAL DATABASE', 'GIS FORMAT', 'GRID FORMAT')):
                role = 'SETTING'

            read: CompiledReadDependency | None = None
            reason: str | None = None
            if role == 'READ':
                if type(command) is not Command:
                    reason = 'specialised-command'
                elif command.define_blocks:
                    # Keep conditional READs out of general command-template
                    # reuse. A separate whole-model proof may certify literal
                    # scenario-only projections; real DEFINE/event blocks must
                    # remain distinguishable and bypass that shortcut.
                    reason = ('scenario-conditional-command'
                              if all(block.type in ('SCENARIO', 'SCENARIO (ELSE)')
                                     for block in command.define_blocks)
                              else 'define-or-conditional-command')
                    if reason == 'scenario-conditional-command' and command.value_orig:
                        # General Command templates still exclude conditionals.
                        # Leaf group reuse has its own branch-aware proof and
                        # therefore needs the complete variable lineage here.
                        read = variables.compile_read(str(command.value_orig))
                elif not command.value_orig:
                    reason = 'empty-read'
                else:
                    read = variables.compile_read(str(command.value_orig))
                    if not read.reusable:
                        reason = 'unproven-expression-or-variable-lineage'
            else:
                # Non-READ commands still belong in the tree for correct
                # ordinal/owner visibility; they are never reused as commands.
                reason = 'not-a-plain-read'

            branches = snapshot_branches(inp.scope)
            input_group, group_reason = _compile_input_group(
                inp, command, role, read, branches,
            )
            node = CompiledControlNode(
                input_uuid=str(inp.uuid),
                ordinal=ordinal,
                owner_control_file=command.parent,
                line_number=inp.line_number,
                command_name=name,
                original_text=str(command.original_text),
                raw_value=str(command.value_orig) if command.value_orig is not None else None,
                scope=tuple(str(s) for s in inp.scope),
                branch_conditions=branches,
                role=role,
                read_dependency=read,
                bypass_reason=reason,
                input_group=input_group,
                input_group_bypass_reason=group_reason,
            )
            nodes.append(node)
            by_identity[id(inp)] = (inp, node)
        return cls(tuple(nodes), MappingProxyType(by_identity))

    def node_for(self, build_input: object) -> CompiledControlNode | None:
        entry = self._by_identity.get(id(build_input))
        if entry is None or entry[0] is not build_input:
            return None
        return entry[1]

    @property
    def eligible_read_nodes(self) -> int:
        return sum(
            node.role == 'READ' and node.bypass_reason is None
            for node in self.nodes
        )

    @property
    def bypassed_read_nodes(self) -> int:
        return sum(
            node.role == 'READ' and node.bypass_reason is not None
            for node in self.nodes
        )

    @property
    def reusable_input_group_nodes(self) -> int:
        """Actual leaf-construction candidates, separate from READ plan counts."""
        return sum(node.input_group is not None for node in self.nodes)

    @property
    def input_group_bypass_reasons(self) -> tuple[tuple[str, int], ...]:
        counts = Counter(node.input_group_bypass_reason for node in self.nodes
                         if node.input_group_bypass_reason is not None)
        return tuple(sorted(counts.items()))

    def is_scenario_literal_model(self, model: TCF) -> bool:
        """Certify read-only inputs controlled *only* by literal scenarios.

        Unlike the completely invariant subset, this may contain IF Scenario
        branches and ELSE/negated scenario conditions.  Reuse is permitted
        only within the exact same selected scenario-slot signature, so the
        existing context evaluator remains authoritative for branch choices.
        All non-READ, variable/event, DEFINE, include, BC, GIS database and
        dynamic selector constructs deliberately bypass this fast path.
        """
        config = model.config
        if (not self.nodes or config.event_db or config.variables
                or config.scenarios
                or str(config.spatial_database) not in ('', '.', 'None')):
            return False
        safe_suffixes = {'.shp', '.tif', '.asc', '.flt'}
        for node in self.nodes:
            if (node.input_group is None
                    or node.role != 'READ'
                    or node.bypass_reason not in (None, 'scenario-conditional-command')
                    or (node.read_dependency is None
                        and node.bypass_reason != 'scenario-conditional-command')
                    or (node.read_dependency is not None
                        and node.read_dependency.relevant_variables)
                    or node.command_name not in ('READ GIS CODE', 'READ GRID ZPTS')
                    or not node.raw_value):
                return False
            if any(
                scope.scope_type not in ('GLOBAL', 'SCENARIO', 'SCENARIO (ELSE)')
                or (scope.scope_type in ('SCENARIO', 'SCENARIO (ELSE)') and (
                    not scope.known
                    or (scope.variable is not None
                        and str(scope.variable).startswith('<<'))
                ))
                for scope in node.branch_conditions
            ):
                return False
            raw = node.raw_value.strip()
            if (not raw or '_event_' in raw.casefold()
                    or any(token in raw for token in '<>~*?|#$%')
                    or Path(raw).suffix.lower() not in safe_suffixes):
                return False
        return True

    def is_invariant_literal_model(self, model: TCF) -> bool:
        """Prove one narrow class of entire models is independent of run flags.

        A completely literal, top-level GIS/code or grid READ-only model
        cannot change its active command stream, variable map, or BC source
        activations with event/scenario flags. No INCLUDE, DEFINE, TEF, global
        substitutions, spatial database or non-READ commands are permitted.
        This deliberately excludes most real TCFs; all others use the
        ordinary per-run resolver. A valid first projection is still required.
        """
        config = model.config
        if (not self.nodes or config.event_db or config.variables
                or config.scenarios
                or str(config.spatial_database) not in ('', '.', 'None')):
            return False
        safe_suffixes = {'.shp', '.tif', '.asc', '.flt'}
        for node in self.nodes:
            if (node.input_group is None
                    or node.role != 'READ' or node.bypass_reason is not None
                    or node.read_dependency is None
                    or node.read_dependency.relevant_variables
                    or node.command_name not in ('READ GIS CODE', 'READ GRID ZPTS')
                    or not node.raw_value
                    or any(branch.scope_type != 'GLOBAL'
                           or branch.negated or branch.else_branch
                           for branch in node.branch_conditions)):
                return False
            raw = node.raw_value.strip()
            # No event marker, variable, wildcard, GPkg selector, multipart
            # command, or other parser-dependent path syntax is provably
            # context invariant across flags.
            if (raw.casefold().find('_event_') != -1
                    or any(token in raw for token in '<>~*?|#$%')
                    or Path(raw).suffix.lower() not in safe_suffixes):
                return False
        return True
