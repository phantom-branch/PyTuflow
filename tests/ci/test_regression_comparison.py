"""False-green regression tests for the original-library evidence gate."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from ci.compare_regression import compare_reports


class RegressionComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_report(self, label: str, cases: dict[str, dict], **group_overrides) -> Path:
        folder = self.root / label
        folder.mkdir(exist_ok=True)
        status_counts = {kind: 0 for kind in ("failed", "error", "skipped")}
        suite = ET.Element("testsuite")
        for nodeid, record in cases.items():
            case = ET.SubElement(suite, "testcase", classname="tests.test_example", name=nodeid)
            properties = ET.SubElement(case, "properties")
            ET.SubElement(properties, "property", name="nodeid", value=nodeid)
            outcome = record["outcome"]
            if outcome == "xfail":
                outcome = "skipped"
            tag = {"failed": "failure", "error": "error", "skipped": "skipped"}.get(outcome)
            if tag:
                ET.SubElement(case, tag, message=record.get("reason", ""))
                status_counts[outcome] += 1
        suite.attrib.update({
            "tests": str(len(cases)), "failures": str(status_counts["failed"]),
            "errors": str(status_counts["error"]), "skipped": str(status_counts["skipped"]),
        })
        ET.ElementTree(suite).write(folder / "tmf.xml", encoding="utf-8")
        group = {
            "required": True, "status": "completed", "collected": list(cases),
            "tests": cases, "collection_errors": [], "junit": "tmf.xml",
            "pytest_exit_code": int(bool(status_counts["failed"] + status_counts["error"])),
            "capabilities": {"numpy": True}, "required_capabilities": ["numpy"],
        }
        group.update(group_overrides)
        report = {
            "schema_version": 1, "completed": True,
            "source": {"sha": "a" * 40, "checkout_unchanged": True},
            "harness": {
                "shared_test_overlays_sha256": {"tests/fm_lib/common/compare_txt.py": "a" * 64},
                "implementation_sha256": "c" * 64,
            },
            "raw_status": "failed" if status_counts["failed"] + status_counts["error"] else "passed",
            "environment": {"python": "3.14.5", "platform": "Windows", "packages": {"pytest": "9.0.3"}},
            "required_groups": ["tmf"], "groups": {"tmf": group},
        }
        path = folder / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def modify(self, path: Path, callback) -> None:
        report = json.loads(path.read_text(encoding="utf-8"))
        callback(report)
        path.write_text(json.dumps(report), encoding="utf-8")

    def pair(self, cases: dict[str, dict] | None = None) -> tuple[Path, Path]:
        cases = cases or {"tests/test_example.py::test_pass": {"outcome": "passed"}}
        return self.write_report("base", deepcopy(cases)), self.write_report("candidate", deepcopy(cases))

    def assert_failed(self, baseline: Path, candidate: Path, phrase: str) -> dict:
        result = compare_reports(baseline, candidate)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(phrase in problem for problem in result["problems"]), result)
        return result

    def test_existing_failures_are_visible_and_new_passing_tests_are_allowed(self):
        cases = {
            "tests/test_example.py::test_failure": {"outcome": "failed", "failure_type": "ValueError", "phase": "call"},
            "tests/test_example.py::test_fixed": {"outcome": "failed", "failure_type": "AssertionError"},
        }
        baseline = self.write_report("base", cases)
        current = deepcopy(cases)
        current["tests/test_example.py::test_fixed"] = {"outcome": "passed"}
        current["tests/test_example.py::test_added"] = {"outcome": "passed"}
        candidate = self.write_report("candidate", current)
        result = compare_reports(baseline, candidate)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(len(result["inherited_failures"]), 1)
        self.assertEqual(len(result["fixed_failures"]), 1)
        self.assertEqual(result["counts"]["candidate"]["tmf"]["failed"], 1)

    def test_new_failure_is_a_regression(self):
        baseline, _ = self.pair()
        candidate = self.write_report("candidate", {"tests/test_example.py::test_pass": {
            "outcome": "failed", "failure_type": "AssertionError",
        }})
        self.assert_failed(baseline, candidate, "Regression")

    def test_new_nonpassing_test_is_not_inherited(self):
        baseline, _ = self.pair()
        candidate = self.write_report("candidate", {
            "tests/test_example.py::test_pass": {"outcome": "passed"},
            "tests/test_example.py::test_new": {"outcome": "failed", "failure_type": "ValueError"},
        })
        self.assert_failed(baseline, candidate, "New non-passing test")

    def test_removed_case_cannot_disappear_from_both_json_and_junit(self):
        baseline = self.write_report("base", {"one": {"outcome": "passed"}, "two": {"outcome": "passed"}})
        candidate = self.write_report("candidate", {"one": {"outcome": "passed"}})
        self.assert_failed(baseline, candidate, "Removed test")

    def test_changed_failure_type_phase_or_signature_is_not_accepted(self):
        record = {"outcome": "failed", "failure_type": "ValueError", "phase": "call", "failure_signature": "invalid time"}
        baseline = self.write_report("base", {"one": record})
        for key, value in (("failure_type", "TypeError"), ("phase", "setup"), ("failure_signature", "bad file")):
            with self.subTest(key=key):
                candidate = self.write_report("candidate", {"one": {**record, key: value}})
                self.assert_failed(baseline, candidate, "Changed failure")

    def test_missing_or_malformed_reports_fail(self):
        baseline, candidate = self.pair()
        candidate.unlink()
        self.assert_failed(baseline, candidate, "Cannot read regression report")
        candidate.write_text("not json", encoding="utf-8")
        self.assert_failed(baseline, candidate, "Cannot read regression report")

    def test_duplicate_json_keys_fail_instead_of_overwriting_evidence(self):
        baseline, candidate = self.pair()
        candidate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        self.assert_failed(baseline, candidate, "Duplicate JSON key")

    def test_empty_required_group_fails(self):
        baseline, _ = self.pair()
        candidate = self.write_report("candidate", {})
        self.assert_failed(baseline, candidate, "collected no tests")

    def test_missing_required_group_fails(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"].pop("tmf"))
        self.assert_failed(baseline, candidate, "Missing required group")

    def test_workflow_can_assert_contract_independently_of_reports(self):
        baseline, candidate = self.pair()
        result = compare_reports(baseline, candidate, ["tmf", "project"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(all("requested contract" in item for item in result["problems"]))

    def test_required_backend_unavailable_is_not_an_accepted_baseline(self):
        baseline, candidate = self.pair()
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["groups"]["tmf"].update(status="capability_unavailable"))
        self.assert_failed(baseline, candidate, "did not complete")

    def test_explicit_optional_capability_skip_is_recorded(self):
        baseline, candidate = self.pair()
        unavailable = {
            "required": False, "status": "capability_unavailable", "reason": "Requires QGIS runtime",
            "collected": [], "tests": {}, "collection_errors": [], "pytest_exit_code": None,
            "capabilities": {"qgis": False}, "required_capabilities": ["qgis"],
        }
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["groups"].update(qgis=unavailable))
        result = compare_reports(baseline, candidate)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["counts"]["candidate"]["qgis"]["collected"], 0)

    def test_optional_capability_skip_requires_explanation(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"].update(qgis={
            "required": False, "status": "capability_unavailable", "collected": [],
            "tests": {}, "collection_errors": [], "pytest_exit_code": None, "capabilities": {"qgis": False},
            "required_capabilities": ["qgis"],
        }))
        self.assert_failed(baseline, candidate, "lacks a capability skip reason")

    def test_optional_unselected_group_does_not_claim_backend_unavailable(self):
        baseline, candidate = self.pair()
        unselected = {
            "required": False, "status": "not_selected", "reason": "Select the separate QGIS job",
            "collected": [], "tests": {}, "collection_errors": [], "pytest_exit_code": None,
            "capabilities": {}, "required_capabilities": ["qgis"],
        }
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["groups"].update(qgis=unselected))
        result = compare_reports(baseline, candidate)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["skipped_groups"], [{
            "group": "qgis", "status": "not_selected", "reason": "Select the separate QGIS job",
        }])

    def test_required_group_cannot_be_marked_unselected(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(
            status="not_selected", reason="Select a separate job", capabilities={},
            collected=[], tests={}, pytest_exit_code=None,
        ))
        self.assert_failed(baseline, candidate, "Required group tmf was not selected")

    def test_unselected_optional_group_cannot_assert_backend_availability(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"].update(qgis={
            "required": False, "status": "not_selected", "reason": "Select separate QGIS job",
            "collected": [], "tests": {}, "collection_errors": [], "pytest_exit_code": None,
            "capabilities": {"qgis": False}, "required_capabilities": ["qgis"],
        }))
        self.assert_failed(baseline, candidate, "must not claim backend availability")

    def test_changed_optional_execution_status_is_visible(self):
        baseline, candidate = self.pair()
        common = {
            "required": False, "reason": "Select separate QGIS job", "collected": [],
            "tests": {}, "collection_errors": [], "pytest_exit_code": None, "required_capabilities": ["qgis"],
        }
        self.modify(baseline, lambda report: report["groups"].update(qgis={
            **common, "status": "not_selected", "capabilities": {},
        }))
        self.modify(candidate, lambda report: report["groups"].update(qgis={
            **common, "status": "capability_unavailable", "capabilities": {"qgis": False},
        }))
        self.assert_failed(baseline, candidate, "Capability execution status changed")

    def test_collection_error_fails_even_with_other_tests_executed(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(collection_errors=["import qgis failed"]))
        self.assert_failed(baseline, candidate, "collection errors")

    def test_duplicate_collected_ids_fail(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"]["tmf"]["collected"].append(report["groups"]["tmf"]["collected"][0]))
        self.assert_failed(baseline, candidate, "contains duplicates")

    def test_missing_execution_outcome_fails(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(tests={}))
        self.assert_failed(baseline, candidate, "collected and executed IDs differ")

    def test_missing_junit_fails(self):
        baseline, candidate = self.pair()
        (candidate.parent / "tmf.xml").unlink()
        self.assert_failed(baseline, candidate, "Missing or unreadable JUnit")

    def test_junit_identity_and_outcome_must_match_json(self):
        baseline, candidate = self.pair()
        xml = candidate.parent / "tmf.xml"
        tree = ET.parse(xml)
        prop = tree.find("./testcase/properties/property")
        prop.set("value", "another-test")
        tree.write(xml)
        self.assert_failed(baseline, candidate, "JUnit and collected IDs differ")
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(
            tests={"tests/test_example.py::test_pass": {"outcome": "failed", "failure_type": "AssertionError"}},
            pytest_exit_code=1,
        ))
        self.modify(candidate, lambda report: report.update(raw_status="failed"))
        self.assert_failed(baseline, candidate, "JSON/JUnit outcome mismatch")

    def test_junit_duplicate_testcases_and_false_counts_fail(self):
        baseline, candidate = self.pair()
        xml = candidate.parent / "tmf.xml"
        tree = ET.parse(xml)
        tree.getroot().append(deepcopy(tree.find("testcase")))
        tree.getroot().set("tests", "2")
        tree.write(xml)
        self.assert_failed(baseline, candidate, "Duplicate JUnit testcase")
        baseline, candidate = self.pair()
        tree = ET.parse(xml)
        tree.getroot().set("tests", "100")
        tree.write(xml)
        self.assert_failed(baseline, candidate, "JUnit tests count disagrees")

    def test_junit_without_nodeid_property_fails(self):
        baseline, candidate = self.pair()
        xml = candidate.parent / "tmf.xml"
        tree = ET.parse(xml)
        tree.find("testcase").remove(tree.find("./testcase/properties"))
        tree.write(xml)
        self.assert_failed(baseline, candidate, "nodeid property")

    def test_invalid_or_inconsistent_pytest_exit_fails(self):
        baseline, candidate = self.pair()
        for exit_code in (2, 3, 4, 5, 1, None, True):
            with self.subTest(exit_code=exit_code):
                self.modify(candidate, lambda report: report["groups"]["tmf"].update(pytest_exit_code=exit_code))
                self.assert_failed(baseline, candidate, "exit code")

    def test_skips_require_exact_explicit_reason_on_both_reports(self):
        cases = {
            "skip": {"outcome": "skipped", "reason": "Windows-only fixture"},
            "pass": {"outcome": "passed"},
        }
        baseline = self.write_report("base", cases)
        candidate = self.write_report("candidate", cases)
        self.assert_failed(baseline, candidate, "Unapproved skip/xfail")
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["groups"]["tmf"].update(allowed_skips={"skip": "Windows-only fixture"}))
        self.assertEqual(compare_reports(baseline, candidate)["status"], "passed")

    def test_all_skipped_required_group_is_not_executed(self):
        cases = {"one": {"outcome": "skipped", "reason": "known backend"}}
        baseline = self.write_report("base", cases, allowed_skips={"one": "known backend"})
        candidate = self.write_report("candidate", cases, allowed_skips={"one": "known backend"})
        self.assert_failed(baseline, candidate, "executed no tests")

    def test_newly_skipped_previously_passing_test_fails_even_if_preapproved(self):
        baseline = self.write_report("base", {
            "one": {"outcome": "passed"}, "two": {"outcome": "passed"},
        }, allowed_skips={"one": "known backend"})
        candidate = self.write_report("candidate", {
            "one": {"outcome": "skipped", "reason": "known backend"}, "two": {"outcome": "passed"},
        }, allowed_skips={"one": "known backend"})
        self.assert_failed(baseline, candidate, "Regression")

    def test_environment_mismatch_is_not_comparable(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["environment"]["packages"].update(pytest="9.1.0"))
        self.assert_failed(baseline, candidate, "environments differ")

    def test_required_capability_must_be_recorded_and_available(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(required_capabilities=["numpy", "h5py"]))
        self.assert_failed(baseline, candidate, "lacks a required capability result")
        self.modify(candidate, lambda report: report["groups"]["tmf"]["capabilities"].update(h5py=False))
        self.assert_failed(baseline, candidate, "unavailable required capability")

    def test_optional_capability_may_be_missing_with_explicit_explanation(self):
        baseline, candidate = self.pair()
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["groups"]["tmf"].update(
                capabilities={"numpy": True, "osgeo.ogr": False},
                optional_capabilities={"osgeo.ogr": "Legacy OGR-only tests use explicit skips; pyogrio remains required"},
            ))
        self.assertEqual(compare_reports(baseline, candidate)["status"], "passed")
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(
            optional_capabilities={}, allowed_skips={"unrelated-test": "unrelated reason"},
        ))
        self.assert_failed(baseline, candidate, "optional capabilities lack an approved explanation")

    def test_optional_capability_contract_cannot_change_during_comparison(self):
        baseline, candidate = self.pair()
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["groups"]["tmf"].update(
                capabilities={"numpy": True, "osgeo.ogr": False},
                optional_capabilities={"osgeo.ogr": "Legacy OGR-only tests use explicit skips"},
            ))
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(
            optional_capabilities={"osgeo.ogr": "Changed capability boundary"},
        ))
        self.assert_failed(baseline, candidate, "Optional capability contract changed")

    def test_required_capability_sets_must_match(self):
        baseline, candidate = self.pair()
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["groups"]["tmf"]["capabilities"].update(h5py=True))
        self.modify(candidate, lambda report: report["groups"]["tmf"]["required_capabilities"].append("h5py"))
        self.assert_failed(baseline, candidate, "Required capability set changed")

    def test_subprocess_failure_cannot_be_hidden_by_completed_pytest_report(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(process_exit_code=124))
        self.assert_failed(baseline, candidate, "process_exit_code disagrees")
        self.modify(candidate, lambda report: report["groups"]["tmf"].update(process_exit_code=0))
        self.assertEqual(compare_reports(baseline, candidate)["status"], "passed")

    def test_mutated_source_checkout_invalidates_report(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["source"].update(checkout_unchanged=False))
        self.assert_failed(baseline, candidate, "Source checkout changed")
        self.modify(candidate, lambda report: report["source"].update(checkout_unchanged=True))
        self.assertEqual(compare_reports(baseline, candidate)["status"], "passed")

    def test_shared_test_helper_overlays_must_match_between_sources(self):
        baseline, candidate = self.pair()
        overlays = {"tests/fm_lib/common/compare_txt.py": "a" * 64}
        for path in (baseline, candidate):
            self.modify(path, lambda report: report["harness"].update(shared_test_overlays_sha256=overlays))
        self.assertEqual(compare_reports(baseline, candidate)["status"], "passed")
        self.modify(candidate, lambda report: report["harness"]["shared_test_overlays_sha256"].update(
            {"tests/fm_lib/common/compare_txt.py": "b" * 64}
        ))
        self.assert_failed(baseline, candidate, "shared test overlay hashes differ")

    def test_overlay_evidence_cannot_disappear(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["harness"].pop("shared_test_overlays_sha256"))
        self.assert_failed(baseline, candidate, "Shared test overlays must be an object")

    def test_interrupted_report_is_rejected_even_if_all_test_results_exist(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report.update(completed=False))
        self.assert_failed(baseline, candidate, "not finalised")
        self.modify(candidate, lambda report: report.pop("completed"))
        self.assert_failed(baseline, candidate, "not finalised")

    def test_missing_source_preservation_evidence_fails(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["source"].pop("checkout_unchanged"))
        self.assert_failed(baseline, candidate, "lacks preservation evidence")

    def test_aggregate_failure_status_cannot_contradict_execution(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report.update(raw_status="failed"))
        self.assert_failed(baseline, candidate, "Aggregate raw_status disagrees")
        baseline, candidate = self.pair({"one": {"outcome": "failed", "failure_type": "AssertionError"}})
        self.modify(candidate, lambda report: report.update(raw_status="passed"))
        self.assert_failed(baseline, candidate, "Aggregate raw_status disagrees")

    def test_harness_implementation_digest_must_exist_and_match(self):
        baseline, candidate = self.pair()
        self.modify(candidate, lambda report: report["harness"].update(implementation_sha256="d" * 64))
        self.assert_failed(baseline, candidate, "harness implementations differ")
        self.modify(candidate, lambda report: report["harness"].pop("implementation_sha256"))
        self.assert_failed(baseline, candidate, "implementation SHA-256")


if __name__ == "__main__":
    unittest.main()
