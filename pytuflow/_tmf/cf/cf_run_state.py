import logging
import re
import typing
from functools import cache

from ..inp.inputs import Inputs, _ContextAppendRecorder
from ..inp.inp_run_state import InputRunState
from ..abc.cf import ControlFile
from ..abc.run_state import RunState
from ..context import Context



if typing.TYPE_CHECKING:
    from .cf_build_state import ControlFileBuildState

logger = logging.getLogger('pytuflow')


@cache
def _batch_append_context_methods() -> dict[type, object]:
    """Original constructors do not edit already-built parent inputs/UUIDs.

    Use aliases captured where each method is defined. A class-level extension
    installed before the first batch must not become trusted by this table.
    """
    from ..inp import block, cf, comment, db, file, folder, gis, grid
    from ..inp import inp_build_state, mat, setting, time_inp, tin, trd

    plain_input_types = (
        inp_build_state.InputBuildState, setting.SettingInput,
        comment.CommentInput, file.FileInput, folder.FolderInput,
        grid.GridInput, time_inp.TimeInput, tin.TinInput, trd.TuflowReadFileInput,
    )
    return {
        **{input_type: inp_build_state._INPUT_BUILD_CONTEXT for input_type in plain_input_types},
        cf.ControlFileInput: cf._CONTROL_FILE_INPUT_CONTEXT,
        db.DatabaseInput: db._DATABASE_INPUT_CONTEXT,
        mat.MatDatabaseInput: db._DATABASE_INPUT_CONTEXT,
        gis.GisInput: gis._GIS_INPUT_CONTEXT,
        block.BlockControlInput: block._BLOCK_CONTROL_INPUT_CONTEXT,
        block.BCBlockControlInput: block._BLOCK_CONTROL_INPUT_CONTEXT,
        block.GridDefinitionFileBlockInput: block._BLOCK_CONTROL_INPUT_CONTEXT,
    }


class ControlFileRunState(RunState, ControlFile):
    """Class for storing the run state of a control file.

    This class should not be instantiated directly, but rather it should be created from an instance
    of a BuildState class using the `context` method of the BuildState class.

    Parameters
    ----------
    build_state : ControlFileBuildState
        The BuildState object that the RunState object is based on.
    context : Context
        The context object that the RunState object is based on.
    parent : ControlFileRunState
        The parent control file run state.
    """
    def __init__(self, build_state: 'ControlFileBuildState', context: Context, parent: 'ControlFileRunState'):
        super().__init__(build_state, context, parent)
        #: ControlFileBuildState: the BuildState object that the RunState object is based on.
        self.bs = build_state
        #: ControlFileRunState: the parent control file
        self.parent = parent
        #: TuflowPath: the path to the control file
        self.fpath = self.bs.fpath
        #: TCFConfig: the configuration settings for the model.
        self.config = self.bs.config
        #: Inputs: list of inputs and comments in the control file
        self.inputs = Inputs[InputRunState]()
        #: bool: whether the control file has been loaded from disk or not.
        self.loaded = self.bs.loaded

        self._inputs = self.bs.inputs

        self._resolve_scope_in_context()

    def __str__(self):
        if self.fpath:
            if self.loaded:
                return self.fpath.name
            else:
                return f'{self.fpath.name} (not found)'
        return 'Empty Control File'

    def __repr__(self):
        return '<{0}Context> {1}'.format(self._name, str(self))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def _resolve_scope_in_context(self) -> None:
        # if context is empty, look for model events / scenario commands in file
        if self.ctx.is_empty():
            d = {}
            model_scenarios = self.bs.root_cf.find_input(lhs='model scenario')
            for s in reversed(model_scenarios):
                d.update({'s{0}'.format(i+1): v for i, v in enumerate(re.split(r'[\t\s|,]+', s.rhs))})
                break
            model_events = self.bs.root_cf.find_input(lhs='model event')
            for e in reversed(model_events):
                d.update({'e{0}'.format(i+1): v for i, v in enumerate(re.split(r'[\t\s|,]+', e.rhs))})
                break
            self.ctx.load_context_from_dict(d)

        # try and resolve variables
        if not self.ctx.var_loaded:
            # Batch dependency collection precomputes the immutable list of
            # variable declarations once per parsed TCF. Each run still
            # independently evaluates scopes and the active variable values.
            compiled_assignments = getattr(self.ctx, '_batch_variable_assignments', None)
            var_map = {}
            if compiled_assignments is not None:
                for var_input, (var_name, var_val) in compiled_assignments:
                    if self.ctx.in_context_by_scope(var_input.scope):
                        var_map[var_name] = var_val
            else:
                var_inputs = getattr(self.ctx, '_batch_variable_inputs', None)
                if var_inputs is None:
                    var_inputs = self.bs.find_input(lhs='set variable', recursive=True)
                for var_input in var_inputs:
                    if self.ctx.in_context_by_scope(var_input.scope):
                        var_name, var_val = var_input.command().parse_variable()
                        var_map[var_name] = var_val
            self.ctx.load_variables(var_map)

        # A fresh, privately constructed batch collection can record first
        # UUID positions incrementally. Never retain an index cache on mutable
        # Inputs, and leave ordinary contexts/edit collections on live lookup.
        append_recorder = None
        append_context_state = {}
        known_methods = {}
        if (getattr(self.ctx, '_batch_active', False)
                and getattr(self.ctx, 'file_resolution', 'eager') == 'deferred'
                and getattr(self.ctx, '_batch_append_indexes_safe', True)):
            from ..batch_dependencies import (
                _batch_append_context_is_trusted, _batch_append_input_scope_is_trusted,
                _batch_append_scope_is_trusted, _batch_append_scope_sources_are_trusted,
            )
            from ..inp.cf import ControlFileInput
            from ..parsers.command import Command, EventCommand
            from ..parsers.fvcommand import FVCommand

            if _batch_append_context_is_trusted(self.ctx):
                append_context_state = object.__getattribute__(self.ctx, '__dict__')
                known_methods = _batch_append_context_methods()
                if _batch_append_scope_sources_are_trusted(append_context_state, known_methods):
                    append_recorder = _ContextAppendRecorder(self.inputs)
        for inp in self._inputs:
            if append_recorder is not None and (
                not _batch_append_context_is_trusted(self.ctx)
                or not _batch_append_input_scope_is_trusted(inp, known_methods)
                or not _batch_append_scope_is_trusted(append_context_state.get('_batch_scopes'))
            ):
                # Scope checks themselves can mutate earlier input UUIDs.
                # Retire before the getter or any callback, including inactive
                # inputs' scope selection. Keep the previously trusted raw
                # storage so even a replacement __dict__ getter is not read.
                append_context_state['_batch_append_indexes_safe'] = False
                append_recorder = None
            if not self.ctx.in_context_by_scope(inp.scope):
                continue

            if inp.lhs.upper() == 'PAUSE':
                raise ValueError('Pause command encountered: {0}'.format(inp.rhs))

            batch_factory = getattr(self.ctx, 'batch_input_state', None)

            if append_recorder is not None:
                # An extension may mutate prior inputs during construction.
                # Disable every enclosing recorder before calling that code;
                # nested control files share this context but own their lists.
                # Do not inspect inactive constructors, or evaluate an unknown
                # class's descriptor merely to decide it cannot be trusted.
                method = known_methods.get(type(inp))
                bound_context = (
                    inp.context
                    if method is not None and getattr(type(inp), 'context', None) is method
                    else None
                )
                if (
                    method is None
                    or getattr(bound_context, '__func__', None) is not method
                    or getattr(bound_context, '__self__', None) is not inp
                    or type(inp._command) not in (Command, EventCommand, FVCommand)
                ):
                    append_context_state['_batch_append_indexes_safe'] = False
                    append_recorder = None

            if append_recorder is not None and isinstance(inp, ControlFileInput):
                # A nested control or FV block can have its own context hook,
                # which may edit this parent's existing inputs. Retire only
                # this recorder; a fresh child collection can still use one.
                # Never inspect generic inp.cf: GIS children are lazy I/O.
                append_recorder = None

            # Opt-in batch-only fast path for independently proven literal
            # inputs. Scope selection and PAUSE/failure handling stay here.
            if batch_factory is None:
                # Instrument only explicitly batch-tagged uncached contexts;
                # standalone upstream-style contexts are unchanged.
                if hasattr(self.ctx, '_batch_input_states_constructed'):
                    self.ctx._batch_input_states_constructed += 1
                input_run_state = inp.context(context=self.ctx, parent=self)
            else:
                input_run_state = batch_factory(inp, self)
            if append_recorder is not None and append_context_state.get('_batch_append_indexes_safe', True):
                if not append_recorder.append(input_run_state):
                    append_context_state['_batch_append_indexes_safe'] = False
            else:
                self.inputs.append(input_run_state)
