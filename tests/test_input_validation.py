"""Synthetic contracts for explicit PyTUFLOW physical input validation.

All fixtures are local, temporary and read-only after construction. The
tests never run TUFLOW or depend on a real GIS/QGIS installation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pytuflow._tmf.batch_dependencies import BatchDependencyRun, BatchInputReference
from pytuflow._tmf.file_reference import (
    DeferredDatabaseActivation,
    DeferredDatabaseSource,
    FileReference,
)
from pytuflow.validation import ValidationOptions, validate_dependencies


def _ref(
    path: Path, *,
    layer: str | None = None,
    csv_columns: tuple[str, ...] | None = None,
    unresolved: tuple[str, ...] = (),
) -> FileReference:
    reference = FileReference(
        base_directory=path.parent,
        expanded_value=str(path.name),
        path_pattern=path,
        layer_pattern=layer,
        origin="Read GIS Code" if layer else "Read File",
        requires_directory_scan=("*" in path.name),
        requires_layer_scan=layer is not None,
        requires_attribute_scan=False,
        requires_database_scan=False,
        unresolved_variables=unresolved,
    )
    if csv_columns is None:
        return reference
    # Current master predates #39's csv_columns reference field. Preserve
    # the precise structural surface until the feature branch is refreshed.
    payload = vars(reference).copy()
    payload["csv_columns"] = csv_columns
    return cast(FileReference, SimpleNamespace(**payload))


def _run(
    index: int,
    refs: tuple[FileReference, ...] = (),
    *,
    sources: tuple[DeferredDatabaseSource, ...] = (),
    activations: tuple[DeferredDatabaseActivation, ...] = (),
    error: str | None = None,
) -> BatchDependencyRun:
    links = tuple(
        BatchInputReference(
            input_uuid=f"input-{ordinal}",
            command_index=ordinal,
            owner_control_file=ref.base_directory / "model.tcf",
            line_number=ordinal + 1,
            reference=ref,
        )
        for ordinal, ref in enumerate(refs)
    )
    return BatchDependencyRun(
        index=index,
        flags=f"-s1 S{index}",
        file_references=refs,
        database_sources=sources,
        database_activations=activations,
        error=error,
        input_references=links,
    )


def _project(*runs: BatchDependencyRun) -> SimpleNamespace:
    return SimpleNamespace(runs=tuple(runs))


def _bc_source(
    path: Path, *,
    columns: tuple[str, ...] | None,
    input_uuid: str = "bc-declaration",
) -> DeferredDatabaseSource:
    source = DeferredDatabaseSource(
        database_path=path.parent / "bc_dbase.csv",
        database_kind="bc",
        entry_name="inflow",
        path_pattern=path,
        owning_command="BC Database",
        owner_control_file=path.parent / "model.tbc",
        input_uuid=input_uuid,
    )
    if columns is None:
        return source
    payload = vars(source).copy()
    payload["csv_columns"] = columns
    return cast(DeferredDatabaseSource, SimpleNamespace(**payload))


def _bc_activation(path: Path, *, input_uuid: str = "bc-declaration") -> DeferredDatabaseActivation:
    return DeferredDatabaseActivation(
        sequence=5,
        input_uuid=input_uuid,
        database_kind="bc",
        database_path=path.parent / "bc_dbase.csv",
        owning_command="BC Database",
        owner_control_file=path.parent / "model.tbc",
        line_number=10,
    )


def test_file_and_directory_status_and_ordered_provenance(tmp_path: Path) -> None:
    present = tmp_path / "exists.shp"
    present.write_bytes(b"data")
    directory = tmp_path / "not-a-file.shp"
    directory.mkdir()
    missing = tmp_path / "missing.tif"
    report = validate_dependencies(
        _project(
            _run(0, (_ref(present), _ref(directory), _ref(missing))),
            _run(1, (_ref(present),)),
        ),
        options=ValidationOptions(case_sensitivity=0),
    )
    assert not report.passed
    assert report.run_count == 2
    assert report.files_examined == 3
    assert report.geopackages_examined == report.csv_headers_examined == 0
    assert [(x.run_index, x.status) for x in report.findings] == [
        (0, "present"),
        (0, "missing"),
        (0, "missing"),
        (1, "present"),
    ]
    assert [(x.input_uuid, x.command_index) for x in report.findings[:3]] == [
        ("input-0", 0),
        ("input-1", 1),
        ("input-2", 2),
    ]


@pytest.mark.parametrize(
    ("candidate", "pattern", "case_sensitivity", "matched"),
    [
        ("Grid_A.TIF", "grid_*.tif", 0, False),
        ("Grid_A.TIF", "grid_*.tif", 1, False),
        ("grid_A.TIF", "grid_*.tif", 1, True),
        ("rain_A.CSV", "rain_*", 1, True),
        ("Rain_A.CSV", "rain_*", 1, False),
        ("rain_A.CSV", "rain_*", 0, True),
        ("Grid_A.TIF", "grid_*.tif", 2, True),
        ("Grid_A.TIF", "grid_*.tif", None, False),
    ],
)
def test_tuflow_linux_filename_glob_case_modes(
    candidate: str, pattern: str, case_sensitivity: int | None,
    matched: bool,
) -> None:
    from pytuflow.validation import _filename_matches

    assert _filename_matches(
        candidate, pattern, case_sensitivity, windows=False,
    ) is matched


def test_unique_wildcards_are_grouped_and_expanded_for_every_run(
    tmp_path: Path,
) -> None:
    for name in ("rain_A.shp", "rain_B.shp"):
        (tmp_path / name).write_bytes(b"test")
    pattern = tmp_path / "rain_*.shp"
    report = validate_dependencies(
        _project(_run(0, (_ref(pattern),)), _run(1, (_ref(pattern),))),
    )
    assert report.passed
    assert report.directories_scanned == 1
    assert report.files_examined == 2
    assert [(f.run_index, f.path.name) for f in report.findings] == [
        (0, "rain_A.shp"),
        (0, "rain_B.shp"),
        (1, "rain_A.shp"),
        (1, "rain_B.shp"),
    ]
    assert all(f.source_pattern == pattern for f in report.findings)


@pytest.mark.parametrize(
    ("pattern", "expected_status"),
    [
        ("absent_*.shp", "missing"),
        ("no_parent/absent_*.shp", "missing"),
        ("*/rain.shp", "unsupported"),
    ],
)
def test_missing_and_unsupported_wildcard_requirements(
    tmp_path: Path, pattern: str, expected_status: str
) -> None:
    report = validate_dependencies(_project(_run(0, (_ref(tmp_path / pattern),))))
    assert len(report.findings) == 1
    assert report.findings[0].status == expected_status
    assert not report.passed


def test_bounded_wildcard_scan_fails_closed(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"source_{index}.shp").write_bytes(b"data")
    report = validate_dependencies(
        _project(_run(0, (_ref(tmp_path / "source_*.shp"),))),
        options=ValidationOptions(maximum_directory_entries=1),
    )
    assert not report.passed
    assert report.findings[0].status == "unresolved"
    assert "bounded scan limit" in report.findings[0].detail
    assert report.files_examined == 0
    assert report.directories_scanned == 1


def test_parser_error_and_unresolved_variables_do_not_stat_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Parser error or unresolved name must not be inspected")

    monkeypatch.setattr(Path, "stat", forbid)
    unresolved = _ref(
        tmp_path / "path_<<~s1~>>.shp", unresolved=("<<~s1~>>",)
    )
    report = validate_dependencies(
        _project(
            _run(0, (unresolved,)),
            _run(1, (_ref(tmp_path / "partial.shp"),), error="Parser failure"),
        )
    )
    assert [x.kind for x in report.findings] == ["context", "file"]
    assert all(x.status == "unresolved" for x in report.findings)
    assert report.files_examined == 0


def test_gpkg_exact_wildcard_and_all_layers_use_one_readonly_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pytuflow import validation

    gpkg = tmp_path / "terrain.gpkg"
    with sqlite3.connect(gpkg) as connection:
        connection.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
        connection.executemany(
            "INSERT INTO gpkg_contents VALUES (?)",
            [("2d_code_L",), ("2d_code_P",)],
        )

    connect = sqlite3.connect
    calls: list[str] = []

    def counted(database: str, *args: object, **kwargs: object) -> sqlite3.Connection:
        calls.append(database)
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(validation.sqlite3, "connect", counted)
    report = validate_dependencies(
        _project(
            _run(0, (_ref(gpkg, layer="2d_code_L"), _ref(gpkg, layer="2d_code_*"))),
            _run(1, (_ref(gpkg, layer="all"), _ref(gpkg, layer="not_there"))),
        ),
    )
    assert report.files_examined == 1
    assert report.geopackages_examined == len(calls) == 1
    assert calls[0].endswith("?mode=ro&immutable=1")
    layers = [finding for finding in report.findings if finding.kind == "layer"]
    assert [item.status for item in layers] == [
        "present", "present", "present", "missing",
    ]
    assert not report.passed
    assert all(item.input_uuid.startswith("input-") for item in layers)


def test_gpkg_uncheckpointed_wal_changes_fail_without_writes(
    tmp_path: Path,
) -> None:
    """Fail on WAL-only changes; leave the editor's WAL and SHM untouched."""
    gpkg = tmp_path / "working.gpkg"
    editor = sqlite3.connect(gpkg)
    try:
        editor.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
        editor.execute("INSERT INTO gpkg_contents VALUES ('checkpointed_layer')")
        editor.commit()
        assert editor.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        editor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        editor.execute("INSERT INTO gpkg_contents VALUES ('wal_only_edit')")
        editor.commit()

        wal = gpkg.with_name(gpkg.name + "-wal")
        shm = gpkg.with_name(gpkg.name + "-shm")
        assert wal.exists() and shm.exists()
        before = {item.name: item.read_bytes() for item in tmp_path.iterdir()}

        report = validate_dependencies(
            _project(
                _run(
                    0,
                    (
                        _ref(gpkg, layer="checkpointed_layer"),
                        _ref(gpkg, layer="wal_only_edit"),
                        _ref(gpkg),  # No layer selector: still an invalid GPKG
                    ),
                )
            )
        )
        after = {item.name: item.read_bytes() for item in tmp_path.iterdir()}

        assert after == before
        assert not report.passed
        assert report.files_examined == 1
        # WAL checks happen before connecting to SQLite, including when no
        # layer was requested. A rejected GPKG must never be counted as an
        # inspected valid GeoPackage.
        assert report.geopackages_examined == 0
        assert len(report.findings) == 3
        assert all(
            finding.status == "unresolved" and finding.kind == "file"
            for finding in report.findings
        )
        assert all(
            "non-empty SQLite -wal journal" in finding.detail
            and "Save/close" in finding.detail
            for finding in report.findings
        )
    finally:
        editor.close()


def test_gpkg_wal_journal_mode_without_sidecars_creates_no_files(
    tmp_path: Path,
) -> None:
    gpkg = tmp_path / "saved.gpkg"
    editor = sqlite3.connect(gpkg)
    try:
        editor.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
        editor.execute("INSERT INTO gpkg_contents VALUES ('saved_layer')")
        editor.commit()
        assert editor.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    finally:
        editor.close()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["saved.gpkg"]
    before = gpkg.read_bytes()
    report = validate_dependencies(
        _project(_run(0, (_ref(gpkg, layer="saved_layer"),)))
    )
    assert report.passed
    assert report.geopackages_examined == 1
    assert gpkg.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["saved.gpkg"]


def test_symlinked_geopackage_rejects_wal_beside_real_target(
    tmp_path: Path,
) -> None:
    """Never accept uncheckpointed WAL edits hidden by a database symlink."""
    target = tmp_path / "real.gpkg"
    alias = tmp_path / "alias.gpkg"
    editor = sqlite3.connect(target)
    try:
        editor.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
        editor.execute("INSERT INTO gpkg_contents VALUES ('saved_layer')")
        editor.commit()
        assert editor.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        editor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        editor.execute("INSERT INTO gpkg_contents VALUES ('wal_only_edit')")
        editor.commit()
        try:
            alias.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"Filesystem symlinks unavailable: {exc}")

        assert (tmp_path / "real.gpkg-wal").stat().st_size > 0
        before = {file.name: file.read_bytes() for file in tmp_path.iterdir()}
        report = validate_dependencies(
            _project(_run(0, (_ref(alias), _ref(alias, layer="saved_layer"))))
        )
        after = {file.name: file.read_bytes() for file in tmp_path.iterdir()}

        assert not report.passed
        assert report.geopackages_examined == 0
        assert report.files_examined == 1
        assert len(report.findings) == 2
        assert all(finding.path == alias for finding in report.findings)
        assert all(
            finding.status == "unresolved"
            and "non-empty SQLite -wal journal" in finding.detail
            for finding in report.findings
        )
        assert after == before
    finally:
        editor.close()


@pytest.mark.skipif(__import__("os").name == "nt", reason="Linux path-case policy")
def test_linux_explicit_case_policy_and_unknown_policy(tmp_path: Path) -> None:
    saved = tmp_path / "Grid_A.TIF"
    saved.write_bytes(b"grid")
    required = tmp_path / "grid_a.tif"
    projection = _project(_run(0, (_ref(required),)))

    unknown = validate_dependencies(projection)
    assert not unknown.passed
    assert unknown.findings[0].status == "unsupported"
    strict = validate_dependencies(
        projection, options=ValidationOptions(case_sensitivity=0)
    )
    assert not strict.passed
    assert strict.findings[0].status == "missing"
    relaxed = validate_dependencies(
        projection, options=ValidationOptions(case_sensitivity=2)
    )
    assert relaxed.passed
    assert relaxed.findings[0].path == saved

    wildcard = _project(_run(0, (_ref(tmp_path / "grid_*.tif"),)))
    matched = validate_dependencies(
        wildcard, options=ValidationOptions(case_sensitivity=2)
    )
    assert matched.passed
    assert matched.findings[0].path == saved


def test_invalid_geopackage_reports_unresolved_layer(tmp_path: Path) -> None:
    gpkg = tmp_path / "not_sqlite.gpkg"
    gpkg.write_bytes(b"invalid database")
    report = validate_dependencies(
        _project(_run(0, (_ref(gpkg, layer="2d_code_L"),))),
    )
    assert [(item.kind, item.status) for item in report.findings] == [
        ("file", "present"), ("layer", "unresolved")
    ]
    assert report.geopackages_examined == 1


def test_csv_header_is_checked_once_for_two_bc_activations(tmp_path: Path) -> None:
    source = tmp_path / "inflow.csv"
    source.write_text(
        "! TUFLOW event data\nEvent ID: E100\nTime,Flow,Stage\n0,2.5,0.1\n",
        encoding="utf-8",
    )
    a = _bc_source(source, columns=("Time", "Flow"))
    b = _bc_source(source, columns=("Time", "Stage"))
    report = validate_dependencies(
        _project(
            _run(0, sources=(a,), activations=(_bc_activation(source),)),
            _run(1, sources=(b,), activations=(_bc_activation(source),)),
        ),
        options=ValidationOptions(check_bc_csv_headers=True),
    )
    assert report.passed
    assert report.files_examined == report.csv_headers_examined == 1
    assert [(item.kind, item.command_index) for item in report.findings] == [
        ("file", 5), ("csv_header", 5), ("file", 5), ("csv_header", 5),
    ]
    assert all(item.input_uuid == "bc-declaration" for item in report.findings)


@pytest.mark.parametrize(
    ("columns", "status", "detail"),
    [
        (("Time", "Missing"), "unresolved", "Missing BC CSV columns"),
        (("Time", "Flow"), "unresolved", "Ambiguous BC CSV columns"),
        (("", "Flow"), "unsupported", "two resolved named column selectors"),
    ],
)
def test_csv_headers_detect_missing_duplicate_and_unresolved_selectors(
    tmp_path: Path, columns: tuple[str, str], status: str, detail: str
) -> None:
    source = tmp_path / "boundary.csv"
    source.write_text("Time,Flow,Flow\n0,1,2\n", encoding="utf-8")
    report = validate_dependencies(
        _project(
            _run(
                0,
                sources=(_bc_source(source, columns=columns),),
                activations=(_bc_activation(source),),
            )
        ),
        options=ValidationOptions(check_bc_csv_headers=True),
    )
    csv_findings = [
        item for item in report.findings if item.kind == "csv_header"
    ]
    assert len(csv_findings) == 1
    assert csv_findings[0].status == status
    assert detail in csv_findings[0].detail
    assert not report.passed


@pytest.mark.parametrize("invalid_first", [False, True])
def test_shared_bc_csv_header_selection_is_independent_per_run(
    tmp_path: Path, invalid_first: bool,
) -> None:
    """One run selecting a preamble must not invalidate a valid Source header."""
    source = tmp_path / "shared.csv"
    source.write_text(
        "Event ID: E100\nTime,Flow\n0,1\n", encoding="utf-8"
    )
    valid = _bc_source(source, columns=("Time", "Flow"))
    invalid = _bc_source(source, columns=("Event ID: E100", "Time"))
    first, second = (invalid, valid) if invalid_first else (valid, invalid)
    report = validate_dependencies(
        _project(
            _run(0, sources=(first,), activations=(_bc_activation(source),)),
            _run(1, sources=(second,), activations=(_bc_activation(source),)),
        ),
        options=ValidationOptions(check_bc_csv_headers=True),
    )
    assert not report.passed
    assert report.files_examined == 1
    assert report.csv_headers_examined == 1
    findings = [item for item in report.findings if item.kind == "csv_header"]
    assert len(findings) == 2
    by_index = {item.run_index: item for item in findings}
    valid_index = 1 if invalid_first else 0
    assert by_index[valid_index].status == "present"
    assert by_index[1 - valid_index].status == "unresolved"
    assert "Missing BC CSV columns" in by_index[1 - valid_index].detail


def test_csv_header_bounds_and_utf8_bom(tmp_path: Path) -> None:
    source = tmp_path / "long_header.csv"
    source.write_text(
        "\ufeff! first line\n! second line\n! third line\n"
        "! fourth line\n! fifth line\nTime,Flow\n0,1\n",
        encoding="utf-8",
    )
    projection = _project(
        _run(
            0,
            sources=(_bc_source(source, columns=("Time", "Flow")),),
            activations=(_bc_activation(source),),
        )
    )
    bounded = validate_dependencies(
        projection, options=ValidationOptions(check_bc_csv_headers=True)
    )
    assert not bounded.passed
    assert bounded.csv_headers_examined == 1
    assert "first 5 physical lines" in bounded.findings[-1].detail

    longer = validate_dependencies(
        projection,
        options=ValidationOptions(check_bc_csv_headers=True, maximum_header_lines=6),
    )
    assert longer.passed
    assert longer.csv_headers_examined == 1


def test_bounded_header_bytes_and_invalid_utf8_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "huge_header.csv"
    source.write_bytes(b"Time,Flow\n" + b"a" * 100)
    projection = _project(
        _run(
            0,
            sources=(_bc_source(source, columns=("Time", "Flow")),),
            activations=(_bc_activation(source),),
        )
    )
    tiny = validate_dependencies(
        projection,
        options=ValidationOptions(check_bc_csv_headers=True, maximum_header_bytes=4),
    )
    assert tiny.findings[-1].status == "unresolved"
    assert "bounded byte limit" in tiny.findings[-1].detail
    source.write_bytes(b"\xff,invalid\n")
    invalid = validate_dependencies(
        projection, options=ValidationOptions(check_bc_csv_headers=True)
    )
    assert invalid.findings[-1].status == "unresolved"


def test_fews_csv_skips_ordinary_header_check(tmp_path: Path) -> None:
    source = tmp_path / "fews.csv"
    source.write_bytes(b"not,an,ordinary,BC,header\n")
    report = validate_dependencies(
        _project(
            _run(
                0,
                sources=(_bc_source(source, columns=()),),
                activations=(_bc_activation(source),),
            )
        ),
        options=ValidationOptions(check_bc_csv_headers=True),
    )
    assert report.passed
    assert report.csv_headers_examined == 0
    assert len(report.findings) == 1
    assert report.findings[0].kind == "file"


def test_mismatched_bc_activation_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "value.csv"
    source.write_text("Time,Flow\n", encoding="utf-8")
    report = validate_dependencies(
        _project(
            _run(
                0,
                sources=(_bc_source(source, columns=("Time", "Flow"), input_uuid="other"),),
                activations=(_bc_activation(source),),
            )
        ),
        options=ValidationOptions(check_bc_csv_headers=True),
    )
    assert not report.passed
    assert report.findings[0].kind == "context"
    assert "no matching active" in report.findings[0].detail
    assert report.files_examined == 0


def test_no_file_check_with_only_optional_validation_disabled(tmp_path: Path) -> None:
    """Turning physical checks off must never implicitly touch source files."""
    invalid = tmp_path / "not_present.shp"
    report = validate_dependencies(
        _project(_run(0, (_ref(invalid),))),
        options=ValidationOptions(
            check_files=False,
            check_gpkg_layers=False,
            check_bc_csv_headers=False,
        ),
    )
    assert report.files_examined == 0
    assert report.directories_scanned == 0


def test_missing_bc_column_metadata_is_not_reported_as_valid(tmp_path: Path) -> None:
    source = tmp_path / "ordinary.csv"
    source.write_text("Time,Flow\n0,1\n", encoding="utf-8")
    report = validate_dependencies(
        _project(
            _run(
                0,
                sources=(_bc_source(source, columns=None),),
                activations=(_bc_activation(source),),
            )
        ),
        options=ValidationOptions(check_bc_csv_headers=True),
    )
    assert not report.passed
    assert report.csv_headers_examined == 0
    assert [(f.kind, f.status) for f in report.findings] == [
        ("file", "present"), ("csv_header", "unsupported"),
    ]


def test_disabled_validation_never_scans_wildcard_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("No filesystem inspection is allowed")

    monkeypatch.setattr(os, "scandir", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    report = validate_dependencies(
        _project(_run(0, (_ref(tmp_path / "source_*.shp"),))),
        options=ValidationOptions(
            check_files=False,
            check_gpkg_layers=False,
            check_bc_csv_headers=False,
        ),
    )
    assert not report.passed
    assert report.files_examined == report.directories_scanned == 0
    assert report.findings[0].status == "unsupported"


def test_primary_bc_database_is_not_misread_as_ordinary_source_csv(
    tmp_path: Path,
) -> None:
    """The BC Database itself is not a Source time-series CSV."""
    database = tmp_path / "bc_dbase.csv"
    database.write_text("Name,Source,Column 1,Column 2\n", encoding="utf-8")
    from dataclasses import replace

    primary = replace(_ref(database), database_kind="bc")
    report = validate_dependencies(
        _project(_run(0, (primary,))),
        options=ValidationOptions(check_bc_csv_headers=True),
    )
    assert report.passed
    assert report.files_examined == 1
    assert report.csv_headers_examined == 0
    assert len(report.findings) == 1
    assert report.findings[0].kind == "file"
