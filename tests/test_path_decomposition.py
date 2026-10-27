"""Path syntax, live rendering, extension hooks and diagnostics must stay consistent."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from pytuflow._tmf.tfpathlib import file as paths


@dataclass
class LiteralPath:
    text: str

    def __str__(self) -> str:
        return self.text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("file.tgc", ("file.tgc", None)),
        ("", ("", None)),
        (r"..\model\file.tbc", (r"..\model\file.tbc", None)),
        ("../model/file.tbc", ("../model/file.tbc", None)),
        (r"\\server\share\FILE.gpkg", (r"\\server\share\FILE.gpkg", None)),
        ("FILE.gpkg >> Layer", ("FILE.gpkg", "Layer")),
        ("FILE.gpkg >> Layer >> Tail", ("FILE.gpkg >> Layer", "Tail")),
        ("FILE.gpkg|layername=Layer|subset=x", ("FILE.gpkg", "Layer")),
        ("FILE.gpkg|layername=", ("FILE.gpkg", "")),
        ("FILE.gpkg|subset=x", ("FILE.gpkg", None)),
        ('NETCDF:"file.nc":water', ("file.nc", "water")),
        ('netCDF:"C:\\data\\file.nc":"Water"', (r"C:\data\file.nc", "Water")),
        ('NETCDF:"/data/file.nc":water', ("/data/file.nc", "water")),
        ("design_<<~s1~>>_03.tgc", ("design_<<~s1~>>_03.tgc", None)),
        (
            "db_<<Alias>>.gpkg >> layer_<<~e1~>>",
            ("db_<<Alias>>.gpkg", "layer_<<~e1~>>"),
        ),
        ("files_*.trd", ("files_*.trd", None)),
        ("literal<<<A>>>", ("literal<<<A>>>", None)),
        ("layerless", ("layerless", None)),
        ("Case.gpkg >> Σ", ("Case.gpkg", "Σ")),
    ],
)
def test_lexical_forms(text: str, expected: tuple[str, str | None]):
    assert (
        paths.TuflowPath._split_db_and_lyr(cast(paths.TuflowPath, LiteralPath(text)))
        == expected
    )
    assert (
        paths.TuflowPath._split_db_and_lyr(cast(paths.TuflowPath, LiteralPath(text)))
        == expected
    )


def test_every_request_renders_current_path_before_reuse(
    monkeypatch: pytest.MonkeyPatch,
):
    path = paths.TuflowPath("initial.tgc")
    current = ["design_EXG_03.tgc"]
    rendered = []

    def render(self) -> str:
        rendered.append(current[0])
        return current[0]

    monkeypatch.setattr(type(path), "__str__", render)
    assert path._split_db_and_lyr() == ("design_EXG_03.tgc", None)
    current[0] = "design_DEV_03.tgc"
    assert path._split_db_and_lyr() == ("design_DEV_03.tgc", None)
    assert path._split_db_and_lyr() == ("design_DEV_03.tgc", None)
    assert len(rendered) == 3


def test_spelling_and_trailing_separator_changes_remain_visible(
    monkeypatch: pytest.MonkeyPatch,
):
    first = paths.TuflowPath("Design_EXG_03.TGC")
    second = paths.TuflowPath("design_exg_03.tgc")
    assert first._split_db_and_lyr()[0] == "Design_EXG_03.TGC"
    assert second._split_db_and_lyr()[0] == "design_exg_03.tgc"
    path = paths.TuflowPath("folder")
    before = path._split_db_and_lyr()
    monkeypatch.setattr(path, "_end_slash", True)
    after = path._split_db_and_lyr()
    assert before != after
    assert after == (str(path), None)


def test_changed_regex_policy_cannot_reuse_default_result(
    monkeypatch: pytest.MonkeyPatch,
):
    path = paths.TuflowPath("db.gpkg >> layer >> tail")
    assert path._split_db_and_lyr() == ("db.gpkg >> layer", "tail")
    with monkeypatch.context() as patch:
        patch.setattr(paths, "SPLIT_DATABASE_REGEX", re.compile(r">>"))
        assert path._split_db_and_lyr() == ("db.gpkg", "layer >> tail")
    assert path._split_db_and_lyr() == ("db.gpkg >> layer", "tail")


def test_stateful_unhashable_split_hook_remains_uncached(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    @dataclass
    class Splitter:
        def split(self, string: str, maxsplit: int) -> list[str]:
            calls.append((string, maxsplit))
            return [f"source{len(calls)}.gpkg", "layer"]

    monkeypatch.setattr(paths, "SPLIT_DATABASE_REGEX", Splitter())
    path = paths.TuflowPath("db.gpkg >> layer")
    assert path._split_db_and_lyr() == ("source1.gpkg", "layer")
    assert path._split_db_and_lyr() == ("source2.gpkg", "layer")
    assert len(calls) == 2


@pytest.mark.filterwarnings("ignore:__str__ returned non-str:DeprecationWarning")
def test_string_subclass_callbacks_are_not_cached(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class Text(str):
        def count(self, *args, **kwargs):
            calls.append(args[0])
            return super().count(*args, **kwargs)

    def render(self) -> str:
        return Text("db.gpkg >> cells")

    path = paths.TuflowPath("initial.gpkg")
    monkeypatch.setattr(type(path), "__str__", render)
    assert path._split_db_and_lyr() == ("db.gpkg", "cells")
    assert path._split_db_and_lyr() == ("db.gpkg", "cells")
    assert calls == [">>", "<<", ">>", "<<"]


def test_custom_split_shape_keeps_original_unpacking_error(
    monkeypatch: pytest.MonkeyPatch,
):
    class Splitter:
        def split(self, string: str, maxsplit: int) -> list[str]:
            return ["single"]

    monkeypatch.setattr(paths, "SPLIT_DATABASE_REGEX", Splitter())
    path = paths.TuflowPath("db.gpkg >> layer")
    assert path._split_db_and_lyr() == ("single",)
    with pytest.raises(ValueError, match="not enough values to unpack"):
        _ = path.dbpath


def test_malformed_netcdf_errors_are_not_cached():
    path = paths.TuflowPath("NETCDF:invalid")
    for _ in range(2):
        with pytest.raises(ValueError, match="not enough values to unpack"):
            path._split_db_and_lyr()


def test_property_decomposition_performs_no_filesystem_access(
    monkeypatch: pytest.MonkeyPatch,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("lexical decomposition performed filesystem I/O")

    path = paths.TuflowPath("../model/geometry.gpkg >> cells")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "iterdir", forbidden)
        assert path.lyrname == "cells"
        assert path.dbpath.name == "geometry.gpkg"
        assert path.lyrname == "cells"
