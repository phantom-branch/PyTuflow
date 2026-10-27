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
    # Linux TUFLOW -cs0/-cs1/-cs2. None means the projection has not
    # provided a policy: a possible spelling mismatch must fail closed.
    case_sensitivity: int | None = None

    def __post_init__(self) -> None:
        if self.case_sensitivity is not None and (
            type(self.case_sensitivity) is not int
            or self.case_sensitivity not in (0, 1, 2)
        ):
            raise ValueError("case_sensitivity must be 0, 1, 2 or None")
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
    secondary_source: bool = False


@dataclass(frozen=True, slots=True)
class _Inspection:
    status: ValidationStatus
    detail: str = ""
    layers: tuple[str, ...] = ()
    layer_error: str = ""
    csv_records: tuple[tuple[str, ...], ...] = ()
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
                        getattr(reference, "csv_columns", None),
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
                        getattr(reference, "csv_columns", None),
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
                    getattr(source, "csv_columns", None),
                    secondary_source=True,
                )
            )
    return requirements, errors


def _has_wildcards(path: str) -> bool:
    return any(char in path for char in "*?[")


def _filename_matches(
    candidate: str, pattern: str, case_sensitivity: int | None, *,
    windows: bool,
) -> bool:
    """Match the final filename using TUFLOW -cs semantics, not folder case.

    -cs0 is strict; -cs1 relaxes extensions only; -cs2 relaxes both filename
    and extension. Windows always uses its filesystem's insensitive names.
    """
    if windows:
        return fnmatch.fnmatchcase(
            os.path.normcase(candidate), os.path.normcase(pattern)
        )
    if case_sensitivity in (0, None):
        return fnmatch.fnmatchcase(candidate, pattern)
    if case_sensitivity == 1:
        return (
            fnmatch.fnmatchcase(Path(candidate).stem, Path(pattern).stem)
            and fnmatch.fnmatchcase(
                Path(candidate).suffix.casefold(),
                Path(pattern).suffix.casefold(),
            )
        )
    return fnmatch.fnmatchcase(candidate.casefold(), pattern.casefold())


def _scan_wildcard_patterns(
    patterns: Collection[Path], *, maximum_entries: int,
    case_sensitivity: int | None,
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
        uncertain: set[Path] = set()
        scans += 1
        problem: tuple[ValidationStatus, str] | None = None
        try:
            with os.scandir(parent) as iterator:
                for index, entry in enumerate(iterator):
                    if index >= maximum_entries:
                        raise ValueError("Wildcard directory exceeds bounded scan limit")
                    for pattern in siblings:
                        if _filename_matches(
                            entry.name, pattern.name, case_sensitivity,
                            windows=os.name == "nt",
                        ):
                            matches[pattern].append(parent / entry.name)
                        elif (
                            os.name != "nt"
                            and case_sensitivity is None
                            and _filename_matches(
                                entry.name, pattern.name, 2, windows=False
                            )
                        ):
                            uncertain.add(pattern)
        except FileNotFoundError:
            problem: tuple[ValidationStatus, str] = (
                "missing", "Wildcard parent directory does not exist"
            )
        except (OSError, ValueError) as exc:
            problem = ("unresolved", f"Cannot inspect wildcard directory: {exc}")
        for pattern in siblings:
            if problem is not None:
                failures[pattern] = problem
            elif pattern in uncertain:
                # A partial strict match cannot certify that -cs1/-cs2 would
                # not select other candidate files in the same directory.
                failures[pattern] = (
                    "unsupported",
                    "Linux filename case policy unknown: supply -cs0/-cs1/-cs2",
                )
            elif matches[pattern]:
                found[pattern] = tuple(sorted(matches[pattern]))
            else:
                failures[pattern] = (
                    "missing", "No input files match wildcard pattern"
                )
    return found, failures, scans


_UNSAVED_GPKG_WAL_ERROR = (
    "GeoPackage has a non-empty SQLite -wal journal; main .gpkg may "
    "not contain saved changes. Save/close the editing session, "
    "checkpoint the database externally, and rerun validation"
)


def _has_unsaved_gpkg_wal(path: Path) -> bool:
    """Detect journal data without reading or altering either SQLite sidecar."""
    wal = path.with_name(path.name + "-wal")
    try:
        return wal.stat().st_size > 0
    except FileNotFoundError:
        return False


def _stat_source(path: Path) -> tuple[ValidationStatus, str]:
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return "missing", "Input source file does not exist"
    except OSError as exc:
        return "unresolved", f"Cannot inspect input source file: {exc}"
    if not stat.S_ISREG(mode):
        return "missing", "Expected a regular file, not a directory or other type"
    if path.suffix.casefold() == ".gpkg":
        try:
            if _has_unsaved_gpkg_wal(path):
                return "unresolved", _UNSAVED_GPKG_WAL_ERROR
        except OSError as exc:
            return "unresolved", f"Cannot inspect GeoPackage WAL state: {exc}"
    return "present", ""


def _gpkg_contents(path: Path) -> tuple[tuple[str, ...], str]:
    """Require a saved main GeoPackage; never create or read journal sidecars.

    SQLite mode=ro may create -wal/-shm files. immutable=1 avoids these
    writes and reads only the checkpointed main .gpkg. A non-empty WAL means
    the main file is not certified complete: fail explicitly instead of
    counting missing WAL-only layers as ordinary absent layers.
    """
    try:
        if _has_unsaved_gpkg_wal(path):
            return (), _UNSAVED_GPKG_WAL_ERROR
        before = path.stat()
        uri = f"{path.absolute().as_uri()}?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            names = tuple(
                str(row[0]) for row in db.execute("SELECT table_name FROM gpkg_contents")
            )
        after = path.stat()
        if _has_unsaved_gpkg_wal(path):
            return (), _UNSAVED_GPKG_WAL_ERROR
        if (before.st_size, before.st_mtime_ns) != (
            after.st_size, after.st_mtime_ns
        ):
            return (), "Main GeoPackage changed during read-only inspection"
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


def _csv_records(
    path: Path, requested: Collection[tuple[str, ...]], *,
    lines_limit: int, bytes_limit: int,
) -> tuple[tuple[tuple[str, ...], ...], str]:
    """Read one bounded CSV snapshot, keeping each run's selectors independent.

    Stop after the first candidate header for *each* selector pair. The same
    physical file is opened once, but no other run's requested columns can
    change which header a given run selects. Never parse numeric series values.
    """
    rows: list[tuple[str, ...]] = []
    requirements = frozenset(
        frozenset(name.strip().casefold() for name in pair if name.strip())
        for pair in requested
        if len(pair) == 2 and all(name.strip() for name in pair)
    )
    selected: set[frozenset[str]] = set()
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
                if not any(columns):
                    record_started = False
                    continue
                rows.append(columns)
                names = {column.casefold() for column in columns}
                for needed in requirements - selected:
                    if needed & names:
                        selected.add(needed)
                if selected == requirements:
                    break
                record_started = False
        return tuple(rows), ""
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        # Headers found before a subsequent malformed record still count:
        # one unrelated, invalid selection must not invalidate a valid run.
        return tuple(rows), f"Cannot inspect CSV header: {exc}"


def _select_csv_header(
    rows: tuple[tuple[str, ...], ...], required: tuple[str, ...], *,
    lines_limit: int, read_error: str,
) -> tuple[tuple[str, ...], str]:
    """Find each requirement's *own* first matching header record."""
    requested = {name.strip().casefold() for name in required if name.strip()}
    for row in rows:
        if requested.intersection(name.casefold() for name in row):
            return row, ""
    return (), read_error or (
        f"No CSV header containing a required name within first {lines_limit} "
        "physical lines"
    )


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
        globs, maximum_entries=policy.maximum_directory_entries,
        case_sensitivity=policy.case_sensitivity,
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
                # Literal Linux filenames may have a deliberately relaxed
                # final-component spelling. Use the same -cs helper as the
                # parsed TUFLOW file resolution; never relax directories.
                if (
                    path == item.path and not _has_wildcards(str(path))
                    and os.name != "nt"
                ):
                    if policy.case_sensitivity is None and not path.exists():
                        failures.append(
                            finding(
                                item, "unsupported", "file", path,
                                "Linux filename case policy unknown: supply -cs0/-cs1/-cs2",
                            )
                        )
                        continue
                    if policy.case_sensitivity in (1, 2):
                        from ._tmf.tfpathlib import TuflowPath

                        try:
                            path = TuflowPath.init_case_policy_path(
                                path, case_sensitivity=policy.case_sensitivity,
                            ).dbpath
                        except (ValueError, OSError) as exc:
                            failures.append(
                                finding(item, "unresolved", "file", path, str(exc))
                            )
                            continue
                concrete.append((item, path))

    gpkg_paths: set[Path] = set()
    csv_requests: dict[Path, set[tuple[str, ...]]] = defaultdict(set)
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
            csv_requests[path].add(item.csv_columns)
    files = {path for _, path in concrete}

    def inspect(path: Path) -> tuple[Path, _Inspection]:
        status, detail = _stat_source(path)
        if status != "present":
            return path, _Inspection(status, detail)
        layers: tuple[str, ...] = ()
        layer_error = ""
        csv_records: tuple[tuple[str, ...], ...] = ()
        csv_error = ""
        if path in gpkg_paths:
            layers, layer_error = _gpkg_contents(path)
        if path in csv_requests:
            csv_records, csv_error = _csv_records(
                path, csv_requests[path],
                lines_limit=policy.maximum_header_lines,
                bytes_limit=policy.maximum_header_bytes,
            )
        return path, _Inspection(
            status,
            detail,
            layers,
            layer_error,
            csv_records,
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
        if policy.check_bc_csv_headers and (
            item.csv_columns is not None
            or (
                item.secondary_source
                and item.database_kind == "bc"
                and path.suffix.casefold() == ".csv"
            )
        ):
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
            elif len(item.csv_columns) != 2 or any(
                not column.strip() or "<<" in column
                for column in item.csv_columns
            ):
                status, detail = _header_status((), item.csv_columns)
                findings.append(
                    finding(item, status, "csv_header", path, detail)
                )
            else:
                header, header_error = _select_csv_header(
                    info.csv_records, item.csv_columns,
                    lines_limit=policy.maximum_header_lines,
                    read_error=info.csv_error,
                )
                if header_error:
                    status, detail = "unresolved", header_error
                else:
                    status, detail = _header_status(
                        header, item.csv_columns
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
