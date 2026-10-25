"""Syntactic contracts for comparing fork tests with the pinned upstream suite."""
from __future__ import annotations

from pathlib import Path

from tests.compare_upstream_tmf_junit import compare


def _report(path: Path, cases: dict[str, tuple[str, str]]) -> Path:
    import xml.etree.ElementTree as ET
    suite = ET.Element("testsuite")
    for name, (status, kind) in cases.items():
        case = ET.SubElement(suite, "testcase", {"classname": "tests.tmf.test_sample", "name": name})
        if status == "failed":
            ET.SubElement(case, "failure", {"type": kind, "message": kind})
        elif status == "skipped":
            ET.SubElement(case, "skipped")
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_matching_upstream_failures_are_reported_but_not_new_regressions(tmp_path: Path):
    baseline = _report(tmp_path / "base.xml", {
        "existing_failure": ("failed", "Pandas4Warning"),
        "passed": ("passed", ""),
    })
    fork = _report(tmp_path / "fork.xml", {
        "existing_failure": ("failed", "Pandas4Warning"),
        "passed": ("passed", ""),
        "new_passing_test": ("passed", ""),
    })
    problems, summary = compare(baseline, fork)
    assert not problems
    assert summary["upstream"]["failed"] == 1
    assert summary["fork"]["failed"] == 1


def test_new_failures_changed_causes_and_removed_tests_fail_gate(tmp_path: Path):
    baseline = _report(tmp_path / "base.xml", {
        "formerly_passing": ("passed", ""),
        "same_name_different_error": ("failed", "ValueError"),
        "removed": ("passed", ""),
    })
    fork = _report(tmp_path / "fork.xml", {
        "formerly_passing": ("failed", "AssertionError"),
        "same_name_different_error": ("failed", "RuntimeError"),
        "brand_new_failed": ("skipped", ""),
    })
    problems, _ = compare(baseline, fork)
    assert len(problems) == 4
    assert any("Regression" in issue for issue in problems)
    assert any("Changed failure category" in issue for issue in problems)
    assert any("Removed upstream case" in issue for issue in problems)
    assert any("New failing or skipped fork test" in issue for issue in problems)
