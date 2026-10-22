"""P4 compatibility gates for the stacked P1/P2/P3 implementation.

These are tiny synthetic correctness fixtures, never throughput benchmarks.
The public tutorial benchmark is a separate, verified-data acceptance gate.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow._tmf.tfpathlib import TuflowPath


def _projection(batch):
    return tuple(
        (
            item.flags,
            item.error,
            item.ordered_inputs,
            item.input_references,
            item.file_references,
            item.database_activations,
            item.database_sources,
        )
        for item in batch.runs
    )


def _bc(path: Path, name: str) -> None:
    path.write_text(
        "Name,Source,Column 1,Column 2\n"
        f"FC01,{name}.csv,Time,Flow\n",
        encoding="utf-8",
    )


def test_nested_declarations_match_graph_off_and_uncached(tmp_path: Path) -> None:
    """All ordered fields, owners and database Source rows must match."""
    geom = tmp_path / "model.tgc"
    geom.write_text(
        "Read GIS Code == gis/code.shp\n"
        "Read Grid Zpts == grids/terrain.tif\n",
        encoding="utf-8",
    )
    bc = tmp_path / "model.tbc"
    bc.write_text(
        "BC Database == nested.csv\n"
        "Read GIS BC == gis/2d_bc_nested.shp\n",
        encoding="utf-8",
    )
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "Set Variable ROOT == gis\n"
        "BC Database == initial.csv\n"
        "Read GIS BC == <<ROOT>>/2d_bc_initial.shp\n"
        "Geometry Control File == model.tgc\n"
        "BC Control File == model.tbc\n"
        "If Scenario == DEV\n"
        "    BC Database == developed.csv\n"
        "Else\n"
        "    BC Database == existing.csv\n"
        "End If\n"
        "Read GIS BC == gis/2d_bc_final.shp\n",
        encoding="utf-8",
    )
    for name in ("initial", "nested", "developed", "existing"):
        _bc(tmp_path / f"{name}.csv", name)
    model = TCF(tcf)
    flags = (
        "-s1 EXG -e1 TP01",
        "-s1 DEV -e1 TP02",
        "-s1 EXG -e1 TP01",
        "-s1 DEV -e1 TP03",
    )
    with (
        patch.object(Path, "open", side_effect=AssertionError("open after parse")),
        patch.object(Path, "stat", side_effect=AssertionError("stat after parse")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob after parse")),
        patch("sqlite3.connect", side_effect=AssertionError("SQLite after parse")),
    ):
        graph = model.collect_batch_dependencies(flags)
        previous_cached = model.collect_batch_dependencies(flags, compile_tree=False)
        uncached = model.collect_batch_dependencies(flags, cache_scopes=False)

    assert graph.passed and previous_cached.passed and uncached.passed
    assert _projection(graph) == _projection(previous_cached) == _projection(uncached)
    assert graph.compiled_graph_nodes > 0
    assert previous_cached.compiled_graph_nodes == 0
    assert graph.compiled_graph_bypassed_reads >= 0
    for run in graph.runs:
        names = [a.database_path.name for a in run.database_activations]
        assert names == [
            "initial.csv", "nested.csv",
            "developed.csv" if "DEV" in run.flags else "existing.csv",
        ]
        assert run.database_activations[1].owner_control_file == bc
        assert run.ordered_inputs[0].command_name.casefold().startswith("set variable")
        assert run.ordered_inputs[0].command_index == 0
        assert len(run.database_sources) == 3


def test_invariant_literal_runs_can_elide_only_safe_run_states(tmp_path: Path) -> None:
    source = tmp_path / "invariant.tcf"
    source.write_text(
        "Read GIS Code == gis/static_code.shp\n"
        "Read Grid Zpts == grid/terrain.tif\n",
        encoding="utf-8",
    )
    model = TCF(source)
    flags = tuple(f"-s1 SCENARIO{i:03d} -e1 TP{i:03d}" for i in range(36))
    graph = model.collect_batch_dependencies(flags)
    no_graph = model.collect_batch_dependencies(flags, compile_tree=False)
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
    assert graph.passed and no_graph.passed and uncached.passed
    assert _projection(graph) == _projection(no_graph) == _projection(uncached)
    assert graph.contexts_reused == 0
    assert graph.invariant_projection_reuses > 0
    assert graph.input_runstates_elided > 0
    assert graph.input_runstates_constructed < no_graph.input_runstates_constructed
    assert no_graph.input_runstates_elided == 0
    assert graph.compiled_graph_nodes == 2
    # Each new invocation independently constructs its own immutable output
    # snapshot. A second call cannot reuse mutable run state from the first.
    second = model.collect_batch_dependencies(("-s1 EXTRA -e1 TP_EXTRA",))
    assert second.passed
    assert second.invariant_projection_reuses == 0


def test_malformed_flags_cannot_reuse_an_invariant_success(tmp_path: Path) -> None:
    source = tmp_path / "invalid.tcf"
    source.write_text("Read GIS Code == gis/static_code.shp\n", encoding="utf-8")
    model = TCF(source)
    flags = ("-s1 EXG", "-s1 DEV", "-s1 EXG -s1 DEV")
    graph = model.collect_batch_dependencies(flags)
    old = model.collect_batch_dependencies(flags, compile_tree=False)
    assert _projection(graph) == _projection(old)
    assert not graph.passed
    invalid = graph.runs[2]
    assert invalid.error
    assert invalid.file_references == ()
    assert invalid.input_references == ()
    assert invalid.ordered_inputs == ()
    assert invalid.database_sources == ()
    assert invalid.database_activations == ()


@pytest.mark.parametrize("source_line", [
    "Read GIS Code == gis/<<E1>>/2d_code.shp\n",
    "Read GIS Code == gis/2d_code_*.shp\n",
])
def test_dynamic_sources_use_original_resolution(tmp_path: Path, source_line: str) -> None:
    tcf = tmp_path / "dynamic.tcf"
    tcf.write_text(source_line, encoding="utf-8")
    model = TCF(tcf)
    flags = ("-e1 TP01", "-e1 TP02", "-e1 TP03")
    with (
        patch.object(Path, "open", side_effect=AssertionError("open after parse")),
        patch.object(Path, "stat", side_effect=AssertionError("stat after parse")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob after parse")),
    ):
        graph = model.collect_batch_dependencies(flags)
        baseline = model.collect_batch_dependencies(flags, compile_tree=False)
    assert graph.passed and baseline.passed
    assert _projection(graph) == _projection(baseline)
    assert graph.invariant_projection_reuses == 0
    assert graph.input_runstates_elided == 0
