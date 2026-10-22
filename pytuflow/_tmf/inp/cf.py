import fnmatch
import logging
import os
import typing
from pathlib import Path

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

    @property
    def files(self) -> list[Path]:
        """Include already-parsed rainfall-index grid dependencies in eager mode.

        The original eager DatabaseInput loaded the CSV as a primary file
        but returned only that index, silently omitting every grid listed
        inside it. This uses the cached build-state dataframe and active
        context; no raster file is re-opened or re-parsed.
        """
        primary = InputRunState.files.fget(self)
        if (getattr(self.ctx, 'file_resolution', 'eager') != 'eager'
                or not self._command.is_rainfall_grid_csv()):
            return primary
        secondary = [ref.path_pattern for ref in self.database_source_references]
        return list(dict.fromkeys([*primary, *secondary]))

    def _resolve_scope_in_context(self):
        super()._resolve_scope_in_context()
        deferred = getattr(self.ctx, 'file_resolution', 'eager') == 'deferred'
        if deferred and not isinstance(self.bs, ControlFileInput):
            # DatabaseInput shares this run-state class, but its cached .cf
            # entries are tables, not recursively parsed control files.
            # The explicit deferred_database_sources API handles database
            # contents; do not apply nested-control coverage checks here.
            return
        if deferred:
            # Use the paths captured when cached child control files were
            # loaded in the initial TCF parse. cf.fpath may be canonicalised
            # to a different UNC/mapped-drive spelling, and must not become
            # the only key for matching run-specific references.
            from ..abc.run_state import ResolveError

            children = tuple(self.bs.cf)
            loaded_paths = tuple(getattr(self.bs, '_cf_loaded_paths', ()))
            if len(children) != len(loaded_paths):
                raise ResolveError(
                    f'Cached nested control-file index incomplete: {self.bs.lhs}'
                )
            matched = set()
            for ref in self.file_references:
                if ref.unresolved_variables:
                    raise ResolveError(f'Unresolved child control file: {ref.path_pattern}')
                pattern = os.path.normpath(str(ref.path_pattern)).casefold()
                selected = [
                    i for i, original in enumerate(loaded_paths)
                    if fnmatch.fnmatchcase(os.path.normpath(str(original)).casefold(), pattern)
                ]
                if not selected:
                    # UNC versus mapped-drive aliases can differ at their
                    # root. Only accept a common *directory and basename*
                    # suffix from the same input's preloaded children;
                    # basename-only matching could select a wrong scenario.
                    pattern_parts = Path(pattern).parts
                    if len(pattern_parts) >= 2:
                        selected = [
                            i for i, original in enumerate(loaded_paths)
                            if len(Path(original).parts) >= 2
                            and all(fnmatch.fnmatchcase(
                                Path(original).parts[-n].casefold(),
                                pattern_parts[-n],
                            ) for n in (1, 2))
                        ]
                if not selected:
                    raise ResolveError(
                        f'No cached nested control file for {ref.path_pattern}'
                    )
                if len(selected) > 1 and not any(
                    char in ref.path_pattern.name for char in '*?['
                ):
                    raise ResolveError(
                        f'Ambiguous cached child for {ref.path_pattern}'
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
        self._cf_loaded_paths = []
        for file in self.files:
            try:
                cf = get_control_file_class(file)(file, self._command.config, self.parent)
                self.cf.append(cf)
                self._cf_loaded_paths.append(Path(file))
            except Exception as e:
                logger.error(f'Error loading control file {file}. Command: {self._command}. Error: {e}')

    def context(self,
                run_context: str | dict[str, str] = '',
                context: Context | None = None,
                parent: 'ControlFileRunState | None' = None) -> ControlFileInputRunState:
        # docstring inherited
        ctx = context if context else Context(run_context, config=self.config)
        return ControlFileInputRunState(self, ctx, parent)
