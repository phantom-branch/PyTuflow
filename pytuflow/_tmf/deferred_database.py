"""Opt-in secondary source discovery using cached TUFLOW database rows."""
from dataclasses import replace
from pathlib import Path

from .file_reference import FileReference, make_file_reference
from .parsers.command import Command


class DeferredDatabaseResolutionError(ValueError):
    """Database sources cannot be completely inspected by the deferred API."""


def _expanded(value, context, *, kind, row):
    """Expand model variables before classifying a table cell."""
    raw = str(value).strip()
    if raw.casefold() in ('nan', 'none'):
        return ''
    translated = str(context.translate(raw)).strip()
    if translated and not context.is_resolved(translated):
        raise DeferredDatabaseResolutionError(
            f'Unresolved {kind} database row {row!s}: {raw}'
        )
    return translated


def _inline_material(value, row):
    """Validate depth/n pairs the same way eager MatDBEntry.is_list identifies.

    Inline comma-delimited values are numeric depth and Manning n pairs,
    not filenames. Malformed comma lists must not silently pass.
    """
    if ',' not in value:
        return False
    tokens = [part.strip().strip('"').strip("'") for part in value.split(',')]
    try:
        numbers = [float(token) for token in tokens]
    except ValueError as exc:
        raise DeferredDatabaseResolutionError(
            f'Invalid inline Manning/depth list at material {row}: {value}'
        ) from exc
    if len(numbers) < 2 or len(numbers) % 2:
        raise DeferredDatabaseResolutionError(
            f'Inline Manning/depth list needs complete depth/n pairs at material {row}: {value}'
        )
    return True


def _validate_soil_rows(frame, context):
    """Validate supported inline soil methods without generating fictitious files.

    SoilDatabase.value() currently implements NONE, ILCL, GA, HO, CO and
    SCS. These methods contain parameters or USDA classifications, not
    secondary filenames; unknown methods fail closed.
    """
    required = {
        'NONE': (),
        'ILCL': (1, 2),
        'GA': (1,),
        'HO': (1, 2, 3, 4),
        'CO': (1, 2),
        'SCS': (1, 2),
    }
    for key, record in frame.iterrows():
        fields = [_expanded(item, context, kind='soils', row=key) for item in record.tolist()]
        if not fields or not fields[0]:
            raise DeferredDatabaseResolutionError(f'Missing soil method at row {key}')
        method = fields[0].upper()
        if method not in required:
            raise DeferredDatabaseResolutionError(f'Unsupported soil method {method} at row {key}')
        for index in required[method]:
            if len(fields) <= index or not fields[index]:
                raise DeferredDatabaseResolutionError(
                    f'Missing {method} parameter {index} at soil row {key}'
                )
            if not (method == 'GA' and index == 1):
                try:
                    float(fields[index])
                except ValueError as exc:
                    raise DeferredDatabaseResolutionError(
                        f'Invalid {method} parameter {index} at soil row {key}: {fields[index]}'
                    ) from exc
        # For GA a numeric suction requires numeric hydraulic conductivity
        # and porosity; a USDA soil-type string is a known inline class.
        if method == 'GA':
            try:
                float(fields[1])
                numeric_ga = True
            except ValueError:
                numeric_ga = False
            if numeric_ga:
                for index in (2, 3):
                    if len(fields) <= index:
                        raise DeferredDatabaseResolutionError(
                            f'Missing GA parameter {index} at soil row {key}'
                        )
                    try:
                        float(fields[index])
                    except ValueError as exc:
                        raise DeferredDatabaseResolutionError(
                            f'Invalid GA parameter {index} at soil row {key}: {fields[index]}'
                        ) from exc


def database_source_references(build_input, context, kind: str | None, config) -> tuple[FileReference, ...]:
    """Describe context-specific secondary sources with no additional file I/O.

    The build-state already contains database rows from initial TCF parsing.
    BC databases use the Source column; materials and soil rows follow\n    the same inline/source classifications supported by eager processing.
    """
    if kind not in ('bc', 'materials', 'soils'):
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
    if kind == 'soils':
        _validate_soil_rows(frame, context)
        return ()
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
        value = _expanded(raw, context, kind=kind, row=key)
        if not value:
            continue
        if kind == 'materials' and _inline_material(value, key):
            continue
        try:
            float(value)
        except ValueError:
            pass
        else:
            continue
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
