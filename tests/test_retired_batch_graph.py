"""Contracts for retiring obsolete compiled batch graphs safely.

Only the *general* CompiledControlTree/mutable group-prototype implementation
is removed. The independent graph-free deferred batch collector remains
available for differential parity against immutable fast fragments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pytuflow import TCF


def test_obsolete_compiled_graph_modules_are_absent() -> None:
    assert importlib.util.find_spec("pytuflow._tmf.compiled_control_tree") is None
    assert importlib.util.find_spec("pytuflow._tmf.group_input_reuse") is None

    # The high-throughput path must not pull the old graph back into imports.
    from pytuflow._tmf.fragment_dependencies import collect_file_dependencies

    assert callable(collect_file_dependencies)


def test_legacy_graph_free_and_immutable_fragment_results_are_identical(
    tmp_path: Path,
) -> None:
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "Set Variable BASE == terrain\n"
        "If Scenario == DEV\n"
        "Read GIS Code == gis/dev.shp\n"
        "Else\n"
        "Read GIS Code == gis/exg.shp\n"
        "End If\n"
        "Read Grid Zpts == grids/<<BASE>>_~e1~.tif\n",
        encoding="utf-8",
    )
    model = TCF(tcf)
    flags = (
        "-s1 DEV -e1 A", "-s1 EXG -e1 B", "-s1 DEV -e1 B",
        "-s1 DEV -e1 A",
    )
    legacy = model.collect_batch_dependencies(flags)
    explicitly_disabled = model.collect_batch_dependencies(flags, compile_tree=False)
    plain = model.collect_batch_dependencies(flags, cache_scopes=False)
    fragments = model.collect_file_dependencies(flags)

    assert legacy.passed and explicitly_disabled.passed and plain.passed
    assert fragments.passed
    assert legacy.runs == explicitly_disabled.runs == plain.runs == fragments.runs
    assert legacy.compiled_graph_nodes == 0
    assert legacy.input_group_state_reuses == 0
    assert legacy.reusable_input_groups == 0
    assert legacy.invariant_projection_reuses == 0


def test_legacy_batch_callback_does_not_consume_future_run_flags(
    tmp_path: Path,
) -> None:
    source = tmp_path / "model.tcf"
    source.write_text("Read Grid Zpts == terrain.tif\n", encoding="utf-8")
    model = TCF(source)
    delivered: list[int] = []

    def flags():
        yield "-s1 DEV"
        assert delivered == [0]
        yield "-s1 EXG"
        assert delivered == [0, 1]

    runs = model.collect_batch_dependencies(
        flags(), on_run=lambda run: delivered.append(run.index)
    )
    assert runs.passed
    assert delivered == [0, 1]
    assert len(runs.runs) == 2


def test_deferred_errors_do_not_yield_partial_graph_free_records(tmp_path: Path) -> None:
    source = tmp_path / "model.tcf"
    source.write_text(
        "Read Grid Zpts == terrain.tif\n"
        "If Scenario == BAD\nPAUSE == stop\nEnd If\n",
        encoding="utf-8",
    )
    model = TCF(source)
    result = model.collect_batch_dependencies(["-s1 BAD", "-s1 GOOD"])
    assert not result.passed
    assert result.runs[0].error is not None
    assert result.runs[0].file_references == ()
    assert result.runs[0].ordered_inputs == ()
    assert result.runs[1].error is None
