"""Opt-in fragment-cache probe must preserve exact public parser semantics."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from pytuflow import TCF
from pytuflow._tmf import fragment_dependencies as fragment

from .fragment_evaluation_probe import FragmentEvaluationProbe
from .profile_fragment_evaluations import load_run_flags


def test_fragment_probe_counts_match_parser_without_changing_runs(tmp_path: Path) -> None:
    model_path = tmp_path / "model.tcf"
    model_path.write_text(
        "Read GIS Code == static.shp\n"
        "Read Grid Zpts == dynamic_<<E1>>.tif\n",
        encoding="utf-8",
    )
    model = TCF(model_path)
    flags = ["-e1 A", "-e1 B", "-e1 A", "-e1 B"]
    ordinary = model.collect_batch_dependencies(flags)
    original_key = fragment._Plan._key
    original_join = fragment._join
    original_init = fragment._FragmentContext.__init__

    probe = FragmentEvaluationProbe()
    with probe.observe():
        result = model.collect_file_dependencies(flags)
    report = probe.snapshot(result)

    assert result.passed and ordinary.passed
    assert result.runs == ordinary.runs
    assert report["run_count"] == report["contexts_constructed"] == len(flags)
    assert report["misses"] == result.fragment_evaluations
    assert report["hits"] == result.fragment_reuses
    assert report["lookups"] == result.fragment_evaluations + result.fragment_reuses
    assert report["hit_rate_percent"] > 0
    assert report["joins"]["calls"] >= len(flags)
    assert report["joins"]["commands_rebased"] >= len(flags)
    assert report["top_anonymous_input_slots"]
    assert report["by_input_type"]
    assert fragment._Plan._key is original_key
    assert fragment._join is original_join
    assert fragment._FragmentContext.__init__ is original_init
    for forbidden in ("model.tcf", "static.shp", "dynamic_A.tif", "dynamic_B.tif", "-e1 A"):
        assert forbidden not in json.dumps(report)
    with pytest.raises(RuntimeError, match="fresh fragment probe"):
        with probe.observe():
            pass


def test_probe_handles_complete_fallback_without_leaking_source(tmp_path: Path) -> None:
    path = tmp_path / "model.tcf"
    path.write_text("Read Grid Zpts == source.tif\n", encoding="utf-8")
    model = TCF(path)
    source = model.inputs[0]
    original = source.context

    def custom(*args, **kwargs):
        return original(*args, **kwargs)

    source.context = custom
    probe = FragmentEvaluationProbe()
    with probe.observe():
        result = model.collect_file_dependencies(["-e1 A", "-e1 B"])
    assert result.passed and result.fallback_runs == 2
    assert probe.snapshot(result)["lookups"] == 0


@pytest.mark.parametrize(
    "value",
    [[], [""], [{}], [{"e1": 5}], [{"e1": ""}], [None], [5], ["-e1 A"] * 2001, {"e1": "A"}],
)
def test_invalid_diagnostic_flags_are_rejected(tmp_path: Path, value) -> None:
    path = tmp_path / "private_flags.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        load_run_flags(path)


def test_diagnostic_flag_loader_preserves_run_order_and_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "private_flags.json"
    flags = ["-e1 A", {"s1": "DEV", "e1": "B"}, "-e1 A"]
    path.write_text(json.dumps(flags), encoding="utf-8")
    assert load_run_flags(path) == flags


def test_help_does_not_load_gis_or_model(tmp_path: Path) -> None:
    root = Path(__file__).absolute().parents[1]
    process = subprocess.run(
        [sys.executable, "-m", "tests.profile_fragment_evaluations", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert "--runs-json" in process.stdout
    assert "--cprofile" in process.stdout
