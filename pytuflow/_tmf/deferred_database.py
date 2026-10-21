"""Opt-in secondary source discovery using cached TUFLOW database rows."""
from dataclasses import replace
from pathlib import Path

from .file_reference import FileReference, make_file_reference
from .parsers.command import Command


class DeferredDatabaseResolutionError(ValueError):
    """Database sources cannot be completely inspected by the deferred API."""


def database_source_references(build_input, context, kind: str | None, config) -> tuple[FileReference, ...]:
    """Describe context-specific secondary sources with no additional file I/O.

    The build-state already contains database rows from initial TCF parsing.
    BC databases use the Source column and materials use their first column.
    """
    if kind not in ('bc', 'materials'):
        raise DeferredDatabaseResolutionError(
            f'Unsupported deferred database schema: {kind!r}'
        )
    databases = tuple(build_input.cf)
    if len(databases) != 1:
        raise DeferredDatabaseResolutionError(
            f'Expected one cached {kind} database, found {len(databases)}'
        )
    database = databases[0]
    if not getattr(database, 'loaded', False) or database.fpath is None:
        raise DeferredDatabaseResolutionError(f'{kind} database has not been loaded')
    frame = database.df
    columns = list(frame.columns)
    if kind == 'bc':
        column = next((col for col in columns if str(col).strip().casefold() == 'source'), None)
        if column is None:
            raise DeferredDatabaseResolutionError('BC database has no Source column')
    else:
        if not columns:
            raise DeferredDatabaseResolutionError('Materials database has no value column')
        column = columns[0]

    refs = []
    for key, raw in frame[column].items():
        value = str(raw).strip()
        if not value or value.casefold() in ('nan', 'none'):
            continue
        try:
            float(value)
        except ValueError:
            pass
        else:
            continue
        if kind == 'materials' and ',' in value:
            raise DeferredDatabaseResolutionError(
                f'Unsupported material list at row {key!s}: {value}'
            )
        expanded = str(context.translate(value)).strip()
        if not expanded or not context.is_resolved(expanded):
            raise DeferredDatabaseResolutionError(
                f'Unresolved {kind} database row {key!s}: {value}'
            )
        command = Command(f'Read File == {expanded}', config, parent=Path(database.fpath))
        found = tuple(
            replace(make_file_reference(part),
                    origin=f'{kind} database row {key!s}', database_kind=None)
            for part in command.parts() if part.is_value_a_file()
        )
        if not found:
            raise DeferredDatabaseResolutionError(
                f'Unrecognised {kind} source in row {key!s}: {value}'
            )
        refs.extend(found)
    return tuple(refs)
