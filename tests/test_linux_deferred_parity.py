"""Native Linux path alias regressions for deferred TUFLOW input discovery."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

from pytuflow import TCF
from pytuflow._tmf import TuflowPath
from pytuflow._tmf.settings import TCFConfig

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux filesystem semantics")


def test_exact_filename_preferred_with_case_only_siblings(tmp_path: Path) -> None:
    """A valid exact spelling must not raise an ambiguous-case error."""
    upper = tmp_path / "Materials.csv"
    lower = tmp_path / "materials.csv"
    upper.write_text("1,0.03\n", encoding="utf-8")
    lower.write_text("2,0.04\n", encoding="utf-8")

    assert TuflowPath.init_case_insensitive_path("Materials.csv", tmp_path).dbpath == Path("Materials.csv")
    assert TuflowPath.init_case_insensitive_path("materials.csv", tmp_path).dbpath == Path("materials.csv")


def test_nonexact_ambiguous_filename_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "Materials.csv").touch()
    (tmp_path / "materials.csv").touch()

    with pytest.raises(RuntimeError, match="Ambiguous case-insensitive match"):
        TuflowPath.init_case_insensitive_path("MATERIALS.csv", tmp_path)


def test_unique_nonexact_filename_preserves_found_spelling(tmp_path: Path) -> None:
    actual = tmp_path / "Materials.csv"
    actual.touch()
    assert TuflowPath.init_case_insensitive_path("materials.csv", tmp_path).dbpath == Path("Materials.csv")


def test_symlink_alias_keeps_original_spelling(tmp_path: Path) -> None:
    target = tmp_path / "Materials.csv"
    target.touch()
    alias = tmp_path / "linked.csv"
    try:
        alias.symlink_to(target)
    except OSError:
        pytest.skip("No symlink support")
    assert TuflowPath.init_case_insensitive_path("linked.csv", tmp_path).dbpath == Path("linked.csv")


def test_deferred_and_eager_nested_reference_agree(tmp_path: Path) -> None:
    """No control-file rescan may substitute an unrelated case-only sibling."""
    selected = tmp_path / "Geometry.TGC"
    selected.write_text("Read GIS Code == gis/selected.shp\n", encoding="utf-8")
    other = tmp_path / "geometry.tgc"
    other.write_text("Read GIS Code == gis/other.shp\n", encoding="utf-8")
    tcf = tmp_path / "model.tcf"
    tcf.write_text("Geometry Control File == Geometry.TGC\n", encoding="utf-8")

    model = TCF(tcf)
    inventories: list[set[str]] = []
    for mode in ("eager", "deferred"):
        run = model.context(file_resolution=mode)
        inventories.append(
            {
                reference.path_pattern.name
                for item in run.find_input(recursive=True)
                for reference in item.file_references
            }
        )
    assert inventories[0] == inventories[1]
    assert "selected.shp" in inventories[1]
    assert "other.shp" not in inventories[1]


def test_gpkg_case_only_siblings_select_exact_database_and_layer(tmp_path: Path) -> None:
    """A layer check must not silently read an unrelated differently cased GPKG."""
    for filename, layer in (
        ("Boundary.gpkg", "2d_bc_upper"),
        ("boundary.gpkg", "2d_bc_lower"),
    ):
        with closing(sqlite3.connect(tmp_path / filename)) as connection:
            connection.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
            connection.execute("INSERT INTO gpkg_contents VALUES (?)", (layer,))
            connection.commit()

    for filename, layer, wrong_layer in (
        ("Boundary.gpkg", "2d_bc_upper", "2d_bc_lower"),
        ("boundary.gpkg", "2d_bc_lower", "2d_bc_upper"),
    ):
        chosen = TuflowPath.init_case_insensitive_path(filename, tmp_path)
        assert chosen.dbpath == Path(filename)
        full_path = tmp_path / chosen.dbpath
        assert TuflowPath(f"{full_path} >> {layer}").exists()
        assert not TuflowPath(f"{full_path} >> {wrong_layer}").exists()


@pytest.mark.parametrize(
    ("case_sensitivity", "requested", "expected_file"),
    [
        (0, "materials.csv", "materials.csv"),
        (1, "materials.csv", "materials.csv"),
        (2, "materials.csv", "Materials.csv"),
        (0, "Materials.CSV", "Materials.CSV"),
        (1, "Materials.CSV", "Materials.csv"),
        (2, "MATERIALS.CSV", "Materials.csv"),
    ],
)
def test_linux_literal_case_modes(case_sensitivity: int, requested: str, expected_file: str, tmp_path: Path) -> None:
    """Default -cs0 must retain incorrect filenames; -cs1/-cs2 match TUFLOW."""
    (tmp_path / "Materials.csv").write_text("Material, Manning\n1,0.04\n", encoding="utf-8")
    selected = TuflowPath.init_case_policy_path(requested, tmp_path, case_sensitivity)
    assert selected.dbpath == Path(expected_file)
    assert (tmp_path / selected.dbpath).is_file() == (expected_file == "Materials.csv")


def test_linux_strict_default_and_database_input_status(tmp_path: Path) -> None:
    """PyTUFLOW eager and explicit deferred materialisation must flag bad casing."""
    actual = tmp_path / "Materials.csv"
    actual.write_text("Material, Manning\n1,0.04\n", encoding="utf-8")
    tcf = tmp_path / "case_policy.tcf"
    tcf.write_text("Read Materials File == Materials.csv\n", encoding="utf-8")

    assert TCFConfig().case_sensitivity == 0
    assert TCF(tcf).config.case_sensitivity == 0

    tcf.write_text("Read Materials File == materials.csv\n", encoding="utf-8")
    strict = TCF(tcf)
    assert strict.config.case_sensitivity == 0
    strict_input = strict.find_input(lhs="Read Materials File")[0]
    assert strict_input.has_missing_files
    strict_deferred = strict.context(file_resolution="deferred").find_input(lhs="Read Materials File")[0]
    assert strict_deferred.file_references[0].path_pattern.name == "materials.csv"

    tolerant = TCF(tcf, config=TCFConfig(case_sensitivity=2))
    tolerant_input = tolerant.find_input(lhs="Read Materials File")[0]
    assert not tolerant_input.has_missing_files
    assert tolerant_input.files[0].name == "Materials.csv"


@pytest.mark.parametrize(
    ("level", "expected"),
    [(0, "Materials.CSV"), (1, "Materials.csv"), (2, "Materials.csv")],
)
def test_linux_extension_only_policy(level: int, expected: str, tmp_path: Path) -> None:
    (tmp_path / "Materials.csv").touch()
    selected = TuflowPath.init_case_policy_path("Materials.CSV", tmp_path, level)
    assert selected.dbpath.name == expected


def test_linux_directories_remain_case_sensitive_under_cs2(tmp_path: Path) -> None:
    (tmp_path / "Model").mkdir()
    (tmp_path / "Model" / "Materials.csv").touch()
    actual = TuflowPath.init_case_policy_path("model/materials.csv", tmp_path, 2)
    assert actual.dbpath == Path("model/materials.csv")
    assert not (tmp_path / actual.dbpath).exists()
    correct_directory = TuflowPath.init_case_policy_path("Model/materials.csv", tmp_path, 2)
    assert correct_directory.dbpath == Path("Model/Materials.csv")


def test_linux_case_policy_with_distinct_filename_siblings(tmp_path: Path) -> None:
    (tmp_path / "Materials.csv").touch()
    (tmp_path / "materials.csv").touch()
    assert TuflowPath.init_case_policy_path("materials.csv", tmp_path, 2).dbpath == Path("materials.csv")
    with pytest.raises(ValueError, match="Ambiguous"):
        TuflowPath.init_case_policy_path("MATERIALS.csv", tmp_path, 2)


@pytest.mark.parametrize("case_sensitivity", [-1, 3, True, "2", None])
def test_invalid_tuflow_case_sensitivity_rejected(case_sensitivity: object) -> None:
    with pytest.raises(ValueError, match="case_sensitivity"):
        TCFConfig(case_sensitivity=case_sensitivity)


def test_linux_wildcard_filename_mode_not_directory_mode(tmp_path: Path) -> None:
    (tmp_path / "Model").mkdir()
    source = tmp_path / "Model" / "Grid_01.TIF"
    source.touch()
    assert list(TuflowPath(tmp_path / "Model").glob("grid_*.tif", case_sensitivity=0)) == []
    assert list(TuflowPath(tmp_path / "Model").glob("grid_*.tif", case_sensitivity=1)) == []
    assert list(TuflowPath(tmp_path / "Model").glob("grid_*.tif", case_sensitivity=2)) == [source]
    assert list(TuflowPath(tmp_path).glob("model/grid_*.tif", case_sensitivity=2)) == []
