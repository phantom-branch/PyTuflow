"""Immutable syntactic input-file references for deferred TUFLOW contexts.

References are not existence assertions. A caller can aggregate them across
contexts and inspect paths, database layers and GIS attributes in bulk.
"""
from dataclasses import dataclass
from pathlib import Path
import re

from .parsers.command import Command
from .tfpathlib import TuflowPath
from .tfstrings.patterns import globify


@dataclass(frozen=True)
class FileReference:
    """Context-expanded source-file pattern and deferred inspection requirements."""

    base_directory: Path
    expanded_value: str
    path_pattern: Path
    layer_pattern: str | None
    origin: str
    requires_directory_scan: bool
    requires_layer_scan: bool
    requires_attribute_scan: bool
    unresolved_variables: tuple[str, ...] = ()


def make_file_reference(command: Command) -> FileReference:
    """Construct a reference lexically, without filesystem or GIS probes."""
    value = str(command.value_expanded_path or command.value).strip()
    db, layer = TuflowPath(value)._split_db_and_lyr()
    owner = command.parent
    base = (Path(owner).parent if owner and owner != Path() else Path.cwd()).absolute()
    path = Path(db)
    if not path.is_absolute():
        path = base / path
    path_glob = str(globify(str(path), command.config.wildcards))
    layer_glob = str(globify(layer, command.config.wildcards)) if layer is not None else None
    unresolved = tuple(dict.fromkeys(re.findall(r'<<[^<>]+>>', value)))
    # All GIS sources are candidates: their attributes may reference further
    # files, especially for 1D network and cross-section layers.
    layer_name = (layer or path.stem).lower()
    # Only layers likely to have file-valued fields need an attribute scan.
    # Unknown/wildcard names remain candidates, preserving dependency coverage.
    from .gis import tuflow_type_requires_feature_iter
    attr_scan = (command.is_read_gis() and not command.is_read_projection()
                 and (bool(tuflow_type_requires_feature_iter(layer_name))
                      or any(char in layer_name for char in '*?<['])
                      or layer_name == 'all'))
    return FileReference(
        base_directory=base, expanded_value=value, path_pattern=Path(path_glob),
        layer_pattern=layer_glob, origin=command.command_orig,
        requires_directory_scan=any(char in path_glob for char in '*?['),
        requires_layer_scan=layer_glob is not None,
        requires_attribute_scan=attr_scan, unresolved_variables=unresolved,
    )
