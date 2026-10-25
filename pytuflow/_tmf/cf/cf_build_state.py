from __future__ import annotations

import logging
import re
import shutil
import stat
import tempfile
from copy import copy, deepcopy
from dataclasses import dataclass
import io
import os.path
import typing
from pathlib import Path
from typing import TextIO, OrderedDict
from uuid import uuid4

from ..abc.input import T_Input, Input
from ..inp.inp_build_state import InputBuildState
from ..inp.inp_run_state import InputRunState
from ..inp.altered_input import AlteredInput
from ..inp.comment import CommentInput
from ..inp.inputs import Inputs
from ..inp.trd import TuflowReadFileInput
from ..tfpathlib import TuflowPath
from ..tmf_types import PathLike
from ..db.db_build_state import DatabaseBuildState
from ..abc.cf import ControlFile
from ..abc.bld_state import BuildState
from ..tfstrings.increment_number import increment_fpath, get_iter_number
from ..tfstrings.geom_suffix import get_geom_suffix
from ..settings import from_config, TCFConfig, FVCConfig
from ..parsers.command import Command
from ..parsers.non_recursive_basic_parser import get_commands
from ..scope_writer import ScopeWriter
from ..inp.altered_input import AlteredInputs
from ..inp.get_input_class import get_input_class
from ..scope import ScopeList
from ..context import Context
from ..scope import Scope

from .. import const


if typing.TYPE_CHECKING:
    from .cf_run_state import ControlFileRunState

logger = logging.getLogger('pytuflow')


def _path_key(path: PathLike) -> str:
    """Compare lexical paths without resolving drive mappings or symlinks."""
    return os.path.normcase(os.path.normpath(str(Path(path).absolute())))


def _path_exists(path: Path) -> bool:
    """Only a missing path is absent; inspection failures must stop a save."""
    # Path.exists() suppresses all OSError on Python 3.14.  In particular,
    # treating an unreadable destination as new would omit its recovery copy.
    try:
        path.stat()
    except FileNotFoundError:
        return False
    return True


def _increment(path: PathLike, inc: str | None) -> Path:
    # Keep native Path keys compatible with the original reference caches;
    # TuflowPath has a different hash from an equal WindowsPath.
    return Path(path if inc is None else increment_fpath(path, inc))


def _copy_scopes(scopes: ScopeList) -> ScopeList:
    # Scope's factory __new__ requires arguments, so copy/deepcopy cannot
    # reconstruct it.  Preserve each concrete scope class and its data.
    result = ScopeList()
    for scope in scopes:
        detached = object.__new__(type(scope))
        detached.__dict__.update(deepcopy(scope.__dict__))
        result.append(detached)
    return result


def _input_signature(inp: InputBuildState) -> tuple:
    blocks = tuple(
        tuple(_input_signature(item) for item in child.inputs.inputs(include_hidden=True))
        for child in inp.cf or ()
        if child.TUFLOW_TYPE in (const.CONTROLFILE.BLOCK, const.CONTROLFILE.BC_BLOCK)
    )
    return (inp.command().original_text, tuple(repr(scope) for scope in inp.scope), blocks)


def _source_signature(cf: ControlFileBuildState, source: PathLike) -> tuple:
    """Describe one physical source in the existing flattened include model."""
    main = _path_key(source) == _path_key(cf.fpath)
    signature = []
    seen_trds = set()
    for inp in cf.inputs.inputs(include_hidden=True):
        if main and inp.trd is not None:
            key = _path_key(inp.trd)
            if key not in seen_trds:
                seen_trds.add(key)
                ref = inp.trd_input
                signature.append(('read-file', key, _input_signature(ref) if ref is not None else None))
        elif (main and inp.trd is None) or (inp.trd is not None and _path_key(inp.trd) == _path_key(source)):
            signature.append(_input_signature(inp))
    return tuple(signature)


@dataclass(frozen=True)
class _SourceText:
    data: bytes
    signature: tuple

    def encode(self, text: str, signature: tuple) -> bytes:
        if signature == self.signature:
            return self.data
        # The parser and writer work with LF.  Restore the source convention
        # once, including absence of a final newline.  Mixed files are copied
        # exactly when unchanged; an edited mixed file uses its first newline.
        match = re.search(br'\r\n|\r|\n', self.data)
        newline = match.group().decode('ascii') if match else '\n'
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        if not self.data.endswith((b'\n', b'\r')):
            text = text.removesuffix('\n')
        bom = b'\xef\xbb\xbf' if self.data.startswith(b'\xef\xbb\xbf') else b''
        return bom + text.replace('\n', newline).encode('utf-8', errors='surrogateescape')


class ModelSaveError(RuntimeError):
    """A replacement failed; inspect recovery_paths if rollback was incomplete.

    Live objects retain their pre-save paths and pending history.  Each entry in
    recovery_paths maps an unrestored destination to a retained copy of its
    original bytes.  An unrestored new destination has no original backup.
    """

    def __init__(self, failed_destination: Path, replaced_paths: tuple[Path, ...],
                 unrestored_paths: tuple[Path, ...], recovery_paths: dict[Path, Path]):
        self.failed_destination = failed_destination
        self.replaced_paths = replaced_paths
        self.unrestored_paths = unrestored_paths
        self.recovery_paths = recovery_paths
        copies = ', '.join(f'{destination} -> {backup}'
                           for destination, backup in recovery_paths.items()) or 'none'
        outcome = 'original destinations restored' if not unrestored_paths else (
            f'rollback incomplete for {", ".join(map(str, unrestored_paths))}; '
            f'recovery copies: {copies}'
        )
        super().__init__(f'Model save failed replacing {failed_destination}: {outcome}. '
                         'Pending model changes and history have been retained.')


def _remove_temporary(path: Path | None, error: BaseException | None = None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as cleanup_error:
        message = f'Could not remove save temporary file {path}: {cleanup_error}'
        if error is not None:
            error.add_note(message)
        else:
            logger.warning(message)


def _stage_bytes(destination: Path, data: bytes) -> Path:
    """Fully write and close a temporary file on the destination filesystem."""
    fd, name = tempfile.mkstemp(prefix=f'.{destination.name}.pytuflow-', suffix='.tmp',
                                dir=destination.parent)
    staged = Path(name)
    try:
        try:
            stream = os.fdopen(fd, 'wb')
        except BaseException:
            os.close(fd)
            raise
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException as error:
        _remove_temporary(staged, error)
        raise
    return staged


@dataclass
class _SaveOutput:
    owner: ControlFileBuildState | DatabaseBuildState
    source: Path
    destination: Path
    inputs: Inputs | None = None
    data: bytes | None = None
    source_text: _SourceText | None = None
    signature: tuple = ()
    staged: Path | None = None
    backup: Path | None = None


class _SaveTransaction:
    """Plan on detached objects; publish disk and object state in that order.

    Each os.replace is atomic on a supporting filesystem.  The complete model
    is not an atomic transaction and there is no crash/power-loss guarantee.
    Backups support recovery from exceptions during the replacement sequence.
    """

    _INPUT_FIELDS = (
        '_command', 'config', 'part_count', 'resolved', '_has_variable',
        '_files', '_rhs_files', '_file_to_original', '_file_to_scope',
        '_files_loaded', '_has_missing_files', '_cf_loaded_paths', '_database_loaded_paths',
    )

    def __init__(self, root: ControlFileBuildState):
        self.originals: dict[int, object] = {}
        self.copies: dict[int, object] = {}
        self.reverse: dict[int, object] = {}
        self.outputs: list[_SaveOutput] = []
        self.assigned: dict[int, Path] = {}
        self.moves: dict[str, Path] = {}
        self.saved: set[int] = set()
        self.root = self._clone_control(root, None)

    def _remember(self, original, detached):
        self.originals[id(original)] = original
        self.copies[id(original)] = detached
        self.reverse[id(detached)] = original
        return detached

    @staticmethod
    def _copy_config(config):
        detached = from_config(config)
        if isinstance(detached.variables, dict):
            detached.variables = detached.variables.copy()
        return detached

    def _clone_control(self, original, parent):
        if id(original) in self.copies:
            return self.copies[id(original)]
        detached = self._remember(original, copy(original))
        detached.parent = parent
        detached.config = self._copy_config(original.config)
        detached.altered_inputs = AlteredInputs()
        if isinstance(original, DatabaseBuildState):
            detached._df = original._df.copy(deep=True)
            return detached
        detached._scope = _copy_scopes(original._scope)
        detached._source_texts = original._source_texts.copy()
        detached.inputs = Inputs([
            self._clone_input(inp, detached, original)
            for inp in original.inputs.inputs(include_hidden=True)
        ])
        detached._read_file_inputs = [
            self._clone_input(inp, detached, original) for inp in original._read_file_inputs
        ]
        if getattr(original, 'parent_input', None) is not None:
            detached.parent_input = self.copies[id(original.parent_input)]
        return detached

    def _clone_input(self, original, parent, source_owner):
        if id(original) in self.copies:
            return self.copies[id(original)]
        detached = self._remember(original, copy(original))
        detached.parent = parent
        # EventDatabase's deepcopy only copies its mapping and drops event
        # inputs.  Keep configuration semantics and detach the mutable command
        # pieces used by rendering/reload explicitly instead.
        detached._command = copy(original.command())
        detached._command.config = self._copy_config(original.command().config)
        detached._command._expander = deepcopy(original.command()._expander)
        detached._command._expander.variables = detached._command.config.variables
        detached._command._define_blocks = deepcopy(original.command().define_blocks)
        if hasattr(original.command(), 'fv_blocks'):
            detached._command.fv_blocks = list(original.command().fv_blocks)
        detached.config = detached._command.config
        detached._scope = _copy_scopes(original.scope)
        for key, value in original.__dict__.items():
            if key in self._INPUT_FIELDS and isinstance(value, (list, dict)):
                setattr(detached, key, value.copy())
        # rhs/lhs edits currently reinitialise an input.  Recover its original
        # source ownership without changing the editing/undo implementation.
        ownership = source_owner._save_source_owners.get(id(original))
        if ownership and original.uuid != ownership[0] and original.trd is None:
            detached.trd, detached.trd_input = ownership[1:]
        if detached.trd_input is not None:
            detached.trd_input = self._clone_input(detached.trd_input, parent, source_owner)
        detached.cf = [self._clone_control(child, parent) for child in original.cf or ()]
        return detached

    @staticmethod
    def _set_reference(inp: InputBuildState, value: PathLike) -> None:
        """Update only a detached command, retaining child identity and scopes."""
        command = inp.command()
        value = str(value)
        if command.value_orig == value:
            return
        leading = ''.join(re.findall(r'^\n*', command.original_text))
        text = f'{leading}{command.leading_whitespace}{command.command_orig} == {value}'
        command.original_text = command.re_add_comments(text, True)
        command.value_orig = value
        command.reload_value()
        inp.part_count = command.part_count
        inp.resolved = '<<' not in str(command.value)

    def _assign(self, owner, source: Path, destination: Path) -> bool:
        if id(owner) in self.assigned:
            if _path_key(self.assigned[id(owner)]) != _path_key(destination):
                raise ValueError(f'One save owner has conflicting destinations: {source}')
            return False
        self.assigned[id(owner)] = destination
        self.moves[_path_key(source)] = destination
        return True

    def _plan_children(self, owner: ControlFileBuildState, inc: str | None) -> None:
        self.saved.add(id(owner))
        for inp in owner.inputs.inputs(include_hidden=True):
            self.saved.add(id(inp))
            if inp.TUFLOW_TYPE in (const.INPUT.BLOCK, const.INPUT.BC_BLOCK, const.INPUT.GRID_DEFINITION_FILE_INPUT):
                for child in inp.cf:
                    self._plan_children(child, inc)
            elif inp.dirty and any(isinstance(child, (ControlFileBuildState, DatabaseBuildState))
                                   for child in inp.cf):
                increment_reference = bool(inp.cf) and all(child.loaded for child in inp.cf)
                for index, child in enumerate(inp.cf):
                    if isinstance(child, DatabaseBuildState):
                        source = Path(child.fpath).absolute()
                        destination = _increment(source, inc) if child.loaded else source
                        if self._assign(child, source, destination):
                            child.fpath = destination
                            self.saved.add(id(child))
                            self.outputs.append(_SaveOutput(child, source, destination))
                    else:
                        self._plan_control(child, inc)
                    # Constructors can canonicalise child.fpath while these
                    # aligned indexes retain a directory alias.  Keep that
                    # lexical spelling and advance its filename too, without
                    # probing or reloading the owned child.
                    index_name = ('_database_loaded_paths' if isinstance(child, DatabaseBuildState)
                                  else '_cf_loaded_paths')
                    loaded_paths = getattr(inp, index_name, ())
                    if index < len(loaded_paths):
                        lexical_source = Path(loaded_paths[index]).absolute()
                        lexical_destination = (_increment(lexical_source, inc)
                                               if child.loaded else lexical_source)
                        self.moves.setdefault(_path_key(lexical_source), lexical_destination)
                if increment_reference:
                    self._set_reference(inp, _increment(inp.rhs, inc))

    def _plan_control(self, owner: ControlFileBuildState, inc: str | None) -> None:
        if owner.fpath is None or owner.fpath == Path():
            raise ValueError('Control file path is not set; provide fpath before writing.')
        source = Path(owner.fpath).absolute()
        destination = _increment(source, inc) if owner.loaded else source
        if not self._assign(owner, source, destination):
            return
        owner._fpath = destination
        child_inc = None if inc is None else get_iter_number(destination.stem, get_geom_suffix(destination.stem))
        self._plan_children(owner, child_inc)
        inputs, trds = owner._get_trd_inputs(owner)
        for trd_path, details in trds.items():
            trd_source = Path(trd_path).absolute()
            trd_inputs = details['inputs']
            source_text = owner._source_texts.get(_path_key(trd_source))
            signature = _source_signature(owner, trd_source)
            changed = source_text is None or signature != source_text.signature
            source_exists = _path_exists(trd_source)
            if source_exists and not changed and not any(inp.dirty for inp in trd_inputs):
                continue
            target = _increment(trd_source, child_inc) if source_exists else trd_source
            self.moves[_path_key(trd_source)] = target
            ref = details['inpref']
            self._set_reference(ref, _increment(ref.rhs, child_inc) if source_exists else ref.rhs)
            updated_refs = set()
            for inp in trd_inputs.inputs(include_hidden=True):
                inp.trd = target
                if inp.trd_input is not None and id(inp.trd_input) not in updated_refs:
                    updated_refs.add(id(inp.trd_input))
                    if source_exists:
                        self._set_reference(inp.trd_input, _increment(inp.trd_input.rhs, child_inc))
            self.outputs.append(_SaveOutput(owner, trd_source, target, trd_inputs,
                                           source_text=source_text))
        self.outputs.append(_SaveOutput(owner, source, destination, inputs,
                                       source_text=owner._source_texts.get(_path_key(source))))

    def _map_path(self, value):
        if value is None or str(value) in ('', '.'):
            return value
        mapped = self.moves.get(_path_key(value))
        return mapped if mapped is not None else value

    def _prepare_objects(self) -> None:
        for detached in self.copies.values():
            detached.config.control_file = self._map_path(detached.config.control_file)
            detached.config.tcf = self._map_path(detached.config.tcf)
            if not isinstance(detached, InputBuildState):
                if isinstance(detached, ControlFileBuildState):
                    detached._fpath = self._map_path(detached.fpath)
                continue
            command = detached.command()
            command.parent = self._map_path(command.parent)
            command.config.control_file = self._map_path(command.config.control_file)
            command.config.tcf = self._map_path(command.config.tcf)
            command.value_expanded_path = self._map_path(command.value_expanded_path)
            for name in ('_files', '_rhs_files', '_cf_loaded_paths', '_database_loaded_paths'):
                if hasattr(detached, name):
                    setattr(detached, name, [self._map_path(path) for path in getattr(detached, name)])
            detached._file_to_original = {
                self._map_path(path): self._map_path(pattern)
                for path, pattern in detached._file_to_original.items()
            }
            detached._file_to_scope = {
                str(self._map_path(path)): scopes for path, scopes in detached._file_to_scope.items()
            }

    def _validate_destinations(self) -> None:
        destinations = {}
        parent_destinations = set()
        identities = {}
        sources = {}
        for original in self.originals.values():
            if isinstance(original, (ControlFileBuildState, DatabaseBuildState)) and original.fpath:
                if original.TUFLOW_TYPE not in (const.CONTROLFILE.BLOCK, const.CONTROLFILE.BC_BLOCK):
                    sources.setdefault(_path_key(original.fpath), set()).add(id(original))
            if isinstance(original, ControlFileBuildState):
                for key in original._source_texts:
                    sources.setdefault(key, set()).add(id(original))
        for output in self.outputs:
            destination = output.destination
            key = _path_key(destination)
            if key in destinations:
                raise ValueError(f'Duplicate save destination: {destination}')
            destinations[key] = output
            if key != _path_key(output.source) and key in sources:
                raise ValueError(f'Save destination would overwrite another source: {destination}')
            try:
                info = destination.lstat()
            except FileNotFoundError:
                info = None
            if info is not None and stat.S_ISLNK(info.st_mode):
                raise ValueError(f'Save destination is a symbolic link: {destination}')
            parent_info = destination.parent.stat()
            parent_destination = (parent_info.st_dev, parent_info.st_ino,
                                  os.path.normcase(destination.name))
            if parent_info.st_ino and parent_destination in parent_destinations:
                raise ValueError(f'Duplicate physical save destination through a directory alias: {destination}')
            parent_destinations.add(parent_destination)
            if info is not None:
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError(f'Save destination is not a regular file: {destination}')
                if not info.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                    raise PermissionError(f'Save destination is read-only: {destination}')
                identity = (info.st_dev, info.st_ino)
                if info.st_ino and identity in identities:
                    raise ValueError(f'Duplicate physical save destination: {destination}')
                identities[identity] = destination
            if output.source_text is not None and _path_exists(output.source):
                if output.source.read_bytes() != output.source_text.data:
                    raise ValueError(f'Source changed on disk since loading: {output.source}')

    def _render(self) -> None:
        for output in self.outputs:
            if output.inputs is None:
                continue  # Database subclasses render to their staging path.
            output.signature = _source_signature(output.owner, output.destination)
            if output.source_text is None or output.signature != output.source_text.signature:
                self._check_include_representation(output.owner)
            buffer = io.StringIO()
            output.owner._write(buffer, output.inputs)
            if output.source_text is not None:
                output.data = output.source_text.encode(buffer.getvalue(), output.signature)
            else:
                output.data = buffer.getvalue().encode('utf-8', errors='surrogateescape')
            output.owner._source_texts.pop(_path_key(output.source), None)
            output.owner._source_texts[_path_key(output.destination)] = _SourceText(output.data, output.signature)

    @staticmethod
    def _check_include_representation(owner: ControlFileBuildState) -> None:
        # Ordered/empty/scoped include editing belongs to W6.  Until that
        # representation exists, fail before publication instead of dropping
        # a directive or merging distinct occurrences during an edited save.
        represented = set()
        paths = {}
        unsupported = False
        for inp in owner.inputs.inputs(include_hidden=True):
            if inp.trd is not None:
                represented.add(id(inp.trd_input))
                key = _path_key(inp.trd)
                if key in paths and paths[key] is not inp.trd_input:
                    unsupported = True
                paths[key] = inp.trd_input
        for ref in owner._read_file_inputs:
            if id(ref) not in represented or ScopeWriter.input_scope(ref):
                unsupported = True
        if unsupported:
            raise ValueError(
                f'Cannot safely edit {owner.fpath}: empty, missing, repeated or scoped Read File '
                'directives are not representable by the current flattened include writer. '
                'Original files are unchanged; ordered include editing is deferred to W6 / PR #21.'
            )

    def _stage(self) -> None:
        for output in self.outputs:
            output.staged = _stage_bytes(output.destination, output.data or b'')
            if output.inputs is None:
                database = output.owner
                database.fpath = output.staged
                try:
                    database.write('inplace')
                    with output.staged.open('r+b') as stream:
                        os.fsync(stream.fileno())
                finally:
                    database.fpath = output.destination
            mode_source = output.destination if _path_exists(output.destination) else output.source
            if _path_exists(mode_source):
                os.chmod(output.staged, stat.S_IMODE(mode_source.stat().st_mode))
        # Back up every existing destination before the first replacement.
        for output in self.outputs:
            if _path_exists(output.destination):
                output.backup = _stage_bytes(output.destination, output.destination.read_bytes())
                shutil.copystat(output.destination, output.backup)

    def _replace(self) -> None:
        replaced = []
        try:
            for output in self.outputs:
                os.replace(output.staged, output.destination)
                replaced.append(output)
        except BaseException as error:
            # A network filesystem can complete a rename and then lose the
            # acknowledgement.  Check the attempted target as well as the
            # replacements whose calls returned successfully.  If inspection
            # fails, attempt recovery conservatively and retain its backup if
            # that also fails.
            try:
                if output.backup is None:
                    output.destination.stat()
                    attempted_changed = True
                else:
                    attempted_changed = output.destination.read_bytes() != output.backup.read_bytes()
            except FileNotFoundError:
                attempted_changed = output.backup is not None
            except OSError:
                attempted_changed = True
            if attempted_changed:
                replaced.append(output)
            unrestored = []
            recovery = {}
            for completed in reversed(replaced):
                backup_bytes = None
                try:
                    if completed.backup is None:
                        completed.destination.unlink()
                    else:
                        backup_bytes = completed.backup.read_bytes()
                        os.replace(completed.backup, completed.destination)
                except OSError as rollback_error:
                    # A rollback can also succeed before its acknowledgement
                    # is lost.  Do not report a consumed backup as recoverable.
                    try:
                        if completed.backup is None:
                            try:
                                completed.destination.stat()
                            except FileNotFoundError:
                                restored = True
                            else:
                                restored = False
                        else:
                            restored = backup_bytes is not None and completed.destination.read_bytes() == backup_bytes
                    except OSError:
                        restored = False
                    if restored:
                        continue
                    unrestored.append(completed.destination)
                    if completed.backup is not None:
                        # Remove this backup from ordinary cleanup before
                        # inspecting it.  A stat error is not proof of absence
                        # and must never discard an original recovery copy.
                        backup = completed.backup
                        completed.backup = None
                        try:
                            backup.stat()
                        except FileNotFoundError:
                            backup = None
                            if backup_bytes is not None:
                                try:
                                    backup = _stage_bytes(completed.destination, backup_bytes)
                                except OSError as recovery_error:
                                    error.add_note(f'Could not recreate recovery copy: {recovery_error}')
                        except OSError as inspection_error:
                            error.add_note(f'Could not inspect recovery copy {backup}; '
                                           f'retaining it: {inspection_error}')
                        if backup is not None:
                            recovery[completed.destination] = backup
                    error.add_note(f'Rollback failed for {completed.destination}: {rollback_error}')
            raise ModelSaveError(output.destination, tuple(item.destination for item in replaced),
                                 tuple(unrestored), recovery) from error

    def _state_updates(self) -> list[tuple[object, dict]]:
        updates = []
        for original_id, detached in self.copies.items():
            original = self.originals[original_id]
            if isinstance(detached, InputBuildState):
                values = {name: getattr(detached, name) for name in self._INPUT_FIELDS if hasattr(detached, name)}
                values['trd'] = detached.trd
                values['trd_input'] = self.reverse.get(id(detached.trd_input), detached.trd_input)
            elif isinstance(detached, ControlFileBuildState):
                values = {'_fpath': detached.fpath, 'config': detached.config,
                          '_source_texts': detached._source_texts,
                          '_save_source_owners': {
                              id(self.reverse[id(inp)]): (inp.uuid, inp.trd,
                                  self.reverse.get(id(inp.trd_input), inp.trd_input))
                              for inp in detached.inputs.inputs(include_hidden=True)
                          }}
            else:
                values = {'_fpath': detached.fpath, 'config': detached.config}
            if id(detached) in self.saved:
                values['_dirty'] = False
                if id(detached) in self.assigned:
                    values['loaded'] = True
                if hasattr(original, 'altered_inputs'):
                    # Retain previous undo blocks, exactly as clear() does,
                    # without calling setters on unsaved siblings.
                    updates.append((original.altered_inputs,
                                    {'_updated_inputs': original.altered_inputs._updated_inputs + [[]]}))
            updates.append((original, values))
        return updates

    def save(self, inc: str | None) -> None:
        self._plan_control(self.root, inc)
        self._validate_destinations()
        self._prepare_objects()
        self._render()
        updates = self._state_updates()
        try:
            self._stage()
            self._replace()
        except BaseException as error:
            for output in self.outputs:
                _remove_temporary(output.staged, error)
                _remove_temporary(output.backup, error)
            raise
        # Prepared plain assignments cannot invoke setters, reload children,
        # serialise data or perform filesystem operations after publication.
        for original, values in updates:
            original.__dict__.update(values)
        for output in self.outputs:
            _remove_temporary(output.backup)


class ControlFileBuildState(BuildState, ControlFile):
    """Initialises the class in a build state.

    If the class is initialised with the ``fpath`` parameter set to None, an empty class will be initialised.

    Parameters
    ----------
    fpath : PathLike, optional
        The path to the control file. If set to None, will initialise an empty control file.

    **kwargs : optional parameters

        - config : TCFConfig, optional
            This object stores useful information such as variable mappings, the event database,
            current spatial database etc. If set to None, a new TCFConfig object will be created.
            For TCFs, the settings object should be left as None.
        - parent : ControlFile, optional
            Will set the parent of the control file to another control file e.g. for a TGC, the parent
            should be set to the TCF. For TCFs, the parent should be set to None.
        - scope : ScopeList, optional
            A list of scope objects that will be inherited by the control file itself. Not currently used
            but reserved in case this is useful information in the future.
        - log_level : str, optional
            The logging level to use for the control file. Options are 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'.
            Default is 'WARNING'.
        - log_to_file : PathLike, optional
            If set, will log the control file to the given file path. Default is None.
    """
    TUFLOW_TYPE = 'ControlFile'

    def __init__(self,
                 path: PathLike = None,
                 config: TCFConfig = None,
                 parent: ControlFile = None,
                 scope: ScopeList = None,
                 **kwargs) -> None:
        super(BuildState, self).__init__()
        #: TCFConfig: The configuration settings for the model.
        self.config = from_config(config) if config is not None else TCFConfig()
        if path is not None:
            self.config.control_file = Path(path)
        #: Inputs: The list of inputs and comments in the control file
        self.inputs = Inputs[InputBuildState]()
        #: ControlFile: The parent control file
        self.parent = parent
        #: AlteredInputs: The list of all changes made to the control file since the last time :meth:`write` was called.
        self.altered_inputs = AlteredInputs()
        #: bool: Whether the control file has been loaded from disk or not.
        self.loaded = False

        self._fpath = Path(path).resolve() if path is not None else None
        self._source_texts = {}
        self._save_source_owners = {}
        self._read_file_inputs = []
        self._dirty = False
        self._active_trd = None  # the active TRD file that is being loaded
        self._active_trd_inp = None
        self._scope = scope if scope is not None else ScopeList()
        
        if self.fpath:
            try:
                self._load(path)
                self.loaded = True
            except FileNotFoundError:
                pass

    def __repr__(self):
        return f'<{self.TUFLOW_TYPE}> {str(self)}'

    def __str__(self):
        if self.fpath:
            if self.loaded:
                return self.fpath.name
            else:
                return f'{self.fpath.name} (not found)'
        return 'Empty Control File'

    @property
    def fpath(self) -> Path:
        """Path: The path to the control file."""
        return self._fpath

    @fpath.setter
    def fpath(self, value: PathLike):
        value = Path(value)
        self._fpath = value
        self.config.control_file = value
        if self.TUFLOW_TYPE == self._parent_tuflow_type() and self.root_cf == self:
            self.config.tcf = value
            for inp in self.inputs:
                inp.config.control_file = value
                for cf in inp.cf:
                    cf.config.tcf = self.config.tcf
                    if inp.TUFLOW_TYPE == const.INPUT.CF:
                        for inp1 in cf.inputs:
                            inp1.config.tcf = self.config.tcf

    def context(self,
                run_context: str | dict[str, str] = '',
                context: Context | None = None,
                parent: 'ControlFileRunState | None' = None) -> 'ControlFileRunState':
        # docstring inherited
        from .cf_run_state import ControlFileRunState
        ctx = context if context else Context(run_context, config=self.config)
        return ControlFileRunState(self, ctx, parent)

    def figure_out_file_scopes(self, scope_list: ScopeList) -> None:
        """no-doc

        Overrides abstract method from BuildState.

        Try and resolve unknown scope variable values based on a known scope list. Not currently connected to anything
        (previously was connected to the load method).

        This method is designed to trickle through all
        BuildState objects and figure out scope definitions when scenarios/variables are used in the file names, and the
        scope is guessed based on the file name and any files it found

        e.g. ``M01_<<s1>>_001.tgc`` - ``M01_5m_001.tgc`` - would guess that the file
        has a ``Scope(Scenario, '5m')``

        Parameters
        ----------
        scope_list: ScopeList
            list of known scopes
        """
        for input_ in self.inputs:
            input_.figure_out_file_scopes(scope_list)

    def record_change(self, inputs: Inputs | DatabaseBuildState, change_type: str):
        """no-doc

        Record a user change to the inputs.

        Not private, but should not be called by the user.

        Parameters
        ----------
        inputs : Inputs
            A list of inputs that have been changed.
        change_type : str
            the type of change that has been made. This is used to determine what to do when storing and
            undoing the change. See AlteredInputs class for change_type options.
        """
        uuid = uuid4()  # allows input changes to be grouped together by giving the same uuid
        if isinstance(inputs, Inputs):
            for inp, ind in inputs.iter_indexes():
                inp.dirty = True
                self.dirty = True
                self.root_cf.dirty = True
                self.root_cf.altered_inputs.add(inp, ind[0], ind[1], uuid, change_type)
        elif isinstance(inputs, DatabaseBuildState):
            self.root_cf.altered_inputs.add(inputs, -1, -1, uuid, 'database')

    def undo(self, include_children: bool = True) -> list[AlteredInput]:
        """Undo the last recorded change. Recorded changes are automatically stored when inputs are changed, added,
        or removed from the control file. The :attr:`dirty` attribute can be checked to see if any changes have
        been made to the control file since the last call to :meth:`write`.

        Note, the returned list of inputs is stored as a :class:`AlteredInput`, which is different from the
        input class used to store the inputs in the control file.

        Parameters
        ----------
        include_children : bool, optional
            This is only applicable for the TCF class. If set to ``True``, will undo the last change regardless if it
            was made in the current control file or a child. If set to ``False``, will only undo the
            last change in the current control file.

        Returns
        -------
        list[AlteredInput]
            A list of inputs that were changed by the undo operation. If no
            changes were made, an empty list is returned.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Scheme == HPC
           Hardware == GPU
           SGS == On

        The following code comments out the SGS input then uses the ``undo`` method to revert the change:

        >>> cf = ... # assume this is the loaded control file object
        >>> sgs_inp = cf.find_input('SGS == On')[0]
        >>> cf.comment_out(sgs_inp)
        <CommentInput> ! SGS == On

        Preview the content of the control file to confirm that the SGS input has been commented out:

        >>> cf.preview()
        ! Control File
        Solution Scheme == HPC
        Hardware == GPU
        ! SGS == On

        Undo the previous operation to uncomment the SGS input:

        >>> cf.undo()
        [<AlteredInput comment_out> ! SGS == On]
        >>> cf.preview()
        ! Control File
        Solution Scheme == HPC
        Hardware == GPU
        SGS == On
        """
        if self.root_cf != self and include_children:
            include_children = False
        return self.root_cf.altered_inputs.undo(self, include_children)

    def reset(self, include_children: bool = True) -> list[AlteredInput]:
        """Resets all recorded changes made to the control file since the last call to :meth:`write`.
        Recorded changes are automatically stored when inputs are changed, added,
        or removed from the control file. The :attr:`dirty` attribute can be checked to see if any changes have
        been made to the control file since the last call to :meth:`write`.

        Note, the returned list of inputs are stored as :class:`AlteredInput`, which is different from the
        input class used to store the inputs in the control file.

        Parameters
        ----------
        include_children : bool
            Only applicable for the TCF class. If set to ``True``, will reset changes regardless of whether they
            were made in the current control file or a child. If set to ``False``, will only reset the
            changes in the current control file.

        Returns
        -------
        list[AlteredInput]
            A list of inputs that were reset by the reset operation. If no
            changes were made, an empty list is returned.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Scheme == HPC
           Hardware == GPU
           SGS == On

        The following code comments out the SGS input and sets the hardware command to ``CPU``.
        It then uses the ``reset`` method to revert all the changes:

        >>> cf = ... # assume this is the loaded control file object
        >>> sgs_inp = cf.find_input('SGS == On')[0]
        >>> cf.comment_out(sgs_inp)
        <CommentInput> ! SGS == On
        >>> hardware_inp = cf.find_input('Hardware == GPU')[0]
        >>> hardware_inp.rhs = 'CPU'

        Preview the content of the control file to confirm that the SGS input has been commented out and the
        hardware input has been changed to ``CPU``:

        >>> cf.preview()
        ! Control File
        Solution Scheme == HPC
        Hardware == CPU
        ! SGS == On

        Reset all operations to take the control file back to its original state:

        >>> cf.reset()
        [<AlteredInput update_value> Hardware == GPU, <AlteredInput comment_out> ! SGS == On]
        >>> cf.preview()
        ! Control File
        Solution Scheme == HPC
        Hardware == GPU
        SGS == On

        """
        if self.root_cf != self and include_children:
            include_children = False
        return self.root_cf.altered_inputs.reset(self, include_children)

    def remove_input(self, inp: InputBuildState) -> InputBuildState | None:
        """Removes the input from the control file.

        Parameters
        ----------
        inp : InputBuildState
            The input to remove from the control file.

        Returns
        -------
        InputBuildState
            The input that was removed. If the method returns ``None``, no input was removed.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Scheme == HPC
           Hardware == GPU
           SGS == On

        The following code removes the SGS input from the control file:

        >>> control_file = ... # assume this is the loaded control file object
        >>> sgs_inp = control_file.find_input('SGS == On')[0]
        >>> control_file.remove_input(sgs_inp)
        <SettingInput> SGS == On

        The content of the control file can be previewed using :meth:`preview` to confirm
        that the SGS command has been removed:

        >>> cf.preview()
        ! Control File
        Solution Scheme == HPC
        Hardware == GPU
        """
        # The input must belong to this exact owner. Input.__eq__ compares
        # command text, so equal commands in siblings are not interchangeable.
        if inp.parent is self and any(current is inp for current in self.inputs):
            inputs = Inputs()
            inputs.append(inp)
            # Inputs.remove() also matches by text. Remove the same instance
            # from both the complete and visible views of this Inputs object.
            all_inputs = self.inputs.inputs(include_hidden=True)
            all_inputs.pop(next(i for i, current in enumerate(all_inputs) if current is inp))
            list.pop(self.inputs, next(i for i, current in enumerate(self.inputs) if current is inp))
            self.record_change(inputs, 'remove_input')
            if self.root_cf and self.root_cf != self:
                self.root_cf.record_change(inputs, 'remove_input')
            return inp
        else:
            for inp1 in self.inputs:
                if inp1.TUFLOW_TYPE == const.INPUT.CF and inp1.cf:
                    for cf in inp1.cf:
                        inp2 = cf.remove_input(inp)
                        if inp2:
                            return inp2
        return None

    def append_input(self, input_text: str | T_Input, gap: int = 0) -> T_Input:
        """Appends a new input to the end of the control file.

        Parameters
        ----------
        input_text : str | T_Input
            The input text to add to the control file (i.e. the TUFLOW command). Leading whitespace will be
            respected. However, the input will be indented automatically depending on its scope and generally
            is not required to be considered by the user in the input text.

            Alternatively, an existing input instance can be passed in. If the input does not already exist
            in the control file, the input instance will be added directly. If the input already exists within
            the control file, a copy of the input will be made and added.
        gap : int, optional
            The number of blank lines to add before the new input. This has no impact on the TUFLOW model, but
            can be useful for readability of the control file when it is written to disk. Default is 0.

        Returns
        -------
        T_Input
            The input that was added. The input type will be determined by the ``input_text`` string e.g. if the
            text is ``Read GIS Z Shape == ...``, then the return input will be of type :class:`GisInput`.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Sceme == HPC
           Hardware == GPU

        The following code appends a new input to the end of the control file:

        >>> cf = ... # assume this is the loaded control file object
        >>> inp = cf.append_input('SGS == On')
        >>> inp
        <SettingInput> SGS == On

        The content of the control file can be previewed using :meth:`preview`:

        >>> cf.preview()
        Solution Scheme == HPC
        Hardware == GPU
        SGS == On

        The new input is not written to disk until :meth:`write` is called. :meth:`undo` can be used
        to revert the last change made to the control file, which in this case would remove the new command.
        """
        return self._add_input(None, input_text, True, gap)

    def insert_input(self, ref_inp: T_Input, input_text: str | T_Input, after: bool = False, gap: int = 0) -> InputBuildState:
        """Inserts an input before, or after, another reference input.

        Parameters
        ----------
        ref_inp : InputBuildState
            The input to place the new command before, or after.
        input_text : str
            The input text to add to the control file (i.e. the TUFLOW command). Leading whitespace will be
            respected. However, the input will be indented automatically depending on its scope and generally
            is not required to be considered by the user in the input text.

            Alternatively, an existing input instance can be passed in. If the input does not already exist
            in the control file, the input instance will be added directly. If the input already exists within
            the control file, a copy of the input will be made and added.
        after : bool, optional
            If True, the new input will be inserted after the referenced input, if set to False, the new
            input will be inserted before. Default is False.
        gap : int, optional
            The number of blank lines to add before, or after (depending on the ``after`` parameter),
            the new input. This has no impact on the TUFLOW model, but can be useful for readability
            of the control file when it is written to disk. Default is 0.

        Returns
        -------
        InputBuildState
            The input that was added. The input type will be determined by the ``input_text`` string e.g. if the
            text is ``Read GIS Z Shape == ...``, then the return input will be of type :class:`GisInput`.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Hardware == GPU
           SGS == On

        The following code inserts a new input to the top of the control file, before the first input:

        >>> cf = ... # assume this is the loaded control file object
        >>> inp = cf.inputs[0]
        >>> new_inp = cf.insert_input(inp, 'Solution Scheme == HPC')
        >>> ref_inp
        <SettingInput> Solution Scheme == HPC

        The content of the control file can be previewed using :meth:`preview`:

        >>> cf.preview()
        Solution Scheme == HPC
        Hardware == GPU
        SGS == On

        The new input is not written to disk until :meth:`write` is called. :meth:`undo` can be used
        to revert the last change made to the control file, which in this case would remove the new command.
        """
        return self._add_input(ref_inp, input_text, after, gap)

    def comment_out(self, inp: InputBuildState) -> CommentInput:
        """Comments out a given input. This has the same effect as :meth:`remove_input`, but keeps the input
        in the control file as a comment. The input can be uncommnented later using the :meth:`uncomment` method.
        Comments can also still be searched for within the control file using the :meth:`find_input` method.

        The input is not mutated, rather a new input is created and replaces the original input in the control file.
        Further reference to the input should use the returned input. The commented out input
        retains the same UUID.

        Parameters
        ----------
        inp : InputBuildState
            The input to comment out.

        Returns
        -------
        CommentInput
            The commented out input.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Scheme == HPC
           Hardware == GPU
           SGS == On

        The following code comments out the SGS input:

        >>> cf = ... # assume this is the loaded control file object
        >>> sgs_inp = cf.find_input('SGS == On')[0]
        >>> commented_inp = cf.comment_out(sgs_inp)
        >>> commented_inp
        <CommentInput> ! SGS == On

        The content of the control file can be previewed using :meth:`preview`:

        >>> cf.preview()
        Solution Scheme == HPC
        Hardware == GPU
        ! SGS == On

        The new input is not written to disk until :meth:`write` is called. :meth:`undo` can be used
        to revert the last change made to the control file, which in this case would be to uncomment the given input.
        """
        new_inp = self._comment_out(inp)
        inputs = Inputs()
        inputs.append(new_inp)
        self.record_change(inputs, 'comment_out')
        if self.root_cf and self.root_cf != self:
            self.root_cf.record_change(inputs, 'comment_out')
        return new_inp

    def uncomment(self, inp: CommentInput) -> InputBuildState:
        """Uncomment a given input.

        The input is not mutated, rather a new input is created and replaces the original input in the control file.
        Further reference to the input should use the returned input. The new input
        retains the same UUID as the original input.

        Parameters
        ----------
        inp : CommentInput
            the input to uncomment

        Returns
        -------
        InputBuildState
            The new input

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Scheme == HPC
           Hardware == GPU
           ! SGS == On

        The following code uncomments the SGS input:

        >>> cf = ... # assume this is the loaded control file object
        >>> commented_inp = cf.find_input('sgs == on', comments=True)[0]
        >>> cf.uncomment(commented_inp)
        <SettingInput> SGS == On

        The content of the control file can be previewed using :meth:`preview` to confirm that the SGS input
        has been uncommented:

        >>> cf.preview()
        Solution Scheme == HPC
        Hardware == GPU
        SGS == On
        """
        new_inp = self._uncomment(inp)
        inputs = Inputs()
        inputs.append(new_inp)
        self.record_change(inputs, 'uncomment')
        if self.root_cf and self.root_cf != self:
            self.root_cf.record_change(inputs, 'uncomment')
        return new_inp

    def write(self, inc: str | None = 'auto') -> 'ControlFileBuildState':
        """Write the object to file. From the TCF class, other control files will also be written if
        their ``dirty`` attribute is returned as ``True``.

        Parameters
        ----------
        inc : str, optional
            The increment method to use. The options are:

            * ``"auto"`` - (default) automatically increment the file name by adding +1 to the number at the end of the file name.
              If the file name does not contain a number, it will be added as "001". The increment number from the
              calling class will be used when writing children. E.g. if the TCF is automatically incremented to
              "100", the TGC increment number will be set to "100" regardless of the current number
              in the TGC file name.
            * ``[str]`` - a user defined suffix to add to the file name. This will replace the existing suffix number if
              the user provides a string representation of a number, otherwise it will be appended to the end of
              the file name.
            * ``"inplace"`` - overwrites the existing file without changing the file name. If called from the TCF,
              the children control files and databases can still be incremented up to the TCF increment number.
            * ``None`` - if set to None, no incrementing will take place and the file will be written without
               changing the file name, including children control files and databases. This is very similar
               to the "inplace" option, but will not increment the file name of children control files and databases.

        Returns
        -------
        ControlFileBuildState
            The control file that was written.

        Notes
        -----
        Every affected control file, read file and database is staged before
        existing destinations or live object state are changed. A replacement
        failure raises :class:`ModelSaveError` after attempting rollback; its
        ``unrestored_paths`` and ``recovery_paths`` describe incomplete recovery.
        Multiple file replacements are not globally atomic, and concurrent
        writers or process/power loss are outside this recovery contract.

        Control files use UTF-8 with surrogateescape, preserving source BOM,
        newline convention and final-newline presence. Unchanged source bytes
        are retained exactly. New files use UTF-8 without BOM and LF. Edited
        include layouts that the flattened writer cannot represent are rejected
        before writing. Direct standalone database writes are not covered by
        this control-file transaction.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Scheme == HPC
           Hardware == GPU
           SGS == On

        The following code updates the hardware command to ``CPU`` and then writes the update to disk inplace such
        that it overwrites the existing control file:

        >>> control_file = ... # assume this is the loaded control file object
        >>> hardware_inp = control_file.find_input('Hardware')[0]
        >>> hardware_inp.rhs = 'CPU'
        >>> control_file.write('inplace')
        """
        transaction = _SaveTransaction(self)
        transaction.save(inc)
        return self

    def preview(self, buf: TextIO | None = None):
        """Preview the control file in ``stdout``. This method is useful for debugging and
        checking the control file content without writing it to disk.

        Parameters
        ----------
        buf : TextIO, optional
            If provided, the control file will be written to this TextIO object instead of ``stdout``.
            If not provided, the control file will be printed to ``stdout``.

        Examples
        --------
        .. code-block:: tuflow
           :linenos:

           ! Control File
           Solution Scheme == HPC
           Hardware == GPU
           SGS == On

        The following code loads and then previews the content of the control file:

        >>> cf = ... # assume this is the loaded control file object
        >>> cf.preview()
        ! Control File
        Solution Scheme == HPC
        Hardware == GPU
        SGS == On
        """
        fo = buf if buf else io.StringIO()
        inputs, _ = self._get_trd_inputs(self)
        self._write(fo, inputs)
        if not buf:
            print(fo.getvalue())

    def add_variable(self, variable_name: str, variable_value: str):
        """no-doc

        Adds a variable to the TCFConfig settings object. This change is propagated to children.
        """
        super().add_variable(variable_name, variable_value)
        for inp in self.inputs:
            inp.add_variable(variable_name, variable_value)
            for cf in inp.cf:
                cf.add_variable(variable_name, variable_value)

    def remove_variable(self, variable_name: str):
        """no-doc

        Removes a variable from the TCFConfig settings object. This change is propagated to children.
        """
        super().remove_variable(variable_name)
        for inp in self.inputs:
            inp.remove_variable(variable_name)
            for cf in inp.cf:
                cf.remove_variable(variable_name)

    def _load(self, path: PathLike) -> None:
        """Loads control file from path - loops through commands in control file.
        Called by :meth:`__init__ <pytuflow.tmf.ControlFileBuildState.__init__>`.

        This method should not be called by the user.

        Parameters
        ----------
        path : PathLike
            The path to the control file. If set to None, will initialise an empty control file.
        """
        p = TuflowPath(path)
        if not p.exists():
            logger.error('Control file not found: {}'.format(path))
            raise FileNotFoundError(f'Control file not found: {p}')
        logger.info('Loading control file at: {}'.format(p))

        if not self.config:
            self.config = self._generate_initial_config(p)

        source_bytes = Path(p).read_bytes()
        parser = self._parser(p, self.config)
        # parser needs to be accessed in a loop like this to maintain the state of the parser for FV blocks
        while True:
            try:
                command = next(parser)
            except StopIteration:
                break
            self._append_input(command, self._active_trd, self._active_trd_inp)
        self._source_texts[_path_key(p)] = _SourceText(
            source_bytes, _source_signature(self, p),
        )

    def _parser(self, path: Path, config: TCFConfig) -> typing.Iterator[Command]:
        return get_commands(path, config)

    def _get_trd_inputs(self, cf: 'ControlFileBuildState') -> tuple[Inputs, dict[Path, dict[str, Inputs | T_Input]]]:
        """Get the inputs that are in TRD files from the control file.
        This method returns a list of input from the control file without inputs that are in TRD files and with the
        "Read File == " input inserted. It also returns a dictionary with the TRD file paths keys and the
        corresponding inputs as values.
        """
        d = OrderedDict()
        ret_inputs = Inputs()
        for inp in cf.inputs.inputs(include_hidden=True):
            if inp.trd is not None:
                if inp.trd not in d:
                    d[inp.trd] = {}
                    d[inp.trd]['inputs'] = Inputs()
                    rel_path = os.path.relpath(inp.trd, cf.fpath.parent)

                    # build TRD text complete with original inline comments
                    trd_command_text = f'{cf._trd_command_lhs()} == {rel_path}'
                    if inp.trd_input and inp.trd_input.command().comment_index:
                        cidx = inp.trd_input.command().comment_index
                        comment = inp.trd_input.command().comment
                        if len(trd_command_text) > cidx + 1:
                            trd_command_text = f'{trd_command_text}  {comment}'
                        else:
                            whitespace = cidx - len(trd_command_text)
                            trd_command_text = f'{trd_command_text}{" " * whitespace}{comment}'
                        
                    trd_inp = TuflowReadFileInput(cf, self._command_class()(trd_command_text, inp.config, line_number=inp.line_number))
                    d[inp.trd]['inpref'] = trd_inp
                    ret_inputs.append(trd_inp)
                d[inp.trd]['inputs'].append(inp)
            else:
                ret_inputs.append(inp)

        return ret_inputs, d
    
    @staticmethod
    def _trd_command_lhs() -> str:
        return 'Read File'
    
    @staticmethod
    def _generate_initial_config(path: Path) -> TCFConfig:
        return TCFConfig(path)
    
    def _command_class(self) -> type[Command]:
        return Command
    
    @staticmethod
    def _parent_tuflow_type() -> str:
        return const.CONTROLFILE.TCF

    @staticmethod
    def _write(fo: TextIO, inputs: Inputs):
        scope_writer = ScopeWriter()
        for inp, scope_writer_ in scope_writer.inputs(fo, inputs):
            inp.write(fo, scope_writer_)

    def _load_trd(self, inp: InputBuildState):
        """Inputs in read files are loaded into the current control file."""
        self._active_trd_inp = inp
        for file in inp.files:
            self._active_trd = file
            try:
                self._load(file)
            except FileNotFoundError:
                pass
        self._active_trd = None
        self._active_trd_inp = None

    def _append_input(self, cmd: Command, trd: TuflowPath | None, trd_input: T_Input | None) -> InputBuildState:
        inp = get_input_class(cmd)(self, cmd)
        if inp.command().is_read_file():
            if trd is not None:
                logger.error(f'Nested TRD files are currently not supported. Command: {inp}')
                raise ValueError(f'Nested TRD files are currently not supported. Command: {inp}')
            self._read_file_inputs.append(inp)
            self._load_trd(inp)
            return inp
        self.inputs.append(inp)
        inp.trd = trd
        inp.trd_input = trd_input
        self._save_source_owners[id(inp)] = (inp.uuid, trd, trd_input)
        self.config.spatial_database = cmd.config.spatial_database
        self.config.spatial_database_tcf = cmd.config.spatial_database_tcf
        return inp

    def _insert_input(self, ind: int, cmd: Command, trd: TuflowPath | None, after: bool, hidden_index: bool = False) -> InputBuildState:
        inp = get_input_class(cmd)(self, cmd)
        if self.inputs.inputs(include_hidden=True) and len(self.inputs.inputs(include_hidden=True)) > ind:
            self.inputs.insert(ind, inp, after, hidden_index)
        else:
            self.inputs.append(inp)
        inp.trd = trd
        self.config = cmd.config
        if inp.command().is_read_file():  # special treatment of read files
            self._load_trd(inp)
        return inp

    def _add_input(self, inp: T_Input | None, input_text: str | T_Input, after: bool = True, gap: int = 0) -> InputBuildState:
        """
        Adds a new input to the control file.

        Parameters
        ----------
        inp : InputBuildState | None
            The input to place the new command after or before. If None, the new command will be added
            to the end of the control file.
        input_text : str
            String with the full command
        after : bool
            True to place the new command after the referenced input, False to place before
        gap : int
            The number of blank lines to add before this command (or after if `after` is True).

        Returns
        -------
        InputBuildState
            The input that was added to the control file.
        """
        # check if input is in another control file if the current control file is a TCF
        if inp and inp not in self.inputs.inputs(include_hidden=True) and self.TUFLOW_TYPE == self._parent_tuflow_type():
            for inp1 in self.inputs:
                if inp1.TUFLOW_TYPE == const.INPUT.CF and inp1.cf:
                    for cf in inp.cf:
                        inp2 = cf.insert_input(inp, input_text, after, gap)
                        if inp2:
                            return inp2
            logger.error(f'Input {inp} not found in control file inputs. Cannot add input {input_text}.')
            raise ValueError(f'Input {inp} not found in control file inputs. Cannot add input {input_text}.')

        if inp is None:  # get the last input (i.e. append to the end of the control file) if inp is None
            index = max(0, len(self.inputs.inputs(include_hidden=True)) - 1)
            try:
                inp = self.inputs.at_index(index, include_hidden=True)
            except IndexError:  # no inputs in the control file
                inp = None
        else:
            index = self.inputs.index(inp, include_hidden=True)

        # config should be taken from previous input in-case the next input after is a 'Spatial Database ==' command
        if not inp:
            config = self.config
        elif after:
            config = inp.config
        else:
            try:
                config = self.inputs.next_before(inp).config
            except ValueError:  # no input before the specified input
                config = from_config(self.config)
                if self.TUFLOW_TYPE == self._parent_tuflow_type():
                    config.spatial_database = Path()
                else:
                    config.spatial_database = self.config.spatial_database_tcf

        # create the command
        cmd = self._command_class()(input_text, config) if isinstance(input_text, str) else input_text.command()
        cmd.config = config
        trd = None
        uuid = None
        scope = None
        if isinstance(input_text, Input):
            trd = input_text.trd
            if input_text.uuid not in [x.uuid for x in self.inputs.inputs(include_hidden=True)]:
                uuid = input_text.uuid
            if not uuid or isinstance(input_text, InputRunState):
                scope = input_text.scope
                input_text = str(input_text)
        inputs = Inputs()  # a container to store all the added inputs, including blank lines

        if after:  # insert blank lines before adding new input if the new input is after the specified input
            i = -1
            for i in range(gap):
                idx = index + i
                blank_inp = self._insert_input(idx, self._command_class()('\n', cmd.config), trd=None, after=after, hidden_index=True)
                inputs.append(blank_inp)
            index += i + 1

        if isinstance(input_text, InputBuildState):
            self.inputs.insert(index, input_text, after, hidden_index=True)
            inp_out = input_text
            inp_out.config = config
            inp_out.parent = self
        else:
            inp_out = self._insert_input(index, cmd, trd, after, hidden_index=True)
            if uuid:
                inp_out.uuid = uuid
            if scope:
                inp_out.scope = scope
        inputs.append(inp_out)

        if not after:  # insert blank lines after adding the new input if the new input is before the specified input
            for i in range(gap):
                blank_inp = self._insert_input(index + i + 1, self._command_class()('\n', cmd.config), trd, after, hidden_index=True)
                inputs.append(blank_inp)

        self.record_change(inputs, 'add_input')
        if self.root_cf and self.root_cf != self:
            self.root_cf.record_change(inputs, 'add_input')

        if cmd.is_set_variable() and Scope('Scenario') not in inp_out.scope and Scope('Event') not in inp_out.scope:
            self.root_cf.add_variable(*cmd.parse_variable())

        return inp_out

    def _comment_out(self, inp: InputBuildState) -> CommentInput:
        config = inp.command().config
        text = inp.command().original_text
        trd = inp.trd
        i = 0
        for i, t in enumerate(text):
            if t not in  [' ', '\t']:
                break
        if i == len(text) - 1:
            i = 0
        if i < 2:
            new_text = f'! {text}'
        else:
            new_text = text[:i] + '! ' + text[i:]

        new_cmd = self._command_class()(new_text, config)
        new_inp = CommentInput(inp.parent, new_cmd)
        new_inp.trd = trd
        inp.parent.inputs.amend(inp, new_inp)
        new_inp.uuid = inp.uuid
        return new_inp

    def _uncomment(self, inp: InputBuildState) -> InputBuildState:
        if inp:
            return inp  # a valid input already

        config = inp.command().config
        text = inp.command().original_text
        trd = inp.trd

        if '!' not in text and '#' not in text:
            logger.warning('Blank line')
            raise ValueError('Blank line')

        if '!' in text:
            i = text.index('!')
            if i + 1 < len(text) and text[i+1] == ' ':
                new_text = text.replace('! ', '', 1)
            else:
                new_text = text.replace('!', '', 1)
        else:
            i = text.index('#')
            if i + 1 < len(text) and text[i+1] == ' ':
                new_text = text.replace('# ', '', 1)
            else:
                new_text = text.replace('#', '', 1)

        new_cmd = self._command_class()(new_text, config)
        new_inp = get_input_class(new_cmd)(self, new_cmd)
        new_inp.trd = trd
        self.inputs.amend(inp, new_inp)
        new_inp.uuid = inp.uuid
        return new_inp
