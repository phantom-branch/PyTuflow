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
