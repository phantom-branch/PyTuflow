"""Fail-closed, immutable W5 baseline evidence reuse for pinned Windows environments.

Only cached upstream/fork reports are reusable. Every PR candidate is executed.
The complete JSON and adjacent JUnit must validate in the current interpreter,
dependency inventory, source pins, overlay hashes and harness version. Invalid
or incomplete evidence is a cache miss; it must never be treated as a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parent.parent))

from ci.compare_regression import ReportError, load_report
from ci.regression_probe import environment
from ci.run_regression import REQUIRED_GROUPS, SHARED_TEST_FILES, harness_fingerprint


def expected_overlays(harness: Path) -> dict[str, str]:
    """Hash the actual test-only overlays injected into both baselines."""
    return {
        name: hashlib.sha256((harness / name).read_bytes()).hexdigest()
        for name in SHARED_TEST_FILES
    }


def cache_key(harness: Path, upstream: str, fork: str) -> str:
    """Content identity includes the exact interpreter, pins and image release."""
    payload = {
        "schema": 1,
        "upstream": upstream,
        "fork": fork,
        "environment": environment(),
        "harness": harness_fingerprint(harness),
        "overlays": expected_overlays(harness),
        "runner_os": os.environ.get("RUNNER_OS", "local"),
        "runner_image_version": os.environ.get("ImageVersion", "unavailable"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def verify_baselines(root: Path, harness: Path, upstream: str, fork: str) -> None:
    """Reject stale/corrupt/partial evidence before skipping *either* baseline."""
    current_environment = environment()
    current_harness = harness_fingerprint(harness)
    overlays = expected_overlays(harness)
    for dirname, expected_sha, label in (
        ("upstream", upstream, "upstream"),
        ("baseline", fork, "fork-baseline"),
    ):
        report_file = root / dirname / "report.json"
        report = load_report(report_file, list(REQUIRED_GROUPS))
        if report.get("label") != label:
            raise ReportError(f"{dirname}: wrong source label")
        if report["source"]["sha"] != expected_sha:
            raise ReportError(f"{dirname}: changed source revision")
        if report["environment"] != current_environment:
            raise ReportError(f"{dirname}: changed interpreter or installed dependencies")
        if report["harness"]["implementation_sha256"] != current_harness:
            raise ReportError(f"{dirname}: changed executable harness")
        if report["harness"]["shared_test_overlays_sha256"] != overlays:
            raise ReportError(f"{dirname}: changed test-only overlays")
        if set(report["groups"]) != {*REQUIRED_GROUPS, "qgis"}:
            raise ReportError(f"{dirname}: missing/unexpected capability groups")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("key", "verify"))
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--fork", required=True)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    harness = Path(__file__).absolute().parent.parent
    if args.action == "key":
        print(cache_key(harness, args.upstream, args.fork))
        return 0
    if args.root is None:
        parser.error("--root is required for verify")
    try:
        verify_baselines(args.root.absolute(), harness, args.upstream, args.fork)
    except (OSError, ValueError, TypeError, KeyError, ReportError) as exc:
        print(f"Baseline cache rejected (normal complete rerun required): {exc}", file=sys.stderr)
        return 1
    print("Verified both immutable baseline evidence sets and every JUnit/capability group.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
