"""Read-only scenario/event flag discovery from existing PyTUFLOW build states."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow.flag_discovery import (
    EventDefinition,
    _read_slots,
    discover_model_flags,
)
from pytuflow._tmf.event import EventDatabase
from pytuflow._tmf.scope import Scope


def _fake_input(
    lhs: str, rhs: str = "", *,
    scope: tuple[Scope, ...] = (),
    children: tuple[object, ...] = (),
    path: str = "model.tcf",
    line: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        lhs=lhs, rhs=rhs, scope=scope, cf=children,
        line_number=line, _command=SimpleNamespace(parent=Path(path)),
    )


def _fake_model(
    inputs: tuple[object, ...], *,
    event_db: EventDatabase | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        fpath=Path("model_<<~s3~>>.tcf"),
        config=SimpleNamespace(event_db=event_db if event_db is not None else EventDatabase()),
        inputs=inputs,
    )


def test_normalise_tuflow_flag_slots_and_aliases() -> None:
    assert _read_slots("a_<<~S~>>_<<~s1~>>_<<~e9~>>_<<~E~>>_<<~s2~>>") == (
        ("scenario", "S1"), ("event", "E9"), ("event", "E1"),
        ("scenario", "S2"),
    )
    assert _read_slots("<<~s1~>><<~s1~>>") == (("scenario", "S1"),)
    assert _read_slots("<<CELL_SIZE>>_<<RANDOM>>") == ()


def test_discovery_separates_scopes_tef_definitions_slots_and_defaults() -> None:
    event_db = EventDatabase({
        "Q100": {"_ARI_": "100yr"},
        "PMF": {"_ARI_": "PMF"},
    })
    nested = SimpleNamespace(
        fpath=Path("geometry.tgc"),
        inputs=(
            _fake_input(
                "Read GIS Code", "z_<<~S2~>>.shp",
                scope=(Scope("SCENARIO", "!DEV"), Scope("EVENT", "Q100")),
                path="geometry.tgc", line=4,
            ),
        ),
    )
    model = _fake_model((
        _fake_input("Model Scenarios", "EXG | DEV", line=1),
        _fake_input("Geometry Control File", "geometry.tgc", children=(nested,), line=2),
        _fake_input(
            "Read GIS Code", "a_<<~E9~>>.gpkg",
            scope=(Scope("SCENARIO", "EXG | ALT"),), line=5,
        ),
        _fake_input("Read Grid Zpts", "grid_<<~s~>>.tif", line=6),
    ), event_db=event_db)
    result = discover_model_flags(model)  # type: ignore[arg-type]

    assert result.scenario_names == ("EXG", "DEV", "ALT")
    assert result.default_scenarios == ("EXG", "DEV")
    assert result.event_names == ("Q100", "PMF")
    assert result.scenario_slots == ("S1", "S2", "S3")
    assert result.event_slots == ("E9",)
    assert result.event_definitions == (
        EventDefinition("Q100", ("_ARI_",)),
        EventDefinition("PMF", ("_ARI_",)),
    )
    nested_evidence = [
        entry for entry in result.evidence
        if entry.owner_control_file == Path("geometry.tgc")
    ]
    assert any(x.value == "DEV" and x.negated for x in nested_evidence)
    assert any(x.value == "Q100" and x.kind == "event" for x in nested_evidence)
    assert any(x.slot == "S2" for x in nested_evidence)
    assert not any(x.slot == "S2" and x.value == "DEV" for x in nested_evidence)


def test_dynamic_includes_and_unresolved_scope_are_reported_not_guessed() -> None:
    model = _fake_model((
        _fake_input(
            "Read GIS Code",
            "z_<<~s1~>>.shp",
            scope=(Scope("SCENARIO", "<<~s2~>>"),),
        ),
        _fake_input("Geometry Control File", "geometry_<<~s1~>>.tgc"),
    ))
    result = discover_model_flags(model)  # type: ignore[arg-type]
    assert result.scenario_slots == ("S1", "S2", "S3")
    assert result.scenario_names == ()
    assert len(result.limitations) == 2
    assert any("unresolved variables" in warning for warning in result.limitations)
    assert any("Dynamic included" in warning for warning in result.limitations)


def test_case_insensitive_event_names_are_deduplicated_but_provenance_preserved() -> None:
    db = EventDatabase({"Q100": {"_ARI_": "100yr"}})
    model = _fake_model((
        _fake_input(
            "Read GIS Code", "input.shp",
            scope=(Scope("EVENT", "q100 | QPMF"),),
        ),
    ), event_db=db)
    result = discover_model_flags(model)  # type: ignore[arg-type]
    assert result.event_names == ("Q100", "QPMF")
    assert len([x for x in result.evidence if x.value and x.value.casefold() == "q100"]) == 2


def test_parse_real_tcf_and_discover_scenarios_from_conditional_blocks(
    tmp_path: Path,
) -> None:
    top = tmp_path / "example.tcf"
    top.write_text(
        "If Scenario == EXG | DEV\n"
        " Read GIS Code == site_<<~s2~>>.shp\n"
        "Else If Scenario == ALT\n"
        " Read GIS Code == alt.shp\n"
        "End If\n"
        "Read Grid Zpts == terrain_<<~e1~>>.tif\n",
        encoding="utf-8",
    )
    model = TCF(top)
    discovered = model.discover_flags()
    assert {"EXG", "DEV", "ALT"} <= set(discovered.scenario_names)
    assert "S2" in discovered.scenario_slots
    assert "E1" in discovered.event_slots
    assert not discovered.event_definitions
    assert discovered == discover_model_flags(model)
    assert not hasattr(discovered, "run_combinations")


def test_event_definitions_from_loaded_tef_are_read_only(tmp_path: Path) -> None:
    tef = tmp_path / "events.tef"
    tef.write_text(
        "Define Event == Q100\n"
        " BC Event Source == _ARI_ | 100yr\n"
        "End Define\n"
        "Define Event == PMF\n"
        " BC Event Source == _ARI_ | PMF\n"
        "End Define\n",
        encoding="utf-8",
    )
    top = tmp_path / "model.tcf"
    top.write_text("Event File == events.tef\n", encoding="utf-8")
    model = TCF(top)
    before = tuple((k, dict(v)) for k, v in model.config.event_db.items())
    result = model.discover_flags()
    assert {"Q100", "PMF"} <= set(result.event_names)
    assert {"Q100", "PMF"} <= {item.name for item in result.event_definitions}
    assert before == tuple((k, dict(v)) for k, v in model.config.event_db.items())


def test_discovery_does_not_stat_open_or_mutate_parsed_sources(
    tmp_path: Path,
) -> None:
    top = tmp_path / "model.tcf"
    top.write_text(
        "If Scenario == DEV\n"
        " Read GIS Code == nonexistent_<<~s1~>>.shp\n"
        "End If\n",
        encoding="utf-8",
    )
    model = TCF(top)
    first = model.discover_flags()

    with (
        patch.object(Path, "stat", side_effect=AssertionError("file stat")),
        patch.object(Path, "open", side_effect=AssertionError("file open")),
        patch("os.scandir", side_effect=AssertionError("directory scan")),
    ):
        second = model.discover_flags()
    assert first == second


@pytest.mark.parametrize("missing", ["scenario", "event"])
def test_empty_model_has_no_implied_run_combinations(
    tmp_path: Path, missing: str,
) -> None:
    top = tmp_path / "empty.tcf"
    top.write_text("Set Variable Model == BASE\n", encoding="utf-8")
    model = TCF(top)
    result = model.discover_flags()
    assert not getattr(result, missing + "_names")
    assert not result.event_definitions
    assert result.default_scenarios == ()
