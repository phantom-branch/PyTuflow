"""Private phase breakdown preserves ordinary-vs-fragment equivalence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pytuflow import TCF
from pytuflow._tmf import fragment_dependencies as fragment
from pytuflow._tmf.batch_dependencies import BatchContext
from pytuflow._tmf.context import Context

from .fragment_evaluation_probe import FragmentEvaluationProbe
from .fragment_key_phase_attribution import PrivateKeyPhaseAttribution


def test_invariant_setting_and_time_key_phase_breakdown(tmp_path: Path) -> None:
    """Repeated static expressions still require translation and scope keys."""
    top = tmp_path / "private_model.tcf"
    top.write_text(
        "Set Variable VarCellSize == 16\n"
        "Start Time == 0\n"
        "End Time == 1440\n"
        "Read GIS Code == private_input.shp\n",
        encoding="utf-8",
    )
    model = TCF(top)
    flags = ["-e1 A", "-e1 B", "-e1 A", "-e1 C"]
    ordinary = model.collect_batch_dependencies(flags)
    original_key = fragment._Plan._key
    original_translate = fragment._FragmentContext.translate
    original_scope = BatchContext.in_context_by_scope
    original_context_translate = Context.translate

    anonymous = FragmentEvaluationProbe()
    phases = PrivateKeyPhaseAttribution()
    with anonymous.observe(), phases.observe():
        actual = model.collect_file_dependencies(flags)

    assert actual.passed and ordinary.passed
    assert actual.runs == ordinary.runs
    summary = phases.snapshot(actual)
    assert summary["key_calls"] == actual.fragment_evaluations + actual.fragment_reuses
    assert summary["key_errors"] == 0
    assert sum(item["key_calls"] for item in summary["by_input_type"].values()) == summary["key_calls"]
    assert any(item["fragment_translate"]["calls"] > 0 for item in summary["by_input_type"].values())
    assert any(item["scope_decision"]["calls"] > 0 for item in summary["by_input_type"].values())
    assert summary["top_anonymous_key_slots"]
    assert fragment._Plan._key is original_key
    assert fragment._FragmentContext.translate is original_translate
    assert BatchContext.in_context_by_scope is original_scope
    assert Context.translate is original_context_translate

    output = tmp_path / "private_report"
    output.mkdir()
    phases.write_private(output, actual)
    with (output / "private_key_phases_by_input.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        records = list(csv.DictReader(handle))
    assert len(records) >= 4
    assert any(row["command_name"].casefold() == "end time" for row in records)
    assert any(row["command_name"].casefold() == "set variable varcellsize" for row in records)
    assert all(float(row["key_inclusive_ms"]) >= 0 for row in records)
    assert all(int(row["key_calls"]) >= 1 for row in records)
    for private in ("private_model.tcf", "private_input.shp", "VarCellSize"):
        assert private not in json.dumps(summary)


def test_phase_patch_restores_methods_on_exception() -> None:
    before = (fragment._Plan._key, fragment._FragmentContext.translate, Context.translate)
    probe = PrivateKeyPhaseAttribution()
    with pytest.raises(RuntimeError, match="test exception"):
        with probe.observe():
            raise RuntimeError("test exception")
    assert before == (fragment._Plan._key, fragment._FragmentContext.translate, Context.translate)
    with pytest.raises(RuntimeError, match="new private key-phase probe"):
        with probe.observe():
            pass


def test_phase_cli_writes_private_source_report(tmp_path: Path) -> None:
    top = tmp_path / "private.tcf"
    top.write_text(
        "Set Variable VarCellSize == 5\nEnd Time == 1\nRead Grid Zpts == private.tif\n",
        encoding="utf-8",
    )
    flags_path = tmp_path / "flags.json"
    flags_path.write_text(json.dumps(["-e1 A", "-e1 B", "-e1 C"]), encoding="utf-8")
    output = tmp_path / "private-output"
    root = Path(__file__).absolute().parents[1]
    result = subprocess.run(
        [
            sys.executable, "-m", "tests.profile_fragment_evaluations",
            "--tcf", str(top),
            "--runs-json", str(flags_path),
            "--output", str(output),
            "--private-key-phases",
        ],
        cwd=root, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((output / "fragment_diagnostic.json").read_text(encoding="utf-8"))
    assert summary["ordinary_full_run_parity"]
    assert summary["key_phase_breakdown"]["key_calls"] == summary["lookups"]
    assert "private.tcf" not in json.dumps(summary)
    assert "VarCellSize" not in json.dumps(summary)
    with (output / "private_key_phases_by_input.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert any(row["command_name"].casefold() == "set variable varcellsize" for row in rows)
    assert sum(int(row["key_calls"]) for row in rows) == summary["lookups"]
