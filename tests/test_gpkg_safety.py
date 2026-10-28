"""Core PyTUFLOW GeoPackage safety independent of the batch validator."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pytuflow._tmf.gpkg_safety import (
    GeoPackageSafetyError,
    check_gpkg_safety,
    read_gpkg_layer_names,
    readonly_gpkg,
)


def test_readonly_core_gpkg_reader_no_auxiliary_files(tmp_path: Path) -> None:
    path = tmp_path / "readable.gpkg"
    with sqlite3.connect(path) as writer:
        writer.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
        writer.execute("INSERT INTO gpkg_contents VALUES ('grid')")
    before = path.read_bytes()

    check_gpkg_safety(path)
    with readonly_gpkg(path) as source:
        assert source.execute(
            "SELECT table_name FROM gpkg_contents"
        ).fetchone() == ("grid",)
    assert read_gpkg_layer_names(path) == (("grid",), "")

    assert path.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {"readable.gpkg"}


def test_core_reader_rejects_active_rollback_journal(tmp_path: Path) -> None:
    path = tmp_path / "busy.gpkg"
    with sqlite3.connect(path) as writer:
        writer.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
    editor = sqlite3.connect(path)
    try:
        editor.execute("PRAGMA journal_mode=DELETE")
        editor.execute("BEGIN IMMEDIATE")
        editor.execute("INSERT INTO gpkg_contents VALUES ('uncommitted')")
        assert path.with_name(path.name + "-journal").stat().st_size > 0
        before = path.read_bytes()
        journal = path.with_name(path.name + "-journal").read_bytes()
        with (
            pytest.raises(GeoPackageSafetyError, match="journal"),
            readonly_gpkg(path) as source,
        ):
            source.execute("SELECT table_name FROM gpkg_contents")
        assert path.read_bytes() == before
        assert path.with_name(path.name + "-journal").read_bytes() == journal
    finally:
        editor.rollback()
        editor.close()
