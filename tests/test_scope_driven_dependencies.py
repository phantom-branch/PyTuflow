"""Graph-free versus optimised dependency collection: behavioural contracts.

Synthetic inputs establish correctness, not performance. Native SSD/SMB timing
belongs to the separate read-only local-agent benchmark protocol.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow._tmf.scope_driven_dependencies import collect_scope_dependencies


def make_model(root: Path) -> TCF:
    (root / "events.tef").write_text(
        "Define Event == E1\n"
        " BC Event Source == _flow_ | alpha\n"
        "End Define\n"
        "Define Event == E2\n"
        " BC Event Source == _flow_ | beta\n"
        "End Define\n",
        encoding="utf-8",
    )
    (root / "geometry.tgc").write_text(
        "Read Grid Zpts == <<FOLDER>>_<<EVENT>>.tif\n"
        "If Event == E2\n"
        " Read GIS Code == second_event.shp\n"
        "End If\n",
        encoding="utf-8",
    )
    (root / "bc.csv").write_text(
        "Name,Source,Column 1,Column 2\n"
        "flow,flow__flow_.csv,Time,Flow\n",
        encoding="utf-8",
    )
    (root / "model.tcf").write_text(
        "Event File == events.tef\n"
        "If Scenario == DEV\n"
        " Set Variable FOLDER == dev\n"
        "Else\n"
        " Set Variable FOLDER == exg\n"
        "End If\n"
        "Set Variable EVENT == _flow_\n"
        "Geometry Control File == geometry.tgc\n"
        "BC Database == bc.csv\n"
        "Read GIS BC == boundary.shp\n",
        encoding="utf-8",
    )
    return TCF(root / "model.tcf")


def assert_parity(model: TCF, flags: list[str | dict[str, str]]) -> None:
    expected = model.collect_file_dependencies(flags)
    actual = collect_scope_dependencies(model, flags)
    assert actual.runs == expected.runs
    assert actual.passed == expected.passed


def test_conditional_variables_tef_substitutions_and_nested_includes(tmp_path: Path) -> None:
    model = make_model(tmp_path)
    flags = [
        "-s1 DEV -e1 E1",
        "-s1 EXG -e1 E1",
        "-s1 DEV -e1 E2",
        "-s1 EXG -e1 E2",
        {"s1": "DEV", "e1": "E1"},
    ]
    assert_parity(model, flags)
    run = collect_scope_dependencies(model, flags)
    assert run.contexts_constructed == 4
    assert run.contexts_reused == 1
    names = [
        {str(ref.path_pattern.name) for ref in item.file_references}
        for item in run.runs
    ]
    assert "dev_alpha.tif" in names[0]
    assert "exg_alpha.tif" in names[1]
    assert "dev_beta.tif" in names[2]
    assert "exg_beta.tif" in names[3]
    assert "second_event.shp" not in names[0]
    assert "second_event.shp" in names[2]
    assert names[0] == names[4]
    assert {
        source.path_pattern.name
        for item in run.runs
        for source in item.database_sources
    } == {"flow_alpha.csv", "flow_beta.csv"}


def test_ordered_database_reassignment_and_activation_provenance(tmp_path: Path) -> None:
    for name in ("first", "second"):
        (tmp_path / f"{name}.csv").write_text(
            "Name,Source,Column 1,Column 2\n"
            f"flow,{name}_flow.csv,Time,Flow\n",
            encoding="utf-8",
        )
    (tmp_path / "model.tcf").write_text(
        "BC Database == first.csv\n"
        "Read GIS BC == one.shp\n"
        "If Scenario == DEV\n"
        " BC Database == second.csv\n"
        "End If\n"
        "Read GIS BC == two.shp\n",
        encoding="utf-8",
    )
    model = TCF(tmp_path / "model.tcf")
    flags = ["-s1 EXG -e1 Q1", "-s1 DEV -e1 Q1"]
    assert_parity(model, flags)
    runs = collect_scope_dependencies(model, flags).runs
    assert len(runs[0].database_activations) == 1
    assert len(runs[1].database_activations) == 2
    assert len(runs[1].ordered_inputs) > len(runs[0].ordered_inputs)
    assert len({x.input_uuid for x in runs[1].database_activations}) == 2


def test_invalid_run_fails_closed_and_later_run_is_independent(tmp_path: Path) -> None:
    (tmp_path / "bad.csv").write_text(
        "Name,Source,Column 1,Column 2\n"
        "flow,<<UNKNOWN>>.csv,Time,Flow\n",
        encoding="utf-8",
    )
    (tmp_path / "model.tcf").write_text(
        "Read Grid Zpts == always.tif\n"
        "If Scenario == BAD\n"
        " BC Database == bad.csv\n"
        "End If\n",
        encoding="utf-8",
    )
    model = TCF(tmp_path / "model.tcf")
    flags = ["-s1 BAD", "-s1 GOOD", "-s1 BAD"]
    assert_parity(model, flags)
    collected = collect_scope_dependencies(model, flags)
    assert not collected.passed
    assert collected.contexts_constructed == 2
    assert collected.contexts_reused == 1
    bad, good, bad_again = collected.runs
    assert bad.error
    assert bad.file_references == bad.input_references == bad.ordered_inputs == ()
    assert bad.database_sources == bad.database_activations == ()
    assert good.error is None
    assert {x.path_pattern.name for x in good.file_references} == {"always.tif"}
    assert bad.error == bad_again.error


def test_postparse_collection_avoids_file_and_directory_probes(tmp_path: Path) -> None:
    model = make_model(tmp_path)
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
    ):
        collected = collect_scope_dependencies(
            model, ["-s1 DEV -e1 E1", "-s1 EXG -e1 E2"]
        )
    assert collected.passed


def test_callback_receives_complete_streamed_run_not_parser_errors(tmp_path: Path) -> None:
    model = make_model(tmp_path)
    observed: list[tuple[int, int]] = []

    def flags():
        yield "-s1 DEV -e1 E1"
        assert observed == [(0, 1)]
        yield "-s1 EXG -e1 E2"

    def on_run(run):
        observed.append((run.index, len(run.database_activations)))

    result = collect_scope_dependencies(model, flags(), on_run=on_run)
    assert result.passed
    assert observed == [(0, 1), (1, 1)]


def test_callback_errors_propagate(tmp_path: Path) -> None:
    model = make_model(tmp_path)

    def raise_error(_run):
        raise RuntimeError("consumer failure")

    with pytest.raises(RuntimeError, match="consumer failure"):
        collect_scope_dependencies(model, ["-s1 DEV -e1 E1"], on_run=raise_error)


def test_new_invocation_uses_new_parsed_source_snapshot(tmp_path: Path) -> None:
    top = tmp_path / "model.tcf"
    top.write_text("Read Grid Zpts == first.tif\n", encoding="utf-8")
    initial = collect_scope_dependencies(TCF(top), ["-e1 E1"])
    top.write_text("Read Grid Zpts == second.tif\n", encoding="utf-8")
    later = collect_scope_dependencies(TCF(top), ["-e1 E1"])
    assert initial.runs[0].file_references[0].path_pattern.name == "first.tif"
    assert later.runs[0].file_references[0].path_pattern.name == "second.tif"


def test_empty_batch_and_single_pass_flag_iterator(tmp_path: Path) -> None:
    model = make_model(tmp_path)
    with pytest.raises(ValueError, match="At least one"):
        collect_scope_dependencies(model, iter(()))
    flags = (f"-s1 DEV -e1 E{n}" for n in (1, 2))
    assert collect_scope_dependencies(model, flags).passed
