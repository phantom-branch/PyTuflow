"""Read-only, deduplicated discovery of TUFLOW GIS attribute-linked input files.

Only the declared file-valued field positions for recognised TUFLOW layer types
are inspected. GeoPackages are opened once per distinct file, not per run.
Unsupported sources/schemas remain unresolved rather than silently passing.
"""

from __future__ import annotations

import csv
import fnmatch
import math
import os
import re
import sqlite3
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dbfread import DBF

from ._tmf.gis import network_attribute_file_sources, tuflow_type_requires_feature_iter
from ._tmf.gis_attr_driver import GISAttributes
from ._tmf.gpkg_safety import readonly_gpkg
from ._tmf.tfpathlib import TuflowPath


@dataclass(frozen=True, slots=True)
class AttributeInspection:
    """Secondary file references or a reason the layer cannot be certified."""

    status: Literal["present", "unresolved"]
    sources: tuple[Path, ...] = ()
    identifiers: tuple[str, ...] = ()
    detail: str = ""
    network_identifiers: tuple[str, ...] = ()
    pit_identifiers: tuple[str, ...] = ()
    bc_identifiers: tuple[str, ...] = ()
    bc_layer_selected: bool = False


def _quote_identifier(value: str) -> str:
    """Quote only identifiers returned by the opened GeoPackage itself."""
    return '"' + value.replace('"', '""') + '"'


def _file_field_index(layer: str) -> int | None:
    """Use the original PyTUFLOW positional GIS-file attribute rules."""
    indexes = tuflow_type_requires_feature_iter(layer)
    if not indexes:
        return None
    if len(indexes) != 1:
        raise ValueError(f"Unsupported multi-column file references in {layer}")
    return indexes[0]


def _bc_name_field_index(layer: str) -> int | None:
    """TUFLOW 2026 §8.4: Name is field three in 2d_bc, first in 2d_sa/rf."""
    if re.match(r"^2d_bc_", layer, re.IGNORECASE):
        return 2
    if re.match(r"^2d_(sa|rf)_", layer, re.IGNORECASE):
        return 0
    return None


def _bc_identifiers_from_rows(
    rows: Iterable[Sequence[object]], layer: str
) -> tuple[str, ...]:
    """Return only database-key Name fields from active BC features.

    2d_bc link/ignore/code geometries never reference BC Name values.
    For HQ, a positive b value generates the curve internally.
    """
    names: set[str] = set()
    two_d_bc = bool(re.match(r"^2d_bc_", layer, re.IGNORECASE))
    source_types = {"HS", "HT", "HQ", "QT", "RF", "SD", "SH", "ST", "VG", "WT", "GT"}
    for attrs in rows:
        if two_d_bc:
            bc_type = str(attrs[0] or "").strip().upper()
            if not bc_type:
                message = f"Blank 2d_bc Type requires external Blank BC Type context: {layer}"
                raise ValueError(message)
            if bc_type not in source_types:
                # Geometries used as links, codes or ignored elements do not
                # name database rows. Unknown kinds are unresolved.
                if bc_type not in {"HX", "SX", "CN", "CD", "IG", "ZP", "2D", "SC"}:
                    message = f"Unrecognised 2d_bc Type {bc_type!r}: {layer}"
                    raise ValueError(message)
                continue
            if bc_type == "HQ":
                if len(attrs) < 3:
                    message = f"Cannot determine automatic HQ curve selection: {layer}"
                    raise ValueError(message)
                slope = attrs[2]
                if slope not in (None, ""):
                    try:
                        if float(str(slope)) > 0:
                            continue
                    except ValueError as exc:
                        message = f"Invalid HQ b slope in {layer}: {slope!r}"
                        raise ValueError(message) from exc
            value = attrs[1]
        else:
            value = attrs[0]
        if not isinstance(value, str) or not value.strip() or "<<" in value or ">>" in value:
            message = f"Missing or unexpanded BC Name in {layer}: {value!r}"
            raise ValueError(message)
        names.add(value.strip())
    return tuple(sorted(names, key=str.casefold))


def _attribute_file_paths(value: str, *, network_m: bool, parent: Path) -> tuple[Path, ...]:
    """Convert candidate TUFLOW attribute values into file references."""
    raw = value.strip()
    if not raw:
        return ()
    if "<<" in raw or ">>" in raw:
        message = "Unexpanded variable or ambiguous GIS attribute reference"
        raise ValueError(message)
    if "|" in raw:
        operation, reference = (part.strip() for part in raw.split("|", maxsplit=1))
        values = (operation, reference) if network_m else (reference,)
    else:
        values = (raw,)
    paths: list[Path] = []
    for item in values:
        if not item:
            message = "Empty GIS attribute file reference"
            raise ValueError(message)
        # TUFLOW interprets an initial slash as relative to the source
        # layer's directory; retain absolute Windows drives/UNC shares.
        windows_absolute = bool(re.match(r"^[A-Za-z]:[\\/]", item) or item.startswith("\\\\"))
        normal = item.replace("\\", "/")
        if normal.startswith("/") and not windows_absolute:
            normal = "." + normal
        candidate = Path(item if windows_absolute else normal)
        if not candidate.is_absolute() and not windows_absolute:
            candidate = parent / candidate
        if windows_absolute and os.name != "nt":
            message = "Windows absolute attribute reference requires Windows inspection"
            raise ValueError(message)
        paths.append(candidate.absolute())
    return tuple(paths)


def _scan_file_reference_rows(
    rows: Iterable[Sequence[object]],
    *,
    layer: str,
    geometry_type: str,
    parent: Path,
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Interpret selected attributes identically for Shapefiles and GeoPackages.

    Provider readers own field positioning, file opening and geometry metadata.
    This function alone owns TUFLOW channel-type and ignore-flag semantics.
    """
    network = bool(re.match(r"^1d_nwk[eb]?_", layer, flags=re.IGNORECASE))
    pit = bool(re.match(r"^1d_pit_", layer, flags=re.IGNORECASE))
    if network and geometry_type.casefold() not in {"linestring", "multilinestring"}:
        if geometry_type.casefold() != "geometry":
            return (), ()  # Known non-line geometries cannot contain line channels.
        message = "Mixed or unknown network geometry requires feature-level inspection"
        raise ValueError(message)

    sources: set[Path] = set()
    database_identifiers: set[str] = set()
    for row in rows:
        value = row[-1]
        if network and isinstance(row[1], str) and row[1].strip().casefold() in {"y", "t"}:
            continue
        kind = row[0].strip().upper() if (network or pit) and isinstance(row[0], str) else ""
        if value is None or value == "":
            if (network and kind in {"M", "Q", "QO", "P"}) or (pit and kind in {"Q", "VPI", "I"}):
                message = f"Required inlet matrix or curve identifier is blank in {layer}"
                raise ValueError(message)
            continue
        if not isinstance(value, str):
            message = f"Non-text GIS file-reference attribute in {layer}"
            raise TypeError(message)
        if network:
            if kind in {"Q", "P"}:
                database_identifiers.add(value.strip())
                continue
            if kind in {"M", "QO"}:
                # Reuse the parser's exact M/QO/Ignore file-versus-curve rule,
                # instead of independently interpreting Inlet_Type pipes.
                attributes = [None] * 11
                attributes[1], attributes[2], attributes[10] = (
                    kind, row[1], value
                )
                source_values = network_attribute_file_sources(attributes)
                if not source_values:
                    raise ValueError(
                        f"Required {kind} file reference absent in {layer}"
                    )
                for file_value in source_values:
                    sources.update(
                        _attribute_file_paths(
                            file_value, network_m=False, parent=parent
                        )
                    )
                continue
            # All other channel types name operational rules or nonfile IDs.
            continue
        elif pit:
            if kind in {"Q", "VPI", "I"}:
                database_identifiers.add(value.strip())
            # Other pit types do not use Inlet_Type to reference a file.
            continue
        sources.update(_attribute_file_paths(value, network_m=network, parent=parent))
    return tuple(sorted(sources)), tuple(sorted(database_identifiers))


def _scan_shapefile(
    path: Path,
) -> tuple[tuple[Path, ...], tuple[str, ...], tuple[str, ...]]:
    """Inspect the original Shapefile DBF positions without extra packages.

    DBF records are read using PyTUFLOW's declared dbfread dependency. The
    SHP header supplies the geometry family (no feature geometries are read).
    """
    dbf = path.with_suffix(".dbf")
    shx = path.with_suffix(".shx")
    if not dbf.is_file() or not shx.is_file():
        raise ValueError("Shapefile requires existing DBF and SHX companions")
    with path.open("rb") as stream:
        header = stream.read(100)
    if len(header) != 100:
        raise ValueError("Truncated Shapefile header")
    shape_type = int.from_bytes(header[32:36], "little")
    geometry_type = (
        "LINESTRING" if shape_type in (3, 13, 23)
        else "GEOMETRY" if shape_type == 0
        else "OTHER"
    )
    reader = DBF(str(dbf), load=False, char_decode_errors="strict")
    fields = reader.field_names
    layer = path.stem
    bc_index = _bc_name_field_index(layer)
    index = _file_field_index(layer)
    if bc_index is not None:
        if len(fields) <= bc_index:
            raise ValueError(f"Missing BC Name column in {layer}")
        if bc_index == 2:
            if len(fields) <= 7:
                raise ValueError(f"2d_bc requires Type, Flags, Name and b fields: {layer}")
            selected = (
                (values[0], values[2], values[7])
                for values in (tuple(record.values()) for record in reader)
            )
        else:
            selected = (
                (values[bc_index],)
                for values in (tuple(record.values()) for record in reader)
            )
        return (), (), _bc_identifiers_from_rows(selected, layer)
    if index is None:
        raise ValueError(f"Unsupported GIS attribute-linked layer type: {layer}")
    network = bool(re.match(r"^1d_nwk[eb]?_", layer, re.IGNORECASE))
    pit = bool(re.match(r"^1d_pit_", layer, re.IGNORECASE))
    if len(fields) <= index or ((network or pit) and len(fields) <= 2):
        raise ValueError(f"Required file-reference attribute index {index} absent from {layer}")
    if network:
        selected = (
            (values[1], values[2], values[index])
            for values in (tuple(record.values()) for record in reader)
        )
    elif pit:
        selected = (
            (values[1], values[index])
            for values in (tuple(record.values()) for record in reader)
        )
    else:
        selected = (
            (values[index],)
            for values in (tuple(record.values()) for record in reader)
        )
    sources, identifiers = _scan_file_reference_rows(
        selected, layer=layer, geometry_type=geometry_type, parent=path.parent
    )
    return sources, identifiers, ()


def _scan_layer(
    connection: sqlite3.Connection, layer: str, geometry_type: str, path: Path
) -> tuple[tuple[Path, ...], tuple[str, ...], tuple[str, ...]]:
    """Read only file-valued attributes; return database identifiers separately.

    TUFLOW 1d_nwk Q and P channels and 1d_pit Q/VPI pits use an inlet
    identifier from the ECF Pit Inlet / Depth Discharge Database. M and QO
    channel matrices instead name files directly. Ignored network rows
    must never introduce input dependencies.
    """
    bc_index = _bc_name_field_index(layer)
    index = _file_field_index(layer)
    if bc_index is None and index is None:
        message = f"Unsupported GIS attribute-linked layer type: {layer}"
        raise ValueError(message)
    network = bool(re.match(r"^1d_nwk[eb]?_", layer, flags=re.IGNORECASE))
    pit = bool(re.match(r"^1d_pit_", layer, flags=re.IGNORECASE))
    if network and geometry_type.casefold() not in {"linestring", "multilinestring"}:
        if geometry_type.casefold() != "geometry":
            return (), (), ()
        message = "Mixed or unknown network geometry requires feature-level inspection"
        raise ValueError(message)
    quoted = _quote_identifier(layer)
    columns = [(name, pk) for _, name, _, _, _, pk in connection.execute(f"PRAGMA table_info({quoted})")]
    geom_names = {
        str(name).casefold()
        for (name,) in connection.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE lower(table_name) = lower(?)",
            (layer,),
        )
    }
    if not geom_names:
        message = f"GeoPackage layer geometry column is unavailable: {layer}"
        raise ValueError(message)
    attrs = [name for name, pk in columns if not pk and str(name).casefold() not in geom_names]
    if bc_index is not None:
        if len(attrs) <= bc_index:
            message = f"Missing BC Name column in {layer}"
            raise ValueError(message)
        if bc_index == 2:
            if len(attrs) <= 7:
                message = f"2d_bc requires Type, Flags, Name and b fields: {layer}"
                raise ValueError(message)
            sql = f"SELECT {', '.join(_quote_identifier(str(attrs[i])) for i in (0, 2, 7))} FROM {quoted}"
        else:
            sql = f"SELECT {_quote_identifier(str(attrs[bc_index]))} FROM {quoted}"
        return (), (), _bc_identifiers_from_rows(connection.execute(sql), layer)
    if index is None or len(attrs) <= index or ((network or pit) and len(attrs) <= 2):
        message = f"Required file-reference attribute index {index} absent from {layer}"
        raise ValueError(message)
    field = _quote_identifier(str(attrs[index]))
    if network:
        ignored = _quote_identifier(str(attrs[2]))
        channel_type = _quote_identifier(str(attrs[1]))
        # All identifiers are sourced from PRAGMA metadata and safely quoted.
        sql = f"SELECT {channel_type}, {ignored}, {field} FROM {quoted}"
    elif pit:
        channel_type = _quote_identifier(str(attrs[1]))
        sql = f"SELECT {channel_type}, {field} FROM {quoted}"
    else:
        sql = f"SELECT {field} FROM {quoted}"

    sources, identifiers = _scan_file_reference_rows(
        connection.execute(sql), layer=layer, geometry_type=geometry_type, parent=path.parent
    )
    return sources, identifiers, ()


def read_bc_inline_constant_names(
    path: Path,
) -> frozenset[str]:
    """Identify inline numeric BC rows not emitted as secondary file references.

    A BC Database header can follow comments or preamble rows. Numeric
    Source values and blank Source with numeric Column 2 are documented
    constants; unknown or variable-based expressions do not pass here.
    This is only read once per distinct primary CSV during GIS materialisation.
    """
    names: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = csv.reader(stream)
        header: list[str] | None = None
        for row in rows:
            keys = [cell.strip().casefold() for cell in row]
            if "name" in keys and "source" in keys:
                header = keys
                break
        if header is None:
            message = f"BC Database is missing Name/Source headings: {path}"
            raise ValueError(message)
        name_col, source_col = header.index("name"), header.index("source")
        column_two = header.index("column 2") if "column 2" in header else None
        for row in rows:
            if not any(cell.strip() for cell in row):
                continue
            if len(row) <= max(name_col, source_col):
                message = f"Invalid BC Database row in {path}"
                raise ValueError(message)
            key = row[name_col].strip().casefold()
            raw = row[source_col].strip()
            constant = raw
            if not constant and column_two is not None and len(row) > column_two:
                constant = row[column_two].strip()
            if not key:
                message = f"Blank BC Database Name in {path}"
                raise ValueError(message)
            if not constant:
                continue
            try:
                number = float(constant)
            except ValueError:
                continue
            if not math.isfinite(number):
                message = f"Nonfinite inline BC constant in {path}: {key}"
                raise ValueError(message)
            if key in names:
                message = f"Duplicate inline BC identifier in {path}: {key}"
                raise ValueError(message)
            names.add(key)
    return frozenset(names)


def read_pit_inlet_database(path: Path) -> dict[str, Path]:
    """Map depth-discharge curve names to Source CSVs using the TUFLOW schema.

    Table 5.27: first column is Name, second is Source. Database CSVs are
    read only once by the caller and are never modified. Reject ambiguous
    or unsupported tables rather than guessing at curve file dependencies.
    """
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if len(fields) < 2 or fields[0].strip().casefold() != "name" or fields[1].strip().casefold() != "source":
            message = f"Pit inlet database needs Name and Source columns: {path}"
            raise ValueError(message)
        mapping: dict[str, Path] = {}
        for row in reader:
            name = str(row.get(fields[0]) or "").strip()
            source = str(row.get(fields[1]) or "").strip()
            if not name or not source or "<<" in source or ">>" in source:
                message = f"Invalid pit inlet database entry in {path}: {name!r}"
                raise ValueError(message)
            key = name.casefold()
            if key in mapping:
                message = f"Duplicate pit inlet identifier in {path}: {name}"
                raise ValueError(message)
            paths = _attribute_file_paths(source, network_m=False, parent=path.parent)
            if len(paths) != 1:
                message = f"Invalid pit inlet Source reference in {path}: {name}"
                raise ValueError(message)
            mapping[key] = paths[0]
        return mapping


def inspect_gis_attribute_sources(
    requests: Collection[tuple[Path, str, bool]],
) -> tuple[dict[tuple[Path, str, bool], AttributeInspection], int]:
    """Read selected GIS attribute records once per distinct physical source.

    Each request holds (concrete file, layer selector, implicit layer).
    Implicit filename-derived layers always use exact literal matching,
    including names 'all' and names containing glob characters. Explicit
    '>> all' and explicit wildcard selectors retain their TUFLOW semantics.

    GeoPackages use the strict read-only main-file/journal acceptance policy
    of the physical validator. Unsupported formats fail closed.
    """
    grouped: dict[Path, set[tuple[str, bool]]] = defaultdict(set)
    for path, layer, implicit in requests:
        grouped[path].add((layer, implicit))

    results: dict[tuple[Path, str, bool], AttributeInspection] = {}
    databases = 0

    def matches(candidate: str, selector: str, implicit: bool) -> bool:
        if implicit:
            return candidate.casefold() == selector.casefold()
        return (
            selector.casefold() == "all"
            or fnmatch.fnmatchcase(candidate.casefold(), selector.casefold())
        )

    for path, selectors in grouped.items():
        if path.suffix.casefold() == ".shp":
            selected = {
                (selector, implicit)
                for selector, implicit in selectors
                if matches(path.stem, selector, implicit)
            }
            for selector, implicit in selectors - selected:
                results[(path, selector, implicit)] = AttributeInspection(
                    "unresolved",
                    detail=f"Shapefile layer does not match selector {selector!r}",
                )
            if selected:
                try:
                    sources, identifiers, bc_names = _scan_shapefile(path)
                    databases += 1
                    for selector, implicit in selected:
                        results[(path, selector, implicit)] = AttributeInspection(
                            "present",
                            sources,
                            identifiers,
                            network_identifiers=(
                                identifiers
                                if re.match(r"^1d_nwk[eb]?_", path.stem, re.IGNORECASE)
                                else ()
                            ),
                            pit_identifiers=(
                                identifiers
                                if re.match(r"^1d_pit_", path.stem, re.IGNORECASE)
                                else ()
                            ),
                            bc_identifiers=bc_names,
                            bc_layer_selected=_bc_name_field_index(path.stem) is not None,
                        )
                except Exception as exc:  # noqa: BLE001 - reject unknown provider failures
                    for selector, implicit in selected:
                        results[(path, selector, implicit)] = AttributeInspection(
                            "unresolved", detail=f"Cannot inspect Shapefile attributes: {exc}"
                        )
            continue
        if path.suffix.casefold() != ".gpkg":
            for selector, implicit in selectors:
                results[(path, selector, implicit)] = AttributeInspection(
                    "unresolved",
                    detail=f"GIS attribute reading does not support {path.suffix or 'unknown'} sources",
                )
            continue
        try:
            # Core PyTUFLOW owns the immutable, pinned, journal-safe view.
            # It checks aliases and rollback/WAL safety both before/after.
            with readonly_gpkg(path) as database:
                databases += 1
                available = {
                    str(name): str(geom)
                    for name, geom in database.execute(
                        "SELECT table_name, geometry_type_name FROM gpkg_geometry_columns"
                    )
                }
                if not available:
                    raise ValueError("No vector layer metadata in GeoPackage")
                cache: dict[str, tuple[tuple[Path, ...], tuple[str, ...], tuple[str, ...]]] = {}
                for selector, implicit in selectors:
                    key = (path, selector, implicit)
                    chosen = [
                        name for name in available
                        if matches(name, selector, implicit)
                    ]
                    if not chosen:
                        results[key] = AttributeInspection(
                            "unresolved",
                            detail=f"No GIS attribute layers matched {selector!r}",
                        )
                        continue
                    try:
                        for layer in chosen:
                            if (
                                _file_field_index(layer) is None
                                and _bc_name_field_index(layer) is None
                            ):
                                # Other TUFLOW GIS layer types carry no known
                                # file-valued attributes or BC Source names.
                                # The physical layer itself was checked by
                                # validate_dependencies().
                                continue
                            if layer not in cache:
                                cache[layer] = _scan_layer(
                                    database, layer, available[layer], path
                                )
                        chosen = [layer for layer in chosen if layer in cache]
                        sources = tuple(sorted({
                            source for layer in chosen for source in cache[layer][0]
                        }))
                        network = tuple(sorted({
                            name for layer in chosen
                            if re.match(r"^1d_nwk[eb]?_", layer, re.IGNORECASE)
                            for name in cache[layer][1]
                        }))
                        pits = tuple(sorted({
                            name for layer in chosen
                            if re.match(r"^1d_pit_", layer, re.IGNORECASE)
                            for name in cache[layer][1]
                        }))
                        bc = tuple(sorted({
                            name for layer in chosen
                            for name in cache[layer][2]
                        }, key=str.casefold))
                        results[key] = AttributeInspection(
                            "present", sources,
                            tuple(sorted(set(network) | set(pits))),
                            network_identifiers=network,
                            pit_identifiers=pits,
                            bc_identifiers=bc,
                            bc_layer_selected=any(
                                _bc_name_field_index(layer) is not None
                                for layer in chosen
                            ),
                        )
                    except (OSError, ValueError, TypeError, sqlite3.DatabaseError) as exc:
                        results[key] = AttributeInspection(
                            "unresolved", detail=f"Cannot inspect GIS attributes: {exc}"
                        )
        except (OSError, ValueError, TypeError, sqlite3.DatabaseError) as exc:
            for selector, implicit in selectors:
                results[(path, selector, implicit)] = AttributeInspection(
                    "unresolved", detail=f"Cannot inspect GIS attributes: {exc}"
                )
    return results, databases
