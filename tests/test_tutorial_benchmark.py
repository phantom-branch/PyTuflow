"""Correctness tests for the public tutorial benchmark (no timing claims).

These tiny temporary synthetic fixtures test archive safety and diff logic,
not representative TUFLOW benchmark performance.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest
from pytuflow import TCF

from tests.benchmark_tutorial_dependencies import (
    batch,
    compare_runs,
    discover_cases,
    extract_flag_pairs,
    extract_verified,
    individual,
    verify_bundle,
)


def _bundle(tmp_path: Path, *, filename: str = "runs/sample.tcf") -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    source = b"Read GIS Code == gis/code.shp\n"
    archive = bundle / "examples.zip"
    with ZipFile(archive, "w") as z:
        z.writestr(filename, source)
    (bundle / "manifest.json").write_text(json.dumps({
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": [{"path": filename, "size": len(source),
                   "sha256": hashlib.sha256(source).hexdigest()}],
    }), encoding="utf-8")
    with (bundle / "baseline.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("tcf", "runs"))
        writer.writerow(("runs/sample.tcf", 1))
    return bundle


def test_bundle_verification_and_temporary_extraction(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest, baseline = verify_bundle(bundle, expected_archive_sha256=None, expected_inventory=None)
    assert manifest["files"][0]["path"] == "runs/sample.tcf"
    assert baseline == {"runs/sample.tcf": 1}
    extracted = tmp_path / "temporary"
    extracted.mkdir()
    extract_verified(bundle, extracted)
    assert discover_cases(extracted, baseline) == {"runs/sample.tcf": ("",)}
    assert not (bundle / "runs").exists()


def test_unapproved_bundle_is_rejected_by_default(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with pytest.raises(ValueError, match="pinned public tutorial"):
        verify_bundle(bundle)


def test_bad_archive_checksum_is_rejected(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with (bundle / "examples.zip").open("ab") as stream:
        stream.write(b"altered")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_bundle(bundle, expected_archive_sha256=None, expected_inventory=None)


def test_unsafe_archive_entry_is_rejected_before_extraction(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, filename="../escape.tcf")
    with pytest.raises(ValueError, match="Unsafe"):
        verify_bundle(bundle, expected_archive_sha256=None, expected_inventory=None)
    assert not (tmp_path / "escape.tcf").exists()


def test_duplicate_flags_are_rejected() -> None:
    assert extract_flag_pairs("TUFLOW.exe -s1 DEV -e1 01.0p sample.tcf") == (
        ("s1", "DEV"), ("e1", "01.0p"),
    )
    with pytest.raises(ValueError, match="Duplicate"):
        extract_flag_pairs("TUFLOW.exe -s1 DEV -s1 EXG sample.tcf")


def test_exact_syntactic_parity_and_both_diff_directions(tmp_path: Path) -> None:
    source = tmp_path / "simple.tcf"
    source.write_text(
        "Set Variable ROOT == gis\n"
        "Read GIS Code == <<ROOT>>/code.shp\n"
        "Read GRID Zpts == grids/terrain.tif\n", encoding="utf-8",
    )
    model = TCF(source)
    flags = ("-s1 EXG -e1 A", "-s1 DEV -e1 B", "-s1 EXG -e1 A")
    expected, _ = individual(model, flags)
    actual, _ = batch(model, flags, cached=True)
    assert all(case.error is None for case in expected)
    assert compare_runs(expected, actual) == {"missing": 0, "extra": 0}
    wrong = list(actual)
    wrong[0] = replace(wrong[0], ordered_inputs=wrong[0].ordered_inputs[:-1])
    assert compare_runs(expected, tuple(wrong))["missing"] == 1
    assert compare_runs(tuple(wrong), expected)["extra"] == 1


def test_failed_context_is_never_partial(tmp_path: Path) -> None:
    tcf = tmp_path / "fail.tcf"
    tcf.write_text("Read GIS Code == gis/input.shp\n", encoding="utf-8")
    baseline, _ = individual(TCF(tcf), ("-s1 DEV -s1 EXG",))
    assert baseline[0].error
    assert baseline[0].file_references == ()
    assert baseline[0].input_references == ()
    assert baseline[0].ordered_inputs == ()
