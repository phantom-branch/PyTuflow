"""Complete-record selection contracts for variable-dependent includes."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytuflow import TCF


def assert_parity(model: TCF, flags: list[str]):
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
    cached = model.collect_batch_dependencies(flags)
    fragments = model.collect_file_dependencies(flags)
    assert uncached.runs == cached.runs == fragments.runs
    return fragments


@pytest.mark.parametrize(
    "command,suffix",
    [
        ("Geometry Control File", "tgc"),
        ("BC Control File", "tbc"),
        ("Geometry Control File", "trd"),
        ("Event File", "tef"),
        ("ESTRY Control File", "ecf"),
        ("Geometry Control File", "tscf"),
    ],
)
@pytest.mark.parametrize(
    "filename,assignments,slot",
    [
        ("<<~s1~>>", "", "s1"),
        ("<<~e1~>>", "", "e1"),
        (
            "<<Alias>>",
            "Set Variable Alias == <<Next>>\nSet Variable Next == <<~s1~>>\n",
            "s1",
        ),
    ],
)
def test_selected_source_identity(
    tmp_path: Path,
    command: str,
    suffix: str,
    filename: str,
    assignments: str,
    slot: str,
) -> None:
    for name in ("EXG", "DEV"):
        (tmp_path / f"design_{name}_03.{suffix}").write_text(
            f"Read GIS Code == {name}.shp\n"
        )
    top = tmp_path / "model.tcf"
    top.write_text(
        assignments
        + "Set Variable VarCellSize == 32\n"
        + f"{command} == design_{filename}_03.{suffix}\n"
    )
    model = TCF(top)
    result = assert_parity(
        model,
        [f"-{slot} EXG -e2 rain1", f"-{slot} DEV -e2 rain2", f"-{slot} EXG -e2 rain3"],
    )
    assert result.passed
    for run, name in zip(result.runs, ("EXG", "DEV", "EXG"), strict=True):
        names = [ref.path_pattern.name for ref in run.file_references]
        assert f"design_{name}_03.{suffix}" in names
        assert f"{name}.shp" in names
    assert result.fragment_reuses > 0


def test_nested_variable_selected_files(tmp_path: Path) -> None:
    for name in ("EXG", "DEV"):
        (tmp_path / f"nested_{name}.trd").write_text(f"Read GIS Code == {name}.shp\n")
    (tmp_path / "geometry.tgc").write_text(
        "Geometry Control File == nested_<<~s1~>>.trd\n"
    )
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == geometry.tgc\n")
    result = assert_parity(TCF(top), ["-s1 EXG", "-s1 DEV", "-s1 EXG"])
    assert result.passed
    assert [run.file_references[-1].path_pattern.name for run in result.runs] == [
        "EXG.shp",
        "DEV.shp",
        "EXG.shp",
    ]


def test_missing_selected_file_does_not_reuse_prior_result(tmp_path: Path) -> None:
    (tmp_path / "design_EXG.tgc").write_text("Read GIS Code == EXG.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == design_<<~s1~>>.tgc\n")
    model = TCF(top)
    result = assert_parity(model, ["-s1 EXG", "-s1 MISSING", "-s1 EXG"])
    assert result.runs[0].error is None
    assert result.runs[1].error
    assert result.runs[2].error is None
    assert not result.runs[1].ordered_inputs
