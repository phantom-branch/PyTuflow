"""Regression tests for the read-only Pyright baseline collector."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


SOURCE = Path(__file__).absolute().parents[2] / "ci" / "typing_baseline.py"
SPEC = importlib.util.spec_from_file_location("typing_baseline", SOURCE)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_summary_is_aggregate_only() -> None:
    payload = {
        "version": "1.1.0",
        "summary": {
            "filesAnalyzed": 28, "errorCount": 12,
            "warningCount": 3, "informationCount": 1,
        },
        "generalDiagnostics": [{
            "file": "F:/private/project/model.tcf",
            "message": "Cannot access private file",
        }],
        "typeCompleteness": {"completenessScore": 0.625},
    }
    metrics = audit.summarise_pyright(payload, 1)
    assert metrics == {
        "exit_code": 1,
        "errorCount": 12, "warningCount": 3, "informationCount": 1,
        "filesAnalyzed": 28, "type_completeness_score": 0.625,
    }
    assert "private" not in json.dumps(metrics)


def test_summary_rejects_invalid_numeric_counts() -> None:
    assert audit.summarise_pyright(
        {"summary": {"errorCount": True}, "typeCompleteness": {"completenessScore": "low"}},
        0,
    )["errorCount"] is None


def test_raw_report_remains_local(tmp_path: Path) -> None:
    destination = tmp_path / "pyright-3.12.json"
    payload = {
        "summary": {"filesAnalyzed": 1, "errorCount": 1, "warningCount": 0, "informationCount": 0},
        "generalDiagnostics": [{"file": "F:/private/sample.py", "message": "bad type"}],
    }
    process = SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr="test stderr")
    with patch.object(audit.subprocess, "run", return_value=process):
        aggregate, valid = audit.run_command(["pyright"], tmp_path, destination)
    assert valid
    assert aggregate["errorCount"] == 1
    assert "private" not in json.dumps(aggregate)
    assert "private" in destination.read_text(encoding="utf-8")
    assert destination.with_suffix(".stderr.txt").read_text(encoding="utf-8") == "test stderr"


def test_unparseable_output_is_not_accepted(tmp_path: Path) -> None:
    process = SimpleNamespace(returncode=1, stdout="not-json", stderr="")
    with patch.object(audit.subprocess, "run", return_value=process):
        aggregate, valid = audit.run_command(
            ["pyright"], tmp_path, tmp_path / "pyright-3.10.json",
        )
    assert not valid
    assert aggregate["tool_error"] == "Pyright did not return JSON"


def test_no_tracked_output_location(tmp_path: Path) -> None:
    checkout = tmp_path / "upstream"
    (checkout / "pytuflow").mkdir(parents=True)
    (checkout / "pytuflow" / "__init__.py").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        audit.main([
            "--source-root", str(checkout),
            "--output-dir", str(checkout / "audit-reports"),
        ])
    assert failure.value.code == 2
    assert not (checkout / "audit-reports").exists()


def test_git_head_does_not_report_noncommit_content(tmp_path: Path) -> None:
    process = SimpleNamespace(returncode=0, stdout="not-an-actual-sha\n", stderr="")
    with patch.object(audit.subprocess, "run", return_value=process):
        assert audit.git_head(tmp_path) is None


@pytest.mark.parametrize("payload", [{}, {"summary": {}}, {"summary": {
    "filesAnalyzed": 1, "errorCount": -1, "warningCount": 0, "informationCount": 0,
}}])
def test_incomplete_or_invalid_summary_fails_closed(tmp_path: Path, payload: dict) -> None:
    process = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
    with patch.object(audit.subprocess, "run", return_value=process):
        aggregate, valid = audit.run_command(["pyright"], tmp_path, tmp_path / "report.json")
    assert not valid
    assert "tool_error" in aggregate


def test_default_python310_target_and_tool_path_sanitisation(tmp_path: Path) -> None:
    checkout = tmp_path / "source"
    (checkout / "pytuflow").mkdir(parents=True)
    (checkout / "pytuflow" / "__init__.py").write_text("", encoding="utf-8")
    output = tmp_path / "reports"
    metrics = {"exit_code": 1, "errorCount": 2, "warningCount": 0,
               "informationCount": 0, "filesAnalyzed": 1, "type_completeness_score": None}
    executable = str(tmp_path / "private" / "pyright.exe")
    with patch.object(audit, "run_command", return_value=(metrics, True)) as run, \
            patch.object(audit, "git_head", return_value="a" * 40):
        assert audit.main(["--source-root", str(checkout), "--output-dir", str(output),
                           "--pyright", executable]) == 0
    assert "3.10" in run.call_args.args[0]
    report = json.loads((output / "summary.json").read_text())
    assert report["tool"] == "pyright.exe"
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize("score", [0.5, None, -1, 2, float("nan"), float("inf"), True])
@pytest.mark.parametrize("wrong_package", [False, True])
def test_verifytypes_is_bound_to_requested_source(tmp_path: Path, wrong_package: bool, score: float | None) -> None:
    package = tmp_path / "pytuflow"
    package.mkdir()
    other = tmp_path / "installed"
    other.mkdir()
    payload = {"summary": {"filesAnalyzed": 1, "errorCount": 0, "warningCount": 0, "informationCount": 0},
               "typeCompleteness": {"packageRootDirectory": str(other if wrong_package else package),
                                    "completenessScore": score,
                                    "exportedSymbolCounts": {"withKnownType": 1, "withAmbiguousType": 0,
                                                             "withUnknownType": 1}}}
    process = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
    with patch.object(audit.subprocess, "run", return_value=process) as run:
        metrics, valid = audit.run_command(["pyright", "--verifytypes", "pytuflow"], tmp_path,
                                          tmp_path / "verify.json")
    assert run.call_args.kwargs["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path)
    assert valid is (not wrong_package and score == 0.5)
    assert metrics["source_package_verified"] is not wrong_package
    if wrong_package:
        assert metrics["type_completeness_score"] is None
    assert str(tmp_path) not in json.dumps(metrics)
