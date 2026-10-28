"""End-to-end checks of the separate deferred batch parser and file validator.

Fixtures are synthetic and use only temporary local files; TUFLOW, GDAL and
QGIS solvers/providers are never launched. Physical checks are explicit.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow.batch_parser import validate_batch
from pytuflow.validation import ValidationOptions


def _gpkg(path: Path, *layers: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO gpkg_contents (table_name) VALUES (?)",
            ((name,) for name in layers),
        )


def test_existing_files_and_named_layers_across_conditional_runs(tmp_path: Path) -> None:
    _gpkg(tmp_path / "dev.gpkg", "2d_code")
    _gpkg(tmp_path / "exg.gpkg", "2d_code")
    (tmp_path / "model.tcf").write_text(
        "If Scenario == DEV\n"
        " Read GIS Code == dev.gpkg >> 2d_code\n"
        "Else\n"
        " Read GIS Code == exg.gpkg >> 2d_code\n"
        "End If\n",
        encoding="utf-8",
    )
    model = TCF(tmp_path / "model.tcf")
    flags = ["-s1 DEV -e1 E1", "-s1 EXG -e1 E1"]
    result = validate_batch(model, flags)
    assert result.passed, result.issues
    assert result.validation.run_count == 2
    assert result.validation.geopackages_examined == 2
    assert result.validation.files_examined == 2
    assert sum(x.kind == "layer" for x in result.validation.findings) == 2
    assert result.dependencies.runs == model.collect_file_dependencies(flags).runs


def test_nonexistent_layer_is_reported_for_exact_run(tmp_path: Path) -> None:
    _gpkg(tmp_path / "model.gpkg", "other_layer")
    (tmp_path / "model.tcf").write_text(
        "Read GIS Code == model.gpkg >> 2d_code\n", encoding="utf-8"
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 DEV"])
    assert not result.passed
    assert any(
        issue.kind == "layer"
        and issue.status == "missing"
        and issue.layer == "2d_code"
        and issue.run_index == 0
        for issue in result.issues
    ), result.issues


def test_missing_files_do_not_pass_even_with_complete_syntax(tmp_path: Path) -> None:
    (tmp_path / "model.tcf").write_text(
        "Read Grid Zpts == missing_<<~s1~>>.tif\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 DEV", "-s1 EXG"])
    assert result.dependencies.passed
    assert not result.passed
    assert {x.run_index for x in result.issues} == {0, 1}
    assert all(x.status == "missing" for x in result.issues)


def test_shared_csv_header_checked_once_and_wrong_columns_fail(tmp_path: Path) -> None:
    (tmp_path / "bc.csv").write_text(
        "Name,Source,Column 1,Column 2\n"
        "flow,inflow.csv,Time,Flow\n",
        encoding="utf-8",
    )
    (tmp_path / "inflow.csv").write_text("Time,Flow\n0,10\n", encoding="utf-8")
    (tmp_path / "model.tcf").write_text(
        "BC Database == bc.csv\n",
        encoding="utf-8",
    )
    flags = ["-s1 EXG -e1 A", "-s1 DEV -e1 B"]
    result = validate_batch(tmp_path / "model.tcf", flags)
    assert result.passed, result.issues
    assert result.validation.csv_headers_examined == 1

    (tmp_path / "inflow.csv").write_text("Time,WrongColumn\n0,10\n", encoding="utf-8")
    invalid = validate_batch(tmp_path / "model.tcf", flags)
    assert not invalid.passed
    assert {
        item.run_index
        for item in invalid.issues
        if item.kind == "csv_header"
    } == {0, 1}


def test_wildcard_layers_and_physical_files_are_all_checked(tmp_path: Path) -> None:
    _gpkg(tmp_path / "terrain_A.gpkg", "terrain_A")
    _gpkg(tmp_path / "terrain_B.gpkg", "terrain_B")
    (tmp_path / "model.tcf").write_text(
        "Read GIS Code == terrain_*.gpkg\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 DEV"])
    assert result.passed, result.issues
    assert result.validation.geopackages_examined == 2
    assert {
        f.layer for f in result.validation.findings if f.kind == "layer"
    } == {"terrain_A", "terrain_B"}


def test_fail_closed_context_does_not_inspect_partial_references(tmp_path: Path) -> None:
    (tmp_path / "model.tcf").write_text(
        "Read Grid Zpts == some_grid.tif\n"
        "If Scenario == BAD\n PAUSE\nEnd If\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 BAD", "-s1 GOOD"])
    assert not result.passed
    assert any(x.kind == "context" and x.run_index == 0 for x in result.issues)
    assert all(
        x.run_index != 0 or x.kind == "context"
        for x in result.validation.findings
    )


def test_validation_options_cannot_conflict_with_parsed_case_policy(tmp_path: Path) -> None:
    (tmp_path / "model.tcf").write_text("Read Grid Zpts == terrain.tif\n", encoding="utf-8")
    parsed = TCF(tmp_path / "model.tcf", case_sensitivity=0)
    with pytest.raises(ValueError, match="case_sensitivity"):
        validate_batch(
            parsed, ["-s1 EXG"],
            options=ValidationOptions(case_sensitivity=2),
        )


def test_dependency_collection_does_not_provoke_physical_checks(tmp_path: Path) -> None:
    (tmp_path / "model.tcf").write_text("Read Grid Zpts == grid.tif\n", encoding="utf-8")
    parsed = TCF(tmp_path / "model.tcf")
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
    ):
        projected = parsed.collect_file_dependencies(["-s1 EXG", "-s1 DEV"])
    assert projected.passed


def _linked_gpkg(path: Path, *, layer: str, file_name: str) -> None:
    """One real GPKG attribute table with the first TUFLOW file field."""
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY)")
        connection.execute(
            "INSERT INTO gpkg_contents (table_name) VALUES (?)", (layer,)
        )
        connection.execute(
            "CREATE TABLE gpkg_geometry_columns "
            "(table_name TEXT, column_name TEXT, geometry_type_name TEXT)"
        )
        connection.execute(
            "INSERT INTO gpkg_geometry_columns "
            "(table_name, column_name, geometry_type_name) VALUES (?, ?, ?)",
            (layer, "geom", "LINESTRING"),
        )
        connection.execute(
            f'CREATE TABLE "{layer}" (fid INTEGER PRIMARY KEY, geom BLOB, Source TEXT)'
        )
        connection.execute(
            f'INSERT INTO "{layer}" (Source) VALUES (?)', (file_name,)
        )


def test_gpkg_feature_linked_csv_must_exist(tmp_path: Path) -> None:
    gpkg = tmp_path / "links.gpkg"
    _linked_gpkg(gpkg, layer="1d_xs_link", file_name="xs_data.csv")
    (tmp_path / "xs_data.csv").write_text("chainage,z\n0,1\n", encoding="utf-8")
    (tmp_path / "model.tcf").write_text(
        "Read GIS Code == links.gpkg >> 1d_xs_link\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 EXG"])
    assert result.passed, result.issues
    assert result.gis_sources_added == 1
    assert result.gis_files_scanned == 1
    assert result.validation.files_examined == 2
    assert any(
        item.path and item.path.name == "xs_data.csv"
        and item.kind == "file" and item.status == "present"
        for item in result.validation.findings
    )

    (tmp_path / "xs_data.csv").unlink()
    missing = validate_batch(tmp_path / "model.tcf", ["-s1 EXG"])
    assert not missing.passed
    assert any(
        item.kind == "file" and item.status == "missing"
        and item.path and item.path.name == "xs_data.csv"
        for item in missing.issues
    )


def test_attribute_linked_sources_are_checked_for_each_run(tmp_path: Path) -> None:
    _linked_gpkg(tmp_path / "links.gpkg", layer="1d_xs_link", file_name="data.csv")
    (tmp_path / "data.csv").write_text("x,z\n0,2\n", encoding="utf-8")
    (tmp_path / "model.tcf").write_text(
        "Read GIS Code == links.gpkg >> 1d_xs_link\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-e1 A", "-e1 B"])
    assert result.passed, result.issues
    assert result.gis_files_scanned == 1
    assert result.gis_sources_added == 2
    assert result.validation.files_examined == 2


def test_unknown_gis_attribute_schema_fails_closed(tmp_path: Path) -> None:
    gpkg = tmp_path / "invalid.gpkg"
    with sqlite3.connect(gpkg) as connection:
        connection.execute("CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY)")
        connection.execute(
            "INSERT INTO gpkg_contents VALUES ('1d_xs_bad')"
        )
        connection.execute(
            "CREATE TABLE gpkg_geometry_columns "
            "(table_name TEXT, column_name TEXT, geometry_type_name TEXT)"
        )
        connection.execute(
            "INSERT INTO gpkg_geometry_columns VALUES "
            "('1d_xs_bad', 'geom', 'LINESTRING')"
        )
        connection.execute('CREATE TABLE "1d_xs_bad" (fid INTEGER PRIMARY KEY, geom BLOB)')
    (tmp_path / "model.tcf").write_text(
        "Read GIS Code == invalid.gpkg >> 1d_xs_bad\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 EXG"])
    assert not result.passed
    assert any(
        item.kind == "attribute" and item.status == "unresolved"
        for item in result.issues
    )


def _bc_gpkg(path: Path, *, name: str) -> None:
    layer = "2d_bc_lines"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY)")
        con.execute("INSERT INTO gpkg_contents VALUES (?)", (layer,))
        con.execute(
            "CREATE TABLE gpkg_geometry_columns "
            "(table_name TEXT, column_name TEXT, geometry_type_name TEXT)"
        )
        con.execute(
            "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'LINESTRING')",
            (layer,),
        )
        con.execute(
            f'CREATE TABLE "{layer}" '
            "(fid INTEGER PRIMARY KEY, geom BLOB, "
            "Type TEXT, Flags TEXT, Name TEXT, f4 TEXT, f5 TEXT, "
            "f6 TEXT, f7 TEXT, b REAL)"
        )
        con.execute(
            f'INSERT INTO "{layer}" (Type, Flags, Name, b) VALUES (?, ?, ?, ?)',
            ("QT", "", name, None),
        )


def test_missing_active_bc_identifier_fails_closed(tmp_path: Path) -> None:
    _bc_gpkg(tmp_path / "bc.gpkg", name="NOT_IN_DATABASE")
    (tmp_path / "bc.csv").write_text(
        "Name,Source,Column 1,Column 2\nvalid,inflow.csv,Time,Flow\n",
        encoding="utf-8",
    )
    (tmp_path / "inflow.csv").write_text(
        "Time,Flow\n0,1\n", encoding="utf-8"
    )
    (tmp_path / "model.tcf").write_text(
        "BC Database == bc.csv\n"
        "Read GIS BC == bc.gpkg >> 2d_bc_lines\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 EXG"])
    assert not result.passed
    assert any(
        finding.kind == "attribute"
        and "NOT_IN_DATABASE" in finding.detail
        for finding in result.issues
    ), result.issues


def test_feature_linked_wildcard_geopackages_scan_every_match(tmp_path: Path) -> None:
    _linked_gpkg(tmp_path / "link_A.gpkg", layer="1d_xs_link", file_name="A.csv")
    _linked_gpkg(tmp_path / "link_B.gpkg", layer="1d_xs_link", file_name="B.csv")
    for name in ("A.csv", "B.csv"):
        (tmp_path / name).write_text("X,Z\n0,1\n", encoding="utf-8")
    (tmp_path / "model.tcf").write_text(
        "Read GIS Code == link_*.gpkg >> 1d_xs_link\n",
        encoding="utf-8",
    )
    result = validate_batch(tmp_path / "model.tcf", ["-s1 EXG"])
    assert result.passed, result.issues
    assert result.gis_files_scanned == 2
    assert result.gis_sources_added == 2
    assert result.validation.files_examined == 4


def test_missing_root_control_file_cannot_pass_empty_inventory(tmp_path: Path) -> None:
    missing = tmp_path / "absent.tcf"
    with pytest.raises(FileNotFoundError, match="was not loaded"):
        validate_batch(missing, ["-s1 DEV"])
    model = TCF(missing)
    assert not model.loaded
    with pytest.raises(FileNotFoundError, match="was not loaded"):
        validate_batch(model, ["-s1 DEV"])
    with pytest.raises(ValueError, match="empty, unnamed"):
        validate_batch(TCF(), ["-s1 DEV"])
