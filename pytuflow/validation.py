"""Optional, read-only physical validation of parsed TUFLOW input references.

Dependency collection and control-file interpretation remain entirely separate.
This module accepts immutable per-run dependency projections and inspects only
the selected source paths, GeoPackage metadata and ordinary BC CSV headers.
No TUFLOW solver, QGIS runtime or ryan-tools dependency is required.
"""

from __future__ import annotations

import csv
import fnmatch
import os
import sqlite3
import stat
from collections import defaultdict
from collections.abc import Collection, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from ._tmf.batch_dependencies import BatchDependencyRun

ValidationStatus = Literal["present", "missing", "unresolved", "unsupported"]
ValidationKind = Literal["file", "wildcard", "layer", "csv_header", "context"]


class DependencyProjection(Protocol):
    """The common immutable run-record surface of batch and fragment results."""

    @property
    def runs(self) -> tuple[BatchDependencyRun, ...]: ...


@dataclass(frozen=True, slots=True)
class ValidationOptions:
    """Explicit physical inspection policy; no IO occurs until validation."""

    check_files: bool = True
    check_gpkg_layers: bool = True
    check_bc_csv_headers: bool = False
    io_workers: int = 1
    maximum_directory_entries: int = 50_000
    maximum_header_lines: int = 5
    maximum_header_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if not 1 <= self.io_workers <= 32:
            raise ValueError("io_workers must be between 1 and 32")
        if min(
            self.maximum_directory_entries,
            self.maximum_header_lines,
            self.maximum_header_bytes,
        ) < 1:
            raise ValueError("Inspection limits must be positive")


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One physical-inspection result attributed to one requested simulation."""

    run_index: int
    flags: str
    status: ValidationStatus
    kind: ValidationKind
    path: Path | None
    detail: str = ""
    layer: str | None = None
    origin: str = ""
    input_uuid: str = ""
    command_index: int = -1
    owner_control_file: Path | None = None
    database_kind: str | None = None
    source_pattern: Path | None = None
    csv_columns: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Ordered findings plus deduplicated physical-inspection counters."""

    findings: tuple[ValidationFinding, ...]
    run_count: int
    files_examined: int
    geopackages_examined: int
    csv_headers_examined: int
    directories_scanned: int

    @property
    def passed(self) -> bool:
        return bool(self.run_count) and all(
            item.status == "present" for item in self.findings
        )


@dataclass(frozen=True, slots=True)
class _Requirement:
    run_index: int
    flags: str
    path: Path
    layer: str | None
    origin: str
    input_uuid: str
    command_index: int
    owner_control_file: Path | None
    database_kind: str | None
    csv_columns: tuple[str, ...] | None
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Inspection:
    status: ValidationStatus
    detail: str = ""
    layers: tuple[str, ...] = ()
    layer_error: str = ""
    csv_header: tuple[str, ...] = ()
    csv_error: str = ""
    gpkg_examined: bool = False
    csv_examined: bool = False


def _requirements(projection: DependencyProjection) -> tuple[
    list[_Requirement], list[ValidationFinding]
]:
    requirements: list[_Requirement] = []
    errors: list[ValidationFinding] = []
    for run in projection.runs:
        if run.error is not None:
            errors.append(
                ValidationFinding(
                    run.index, run.flags, "unresolved", "context", None, run.error
                )
            )
            continue  # Never inspect any partial references from a failed run.

        links = run.input_references
        if links:
            for link in links:
                reference = link.reference
                requirements.append(
                    _Requirement(
                        run.index,
                        run.flags,
                        reference.path_pattern,
                        reference.layer_pattern,
                        reference.origin,
                        link.input_uuid,
                        link.command_index,
                        link.owner_control_file,
                        reference.database_kind,
                        reference.csv_columns,
                        reference.unresolved_variables,
                    )
                )
        else:
            # Older batch projections may not expose per-input identities.
            for reference in run.file_references:
                requirements.append(
                    _Requirement(
                        run.index,
                        run.flags,
                        reference.path_pattern,
                        reference.layer_pattern,
                        reference.origin,
                        "",
                        -1,
                        None,
                        reference.database_kind,
                        reference.csv_columns,
                        reference.unresolved_variables,
                    )
                )

        activations = {
            activation.input_uuid: activation
            for activation in run.database_activations
        }
        for source in run.database_sources:
            owner = activations.get(source.input_uuid)
            if source.input_uuid and owner is None:
                errors.append(
                    ValidationFinding(
                        run.index,
                        run.flags,
                        "unresolved",
                        "context",
                        source.path_pattern,
                        "Secondary source has no matching active database declaration",
                        origin=source.owning_command,
                        input_uuid=source.input_uuid,
                        owner_control_file=source.owner_control_file,
                        database_kind=source.database_kind,
                    )
                )
                continue
            if owner is not None and owner.database_kind != source.database_kind:
                errors.append(
                    ValidationFinding(
                        run.index,
                        run.flags,
                        "unresolved",
                        "context",
                        source.path_pattern,
                        "Secondary source kind does not match its active database",
                        origin=source.owning_command,
                        input_uuid=source.input_uuid,
                        owner_control_file=source.owner_control_file,
                        database_kind=source.database_kind,
                    )
                )
                continue
            requirements.append(
                _Requirement(
                    run.index,
                    run.flags,
                    source.path_pattern,
                    source.layer_pattern,
                    source.owning_command,
                    source.input_uuid,
                    owner.sequence if owner is not None else -1,
                    source.owner_control_file,
                    source.database_kind,
                    source.csv_columns,
                )
            )
    return requirements, errors


def _has_wildcards(path: str) -> bool:
    return any(char in path for char in "*?[")


def _scan_wildcard_patterns(
    patterns: Collection[Path], *, maximum_entries: int
) -> tuple[
    dict[Path, tuple[Path, ...]], dict[Path, tuple[ValidationStatus, str]], int
]:
    """Scan a directory once for all requested filename patterns in it."""

    found: dict[Path, tuple[Path, ...]] = {}
    failures: dict[Path, tuple[ValidationStatus, str]] = {}
    grouped: dict[Path, list[Path]] = defaultdict(list)
    for pattern in patterns:
        if _has_wildcards(str(pattern.parent)):
            failures[pattern] = (
                "unsupported",
                "Wildcard directories require an explicit traversal policy",
            )
        else:
            grouped[pattern.parent].append(pattern)

    scans = 0
    for parent, siblings in grouped.items():
        matches: dict[Path, list[Path]] = {pattern: [] for pattern in siblings}
        scans += 1
        problem: tuple[ValidationStatus, str] | None = None
        try:
            with os.scandir(parent) as iterator:
                for index, entry in enumerate(iterator):
                    if index >= maximum_entries:
                        raise ValueError("Wildcard directory exceeds bounded scan limit")
                    candidate = os.path.normcase(entry.name)
                    for pattern in siblings:
                        if fnmatch.fnmatchcase(
                            candidate, os.path.normcase(pattern.name)
                        ):
                            matches[pattern].append(parent / entry.name)
        except FileNotFoundError:
            problem: tuple[ValidationStatus, str] = (
                "missing", "Wildcard parent directory does not exist"
            )
        except (OSError, ValueError) as exc:
            problem = ("unresolved", f"Cannot inspect wildcard directory: {exc}")
        for pattern in siblings:
            if problem is not None:
                failures[pattern] = problem
            elif matches[pattern]:
                found[pattern] = tuple(sorted(matches[pattern]))
            else:
                failures[pattern] = (
                    "missing", "No input files match wildcard pattern"
                )
    return found, failures, scans


def _stat_source(path: Path) -> tuple[ValidationStatus, str]:
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return "missing", "Input source file does not exist"
    except OSError as exc:
        return "unresolved", f"Cannot inspect input source file: {exc}"
    if not stat.S_ISREG(mode):
        return "missing", "Expected a regular file, not a directory or other type"
    return "present", ""


def _gpkg_contents(path: Path) -> tuple[tuple[str, ...], str]:
    try:
        uri = f"{path.absolute().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            names = tuple(
                str(row[0]) for row in db.execute("SELECT table_name FROM gpkg_contents")
            )
        return names, ""
    except (OSError, sqlite3.DatabaseError, ValueError) as exc:
        return (), f"Cannot inspect GeoPackage layers: {exc}"


def _layer_status(
    requested: str, existing: tuple[str, ...]
) -> tuple[ValidationStatus, str]:
    names = tuple(name.casefold() for name in existing)
    pattern = requested.casefold().strip()
    if pattern == "all":
        matched = bool(names)
    elif _has_wildcards(pattern):
        matched = any(fnmatch.fnmatchcase(name, pattern) for name in names)
    else:
        matched = pattern in names
    if matched:
        return "present", ""
    return "missing", f"GeoPackage layer does not exist: {requested}"


def _csv_header(
    path: Path, requested: Collection[str], *, lines_limit: int, bytes_limit: int
) -> tuple[tuple[str, ...], str]:
    """Read only the first eligible CSV header within strict physical bounds."""

    needed = {column.strip().casefold() for column in requested if column.strip()}
    try:
        with path.open("rb") as source:
            remaining = bytes_limit
            record_started = False

            def lines() -> Iterator[str]:
                nonlocal remaining, record_started
                for number in range(lines_limit):
                    line = source.readline(remaining + 1)
                    if len(line) > remaining:
                        raise ValueError("CSV header exceeds bounded byte limit")
                    if not line:
                        return
                    remaining -= len(line)
                    decoded = line.decode("utf-8-sig" if number == 0 else "utf-8")
                    if not record_started and (
                        not decoded.strip() or decoded.lstrip().startswith("!")
                    ):
                        continue
                    record_started = True
                    yield decoded

            for record in csv.reader(lines(), strict=True):
                columns = tuple(column.strip() for column in record)
                if any(columns) and (
                    not needed or needed.intersection(
                        column.casefold() for column in columns
                    )
                ):
                    return columns, ""
                record_started = False
        return (), (
            f"No CSV header containing a required name within first {lines_limit} "
            "physical lines"
        )
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        return (), f"Cannot inspect CSV header: {exc}"


def _header_status(
    header: tuple[str, ...], required: tuple[str, ...]
) -> tuple[ValidationStatus, str]:
    if len(required) != 2 or any(
        not column.strip() or "<<" in column for column in required
    ):
        return "unsupported", "BC CSV requires two resolved named column selectors"
    counts: dict[str, int] = defaultdict(int)
    for column in header:
        counts[column.casefold()] += 1
    missing = list(dict.fromkeys(
        column for column in required
        if counts[column.strip().casefold()] == 0
    ))
    ambiguous = list(dict.fromkeys(
        column for column in required
        if counts[column.strip().casefold()] > 1
    ))
    if missing or ambiguous:
        problems: list[str] = []
        if missing:
            problems.append(f"Missing BC CSV columns: {', '.join(missing)}")
        if ambiguous:
            problems.append(f"Ambiguous BC CSV columns: {', '.join(ambiguous)}")
        return "unresolved", "; ".join(problems)
    return "present", ""


def validate_dependencies(
    projection: DependencyProjection,
    *,
    options: ValidationOptions | None = None,
) -> ValidationReport:
    """Inspect explicitly requested TUFLOW inputs without changing the model.

    Source references come from an already-parsed run projection. No TCF
    parsing, variable substitution, simulator execution or model edits occur.
    File results are shared only within this invocation; finding ownership is
    restored independently for each run and source declaration.
    """

    policy = options if options is not None else ValidationOptions()
    if not projection.runs:
        raise ValueError("At least one run is required for input validation")
    requirements, failures = _requirements(projection)

    def finding(
        item: _Requirement,
        status: ValidationStatus,
        kind: ValidationKind,
        path: Path,
        detail: str = "",
    ) -> ValidationFinding:
        return ValidationFinding(
            item.run_index,
            item.flags,
            status,
            kind,
            path,
            detail,
            item.layer if kind == "layer" else None,
            item.origin,
            item.input_uuid,
            item.command_index,
            item.owner_control_file,
            item.database_kind,
            item.path if path != item.path else None,
            item.csv_columns if kind == "csv_header" else None,
        )

    # Explicitly disabled inspection is never treated as validation success.
    # In particular, do not scandir wildcard directories when file checks
    # were disabled by the caller.
    if not policy.check_files:
        return ValidationReport(
            tuple(failures) + tuple(
                finding(item, "unsupported", "file", item.path,
                        "Physical input-file inspection was disabled")
                for item in requirements
            ),
            len(projection.runs), 0, 0, 0, 0,
        )

    globs = {
        item.path for item in requirements
        if _has_wildcards(str(item.path))
        and not item.unresolved and "<<" not in str(item.path)
    }
    expansions, glob_errors, scan_count = _scan_wildcard_patterns(
        globs, maximum_entries=policy.maximum_directory_entries
    )
    concrete: list[tuple[_Requirement, Path]] = []
    for item in requirements:
        if item.unresolved or "<<" in str(item.path):
            failures.append(
                finding(item, "unresolved", "file", item.path, "Unresolved TUFLOW variables")
            )
        elif item.path in glob_errors:
            status, detail = glob_errors[item.path]
            failures.append(finding(item, status, "wildcard", item.path, detail))
        else:
            for path in expansions.get(item.path, (item.path,)):
                concrete.append((item, path))

    gpkg_paths: set[Path] = set()
    csv_requests: dict[Path, set[str]] = defaultdict(set)
    for item, path in concrete:
        if (
            policy.check_gpkg_layers
            and item.layer is not None
            and path.suffix.casefold() == ".gpkg"
        ):
            gpkg_paths.add(path)
        if (
            policy.check_bc_csv_headers
            and item.csv_columns is not None
            and len(item.csv_columns) == 2
            and path.suffix.casefold() == ".csv"
        ):
            csv_requests[path].update(item.csv_columns)
    files = {path for _, path in concrete}

    def inspect(path: Path) -> tuple[Path, _Inspection]:
        status, detail = _stat_source(path)
        if status != "present":
            return path, _Inspection(status, detail)
        layers: tuple[str, ...] = ()
        layer_error = ""
        csv_columns: tuple[str, ...] = ()
        csv_error = ""
        if path in gpkg_paths:
            layers, layer_error = _gpkg_contents(path)
        if path in csv_requests:
            csv_columns, csv_error = _csv_header(
                path,
                csv_requests[path],
                lines_limit=policy.maximum_header_lines,
                bytes_limit=policy.maximum_header_bytes,
            )
        return path, _Inspection(
            status,
            detail,
            layers,
            layer_error,
            csv_columns,
            csv_error,
            path in gpkg_paths,
            path in csv_requests,
        )

    examined: dict[Path, _Inspection] = {}
    if policy.check_files:
        ordered = sorted(files)
        if policy.io_workers == 1:
            examined = dict(inspect(path) for path in ordered)
        else:
            with ThreadPoolExecutor(max_workers=policy.io_workers) as executor:
                examined = dict(executor.map(inspect, ordered))

    findings = failures[:]
    for item, path in concrete:
        if not policy.check_files:
            continue
        info = examined[path]
        findings.append(finding(item, info.status, "file", path, info.detail))
        if info.status != "present":
            continue
        if (
            policy.check_gpkg_layers and item.layer is not None
            and path.suffix.casefold() == ".gpkg"
        ):
            if info.layer_error:
                findings.append(
                    finding(item, "unresolved", "layer", path, info.layer_error)
                )
            else:
                status, detail = _layer_status(item.layer, info.layers)
                findings.append(finding(item, status, "layer", path, detail))
        if policy.check_bc_csv_headers and item.database_kind == "bc":
            if item.csv_columns is None:
                if path.suffix.casefold() == ".csv":
                    findings.append(
                        finding(
                            item, "unsupported", "csv_header", path,
                            "Parser did not provide BC CSV column requirements",
                        )
                    )
                continue
            if not item.csv_columns:
                continue  # FEWS/nonordinary CSV: no ordinary named selectors.
            if path.suffix.casefold() != ".csv":
                findings.append(
                    finding(
                        item, "unsupported", "csv_header", path,
                        "BC column selectors require an ordinary Source CSV",
                    )
                )
            elif info.csv_error:
                findings.append(
                    finding(item, "unresolved", "csv_header", path, info.csv_error)
                )
            else:
                status, detail = _header_status(
                    info.csv_header, item.csv_columns
                )
                findings.append(
                    finding(item, status, "csv_header", path, detail)
                )

    return ValidationReport(
        tuple(findings),
        len(projection.runs),
        len(examined),
        sum(result.gpkg_examined for result in examined.values()),
        sum(result.csv_examined for result in examined.values()),
        scan_count,
    )
