import fnmatch
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
            # Cached child control files were already loaded during the
            # one-time TCF parse. Their paths may have been canonicalised to
            # UNC while the run-specific command still names a mapped drive.
            # First match complete lexical paths, then permit a *unique*
            # filename match within this input's own parsed children.
            # Never silently discard an unmatched or ambiguous child.
            from ..abc.run_state import ResolveError

            children = tuple(self.bs.cf)
            matched = set()
            references = self.file_references
            for ref in references:
                if ref.unresolved_variables:
                    raise ResolveError(f'Unresolved child control file: {ref.path_pattern}')
                path = os.path.normpath(str(ref.path_pattern)).casefold()
                full_matches = [
                    i for i, cf in enumerate(children)
                    if fnmatch.fnmatchcase(
                        os.path.normpath(str(cf.fpath.absolute())).casefold(), path,
                    )
                ]
                if full_matches:
                    selected = full_matches
                else:
                    # The build-state list is scoped to this specific READ
                    # command; a filename match cannot import an unrelated
                    # control file from another command. Duplicated names
                    # remain ambiguous and must fail closed.
                    name = ref.path_pattern.name.casefold()
                    selected = [
                        i for i, cf in enumerate(children)
                        if fnmatch.fnmatchcase(cf.fpath.name.casefold(), name)
                    ]
                    if len(selected) > 1 and not any(c in matched for c in selected):
                        raise ResolveError(
                            f'Ambiguous cached child for {ref.path_pattern}'
                        )
                if not selected:
                    raise ResolveError(
                        f'No cached nested control file for {ref.path_pattern}'
                    )
                matched.update(selected)
            for i in sorted(matched):
                self.cf.append(children[i].context(context=self.ctx, parent=self.parent))
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
