"""Read-only, public TUFLOW tutorial differential and warm-cache benchmark.

Usage (Windows Python 3.14, from the PyTUFLOW repository root):
    py -3.14 tests/benchmark_tutorial_dependencies.py --bundle E:\test-data\tuflow\example_input_preflight
    py -3.14 tests/benchmark_tutorial_dependencies.py --bundle ... --tcf EG02_014.tcf --runs 500

No solver or batch file is executed. This measures SYNTACTIC PyTUFLOW
dependency discovery; it does not replace the ryan-tools materialised GIS/
attribute/BC/raster preflight. Private models must never be supplied here.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from pathlib import Path, PurePosixPath
from statistics import median
from time import perf_counter
from zipfile import ZipFile

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import (
    BatchDependencyRun,
    BatchInputCommand,
    BatchInputReference,
)

FLAG = re.compile(r'(?<!\S)-([es]\d)\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE)
TCF_NAME = re.compile(r'([^\s"/\\]+\.tcf)', re.IGNORECASE)
IGNORED = ("set ", "rem ", "@rem ", "::", "echo ", "@echo ")
COUNTERS = (
    "contexts_constructed", "contexts_reused", "commands_constructed",
    "commands_cloned", "command_template_bypasses", "unique_command_templates",
    "compiled_variable_nodes", "compiled_read_nodes", "command_plan_hits",
    "variable_template_clones", "scope_builds", "scope_hits",
    "graph_node_evaluations", "graph_nodes_skipped", "graph_hits",
    "graph_bypasses", "run_state_constructors",
    "relevant_context_signatures",
    "compiled_graph_nodes", "compiled_graph_eligible_reads",
    "compiled_graph_bypassed_reads", "graph_node_lookups",
    "graph_node_fallbacks",
    "cross_run_scope_hits", "cross_run_scope_misses", "translation_hits",
    "translation_misses", "cross_run_reference_hits",
    "cross_run_reference_misses", "cross_run_reference_bypasses",
    "within_run_reference_hits", "unique_reference_signatures",
)
PHASES = (
    "compilation_seconds", "context_construction_seconds",
    "reference_collection_seconds", "database_projection_seconds",
)


def verify_bundle(bundle: Path) -> tuple[dict, dict[str, int]]:
    """Verify checksum, size, all members and traversal safety before extraction."""
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    archive_path = bundle / "examples.zip"
    archive_hash = hashlib.sha256()
    with archive_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            archive_hash.update(chunk)
    if archive_hash.hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Tutorial archive SHA-256 mismatch")
    expected = {row["path"]: row for row in manifest["files"]}
    if len(expected) != len(manifest["files"]) or not expected:
        raise ValueError("Duplicate or empty tutorial manifest")
    with ZipFile(archive_path) as archive:
        actual = archive.infolist()
        if len(actual) != len(expected) or {row.filename for row in actual} != set(expected):
            raise ValueError("Archive member list differs from manifest")
        for item in actual:
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute() or "\\" in item.filename or ":" in item.filename
                or any(part in ("", ".", "..") for part in path.parts)
                or item.is_dir() or ((item.external_attr >> 16) & 0o170000) == 0o120000
            ):
                raise ValueError("Unsafe tutorial archive entry")
            declared = expected[item.filename]
            digest = hashlib.sha256()
            size = 0
            with archive.open(item) as data:
                for block in iter(lambda: data.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
            if size != declared["size"] or digest.hexdigest() != declared["sha256"]:
                raise ValueError("Tutorial archive member checksum or size mismatch")
    with (bundle / "baseline.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    baseline = {row["tcf"]: int(row["runs"]) for row in rows}
    if len(baseline) != len(rows) or not baseline:
        raise ValueError("Duplicate or empty tutorial baseline")
    return manifest, baseline


def extract_verified(bundle: Path, destination: Path) -> None:
    """Only invoke after verification; extract safe members without extractall()."""
    with ZipFile(bundle / "examples.zip") as archive:
        for item in archive.infolist():
            target = destination.joinpath(*PurePosixPath(item.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as reader, target.open("xb") as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(chunk)


def extract_flag_pairs(line: str) -> tuple[tuple[str, str], ...]:
    """Read flag literals from a launcher line; never execute the launcher."""
    entries = [(m[1].lower(), m[2] if m[2] is not None else m[3]) for m in FLAG.finditer(line)]
    if len({name for name, _ in entries}) != len(entries):
        raise ValueError("Duplicate simulation flag in tutorial launcher")
    return tuple(entries)


def discover_cases(root: Path, baseline: dict[str, int]) -> dict[str, tuple[str, ...]]:
    """Enumerate batch-described runs and unparameterised standalone TCFs."""
    found: dict[str, list[str]] = {}
    for launcher in sorted((root / "runs").glob("*.bat")):
        for line in launcher.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.lower().startswith(IGNORED):
                continue
            match = TCF_NAME.search(line)
            if not match:
                continue
            rel = "runs/" + match[1]
            if rel not in baseline:
                raise ValueError("Launcher references a TCF absent from the baseline")
            pairs = extract_flag_pairs(line)
            flags = " ".join(f"-{key} {value}" for key, value in pairs)
            if flags not in found.setdefault(rel, []):
                found[rel].append(flags)
    for rel in baseline:
        if rel not in found:
            if re.search(r"~[es]\d~", Path(rel).name, re.IGNORECASE):
                raise ValueError("Unexpanded parameterised TCF has no launcher combination")
            found[rel] = [""]
        if not (root / rel).is_file():
            raise ValueError("TCF named in baseline is missing from verified archive")
        if len(found[rel]) != baseline[rel]:
            raise ValueError(
                f"Tutorial run-count discrepancy for {Path(rel).name}: "
                f"found {len(found[rel])}, expected {baseline[rel]}"
            )
    if set(found) != set(baseline):
        raise ValueError("Tutorial TCF inventory differs from baseline")
    return {key: tuple(found[key]) for key in sorted(found)}


def canonical(value: object) -> object:
    """Compare EVERY dataclass field, including UUID, owner, activation order and flags."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in value.items()}
    return value


def run_identity(case: BatchDependencyRun) -> dict:
    return {
        "error": case.error,
        "ordered_inputs": canonical(case.ordered_inputs),
        "input_references": canonical(case.input_references),
        "file_references": canonical(case.file_references),
        "database_activations": canonical(case.database_activations),
        "database_sources": canonical(case.database_sources),
    }


def compare_runs(reference: tuple[BatchDependencyRun, ...],
                 candidate: tuple[BatchDependencyRun, ...]) -> dict[str, int]:
    """Multiset diff retains duplicate commands and disallows partial-error passes."""
    missing = extra = 0
    if len(reference) != len(candidate):
        return {"missing": len(reference), "extra": len(candidate)}
    for expected, received in zip(reference, candidate, strict=True):
        if expected.index != received.index or expected.flags != received.flags:
            missing += 1
            extra += 1
            continue
        left = run_identity(expected)
        right = run_identity(received)
        for key in left:
            if key == "error":
                if left[key] != right[key]:
                    missing += 1
                    extra += 1
                continue
            a = Counter(json.dumps(item, sort_keys=True) for item in left[key])
            b = Counter(json.dumps(item, sort_keys=True) for item in right[key])
            missing += sum((a - b).values())
            extra += sum((b - a).values())
            # A pure reorder is still a parity failure, even when
            # both multisets contain exactly the same identities.
            if a == b and left[key] != right[key]:
                missing += 1
                extra += 1
    return {"missing": missing, "extra": extra}


@contextmanager
def sampled_rss():
    """Optional ~20 ms sampled RSS, explicitly NOT an exact allocation peak."""
    try:
        import psutil  # optional; absence must be visible
    except ImportError:
        yield {"bytes": None, "method": "unavailable (psutil not installed)"}
        return
    proc = psutil.Process()
    stop = threading.Event()
    reading = {"bytes": proc.memory_info().rss, "method": "psutil RSS sampled ~20 ms"}
    def poll():
        while not stop.wait(0.02):
            reading["bytes"] = max(reading["bytes"], proc.memory_info().rss)
    worker = threading.Thread(target=poll, daemon=True)
    worker.start()
    try:
        yield reading
    finally:
        stop.set()
        worker.join()
        reading["bytes"] = max(reading["bytes"], proc.memory_info().rss)


def individual(model: TCF, flags: tuple[str, ...]) -> tuple[tuple[BatchDependencyRun, ...], dict]:
    results: list[BatchDependencyRun] = []
    phases = {key: 0.0 for key in PHASES}
    started = perf_counter()
    for index, flag in enumerate(flags):
        try:
            t = perf_counter()
            run = model.context(flag, file_resolution="deferred")
            phases["context_construction_seconds"] += perf_counter() - t
            t = perf_counter()
            inputs = tuple(run.find_input())
            ordered = tuple(
                BatchInputCommand(str(inp.uuid), ordinal, inp._command.parent,
                                  inp.line_number, str(inp.lhs), str(inp._command.original_text))
                for ordinal, inp in enumerate(inputs)
            )
            input_refs = tuple(
                BatchInputReference(owner.input_uuid, owner.command_index,
                                    owner.owner_control_file, owner.line_number, ref)
                for owner, inp in zip(ordered, inputs, strict=True)
                for ref in inp.file_references
            )
            refs = tuple(record.reference for record in input_refs)
            phases["reference_collection_seconds"] += perf_counter() - t
            t = perf_counter()
            activations = run.deferred_database_activations()
            sources = tuple(
                source for activation in activations
                for source in run.deferred_database_sources_for_activation(activation.input_uuid)
            )
            phases["database_projection_seconds"] += perf_counter() - t
            results.append(BatchDependencyRun(
                index, flag, refs, sources, activations, None, input_refs, ordered
            ))
        except Exception as exc:
            results.append(BatchDependencyRun(
                index, flag, (), (), (), f"{type(exc).__name__}: {exc}"
            ))
    return tuple(results), {
        "total_seconds": perf_counter() - started,
        "phases_seconds": phases,
        "counters": {},
    }


def batch(model: TCF, flags: tuple[str, ...], *, cached: bool):
    started = perf_counter()
    report = model.collect_batch_dependencies(flags, cache_scopes=cached)
    return report.runs, {
        "total_seconds": perf_counter() - started,
        "internal_total_seconds": report.elapsed_seconds,
        "phases_seconds": {key: getattr(report, key, None) for key in PHASES},
        "counters": {key: getattr(report, key, None) for key in COUNTERS},
    }


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).absolute().parent.parent,
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def measure(tcf: Path, original_flags: tuple[str, ...], *,
            requested_runs: int | None, trials: int) -> dict:
    if requested_runs is not None and requested_runs < 1:
        raise ValueError("--runs must be positive")
    flags = (
        original_flags
        if requested_runs is None else
        tuple(original_flags[i % len(original_flags)] for i in range(requested_runs))
    )
    modes = ("individual_deferred", "batch_uncached", "batch_cached")
    results: dict[str, list[dict]] = {mode: [] for mode in modes}
    differences: dict[str, dict[str, int]] = {}
    errors: dict[str, int] = {}
    error_totals: Counter[str] = Counter()
    failure_examples: dict[str, list[dict[str, object]]] = {}
    observed: tuple[BatchDependencyRun, ...] = ()
    gc.collect()
    initial = perf_counter()
    model = TCF(tcf)
    parse_seconds = perf_counter() - initial
    for trial in range(trials):
        order = modes[trial % len(modes):] + modes[:trial % len(modes)]
        projections = {}
        for mode in order:
            with sampled_rss() as memory:
                if mode == "individual_deferred":
                    projection, stats = individual(model, flags)
                else:
                    projection, stats = batch(model, flags, cached=(mode == "batch_cached"))
            stats["sampled_peak_rss"] = memory.copy()
            projections[mode] = projection
            results[mode].append(stats)
        baseline = projections["individual_deferred"]
        observed = baseline
        for mode in modes:
            errors[mode] = sum(case.error is not None for case in projections[mode])
            error_totals[mode] += errors[mode]
            if errors[mode]:
                failure_examples.setdefault(mode, [])
                failure_examples[mode].extend(
                    {"index": case.index, "flags": case.flags,
                     "error": case.error.replace(str(tcf.parent), "<tutorial>")
                     if case.error else None}
                    for case in projections[mode]
                    if case.error is not None
                )
                failure_examples[mode] = failure_examples[mode][:10]
            diff = compare_runs(baseline, projections[mode])
            previous = differences.get(mode, {"missing": 0, "extra": 0})
            differences[mode] = {
                "missing": previous["missing"] + diff["missing"],
                "extra": previous["extra"] + diff["extra"],
            }
    unresolved = sum(
        bool(ref.unresolved_variables)
        for case in observed for ref in case.file_references
    )
    valid = (unresolved == 0
             and all(count == 0 for count in error_totals.values())
             and all(
                 difference == {"missing": 0, "extra": 0}
                 for difference in differences.values()
             ))
    primary_paths = {
        str(ref.path_pattern)
        for case in observed for ref in case.file_references
    }
    secondary_paths = {
        str(source.path_pattern)
        for case in observed for source in case.database_sources
    }
    return {
        "model": tcf.name,
        "status": "passed_syntactic_parity" if valid else "failed_or_unsupported",
        "requested_runs": len(flags),
        "original_documented_combinations": len(original_flags),
        "distinct_complete_flag_signatures": len(set(flags)),
        "workload_type": "documented_combinations" if requested_runs is None
                         else "repeated-combination throughput stress test",
        "parse_seconds": parse_seconds,
        "trials": trials,
        "differences_across_trials": differences,
        "failed_runs_last_trial": errors,
        "failed_runs_across_trials": dict(error_totals),
        "error_samples": failure_examples,
        "per_run_reference_total": sum(len(case.file_references) for case in observed),
        "per_run_secondary_source_total": sum(len(case.database_sources) for case in observed),
        "unresolved_primary_references": unresolved,
        "requires_attribute_scan": sum(
            ref.requires_attribute_scan
            for case in observed for ref in case.file_references
        ),
        "requires_database_scan": sum(
            ref.requires_database_scan
            for case in observed for ref in case.file_references
        ),
        "requires_raster_metadata_scan": sum(
            ref.requires_raster_metadata_scan
            for case in observed for ref in case.file_references
        ),
        "physically_unique_paths": None,
        "unique_lexical_primary_paths": len(primary_paths),
        "unique_lexical_primary_and_secondary_paths": len(primary_paths | secondary_paths),
        "note_unique_paths": "Lexical syntactic only; physical aliases and GIS materialisation not checked",
        "modes": {
            mode: {
                "total_seconds": {
                    "trials": [row["total_seconds"] for row in rows],
                    "median": median(row["total_seconds"] for row in rows),
                },
                "trials_detail": rows,
            } for mode, rows in results.items()
        },
        "compiled_tree_status": (
            "compiled control tree instrumented in cached batch"
            if any(
                row["counters"].get("compiled_graph_nodes")
                for row in results["batch_cached"]
            )
            else "not available on checked-out parser source"
        ),
        "materialised_parity_status": "not evaluated by this syntactic harness",
        "distinct_relevant_context_signatures": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path,
                        help="Existing public tutorial bundle directory (examples.zip/manifest.json/baseline.csv)")
    parser.add_argument("--tcf", action="append",
                        help="Public TCF filename (repeatable); default: all 161 TCFs")
    parser.add_argument("--runs", type=int, help="Repeat combinations to this run count PER selected TCF")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--output", type=Path, help="Optional JSON report outside the data checkout")
    options = parser.parse_args(argv)
    if options.trials < 1:
        parser.error("--trials must be positive")
    bundle = options.bundle.absolute()
    if options.output and options.output.absolute().is_relative_to(bundle):
        parser.error("Reports must not be written into the public data checkout")
    # An absent optional fixture is UNAVAILABLE rather than a fabricated pass.
    if not (bundle / "examples.zip").is_file():
        print(json.dumps({"status": "unavailable", "reason": "public tutorial archive not installed"}))
        return 2
    manifest, baseline = verify_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix="pytuflow-public-tutorial-", ignore_cleanup_errors=True) as temp:
        root = Path(temp)
        extract_verified(bundle, root)
        cases = discover_cases(root, baseline)
        if options.tcf:
            requested = set(options.tcf)
            cases = {name: combinations for name, combinations in cases.items()
                     if Path(name).name in requested}
            if requested != {Path(name).name for name in cases}:
                raise ValueError("Unknown public tutorial TCF selection")
        records = []
        for name, combinations in cases.items():
            try:
                record = measure(root / name, combinations,
                                 requested_runs=options.runs, trials=options.trials)
            except Exception as exc:
                # No failed/unsupported case may disappear from the report.
                message = f"{type(exc).__name__}: {exc}"
                record = {"model": Path(name).name, "status": "failed_or_unsupported",
                          "reason": message.replace(str(root), "<tutorial>")}
            records.append(record)
        gc.collect()
    complete = bool(records) and all(r["status"] == "passed_syntactic_parity" for r in records)
    summary = {
        "status": "passed_syntactic_parity" if complete else "failed_or_unsupported",
        "dataset": "public TUFLOW tutorial only",
        "archive_sha256": manifest["archive_sha256"],
        "verified_archive_members": len(manifest["files"]),
        "baseline_models": len(baseline),
        "baseline_runs": sum(baseline.values()),
        "tested_models": len(records),
        "source_sha": _git_sha(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "trials": options.trials,
        "gc_policy": "gc.collect() before model parse; normal GC during trials",
        "note": "No solver, persistent resource cache, private model or full GIS materialisation",
        "results": records,
    }
    rendered = json.dumps(summary, indent=2, default=str)
    if options.output:
        path = options.output.absolute()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Report: {path}")
    else:
        print(rendered)
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
