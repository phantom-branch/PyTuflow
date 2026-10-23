"""Regression tests for invocation-local ordered run input and activation lookup."""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import BatchContext
from pytuflow._tmf.cf.tcf_run_state import TCFRunState
from pytuflow._tmf.tfpathlib import TuflowPath


def _bc_csv(path: Path, source: str) -> None:
    path.write_text(
        "Name,Source,Column 1,Column 2\n"
        f"FC01,{source},Time,Flow\n",
        encoding="utf-8",
    )


def _nested_model(tmp_path: Path) -> TCF:
    (tmp_path / "geometry.tgc").write_text(
        "Read Grid Zpts == grids/dem.tif\n", encoding="utf-8",
    )
    (tmp_path / "boundaries.tbc").write_text(
        "BC Database == nested.csv\n"
        "Read GIS BC == gis/2d_bc_nested.shp\n", encoding="utf-8",
    )
    (tmp_path / "model.ecf").write_text(
        "Read GIS Network == gis/1d_nwk_model.shp\n", encoding="utf-8",
    )
    (tmp_path / "model.tcf").write_text(
        "Set Variable FLAG == 1\n"  # zero file references, but occupies ordinal 0
        "BC Database == first.csv\n"
        "Read GIS BC == gis/2d_bc_first.shp\n"
        "Geometry Control File == geometry.tgc\n"
        "BC Control File == boundaries.tbc\n"
        "ESTRY Control File == model.ecf\n"
        "If Scenario == DEV\n"
        "    BC Database == developed.csv\n"
        "Else\n"
        "    BC Database == existing.csv\n"
        "End If\n"
        "Read GIS BC == gis/2d_bc_final.shp\n",
        encoding="utf-8",
    )
    for name in ("first", "nested", "developed", "existing"):
        _bc_csv(tmp_path / f"{name}.csv", f"{name}_hydrograph.csv")
    return TCF(tmp_path / "model.tcf")


def _single_projection(model: TCF, flags: str):
    run = model.context(flags, file_resolution="deferred")
    inputs = tuple(run.find_input())
    activations = run.deferred_database_activations()
    sources = tuple(
        src
        for activation in activations
        for src in run.deferred_database_sources_for_activation(activation.input_uuid)
    )
    return inputs, activations, sources


@pytest.mark.parametrize("cache_scopes", [True, False])
def test_nested_order_uuid_and_full_batch_deferred_parity(tmp_path: Path, cache_scopes: bool):
    model = _nested_model(tmp_path)
    flags = ("-s1 EXG -e1 TP01", "-s1 DEV -e1 TP02", "-s1 EXG -e1 TP01")
    expected = [_single_projection(model, flag) for flag in flags]

    # The parser is allowed initial I/O; projecting contexts and cached
    # database entries must not subsequently probe storage or GIS.
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
        patch("sqlite3.connect", side_effect=AssertionError("sqlite")),
    ):
        batch = model.collect_batch_dependencies(flags, cache_scopes=cache_scopes)

    assert batch.passed
    for case, (inputs, activations, sources) in zip(batch.runs, expected, strict=True):
        assert case.error is None
        assert case.database_activations == activations  # exact frozen records
        assert case.database_sources == sources  # exact entry/owner/source records
        assert case.file_references == tuple(
            ref for inp in inputs for ref in inp.file_references
        )
        assert case.ordered_inputs == tuple(
            type(item)(
                input_uuid=str(inp.uuid),
                command_index=sequence,
                owner_control_file=inp._command.parent,
                line_number=inp.line_number,
                command_name=str(inp.lhs),
                command_text=str(inp._command.original_text),
                reference_count=len(inp.file_references),
            )
            for sequence, (item, inp) in enumerate(zip(case.ordered_inputs, inputs, strict=True))
        )
        assert tuple(item.input_uuid for item in case.ordered_inputs) == tuple(
            str(inp.uuid) for inp in inputs
        )
        assert [act.database_path.name for act in activations] == [
            "first.csv", "nested.csv",
            "developed.csv" if "DEV" in case.flags else "existing.csv",
        ]
        assert [act.sequence for act in activations] == sorted(act.sequence for act in activations)
        assert next(act for act in activations if act.database_path.name == "nested.csv").owner_control_file == (
            tmp_path / "boundaries.tbc"
        )
        assert len({act.input_uuid for act in activations}) == 3
        assert case.ordered_inputs[0].command_name.casefold().startswith("set variable")
        assert case.ordered_inputs[0].command_index == 0
        assert all(act.sequence > 0 for act in activations)
    assert batch.runs[0].database_activations == batch.runs[2].database_activations


def test_many_activations_use_only_one_index_traversal_in_batch(tmp_path: Path):
    tcf = tmp_path / "many.tcf"
    tcf.write_text(
        "Set Variable CONTROL == 1\n"
        + "".join(f"BC Database == bc_{i}.csv\n" for i in range(16)),
        encoding="utf-8",
    )
    for i in range(16):
        _bc_csv(tmp_path / f"bc_{i}.csv", f"flow_{i}.csv")
    model = TCF(tcf)
    context = BatchContext("-s1 EXG", config=model.config)
    context._batch_run_index = 0
    run = model.context(context=context, file_resolution="deferred")

    find_input = TCFRunState.find_input
    traversals = []

    def tracked(self, *args, **kwargs):
        traversals.append((args, kwargs))
        return find_input(self, *args, **kwargs)

    with patch.object(TCFRunState, "find_input", tracked):
        activations = run.deferred_database_activations()
        sources = tuple(
            source
            for activation in activations
            for source in run.deferred_database_sources_for_activation(activation.input_uuid)
        )
        assert run.deferred_database_activations() == activations

    assert len(activations) == 16
    assert len(sources) == 16
    assert len(traversals) == 1
    assert all(source.input_uuid == activation.input_uuid for source, activation in zip(
        sources, activations, strict=True,
    ))
    # Identity index is read-only, with no run-state object or result shared
    # with another context or invocation.
    index = run._deferred_run_input_index()
    with pytest.raises(TypeError):
        index.by_uuid["nonexistent"] = ()


def test_public_mutable_run_state_refreshes_input_uuid_index(tmp_path: Path):
    tcf = tmp_path / "mutable.tcf"
    tcf.write_text("BC Database == one.csv\n", encoding="utf-8")
    _bc_csv(tmp_path / "one.csv", "one_source.csv")
    model = TCF(tcf)
    run = model.context(file_resolution="deferred")
    old = run.deferred_database_activations()[0]
    original = run.find_input(lhs="BC Database")[0]
    original.uuid = uuid4()
    new = run.deferred_database_activations()[0]
    assert old.input_uuid != new.input_uuid
    with pytest.raises(ValueError, match="found 0"):
        run.deferred_database_sources_for_activation(old.input_uuid)
    assert run.deferred_database_sources_for_activation(new.input_uuid)[0].input_uuid == (
        new.input_uuid
    )


def test_duplicate_and_missing_uuids_fail_closed(tmp_path: Path):
    tcf = tmp_path / "duplicate.tcf"
    tcf.write_text(
        "BC Database == first.csv\nBC Database == second.csv\n",
        encoding="utf-8",
    )
    _bc_csv(tmp_path / "first.csv", "one.csv")
    _bc_csv(tmp_path / "second.csv", "two.csv")
    model = TCF(tcf)
    run = model.context(file_resolution="deferred")
    inputs = run.find_input(lhs="BC Database")
    inputs[1].uuid = inputs[0].uuid
    activations = run.deferred_database_activations()
    assert len(activations) == 2
    assert [act.sequence for act in activations] == [0, 1]
    assert activations[0].input_uuid == activations[1].input_uuid
    with pytest.raises(ValueError, match="found 2"):
        run.deferred_database_sources_for_activation(activations[0].input_uuid)
    with pytest.raises(ValueError, match="found 0"):
        run.deferred_database_sources_for_activation("missing-uuid")


def test_invalid_secondary_database_batch_error_projection_is_exact(tmp_path: Path):
    tcf = tmp_path / "invalid.tcf"
    tcf.write_text(
        "BC Database == bad.csv\nRead GIS BC == gis/2d_bc.shp\n",
        encoding="utf-8",
    )
    # A cached primary is valid, but absent Source column must be rejected.
    (tmp_path / "bad.csv").write_text(
        "Name,NotSource\nFC01,flow.csv\n", encoding="utf-8",
    )
    model = TCF(tcf)
    run = model.context(file_resolution="deferred")
    activations = run.deferred_database_activations()
    assert len(activations) == 1
    with pytest.raises(ValueError) as error:
        run.deferred_database_sources_for_activation(activations[0].input_uuid)
    result = model.collect_batch_dependencies(("-s1 EXG",))
    assert not result.passed
    case = result.runs[0]
    assert case.error == f"{type(error.value).__name__}: {error.value}"
    assert case.database_sources == ()
    assert case.database_activations == ()
    assert case.file_references == ()
    assert case.input_references == ()
    assert case.ordered_inputs == ()


def test_ad_and_hydraulic_activations_keep_distinct_kinds(tmp_path: Path):
    tcf = tmp_path / "ad.tcf"
    tcf.write_text(
        "BC Database == hydraulic.csv\n"
        "AD Global Database == global.csv\n"
        "AD BC Database == ad.csv\n",
        encoding="utf-8",
    )
    _bc_csv(tmp_path / "hydraulic.csv", "hydro.csv")
    _bc_csv(tmp_path / "ad.csv", "concentration.csv")
    (tmp_path / "global.csv").write_text(
        "Name,Initial Condition,Minimum Dispersion\nTracer,0,0\n",
        encoding="utf-8",
    )
    model = TCF(tcf)
    run = model.context(file_resolution="deferred")
    activations = run.deferred_database_activations()
    expected = tuple(
        source
        for activation in activations
        for source in run.deferred_database_sources_for_activation(activation.input_uuid)
    )
    batch = model.collect_batch_dependencies(("-s1 EXG",))
    assert batch.passed
    assert batch.runs[0].database_activations == activations
    assert batch.runs[0].database_sources == expected
    assert {x.database_kind for x in activations} == {"bc", "ad_bc", "ad_global"}
    assert {s.database_kind for s in expected} == {"bc", "ad_bc"}
