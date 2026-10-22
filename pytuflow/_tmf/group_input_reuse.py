"""Conservative, invocation-local reuse of independent literal READ input states.

The ordinary control-file traversal still decides activation, variable ordering,
failures and database side effects.  Only leaf GIS CODE / GRID ZPTS commands
with literal paths can skip their expensive InputRunState initialiser.  A
successful entire run must certify a prototype before another run can use it.
"""
from __future__ import annotations

from copy import copy
from pathlib import Path
from typing import TYPE_CHECKING

from .parsers.command import Command
from .settings import from_config

if TYPE_CHECKING:
    from .compiled_control_tree import CompiledControlTree
    from .context import Context


_SAFE_COMMANDS = frozenset({"READ GIS CODE", "READ GRID ZPTS"})
_SAFE_SUFFIXES = frozenset({".shp", ".tif", ".asc", ".flt"})
_MAX_TEMPLATES = 10_000


class LiteralInputGroupCache:
    """One batch's proven prototypes, never shared across invocations."""

    def __init__(self, graph: CompiledControlTree):
        self.graph = graph
        self._prototypes: dict[tuple[object, ...], tuple[object, object]] = {}

    def _key(self, build_input, ctx: Context) -> tuple[object, ...] | None:
        node = self.graph.node_for(build_input)
        if (node is None or node.role != "READ" or node.bypass_reason is not None
                or node.command_name not in _SAFE_COMMANDS
                or any(scope.scope_type != "GLOBAL" for scope in node.branch_conditions)
                or not node.raw_value or not node.read_dependency
                or node.read_dependency.relevant_variables):
            return None

        command = build_input.command()
        if (type(command) is not Command or command.define_blocks
                or command.original_text != node.original_text
                or str(command.value_orig) != node.raw_value
                or not build_input.rhs or str(build_input.rhs) != node.raw_value):
            return None
        raw = node.raw_value.strip()
        if (not raw or "_event_" in raw.casefold()
                or any(token in raw for token in "<>~*?|#$%")
                or Path(raw).suffix.lower() not in _SAFE_SUFFIXES
                or ctx.translate(raw) != raw
                or not ctx.is_resolved(raw)
                or getattr(ctx, 'file_resolution', None) != 'deferred'):
            return None
        cfg = build_input.config
        # A spatial database, layer selector or late-bound wildcard may change
        # the physical meaning of a bare GIS name. Do not certify those reads.
        if str(cfg.spatial_database) not in ("", ".", "None"):
            return None
        # These settings affect deferred expansion and reference classification.
        # Keep per-input identity + source text and the exact lexical paths.
        return (
            id(build_input), node.original_text, node.input_uuid, node.ordinal,
            str(command.parent), command.part_index, command.line_number,
            str(cfg.tcf), str(cfg.control_file), str(cfg.root_folder),
            str(cfg.spatial_database), str(cfg.gis_format),
            str(cfg.grid_format), tuple(map(str, cfg.wildcards)),
            str(cfg.check_file_prefix_1d), str(cfg.check_file_prefix_2d),
        )

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
        state._scope = copy(prototype._rs._scope)
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
            key = self._key(build_input, ctx)
            if key is None:
                return None, None
            entry = self._prototypes.get(key)
            if entry is None or entry[0] is not build_input:
                return None, key
            result = self._clone(entry[1], build_input, ctx, parent)
            return (result, key) if result is not None else (None, None)
        except Exception:
            # Optimisation failures cannot change normal parser behaviour.
            return None, None

    def commit(self, pending) -> None:
        """Only fully successful run projections may certify later reuse."""
        for key, build_input, state in pending:
            if key in self._prototypes or len(self._prototypes) >= _MAX_TEMPLATES:
                continue
            # The retained exemplar cannot be mutated through the returned
            # projection or its original run tree.
            try:
                exemplar = self._clone(state, build_input, state.ctx, None)
            except Exception:
                continue
            if exemplar is None:
                continue
            exemplar.ctx = None
            exemplar.parent = None
            exemplar._command.config.variables = {}
            exemplar._command._expander.variables = {}
            self._prototypes[key] = (build_input, exemplar)

    @property
    def unique_groups(self) -> int:
        return len(self._prototypes)
