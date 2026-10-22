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


def test_batch_ordered_inputs_match_individual_runs_across_scenario_branches(
    tmp_path: Path,
) -> None:
    source = tmp_path / "branching.tcf"
    source.write_text(
        "Set Variable ROOT == gis\n"
        "If Scenario == DEV\n"
        "    Read GIS Code == <<ROOT>>/dev.shp\n"
        "Else\n"
        "    Read GIS Code == <<ROOT>>/exg.shp\n"
        "End If\n"
        "Read GRID Zpts == grids/dem.tif\n",
        encoding="utf-8",
    )
    model = TCF(source)
    flags = ("-s1 EXG -e1 Q010", "-s1 DEV -e1 Q010", "-s1 EXG -e1 Q100")
    cached = model.collect_batch_dependencies(flags)
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)

    assert cached.passed and uncached.passed
    for flag, projected, baseline in zip(flags, cached.runs, uncached.runs, strict=True):
        assert projected.ordered_inputs == baseline.ordered_inputs
        assert projected.input_references == baseline.input_references
        assert projected.file_references == baseline.file_references
        active = tuple(model.context(flag, file_resolution="deferred").find_input())
        assert [
            (item.command_index, item.input_uuid, item.owner_control_file,
             item.line_number, item.command_name, item.command_text)
            for item in projected.ordered_inputs
        ] == [
            (index, str(inp.uuid), inp._command.parent, inp.line_number,
             str(inp.lhs), str(inp._command.original_text))
            for index, inp in enumerate(active)
        ]
        assert [
            (item.command_index, item.input_uuid, item.reference)
            for item in projected.input_references
        ] == [
            (index, str(inp.uuid), ref)
            for index, inp in enumerate(active)
            for ref in inp.file_references
        ]

    # Branch membership changes the active command stream; an unrelated
    # event flag must not accidentally reuse a different scenario's inputs.
    assert cached.runs[0].ordered_inputs == cached.runs[2].ordered_inputs
    assert cached.runs[0].ordered_inputs != cached.runs[1].ordered_inputs


def test_batch_activation_sequence_joins_full_command_order(tmp_path: Path) -> None:
    def write_bc_database(path: Path, source: str) -> None:
        path.write_text(
            "Name,Source,Column 1,Column 2,Add Col 1,Mult Col 2,Add Col 2,"
            "Column 3,Column 4\n"
            f"FC01,{source},time,flow,,,,,\n",
            encoding="utf-8",
        )

    source = tmp_path / "reassigned.tcf"
    source.write_text(
        "BC Database == before.csv\n"
        "Read GIS BC == gis/2d_bc_before.shp\n"
        "Set Variable UNUSED == no_file\n"
        "BC Database == after.csv\n"
        "Read GIS BC == gis/2d_bc_after.shp\n",
        encoding="utf-8",
    )
    write_bc_database(tmp_path / "before.csv", "before_source.csv")
    write_bc_database(tmp_path / "after.csv", "after_source.csv")
    batch = TCF(source).collect_batch_dependencies(("-s1 EXG", "-s1 EXG -e1 Q100"))
    assert batch.passed

    for run in batch.runs:
        activations = [a for a in run.database_activations if a.database_kind == "bc"]
        assert [a.database_path.name for a in activations] == ["before.csv", "after.csv"]
        assert len({a.input_uuid for a in activations}) == 2
        assert all(
            run.ordered_inputs[a.sequence].input_uuid == a.input_uuid
            and run.ordered_inputs[a.sequence].owner_control_file == a.owner_control_file
            and run.ordered_inputs[a.sequence].line_number == a.line_number
            for a in activations
        )
        assert [s.path_pattern.name for s in run.database_sources] == [
            "before_source.csv", "after_source.csv",
        ]
        assert [s.input_uuid for s in run.database_sources] == [
            activation.input_uuid for activation in activations
        ]
        assert any(
            cmd.command_name.casefold().startswith("set variable")
            and cmd.command_index not in {ref.command_index for ref in run.input_references}
            for cmd in run.ordered_inputs
        )


def test_batch_failed_and_repeated_runs_never_expose_partial_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "conditional_database.tcf"
    source.write_text("BC Database == bc_<<~s1~>>.csv\n", encoding="utf-8")
    (tmp_path / "bc_A.csv").write_text(
        "Name,Source,Column 1,Column 2,Add Col 1,Mult Col 2,Add Col 2,"
        "Column 3,Column 4\n"
        "FC01,source.csv,time,flow,,,,,\n",
        encoding="utf-8",
    )
    flags = ("-s1 A", "-s1 MISSING", "-s1 A", "-s1 MISSING")
    batch = TCF(source).collect_batch_dependencies(flags)
    assert not batch.passed
    assert batch.contexts_constructed == 2
    assert batch.contexts_reused == 2
    assert batch.runs[0].error is None
    assert batch.runs[0].ordered_inputs
    assert batch.runs[0].input_references
    assert batch.runs[2].ordered_inputs == batch.runs[0].ordered_inputs
    assert batch.runs[2].input_references == batch.runs[0].input_references
    for index in (1, 3):
        run = batch.runs[index]
        assert run.error
        assert run.file_references == ()
        assert run.database_sources == ()
        assert run.database_activations == ()
        assert run.input_references == ()
        assert run.ordered_inputs == ()
    assert batch.runs[1].error == batch.runs[3].error


def test_batch_nested_owner_descriptors_are_immutable(tmp_path: Path) -> None:
    from dataclasses import FrozenInstanceError

    import pytest

    geom = tmp_path / "nested.tgc"
    geom.write_text("Read GIS Z Shape == gis/2d_zsh.shp\n", encoding="utf-8")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == nested.tgc\n", encoding="utf-8")

    batch = TCF(top).collect_batch_dependencies(("-s1 EXG",))
    assert batch.passed
    commands = batch.runs[0].ordered_inputs
    nested = [item for item in commands if item.owner_control_file == geom]
    assert len(nested) == 1
    assert nested[0].line_number == 1
    assert nested[0].command_name.casefold() == "read gis z shape"
    assert any(item.owner_control_file == top for item in commands)
    assert any(
        reference.input_uuid == nested[0].input_uuid
        and reference.command_index == nested[0].command_index
        and reference.owner_control_file == geom
        for reference in batch.runs[0].input_references
    )
    with pytest.raises(FrozenInstanceError):
        nested[0].command_index = -1
