"""Invocation-local, immutable projection of the parsed control-file input tree.

This is a *syntactic* graph.  It never opens files or constructs run states.
Runtime Context and the existing resolver remain authoritative for scope,
activation, substitutions and command ordering.  Immutable nodes are not
proof that a mutable InputRunState can be reused across simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

from .compiled_dependency_plan import CompiledReadDependency, CompiledVariablePlan


@dataclass(frozen=True, slots=True)
class CompiledBranchDependency:
    """Snapshot of an ordered scope/branch, including ELSE and negation."""

    scope_type: str
    names: tuple[str, ...]
    variable: str | None
    negated: bool
    else_branch: bool
    known: bool


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
                    reason = 'define-or-conditional-command'
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

            node = CompiledControlNode(
                input_uuid=str(inp.uuid),
                ordinal=ordinal,
                owner_control_file=command.parent,
                line_number=inp.line_number,
                command_name=name,
                original_text=str(command.original_text),
                raw_value=str(command.value_orig) if command.value_orig is not None else None,
                scope=tuple(str(s) for s in inp.scope),
                branch_conditions=tuple(
                    CompiledBranchDependency(
                        scope_type=str(scope.type).upper(),
                        names=tuple(map(str, scope.names)),
                        variable=str(scope.var) if scope.var is not None else None,
                        negated=scope.is_neg(),
                        else_branch=bool(getattr(scope, '_else', False)),
                        known=bool(scope.known),
                    )
                    for scope in inp.scope
                ),
                role=role,
                read_dependency=read,
                bypass_reason=reason,
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
                or config.scenarios or config.spatial_database):
            return False
        safe_suffixes = {'.shp', '.tif', '.asc', '.flt'}
        for node in self.nodes:
            if (node.role != 'READ' or node.bypass_reason is not None
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
