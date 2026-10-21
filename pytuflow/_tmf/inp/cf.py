import logging
import os
import typing

from .file import FileInput
from .inp_run_state import InputRunState
from ..context import Context
from ..abc.bld_state import BuildState
from .. import const



if typing.TYPE_CHECKING:
    # noinspection PyUnusedImports
    from ..cf.cf_run_state import ControlFileRunState

logger = logging.getLogger('pytuflow')


class ControlFileInputRunState(InputRunState):

    def _resolve_scope_in_context(self):
        super()._resolve_scope_in_context()
        deferred = getattr(self.ctx, 'file_resolution', 'eager') == 'deferred'
        if deferred:
            # Source commands retain their *owning control file*, unlike a
            # relative value created from the process working directory.
            # Compare against expanded syntactic references with no probing.
            paths = {
                os.path.normcase(os.path.normpath(str(ref.path_pattern)))
                for ref in self.file_references
                if not ref.unresolved_variables
            }
            for cf in self.bs.cf:
                cf_path = os.path.normcase(os.path.normpath(str(cf.fpath.absolute())))
                if cf_path in paths:
                    self.cf.append(cf.context(context=self.ctx, parent=self.parent))
        else:
            for cf in self.bs.cf:
                if cf.fpath.resolve() == self.value.resolve():
                    self.cf.append(cf.context(context=self.ctx, parent=self.parent))


class ControlFileInput(FileInput):
    """
    Class for control files.Includes TRD, TEF

    | e.g.
    | :code:`Geometry Control File == geometry_control_file.tgc`
    """
    TUFLOW_TYPE = const.INPUT.CF

    @property
    def dirty(self) -> bool:
        return self._dirty or any(cf.dirty for cf in self.cf)

    @dirty.setter
    def dirty(self, value: bool):
        BuildState.dirty.fset(self, value)

    def _load(self, load_control_files: bool):
        super()._load(load_control_files)
        if load_control_files:
            self._load_control_files()

    def _load_files(self):
        super()._load_files()
        self._files_loaded = True

    def _load_control_files(self):
        from ..cf.get_control_file_class import get_control_file_class
        for file in self.files:
            try:
                cf = get_control_file_class(file)(file, self._command.config, self.parent)
                self.cf.append(cf)
            except Exception as e:
                logger.error(f'Error loading control file {file}. Command: {self._command}. Error: {e}')

    def context(self,
                run_context: str | dict[str, str] = '',
                context: Context | None = None,
                parent: 'ControlFileRunState | None' = None) -> ControlFileInputRunState:
        # docstring inherited
        ctx = context if context else Context(run_context, config=self.config)
        return ControlFileInputRunState(self, ctx, parent)
