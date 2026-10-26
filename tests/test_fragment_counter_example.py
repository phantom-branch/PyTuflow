"""Public, synthetic proof that fragment-cache lookups are not file access.

A single TCF describes 20 nonexistent GIS paths and 120 ordinary non-file
settings. All 456 run flags are distinct, but the parsed commands are static.
After the TCF is parsed, no source file access is permitted during projection.
The test prints aggregate counts but never reveals private user workloads.
"""

from pathlib import Path
from unittest.mock import patch

from pytuflow import TCF


def test_456_contexts_20_files_many_fragments_are_not_file_reads(tmp_path: Path) -> None:
    """Cache hit counts follow input commands, not physical path read counts."""
    runs = 456
    gis_commands = 20
    setting_commands = 120

    # Every path is deliberately absent. No source SHP is necessary because
    # fragment mode constructs syntactic FileReference records only.
    gis_lines = [f"Read GIS Code == synthetic_{i:02d}.shp" for i in range(gis_commands)]
    settings = [f"Set Code == {i + 1}" for i in range(setting_commands)]
    tcf_path = tmp_path / "synthetic.tcf"
    tcf_path.write_text("\n".join((*gis_lines, *settings, "")), encoding="utf-8")
    model = TCF(tcf_path)
    flags = [f"-e1 E{i:03d}" for i in range(runs)]

    with (
        patch.object(Path, "open", side_effect=AssertionError("Unexpected physical file open")),
        patch.object(Path, "stat", side_effect=AssertionError("Unexpected physical stat")),
    ):
        result = model.collect_file_dependencies(flags)

    assert result.passed
    assert result.fallback_runs == 0
    assert len(result.runs) == runs
    assert all(len(run.file_references) == gis_commands for run in result.runs)
    unique_paths = {str(ref.path_pattern) for run in result.runs for ref in run.file_references}
    assert len(unique_paths) == gis_commands

    references = sum(len(run.file_references) for run in result.runs)
    lookups = result.fragment_evaluations + result.fragment_reuses
    assert lookups >= runs * (gis_commands + setting_commands)
    assert result.fragment_reuses > references
    assert result.fragment_evaluations < lookups
    print(
        "PUBLIC SYNTHETIC EXAMPLE: "
        f"runs={runs}, unique_paths={len(unique_paths)}, "
        f"logical_file_references={references}, fragment_lookups={lookups}, "
        f"fragment_evaluations={result.fragment_evaluations}, "
        f"fragment_reuses={result.fragment_reuses}, "
        "post_parse_file_opens=0, post_parse_file_stats=0"
    )
