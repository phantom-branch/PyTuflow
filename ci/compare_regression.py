"""Compare complete original-library regression reports without hiding failures.

Both inputs must include the JSON result and its adjacent JUnit files. Existing
failures are accepted only when the same test has the same failure category (and
signature, when supplied). Missing tests, changed failures, collection errors,
unapproved skips and mismatched environments fail the gate.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


OUTCOMES = {"passed", "failed", "error", "skipped", "xfail", "xpass"}
FAILURES = {"failed", "error"}
SKIPS = {"skipped", "xfail"}


class ReportError(ValueError):
    """A report cannot establish complete execution of its declared contract."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReportError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def _mapping(value: object, label: str) -> dict:
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _strings(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    _require(isinstance(value, list), f"{label} must be a list")
    _require(all(isinstance(item, str) and item for item in value),
             f"{label} must contain nonempty strings")
    _require(len(set(value)) == len(value), f"{label} contains duplicates")
    if nonempty:
        _require(bool(value), f"{label} must not be empty")
    return value


def _junit_cases(path: Path) -> dict[str, str]:
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        raise ReportError(f"Missing or unreadable JUnit report {path.name}: {exc}") from exc
    root = tree.getroot()
    _require(root.tag in {"testsuite", "testsuites"}, "Invalid JUnit root element")
    result = {}
    suites = list(root.iter("testsuite"))
    _require(bool(suites), "JUnit report has no testsuite")
    for suite in suites:
        cases = list(suite.findall("testcase"))
        if not cases and suite.findall("testsuite"):
            continue
        counts = Counter()
        for case in cases:
            properties = case.findall("./properties/property[@name='nodeid']")
            _require(len(properties) == 1 and bool(properties[0].get("value")),
                     "JUnit testcase must have exactly one nonempty nodeid property")
            nodeid = properties[0].get("value")
            _require(nodeid not in result, f"Duplicate JUnit testcase: {nodeid}")
            outcomes = [child for child in case if child.tag in {"failure", "error", "skipped"}]
            _require(len(outcomes) <= 1, f"Ambiguous JUnit outcomes for {nodeid}")
            outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}.get(
                outcomes[0].tag if outcomes else "", "passed"
            )
            result[nodeid] = outcome
            counts[outcome] += 1
        expected = {
            "tests": len(cases), "failures": counts["failed"],
            "errors": counts["error"], "skipped": counts["skipped"],
        }
        for name, value in expected.items():
            raw = suite.get(name)
            _require(raw is not None and raw.isdecimal(), f"JUnit testsuite lacks valid {name} count")
            _require(int(raw) == value, f"JUnit {name} count disagrees with its testcases")
    _require(bool(result), "JUnit report contains no testcases")
    return result


def _validate_group(name: str, value: object, report_path: Path) -> dict:
    group = _mapping(value, f"Group {name}")
    _require(type(group.get("required")) is bool, f"Group {name} lacks a required flag")
    capabilities = _mapping(group.get("capabilities"), f"Group {name} capabilities")
    required_capabilities = _strings(group.get("required_capabilities"),
                                     f"Group {name} required_capabilities", nonempty=True)
    collected = _strings(group.get("collected"), f"Group {name} collected IDs")
    tests = _mapping(group.get("tests"), f"Group {name} tests")
    collection_errors = group.get("collection_errors")
    _require(isinstance(collection_errors, list), f"Group {name} lacks collection_errors")
    _require(not collection_errors, f"Group {name} has collection errors: {collection_errors}")
    if group.get("status") == "not_selected":
        _require(not group["required"], f"Required group {name} was not selected")
        _require(isinstance(group.get("reason"), str) and bool(group["reason"].strip()),
                 f"Optional group {name} lacks a selection boundary reason")
        _require(not capabilities, f"Unselected group {name} must not claim backend availability")
        _require(not collected and not tests and group.get("pytest_exit_code") is None
                 and group.get("process_exit_code") is None,
                 f"Unselected group {name} has inconsistent execution evidence")
        return group
    _require(bool(capabilities) and all(isinstance(key, str) and type(item) is bool for key, item in capabilities.items()),
             f"Group {name} capabilities must map names to booleans")
    _require(set(required_capabilities) <= set(capabilities),
             f"Group {name} lacks a required capability result")
    if group.get("status") == "capability_unavailable" and not group["required"]:
        _require(isinstance(group.get("reason"), str) and bool(group["reason"].strip()),
                 f"Optional group {name} lacks a capability skip reason")
        _require(not collected and not tests and group.get("pytest_exit_code") is None,
                 f"Optional group {name} has inconsistent unavailable-capability evidence")
        _require(group.get("process_exit_code") is None,
                 f"Optional group {name} records a process exit without execution")
        return group
    _require(group.get("status") == "completed", f"Group {name} did not complete: {group.get('status')}")
    _require(all(capabilities[capability] for capability in required_capabilities),
             f"Group {name} has an unavailable required capability")
    _require(bool(collected), f"Group {name} collected no tests")
    _require(set(collected) == set(tests), f"Group {name} collected and executed IDs differ")
    allowed_skips = _mapping(group.get("allowed_skips", {}), f"Group {name} allowed_skips")
    _require(all(isinstance(nodeid, str) and nodeid and isinstance(reason, str) and reason.strip()
                 for nodeid, reason in allowed_skips.items()),
             f"Group {name} allowed_skips must name exact tests with nonempty reasons")
    optional_capabilities = _mapping(group.get("optional_capabilities", {}), f"Group {name} optional_capabilities")
    _require(all(isinstance(key, str) and key and isinstance(reason, str) and reason.strip()
                 for key, reason in optional_capabilities.items()),
             f"Group {name} optional_capabilities must explain each optional backend")
    optional_missing = {key for key, available in capabilities.items() if not available} - set(required_capabilities)
    _require(optional_missing <= set(optional_capabilities),
             f"Group {name} unavailable optional capabilities lack an approved explanation: {sorted(optional_missing)}")
    for nodeid, record_value in tests.items():
        record = _mapping(record_value, f"Test {nodeid}")
        outcome = record.get("outcome")
        _require(outcome in OUTCOMES, f"Invalid outcome for {nodeid}: {outcome!r}")
        _require(outcome != "xpass", f"Unexpected XPASS: {nodeid}")
        if outcome in FAILURES:
            _require(isinstance(record.get("failure_type"), str) and bool(record["failure_type"]),
                     f"Failure lacks a category: {nodeid}")
            if "failure_signature" in record:
                _require(isinstance(record["failure_signature"], str), f"Invalid failure signature: {nodeid}")
        if outcome in SKIPS:
            reason = record.get("reason")
            _require(isinstance(reason, str) and bool(reason), f"Skip lacks a reason: {nodeid}")
            _require(nodeid in allowed_skips and allowed_skips[nodeid] == reason,
                     f"Unapproved skip/xfail: {nodeid}: {reason}")
    _require(any(record["outcome"] in {"passed", "failed", "error"} for record in tests.values()),
             f"Group {name} executed no tests (all skipped/xfail)")
    exit_code = group.get("pytest_exit_code")
    _require(type(exit_code) is int and exit_code in {0, 1},
             f"Group {name} has invalid pytest exit code: {exit_code!r}")
    has_failures = any(record["outcome"] in FAILURES for record in tests.values())
    _require(exit_code == int(has_failures), f"Group {name} pytest exit code disagrees with outcomes")
    if "process_exit_code" in group:
        process_exit = group["process_exit_code"]
        _require(type(process_exit) is int and process_exit == exit_code,
                 f"Group {name} process_exit_code disagrees with pytest_exit_code")
    junit_name = group.get("junit")
    _require(isinstance(junit_name, str) and bool(junit_name), f"Group {name} lacks JUnit path")
    junit_path = Path(junit_name)
    _require(not junit_path.is_absolute() and ".." not in junit_path.parts,
             f"Group {name} JUnit path must be relative to the JSON report directory")
    junit = _junit_cases(report_path.parent / junit_path)
    _require(set(junit) == set(collected), f"Group {name} JUnit and collected IDs differ")
    for nodeid, record in tests.items():
        outcome = "skipped" if record["outcome"] == "xfail" else record["outcome"]
        _require(junit[nodeid] == outcome, f"Group {name} JSON/JUnit outcome mismatch: {nodeid}")
    return group


def load_report(path: Path, required_groups: list[str] | None = None) -> dict:
    """Read and verify all evidence required to use a report as a comparison input."""
    try:
        report = _mapping(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object), "Report")
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"Cannot read regression report {path}: {exc}") from exc
    _require(type(report.get("schema_version")) is int and report["schema_version"] == 1,
             "Unsupported regression report schema_version")
    _require(report.get("completed") is True, "Regression report was not finalised")
    source = _mapping(report.get("source"), "Source")
    sha = source.get("sha")
    _require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) is not None,
             "Source must include an exact 40-character commit SHA")
    _require(source.get("checkout_unchanged") is True, "Source checkout changed or lacks preservation evidence")
    harness = _mapping(report.get("harness"), "Harness")
    overlays = _mapping(harness.get("shared_test_overlays_sha256"), "Shared test overlays")
    _require(bool(overlays) and all(isinstance(name, str) and name and isinstance(digest, str)
                                   and re.fullmatch(r"[0-9a-f]{64}", digest) is not None for name, digest in overlays.items()),
             "Shared test overlays must record exact SHA-256 hashes")
    implementation = harness.get("implementation_sha256")
    _require(isinstance(implementation, str) and re.fullmatch(r"[0-9a-f]{64}", implementation) is not None,
             "Harness must record its implementation SHA-256")
    environment = _mapping(report.get("environment"), "Environment")
    for name in ("python", "platform"):
        _require(isinstance(environment.get(name), str) and bool(environment[name]),
                 f"Environment lacks {name}")
    packages = _mapping(environment.get("packages"), "Environment packages")
    _require(bool(packages) and all(isinstance(k, str) and isinstance(v, str) for k, v in packages.items()),
             "Environment must record package versions")
    contract = _strings(report.get("required_groups"), "Required groups", nonempty=True)
    if required_groups is not None:
        _require(set(contract) == set(required_groups), "Declared required groups differ from the requested contract")
    groups = _mapping(report.get("groups"), "Groups")
    for name in contract:
        _require(name in groups, f"Missing required group: {name}")
    for name, group in groups.items():
        group = _validate_group(name, group, path)
        _require(group["required"] == (name in contract), f"Group {name} required flag differs from contract")
    has_failures = any(record["outcome"] in FAILURES for group in groups.values() for record in group["tests"].values())
    expected_status = "failed" if has_failures else "passed"
    _require(report.get("raw_status") == expected_status,
             f"Aggregate raw_status disagrees with executed outcomes (expected {expected_status})")
    return report


def _counts(report: dict) -> dict[str, dict[str, int]]:
    result = {}
    for name, group in report["groups"].items():
        counts = Counter(record["outcome"] for record in group["tests"].values())
        result[name] = {"collected": len(group["collected"]), **{outcome: counts[outcome] for outcome in sorted(OUTCOMES)}}
    return result


def compare_reports(baseline_path: Path, candidate_path: Path, required_groups: list[str] | None = None) -> dict:
    """Return a machine-readable comparison, including inherited failure IDs."""
    result = {
        "schema_version": 1, "status": "failed", "problems": [],
        "sources": {}, "counts": {}, "inherited_failures": [], "fixed_failures": [],
        "inherited_skips": [], "skipped_groups": [],
    }
    reports = {}
    for label, path in (("baseline", baseline_path), ("candidate", candidate_path)):
        try:
            reports[label] = load_report(path, required_groups)
            result["sources"][label] = reports[label]["source"]
            result["counts"][label] = _counts(reports[label])
        except (ReportError, TypeError, KeyError) as exc:
            result["problems"].append(f"Invalid {label} report: {exc}")
    if len(reports) != 2:
        return result
    baseline, candidate = reports["baseline"], reports["candidate"]
    problems = result["problems"]
    if baseline["environment"] != candidate["environment"]:
        problems.append("Baseline and candidate environments differ")
    base_overlays = baseline.get("harness", {}).get("shared_test_overlays_sha256")
    current_overlays = candidate.get("harness", {}).get("shared_test_overlays_sha256")
    if base_overlays != current_overlays:
        problems.append("Baseline and candidate shared test overlay hashes differ")
    if baseline["harness"]["implementation_sha256"] != candidate["harness"]["implementation_sha256"]:
        problems.append("Baseline and candidate harness implementations differ")
    if set(baseline["required_groups"]) != set(candidate["required_groups"]):
        problems.append("Baseline and candidate required-group contracts differ")
    if set(baseline["groups"]) != set(candidate["groups"]):
        problems.append("Baseline and candidate capability groups differ")
    for name, base_group in baseline["groups"].items():
        current = candidate["groups"].get(name)
        if current is None:
            continue
        if current["status"] in {"capability_unavailable", "not_selected"}:
            result["skipped_groups"].append({"group": name, "status": current["status"], "reason": current["reason"]})
        if base_group.get("capabilities", {}) != current.get("capabilities", {}):
            problems.append(f"Capability set changed for group {name}")
        if set(base_group["required_capabilities"]) != set(current["required_capabilities"]):
            problems.append(f"Required capability set changed for group {name}")
        if base_group.get("optional_capabilities", {}) != current.get("optional_capabilities", {}):
            problems.append(f"Optional capability contract changed for group {name}")
        if base_group.get("allowed_skips", {}) != current.get("allowed_skips", {}):
            problems.append(f"Allowed-skip contract changed for group {name}")
        if base_group["status"] != current["status"]:
            problems.append(f"Capability execution status changed for group {name}")
        base_tests, current_tests = base_group["tests"], current["tests"]
        for nodeid, old in base_tests.items():
            new = current_tests.get(nodeid)
            if new is None:
                problems.append(f"Removed test: {name}: {nodeid}")
                continue
            if new["outcome"] == "passed":
                if old["outcome"] in FAILURES:
                    result["fixed_failures"].append({"group": name, "nodeid": nodeid, **old})
                continue
            if new["outcome"] != old["outcome"]:
                problems.append(f"Regression: {name}: {nodeid}: {old['outcome']} -> {new['outcome']}")
            elif new["outcome"] in FAILURES:
                identity_keys = ("failure_type", "failure_signature", "phase")
                if any(old.get(key) != new.get(key) for key in identity_keys):
                    problems.append(f"Changed failure: {name}: {nodeid}")
                else:
                    result["inherited_failures"].append({"group": name, "nodeid": nodeid, **new})
            elif new.get("reason") != old.get("reason"):
                problems.append(f"Changed skip reason: {name}: {nodeid}")
            elif new["outcome"] in SKIPS:
                result["inherited_skips"].append({"group": name, "nodeid": nodeid, **new})
        for nodeid, record in current_tests.items():
            if nodeid not in base_tests and record["outcome"] != "passed":
                problems.append(f"New non-passing test: {name}: {nodeid}: {record['outcome']}")
    result["status"] = "passed" if not problems else "failed"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--required-group", action="append", dest="required_groups")
    args = parser.parse_args(argv)
    result = compare_reports(args.baseline, args.candidate, args.required_groups)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
