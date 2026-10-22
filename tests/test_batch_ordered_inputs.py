"""Contract tests for complete, ordered batch input ownership.

The regular FileReference projection excludes non-file commands. A consumer
must still be able to reconstruct command ordering and database activations.
"""

from pathlib import Path

from pytuflow import TCF


def test_batch_exposes_non_file_commands_and_original_ordinals(tmp_path: Path) -> None:
    source = tmp_path / "ensemble.tcf"
    source.write_text(
        "Set Variable ROOT == gis\n"
        "Read GIS Code == <<ROOT>>/2d_code_R.shp\n"
        "Read GRID Zpts == grids/dem.tif\n",
        encoding="utf-8",
    )
    model = TCF(source)
    flags = ("-s1 EXG -e1 01.0p", "-s1 EXG -e1 02.0p", "-s1 EXG -e1 01.0p")
    batch = model.collect_batch_dependencies(flags)

    assert batch.passed
    assert len(batch.runs) == len(flags)
    assert batch.contexts_reused == 1
    for case, flag in zip(batch.runs, flags, strict=True):
        expected = tuple(model.context(flag, file_resolution="deferred").find_input())
        commands = case.ordered_inputs
        assert len(commands) == len(expected)
        assert tuple(command.command_index for command in commands) == tuple(range(len(expected)))
        assert tuple(command.input_uuid for command in commands) == tuple(str(inp.uuid) for inp in expected)
        assert tuple(command.command_name for command in commands) == tuple(str(inp.lhs) for inp in expected)

        file_owners = {(record.command_index, record.input_uuid) for record in case.input_references}
        assert all((record.command_index, record.input_uuid) in {
            (command.command_index, command.input_uuid) for command in commands
        } for record in case.input_references)
        assert any(
            (command.command_index, command.input_uuid) not in file_owners
            for command in commands
        )


def test_batch_reused_flags_keep_distinct_run_indexes_with_same_order(tmp_path: Path) -> None:
    source = tmp_path / "shared.tcf"
    source.write_text("Read GIS Code == gis/2d_code_R.shp\n", encoding="utf-8")
    batch = TCF(source).collect_batch_dependencies(("-s1 EXG", "-s1 EXG"))
    assert batch.passed
    assert [case.index for case in batch.runs] == [0, 1]
    assert batch.runs[0].ordered_inputs == batch.runs[1].ordered_inputs
    assert batch.runs[0].input_references == batch.runs[1].input_references
