"""Empty/comment BC rows must not be validated as constant boundaries."""

from pathlib import Path
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow._tmf.deferred_database import DeferredDatabaseResolutionError
from pytuflow._tmf.tfpathlib import TuflowPath


@pytest.mark.parametrize("separator", [",! spreadsheet note,,,", ",,,", ",,,! note"])
def test_bc_empty_comment_and_separator_rows_are_not_boundaries(
    tmp_path: Path, separator: str
) -> None:
    from pytuflow._tmf.db.bc_dbase import BCDatabase

    path = tmp_path / "conditions.csv"
    path.write_text(
        "Name,Source,Column 1,Column 2\n"
        "Rain,rain.csv,Time,Rain\n" + separator + "\n"
        "Constant,,,2.75\n",
        encoding="utf-8",
    )
    database = BCDatabase(path)
    # Exercise the actual CSV-loader result, not a pre-cleaned test dataframe.
    assert len(database.df) == 3
    assert database.df.index.isna().sum() == 1
    source = tmp_path / "model.tcf"
    source.write_text("BC Database == conditions.csv\n", encoding="utf-8")
    model = TCF(source)
    flags = ["-s1 A", "-s1 B", "-s1 A"]
    states = [
        model.context("-s1 A", file_resolution=mode) for mode in ("eager", "deferred")
    ]
    with (
        patch.object(Path, "open", side_effect=AssertionError("source opened")),
        patch.object(Path, "stat", side_effect=AssertionError("source stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("source glob")),
    ):
        for state in states:
            refs = state.database_sources()
            assert len(refs) == 1
            assert refs[0].entry_name == "Rain"
            assert refs[0].path_pattern == tmp_path / "rain.csv"
        uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
        cached = model.collect_batch_dependencies(flags)
        fragments = model.collect_file_dependencies(flags)
    assert uncached.passed and cached.passed and fragments.passed
    assert uncached.runs == cached.runs == fragments.runs
    assert len(model.inputs[0].cf[0].df) == 3  # source snapshot is not mutated
    assert model.inputs[0].cf[0].df.index.isna().sum() == 1


@pytest.mark.parametrize("row", ["Boundary,,,", ",,,not-numeric"])
def test_bc_empty_row_filter_preserves_invalid_declarations(
    tmp_path: Path, row: str
) -> None:
    source = tmp_path / "model.tcf"
    source.write_text("BC Database == conditions.csv\n", encoding="utf-8")
    (tmp_path / "conditions.csv").write_text(
        "Name,Source,Column 1,Column 2\n" + row + "\n", encoding="utf-8"
    )
    model = TCF(source)
    with pytest.raises(DeferredDatabaseResolutionError, match="Column 2"):
        model.context(file_resolution="deferred").deferred_database_sources()
    result = model.collect_file_dependencies(["-s1 A"])
    assert not result.passed
    assert not result.fragments


def test_bc_unnamed_row_with_source_is_not_discarded(tmp_path: Path) -> None:
    source = tmp_path / "model.tcf"
    source.write_text("BC Database == conditions.csv\n", encoding="utf-8")
    (tmp_path / "conditions.csv").write_text(
        "Name,Source,Column 1,Column 2\n,retain.csv,Time,Value\n", encoding="utf-8"
    )
    refs = TCF(source).context(file_resolution="deferred").deferred_database_sources()
    assert len(refs) == 1
    assert refs[0].path_pattern == tmp_path / "retain.csv"
