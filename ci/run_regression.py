"""Run public legacy suites in disposable source/fixture copies, with full evidence.

No virtual environments, Git worktrees, proprietary solvers or external model
data are used. A nonzero raw test result remains nonzero; compare_regression.py
separately decides whether it is an inherited failure or a new regression.
"""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile


REQUIRED_GROUPS = ("time_series", "python_mesh", "tmf", "project", "fm")
SHARED_TEST_FILES = (
    "tests/fm_lib/integration_tests/test_conversion.py",
    "tests/fm_lib/common/compare_txt.py",
)


def git(source: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *arguments], text=True).strip()


def checkout_fingerprint(source: Path) -> str:
    """Detect changed dirty contents as well as new/deleted files and HEAD."""
    digest = hashlib.sha256(git(source, "rev-parse", "HEAD").encode())
    digest.update(subprocess.check_output(["git", "-C", str(source), "diff", "--binary", "HEAD"]))
    for name in git(source, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if name:
            path = source / name
            if path.is_file():
                digest.update(name.encode())
                digest.update(path.read_bytes())
            else:
                digest.update((name + "<directory-or-missing>").encode())
    return digest.hexdigest()


def harness_fingerprint(harness: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((harness / "ci").glob("*")):
        if path.is_file() and path.suffix in {".py", ".txt"}:
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def snapshot(source: Path, revision: str, destination: Path, harness: Path) -> dict[str, str]:
    destination.mkdir()
    archive = destination.parent / "source.tar"
    with archive.open("wb") as stream:
        subprocess.run(["git", "-C", str(source), "archive", revision], stdout=stream, check=True)
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter="data")
    archive.unlink()
    overlays = {}
    # Apply the same corrected *test helpers* to every revision. No production
    # files are overlaid; the hashes make this harness revision explicit.
    for relative in SHARED_TEST_FILES:
        original = harness / relative
        target = destination / relative
        shutil.copyfile(original, target)
        overlays[relative] = hashlib.sha256(original.read_bytes()).hexdigest()
    return overlays


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--label", required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--group", action="append", choices=(*REQUIRED_GROUPS, "qgis"))
    parser.add_argument("--timeout", type=int, default=1200, help="Timeout in seconds per capability group")
    args = parser.parse_args()
    source = args.source.absolute()
    harness = Path(__file__).absolute().parent.parent
    output = args.report_dir.absolute()
    if output.is_relative_to(source):
        parser.error("Reports must be outside the source checkout")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Report directory must be empty to prevent accepting stale evidence")
    groups = args.group or list(REQUIRED_GROUPS)
    if len(groups) != len(set(groups)):
        parser.error("Repeated groups are not allowed")
    revision = git(source, "rev-parse", "--verify", args.ref + "^{commit}")
    before = checkout_fingerprint(source)
    report = {
        "schema_version": 1, "label": args.label, "completed": False,
        "source": {"sha": revision, "requested_ref": args.ref, "repository": str(source)},
        "harness": {"sha": git(harness, "rev-parse", "HEAD"), "dirty": bool(git(harness, "status", "--porcelain")), "implementation_sha256": harness_fingerprint(harness)},
        "required_groups": groups, "groups": {}, "environment": {},
        "command": [sys.executable, *sys.argv],
    }
    failed = False
    for group in groups:
        print(f"{args.label}: {group} at {revision}", flush=True)
        # Use the explicit report location, not Windows' default %TEMP%, whose
        # RUNNER~1 alias changes legacy lexical-vs-canonical path assertions.
        with tempfile.TemporaryDirectory(prefix=f"pytuflow-{group}-", dir=output.parent) as directory:
            temporary = Path(directory)
            checkout = temporary / "source"
            overlays = snapshot(source, revision, checkout, harness)
            report["harness"]["shared_test_overlays_sha256"] = overlays
            command = [
                sys.executable, str(harness / "ci" / "regression_probe.py"),
                "--group", group, "--source-root", str(checkout),
                "--report", str(output / f"{group}.json"),
                "--junit", str(output / f"{group}.xml"), "--temporary", str(temporary),
            ]
            environment = os.environ.copy()
            # Prevent unrelated globally installed pytest plugins changing the
            # suite. No change to pyproject's warnings or test assertions.
            environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
            environment.pop("PYTEST_ADDOPTS", None)
            environment.pop("PYTEST_PLUGINS", None)
            environment["PYTHONNOUSERSITE"] = "1"
            environment["PYTHONUNBUFFERED"] = "1"
            environment["MPLCONFIGDIR"] = str(temporary / "matplotlib")
            environment["PYVISTA_OFF_SCREEN"] = "true"
            with (output / f"{group}.log").open("w", encoding="utf-8") as log:
                try:
                    completed = subprocess.run(command, cwd=checkout, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                    returncode = completed.returncode
                except subprocess.TimeoutExpired:
                    log.write(f"\nGroup exceeded {args.timeout}s timeout\n")
                    returncode = 124
            group_path = output / f"{group}.json"
            if group_path.is_file():
                record = json.loads(group_path.read_text(encoding="utf-8"))
                group_environment = record.pop("environment")
                if report["environment"] and report["environment"] != group_environment:
                    record["status"] = "environment_error"
                    record["reason"] = "Interpreter or dependency inventory changed between groups"
                report["environment"] = group_environment
            else:
                record = {"required": True, "status": "incomplete", "reason": "Probe did not write its report", "collected": [], "tests": {}, "collection_errors": [], "pytest_exit_code": None, "junit": f"{group}.xml"}
            record["process_exit_code"] = returncode
            record["command"] = command
            report["groups"][group] = record
            failed |= returncode != 0 or record["status"] != "completed"
            print(f"  {record['status']}: collected={len(record['collected'])}, outcomes={record.get('counts', {})}", flush=True)
        # Always retain progress if a later group is interrupted.
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if "qgis" not in groups:
        report["groups"]["qgis"] = {
            "required": False, "status": "not_selected",
            "reason": "QGIS integration is a separately selected real-runtime job; run --group qgis from its configured interpreter",
            "collected": [], "tests": {}, "collection_errors": [], "capabilities": {},
            "required_capabilities": ["qgis"],
            "pytest_exit_code": None,
        }
    report["source"]["checkout_unchanged"] = before == checkout_fingerprint(source)
    failed |= not report["source"]["checkout_unchanged"]
    report["counts"] = dict(sum((Counter(item.get("counts", {})) for item in report["groups"].values()), Counter()))
    report["raw_status"] = "failed" if failed else "passed"
    report["completed"] = True
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"report": str(output / "report.json"), "raw_status": report["raw_status"], "counts": report["counts"]}), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
