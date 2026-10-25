"""Read-only local Pyright baseline for upstream/fork interpreter compatibility.

Run from an existing checkout; requires an existing `pyright` executable.
No virtual environments, dependency installation or source modifications.
Raw reports can include private local paths and must remain local.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PYTHON_TARGETS = ("3.10", "3.12", "3.13", "3.14")


def summarise_pyright(payload: dict, exit_code: int) -> dict:
    """Return aggregate metrics without paths, symbols or source excerpts."""
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    completeness = payload.get("typeCompleteness")
    if not isinstance(completeness, dict):
        completeness = {}
    fields = ("errorCount", "warningCount", "informationCount", "filesAnalyzed")
    result = {"exit_code": exit_code}
    for key in fields:
        value = summary.get(key)
        result[key] = value if isinstance(value, int) and not isinstance(value, bool) else None
    score = completeness.get("completenessScore")
    result["type_completeness_score"] = (
        score if isinstance(score, (int, float)) and not isinstance(score, bool) else None
    )
    return result


def git_head(root: Path) -> str | None:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True,
        check=False, encoding="utf-8", errors="replace",
    )
    if process.returncode != 0:
        return None
    sha = process.stdout.strip()
    return sha if len(sha) == 40 and all(ch in "0123456789abcdef" for ch in sha) else None


def run_command(command: list[str], root: Path, destination: Path) -> tuple[dict, bool]:
    """Save full raw diagnostics locally and return only path-free aggregates."""
    environment = os.environ.copy()
    # --verifytypes searches interpreter paths rather than trusting cwd/extraPaths.
    # Bind this child only to the selected checkout; do not install the package.
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(root), environment.get("PYTHONPATH", "")) if item
    )
    try:
        process = subprocess.run(
            command, cwd=root, text=True, capture_output=True, check=False,
            encoding="utf-8", errors="replace",
            env=environment,
        )
    except OSError as exc:
        destination.with_suffix(".error.txt").write_text(str(exc), encoding="utf-8")
        return {"tool_error": "Unable to start Pyright", "exit_code": None}, False

    destination.write_text(process.stdout, encoding="utf-8")
    if process.stderr:
        destination.with_suffix(".stderr.txt").write_text(process.stderr, encoding="utf-8")
    try:
        payload = json.loads(process.stdout)
    except (ValueError, TypeError):
        return {"tool_error": "Pyright did not return JSON", "exit_code": process.returncode}, False
    if not isinstance(payload, dict):
        return {"tool_error": "Pyright JSON is not an object", "exit_code": process.returncode}, False

    # Pyright code 1 commonly means diagnostics were found, not tool failure.
    metric = summarise_pyright(payload, process.returncode)
    valid = process.returncode in (0, 1) and all(
        isinstance(metric[key], int) and metric[key] >= 0
        for key in ("errorCount", "warningCount", "informationCount", "filesAnalyzed")
    )
    if not valid:
        metric["tool_error"] = "Pyright failed or returned an incomplete summary"
    if "--verifytypes" in command:
        completeness = payload.get("typeCompleteness", {})
        package_root = completeness.get("packageRootDirectory") if isinstance(completeness, dict) else None
        try:
            # Follow links deliberately to verify actual analysed package identity.
            matches_source = isinstance(package_root, str) and (root / "pytuflow").samefile(package_root)
        except OSError:
            matches_source = False
        counts = completeness.get("exportedSymbolCounts", {}) if isinstance(completeness, dict) else {}
        keys = ("withKnownType", "withAmbiguousType", "withUnknownType")
        counts_valid = isinstance(counts, dict) and all(
            isinstance(counts.get(key), int) and not isinstance(counts[key], bool) and counts[key] >= 0
            for key in keys
        )
        score = metric["type_completeness_score"]
        score_valid = score is not None and math.isfinite(score) and 0 <= score <= 1
        source_verified = matches_source and counts_valid and sum(counts[key] for key in keys) > 0
        if not score_valid:
            metric["tool_error"] = "Pyright returned an invalid completeness score"
            valid = False
        metric["source_package_verified"] = source_verified
        metric["exported_symbols"] = {key: counts[key] for key in keys} if counts_valid else None
        if not source_verified:
            metric["type_completeness_score"] = None
            metric["tool_error"] = "Pyright did not inspect the requested source package"
            valid = False
    return metric, valid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=Path(__file__).absolute().parents[1],
        help="Existing upstream or fork checkout; never modified",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="New, untracked output directory, preferably outside the repository",
    )
    parser.add_argument(
        "--targets", nargs="+", choices=PYTHON_TARGETS,
        default=["3.10"],
    )
    parser.add_argument("--pyright", default="pyright", help="Existing Pyright executable")
    parser.add_argument(
        "--verifytypes", action="store_true",
        help="Additionally collect public type completeness under each target",
    )
    args = parser.parse_args(argv)
    root = args.source_root.absolute()
    output = args.output_dir.absolute()
    if not (root / "pytuflow" / "__init__.py").is_file():
        parser.error("--source-root must be a PyTUFLOW checkout")
    if root == output or root in output.parents:
        parser.error("--output-dir must be outside the source checkout")
    if output.exists():
        parser.error("--output-dir must not exist; use a fresh run directory")
    if len(set(args.targets)) != len(args.targets):
        parser.error("--targets must not contain duplicates")
    output.mkdir(parents=True)

    report = {
        "contract": "diagnostics only; not Python runtime or installation acceptance",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "checkout_sha": git_head(root),
        "tool": Path(args.pyright).name,
        "targets": {},
    }
    healthy = True
    for target in args.targets:
        command = [args.pyright, "pytuflow", "--pythonversion", target, "--outputjson"]
        metric, valid = run_command(command, root, output / f"pyright-{target}.json")
        report["targets"][target] = {"source_diagnostics": metric}
        healthy &= valid
        if args.verifytypes:
            command = [
                args.pyright, "--verifytypes", "pytuflow", "--ignoreexternal",
                "--pythonversion", target, "--outputjson",
            ]
            metric, valid = run_command(
                command, root, output / f"verifytypes-{target}.json",
            )
            report["targets"][target]["public_api_types"] = metric
            healthy &= valid

    (output / "summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not healthy:
        print("One or more Pyright invocations failed: inspect local raw reports.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
