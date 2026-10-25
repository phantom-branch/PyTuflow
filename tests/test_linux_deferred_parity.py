"""Native Linux path alias regressions for deferred TUFLOW input discovery."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

from pytuflow import TCF
from pytuflow._tmf import TuflowPath

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
