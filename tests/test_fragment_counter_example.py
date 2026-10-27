"""Public, synthetic proof that fragment-cache lookups are not file access.

A single TCF describes 20 nonexistent GIS paths and 120 ordinary non-file
settings. All 456 run flags are distinct, but the parsed commands are static.
After the TCF is parsed, no source file access is permitted during projection.
The test prints aggregate counts but never reveals private user workloads.
"""

import csv
from pathlib import Path
from unittest.mock import patch

from pytuflow import TCF

from .fragment_filename_attribution import PrivateFragmentAttribution


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

    attribution = PrivateFragmentAttribution()
    with (
        patch.object(Path, "open", side_effect=AssertionError("Unexpected physical file open")),
        patch.object(Path, "stat", side_effect=AssertionError("Unexpected physical stat")),
        attribution.observe(),
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
    observed = attribution.summary(result)
    assert observed["lookup_trace_rows"] == lookups
    assert observed["cache_hits"] == result.fragment_reuses
    assert observed["source_input_slots"] == gis_commands + setting_commands
    assert observed["distinct_resolved_patterns_in_fragment_links"] == gis_commands

    private = tmp_path / "private_synthetic_report"
    private.mkdir()
    attribution.write_private(private, result)
    with (private / "private_file_totals.csv").open(newline="", encoding="utf-8-sig") as handle:
        filename_rows = list(csv.DictReader(handle))
    with (private / "private_lookup_trace.csv").open(newline="", encoding="utf-8-sig") as handle:
        lookup_rows = list(csv.DictReader(handle))
    assert len(filename_rows) == gis_commands
    assert len(lookup_rows) == lookups
    assert sum(int(row["logical_run_references"]) for row in filename_rows) == references
    assert sum(int(row["fragment_hit_associations"]) for row in filename_rows) == (
        result.fragment_reuses - setting_commands * (runs - 1)
    )
    print(
        "PUBLIC SYNTHETIC FILE ATTRIBUTION: "
        f"source_commands={observed['source_input_slots']}, "
        f"resolved_patterns={len(filename_rows)}, lookup_trace_rows={len(lookup_rows)}"
    )
    print(
        "PUBLIC SYNTHETIC EXAMPLE: "
        f"runs={runs}, unique_paths={len(unique_paths)}, "
        f"logical_file_references={references}, fragment_lookups={lookups}, "
        f"fragment_evaluations={result.fragment_evaluations}, "
        f"fragment_reuses={result.fragment_reuses}, "
        "post_parse_file_opens=0, post_parse_file_stats=0"
    )
