"""Private per-filename hit/time attribution without altering public parsing."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pytuflow import TCF
from pytuflow._tmf import fragment_dependencies as fragments

from .fragment_evaluation_probe import FragmentEvaluationProbe
from .fragment_filename_attribution import PrivateFragmentAttribution
from .test_fragment_dependencies import model_files


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_complete_private_lookup_trace_links_commands_and_file_patterns(tmp_path: Path) -> None:
    model = model_files(tmp_path)
    flags = [
        "-s1 DEV -e1 Q10",
        "-s1 DEV -e1 Q100",
        "-s1 DEV -e1 Q10",
        "-s1 EXG -e1 Q100",
    ]
    expected = model.collect_batch_dependencies(flags)
    original_evaluate = fragments._Plan.evaluate
    original_key = fragments._Plan._key
    original_init = fragments._FragmentContext.__init__

    anonymous = FragmentEvaluationProbe()
    private = PrivateFragmentAttribution()
    with anonymous.observe(), private.observe():
        actual = model.collect_file_dependencies(flags)

    assert actual.passed and actual.fallback_runs == 0
    assert actual.runs == expected.runs
    stats = private.summary(actual)
    public = anonymous.snapshot(actual)
    assert stats["lookup_trace_rows"] == public["lookups"]
    assert stats["cache_hits"] == actual.fragment_reuses
    assert stats["cache_misses"] == actual.fragment_evaluations
    assert stats["distinct_resolved_patterns_in_fragment_links"] >= 4
    assert stats["failed_evaluate_calls"] == 0
    assert fragments._Plan.evaluate is original_evaluate
    assert fragments._Plan._key is original_key
    assert fragments._FragmentContext.__init__ is original_init

    destination = tmp_path / "private_output"
    destination.mkdir()
    private.write_private(destination, actual)
    lookups = _csv(destination / "private_lookup_trace.csv")
    sources = _csv(destination / "private_input_totals.csv")
    files = _csv(destination / "private_file_totals.csv")
    links = _csv(destination / "private_fragment_files.csv")

    assert len(lookups) == stats["lookup_trace_rows"]
    assert len({int(row["context_ordinal"]) for row in lookups}) == len(flags)
    assert sum(row["cache_result"] == "hit" for row in lookups) == actual.fragment_reuses
    assert sum(row["cache_result"] == "miss" for row in lookups) == actual.fragment_evaluations
    assert len(sources) == stats["source_input_slots"]
    assert all(float(row["key_inclusive_ms"]) >= 0 for row in sources)
    assert all(float(row["p95_hit_exclusive_ms"]) >= 0 for row in sources)
    assert {row["fragment_id"] for row in lookups} == {row["fragment_id"] for row in links} | {
        row["fragment_id"] for row in lookups if row["fragment_id"] not in {
            link["fragment_id"] for link in links
        }
    }
    assert any(row["owner_control_file"].endswith("boundary.tbc") for row in sources)
    assert any(row["resolved_file_pattern"].endswith("terrain.tif") for row in links)
    assert any(row["resolved_file_pattern"].endswith("inflow_ten.csv") for row in files)
    assert any(row["resolved_file_pattern"].endswith("inflow_hundred.csv") for row in files)
    assert any(int(row["fragment_hit_associations"]) > 0 for row in files)
    assert any(int(row["logical_run_references"]) > 0 for row in files)
    assert all(float(row["associated_key_ms"]) >= 0 for row in files)

    # The ordinary/public report is intentionally redacted. The private data
    # contains paths and control-file names only because it was opted into.
    assert "geometry.tgc" in (destination / "private_input_totals.csv").read_text(encoding="utf-8-sig")
    for sensitive in ("geometry.tgc", "boundary.tbc", "terrain.tif", "inflow_ten.csv"):
        assert sensitive not in json.dumps(stats)
        assert sensitive not in json.dumps(public)


def test_probe_works_when_no_fragment_plan_is_available(tmp_path: Path) -> None:
    model_file = tmp_path / "example.tcf"
    model_file.write_text("Read Grid Zpts == source.tif\n", encoding="utf-8")
    model = TCF(model_file)
    original = model.inputs[0].context

    def custom(*args: object, **kwargs: object) -> object:
        return original(*args, **kwargs)

    model.inputs[0].context = custom
    anonymous = FragmentEvaluationProbe()
    private = PrivateFragmentAttribution()
    with anonymous.observe(), private.observe():
        actual = model.collect_file_dependencies(["-e1 A", "-e1 B"])
    assert actual.passed
    assert actual.fallback_runs == 2
    summary = private.summary(actual)
    assert summary["lookup_trace_rows"] == 0
    target = tmp_path / "fallback-private"
    target.mkdir()
    private.write_private(target, actual)
    assert not _csv(target / "private_lookup_trace.csv")


def test_exception_restores_original_evaluator(tmp_path: Path) -> None:
    original_eval = fragments._Plan.evaluate
    original_key = fragments._Plan._key
    original_init = fragments._FragmentContext.__init__
    attribution = PrivateFragmentAttribution()
    with pytest.raises(RuntimeError, match="test exception"):
        with attribution.observe():
            raise RuntimeError("test exception")
    assert fragments._Plan.evaluate is original_eval
    assert fragments._Plan._key is original_key
    assert fragments._FragmentContext.__init__ is original_init
    with pytest.raises(RuntimeError, match="new private fragment attribution probe"):
        with attribution.observe():
            pass


def test_cli_writes_private_csvs_but_keeps_json_anonymous(tmp_path: Path) -> None:
    model_file = tmp_path / "private_model.tcf"
    model_file.write_text(
        "Read GIS Code == private_static.shp\n"
        "Read Grid Zpts == private_dynamic_<<E1>>.tif\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "private_flags.json"
    run_file.write_text(json.dumps(["-e1 Q10", "-e1 Q100", "-e1 Q10"]), encoding="utf-8")
    output = tmp_path / "private_results"
    root = Path(__file__).absolute().parents[1]
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.profile_fragment_evaluations",
            "--tcf",
            str(model_file),
            "--runs-json",
            str(run_file),
            "--output",
            str(output),
            "--private-file-attribution",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads((output / "fragment_diagnostic.json").read_text(encoding="utf-8"))
    assert report["ordinary_full_run_parity"]
    assert report["private_file_attribution"]["lookup_trace_rows"] == report["lookups"]
    assert "private_static.shp" not in json.dumps(report)
    assert "private_dynamic_Q100.tif" not in json.dumps(report)
    assert "private_model.tcf" not in json.dumps(report)
    patterns = {row["resolved_file_pattern"] for row in _csv(output / "private_file_totals.csv")}
    assert any(pattern.endswith("private_static.shp") for pattern in patterns)
    assert any(pattern.endswith("private_dynamic_Q100.tif") for pattern in patterns)
    assert (output / "private_fragment_files.csv").exists()
    assert (output / "private_input_totals.csv").exists()
    assert (output / "private_lookup_trace.csv").exists()
