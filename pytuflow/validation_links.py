"""Conservative second-stage discovery of GIS feature-linked file inputs.

This module never changes original parsed commands or the immutable fragment
projection. A successful physical base-file/layer check is prerequisite to
reading attribute tables. Every supported attribute layer is scanned at most
once per distinct physical file/selector within this invocation.

Unsupported providers, schemas and unmatched curve/BC identifiers fail closed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ._tmf.dependency_records import BatchDependencyRun, BatchInputReference
from ._tmf.file_reference import FileReference
from ._tmf.gis import tuflow_type_requires_feature_iter
from .validation import (
    ValidationFinding,
    ValidationReport,
    _implicit_gpkg_layer,
)
from .validation_gis import (
    AttributeInspection,
    inspect_gis_attribute_sources,
    read_bc_inline_constant_names,
)

if TYPE_CHECKING:
    from ._tmf.fragment_dependencies import FragmentBatchResult


@dataclass(frozen=True, slots=True)
class ExtendedProjection:
    runs: tuple[BatchDependencyRun, ...]


@dataclass(frozen=True, slots=True)
class GISExpansion:
    projection: ExtendedProjection
    findings: tuple[ValidationFinding, ...]
    linked_sources: int
    gis_files_scanned: int


def _linked_reference(parent: BatchInputReference, path: Path) -> BatchInputReference:
    expression = str(path)
    source = parent.reference
    file = FileReference(
        base_directory=path.parent,
        expanded_value=expression,
        path_pattern=path,
        layer_pattern=None,
        origin=f"GIS attribute of {source.origin}",
        requires_directory_scan=any(character in path.name for character in "*?["),
        requires_layer_scan=False,
        requires_attribute_scan=False,
        requires_database_scan=False,
        unresolved_variables=tuple(re.findall(r"<<[^<>]+>>", expression)),
    )
    return BatchInputReference(
        input_uuid=parent.input_uuid,
        command_index=parent.command_index,
        owner_control_file=parent.owner_control_file,
        line_number=parent.line_number,
        reference=file,
    )


def extend_gis_dependencies(
    projection: FragmentBatchResult,
    checked: ValidationReport,
) -> GISExpansion:
    """Add validated primary GIS attribute link candidates to the projection.

    Existing model/fragment records are never mutated. This prepares a second
    physical check on the union of original and attribute-derived sources, not
    an implicit lookup during scenario/event evaluation.
    """
    sources: dict[tuple[int, str, int], list[BatchInputReference]] = defaultdict(list)
    scan_requests: set[tuple[Path, str, bool]] = set()
    needs: list[tuple[BatchDependencyRun, BatchInputReference, Path, str, bool, bool]] = []
    findings: list[ValidationFinding] = []

    # File existence/layer validation has already resolved wildcard filename
    # patterns, so GIS attribute scanning never probes a missing primary file.
    by_parent: dict[tuple[int, str, int, str, Path], list[Path]] = defaultdict(list)
    for item in checked.findings:
        if (
            item.kind == "file"
            and item.status == "present"
            and item.path is not None
        ):
            key = (
                item.run_index, item.input_uuid, item.command_index,
                item.origin, item.source_pattern or item.path,
            )
            by_parent[key].append(item.path)

    for run in projection.runs:
        commands = {
            command.command_index: command.command_name.casefold()
            for command in run.ordered_inputs
        }
        if run.error is not None:
            continue
        for link in run.input_references:
            original = link.reference
            layer_name = str(original.layer_pattern or original.path_pattern.stem)
            is_bc = bool(
                commands.get(link.command_index, "").startswith(
                    ("read gis bc", "read gis sa", "read gis rf")
                ) and re.match(r"^2d_(bc|sa|rf)_", layer_name, flags=re.IGNORECASE)
            )
            if not original.requires_attribute_scan and not is_bc:
                continue
            key = (
                run.index,
                link.input_uuid,
                link.command_index,
                original.origin,
                original.path_pattern,
            )
            for path in by_parent.get(key, []):
                implicit = _implicit_gpkg_layer(original)
                selector = (
                    path.stem if implicit or original.layer_pattern is None
                    else str(original.layer_pattern)
                )
                # A wildcard filename/layer is conservatively labelled as
                # an attribute candidate by FileReference, even when its
                # concrete result is a plain 2d_code/2d_mat layer. Do not
                # require GIS feature-table metadata for such input layers.
                # Explicit wildcard/'all' selectors may contain linked 1D
                # layers, so the inspector must check their concrete matches.
                known_file_fields = bool(
                    tuflow_type_requires_feature_iter(selector)
                )
                explicit_wildcard = (
                    not implicit
                    and original.layer_pattern is not None
                    and (any(char in selector for char in "*?[")
                         or selector.casefold() == "all")
                )
                if (
                    original.requires_table_link_scan
                    and not known_file_fields
                ):
                    findings.append(
                        ValidationFinding(
                            run_index=run.index,
                            flags=run.flags,
                            status="unresolved",
                            kind="attribute",
                            path=path,
                            detail="Unclassified GIS table-link schema cannot be certified",
                            layer=selector,
                            origin=original.origin,
                            input_uuid=link.input_uuid,
                            command_index=link.command_index,
                            owner_control_file=link.owner_control_file,
                        )
                    )
                    continue
                if not (
                    known_file_fields or is_bc
                    or original.requires_table_link_scan
                    or explicit_wildcard
                ):
                    continue
                request = (path, selector, implicit)
                scan_requests.add(request)
                needs.append((run, link, path, selector, implicit, is_bc))

    if not needs:
        return GISExpansion(
            ExtendedProjection(tuple(projection.runs)), (), 0, 0
        )

    inspected, count = inspect_gis_attribute_sources(scan_requests)
    inline_cache: dict[Path, frozenset[str] | str] = {}

    for run, link, path, selector, implicit, is_bc in needs:
        result: AttributeInspection = inspected[(path, selector, implicit)]

        def issue(
            detail: str,
            *,
            run: BatchDependencyRun = run,
            link: BatchInputReference = link,
            path: Path = path,
            selector: str = selector,
        ) -> None:
            findings.append(
                ValidationFinding(
                    run_index=run.index,
                    flags=run.flags,
                    status="unresolved",
                    kind="attribute",
                    path=path,
                    detail=detail,
                    layer=selector,
                    origin=link.reference.origin,
                    input_uuid=link.input_uuid,
                    command_index=link.command_index,
                    owner_control_file=link.owner_control_file,
                    database_kind=link.reference.database_kind,
                )
            )

        if result.status != "present":
            issue(result.detail or "Cannot certify GIS attribute dependencies")
            continue

        key = (run.index, link.input_uuid, link.command_index)
        sources[key].extend(_linked_reference(link, item) for item in result.sources)

        # Inlet and depth-discharge IDs are not file paths. They must resolve
        # through the selected cached parser database; never invent a path.
        for identifiers, kind in (
            (result.network_identifiers, "depth_discharge"),
            (result.pit_identifiers, "pit_inlet"),
        ):
            if not identifiers:
                continue
            existing = {
                source.entry_name.casefold()
                for source in run.database_sources
                if source.database_kind == kind
            }
            for identifier in identifiers:
                if identifier.casefold() not in existing:
                    issue(f"Unresolved {kind} curve identifier: {identifier}")

        if is_bc and result.bc_identifiers:
            activations = [
                a for a in run.database_activations
                if a.database_kind == "bc" and a.sequence < link.command_index
            ]
            if not activations:
                issue("GIS BC/SA/RF layer has no preceding active BC Database")
                continue
            active = max(activations, key=lambda a: a.sequence)
            names = {
                source.entry_name.casefold()
                for source in run.database_sources
                if source.database_kind == "bc" and source.input_uuid == active.input_uuid
            }
            for identifier in result.bc_identifiers:
                if identifier.casefold() in names:
                    continue
                if active.database_path not in inline_cache:
                    try:
                        inline_cache[active.database_path] = read_bc_inline_constant_names(
                            active.database_path
                        )
                    except (OSError, ValueError, UnicodeError) as exc:
                        inline_cache[active.database_path] = str(exc)
                constants = inline_cache[active.database_path]
                if (
                    not isinstance(constants, str)
                    and identifier.casefold() in constants
                ):
                    continue
                issue(
                    f"Active BC Database has no resolvable Source or inline "
                    f"constant for {identifier!r}"
                )

    extended: list[BatchDependencyRun] = []
    added = 0
    for run in projection.runs:
        seen: set[tuple[object, ...]] = set()
        links: list[BatchInputReference] = []
        for link in run.input_references:
            key = (run.index, link.input_uuid, link.command_index)
            for extra in sources.get(key, ()):
                fingerprint = (extra.input_uuid, extra.command_index,
                               extra.reference.path_pattern, extra.reference.layer_pattern)
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    links.append(extra)
        added += len(links)
        extended.append(
            replace(
                run,
                input_references=run.input_references + tuple(links),
                file_references=run.file_references
                + tuple(link.reference for link in links),
            )
        )

    return GISExpansion(
        ExtendedProjection(tuple(extended)), tuple(findings), added, count
    )
