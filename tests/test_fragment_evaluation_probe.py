"""Opt-in fragment-cache probe must preserve exact public parser semantics."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from pytuflow import TCF
from pytuflow._tmf import fragment_dependencies as fragment

from .fragment_evaluation_probe import FragmentEvaluationProbe
from .profile_fragment_evaluations import focus_functions, load_run_flags


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
    assert (
        report["misses_with_new_local_signature"]
        + report["misses_with_reused_local_signature"]
        + report["misses_with_identical_uncached_key"]
        == report["misses"]
    )
    assert report["hits"] == result.fragment_reuses
    assert report["lookups"] == result.fragment_evaluations + result.fragment_reuses
    assert report["hit_rate_percent"] > 0
    assert len(report["run_progression"]) == len(flags)
    assert [row["context"] for row in report["run_progression"]] == [1, 2, 3, 4]
    assert sum(row["lookups"] for row in report["run_progression"]) == report["lookups"]
    assert sum(row["hits"] for row in report["run_progression"]) == report["hits"]
    assert sum(row["misses"] for row in report["run_progression"]) == report["misses"]
    assert report["lookups_per_context"]["average"] > 0
    assert report["misses_per_context"]["average"] > 0
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


def test_parent_misses_can_be_attributed_to_varying_children(tmp_path: Path) -> None:
    """An unchanged control-file reference can have a dynamic child subtree."""
    child = tmp_path / "geometry.tgc"
    child.write_text("Read Grid Zpts == dynamic_<<E1>>.tif\n", encoding="utf-8")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == geometry.tgc\n", encoding="utf-8")
    model = TCF(top)
    flags = ["-e1 A", "-e1 B", "-e1 A"]
    expected = model.collect_batch_dependencies(flags)

    probe = FragmentEvaluationProbe()
    with probe.observe():
        actual = model.collect_file_dependencies(flags)
    report = probe.snapshot(actual)

    assert actual.runs == expected.runs
    assert actual.passed
    assert report["misses_with_reused_local_signature"] >= 1
    parent = report["by_input_type"]["ControlFileInput"]
    assert parent["repeated_local_signature_misses"] >= 1
    child = report["by_input_type"]["GridInput"]
    assert child["new_local_signature_misses"] >= 2


def test_full_cache_or_failed_seeding_does_not_mimic_descendant_change(tmp_path: Path) -> None:
    """The same complete key can miss repeatedly when caching is disabled."""
    from unittest.mock import patch

    top = tmp_path / "model.tcf"
    top.write_text("Read Grid Zpts == static.tif\n", encoding="utf-8")
    model = TCF(top)
    flags = ["-e1 A", "-e1 A", "-e1 A", "-e1 A"]
    observer = FragmentEvaluationProbe()
    with patch.object(fragment, "_LIMIT", 0), observer.observe():
        result = model.collect_file_dependencies(flags)

    report = observer.snapshot(result)
    assert result.passed and result.fallback_runs == 0
    assert report["misses"] == 4
    assert report["hits"] == 0
    assert report["misses_with_new_local_signature"] == 1
    assert report["misses_with_reused_local_signature"] == 0
    assert report["misses_with_identical_uncached_key"] == 3


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


def test_profile_focus_functions_include_join_key_and_dataclass_replace() -> None:
    import cProfile
    from dataclasses import dataclass, replace

    from pytuflow._tmf.fragment_dependencies import DependencyFragment, _join

    @dataclass(frozen=True)
    class Record:
        value: int

    profile = cProfile.Profile()
    profile.enable()
    _join((DependencyFragment(), DependencyFragment()))
    replace(Record(1), value=2)
    profile.disable()

    records = focus_functions(profile)
    observed = {(row["module"], row["function"]) for row in records}
    assert ("fragment_dependencies.py", "_join") in observed
    assert ("dataclasses.py", "replace") in observed
