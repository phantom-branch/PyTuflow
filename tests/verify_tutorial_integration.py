"""P4 same-head differential on the pinned, verified PUBLIC TUFLOW tutorial.

Read-only parser validation, not a simulation or materialised GIS/BC check.
Usage:
  python tests/verify_tutorial_integration.py --bundle PATH [--trials 1]
  python tests/verify_tutorial_integration.py --bundle PATH --tcf EG16_~s1~_~s2~_002.tcf --trials 3

No source datasets, paths or user model content are included in the report.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

from pytuflow import TCF

from benchmark_tutorial_dependencies import (
    compare_runs,
    discover_cases,
    extract_verified,
    individual,
    verify_bundle,
)

MODES = (
    "individual_deferred",
    "batch_uncached",
    "batch_cached_no_graph",
    "batch_compiled",
)


def inspect_model(tcf: Path, flags: tuple[str | dict[str, str], ...], trials: int) -> dict:
    """Compare all immutable per-run records for four same-head modes."""
    source = TCF(tcf)
    sample: dict[str, list[dict]] = {mode: [] for mode in MODES}
    counts = {"missing": 0, "extra": 0, "failed_runs": 0, "unresolved": 0}
    error_types: set[str] = set()
    for trial in range(trials):
        mode_order = MODES[trial % len(MODES):] + MODES[:trial % len(MODES)]
        results = {}
        for mode in mode_order:
            started = perf_counter()
            if mode == "individual_deferred":
                projections, stat = individual(source, flags)
                measurements = {"total_seconds": perf_counter() - started}
                measurements.update(stat)
                run_records = projections
            else:
                options = {
                    "batch_uncached": {"cache_scopes": False},
                    "batch_cached_no_graph": {"cache_scopes": True, "compile_tree": False},
                    "batch_compiled": {"cache_scopes": True, "compile_tree": True},
                }[mode]
                result = source.collect_batch_dependencies(flags, **options)
                run_records = result.runs
                measurements = {
                    "total_seconds": perf_counter() - started,
                    "internal_seconds": result.elapsed_seconds,
                    "compiled_graph_nodes": result.compiled_graph_nodes,
                    "compiled_graph_eligible_reads": result.compiled_graph_eligible_reads,
                    "compiled_graph_bypassed_reads": result.compiled_graph_bypassed_reads,
                    "graph_node_lookups": result.graph_node_lookups,
                    "graph_node_fallbacks": result.graph_node_fallbacks,
                    "input_runstates_constructed": result.input_runstates_constructed,
                    "input_runstates_elided": result.input_runstates_elided,
                    "compiled_input_group_candidates": result.compiled_input_group_candidates,
                    "input_group_bypass_reasons": result.input_group_bypass_reasons,
                    "input_group_cache_bypass_reason": result.input_group_cache_bypass_reason,
                    "reusable_input_groups": result.reusable_input_groups,
                    "input_group_fallbacks": result.input_group_fallbacks,
                    "input_group_state_reuses": result.input_group_state_reuses,
                    "failed_run_input_runstates_constructed": result.failed_run_input_runstates_constructed,
                    "failed_run_input_runstates_elided": result.failed_run_input_runstates_elided,
                    "input_group_costs_seconds": {
                        "key": result.input_group_key_seconds,
                        "clone": result.input_group_clone_seconds,
                        "certification": result.input_group_certification_seconds,
                        "construction": result.input_state_construction_seconds,
                    },
                    "invariant_projection_reuses": result.invariant_projection_reuses,
                    "contexts_constructed": result.contexts_constructed,
                    "contexts_reused": result.contexts_reused,
                    "commands_constructed": result.commands_constructed,
                    "commands_cloned": result.commands_cloned,
                    "command_plan_hits": result.command_plan_hits,
                    "compilation_seconds": result.compilation_seconds,
                    "context_construction_seconds": result.context_construction_seconds,
                    "reference_collection_seconds": result.reference_collection_seconds,
                    "database_projection_seconds": result.database_projection_seconds,
                }
            results[mode] = run_records
            sample[mode].append(measurements)

        expected = results["individual_deferred"]
        for mode in MODES:
            projection = results[mode]
            difference = compare_runs(expected, projection)
            counts["missing"] += difference["missing"]
            counts["extra"] += difference["extra"]
            for run in projection:
                if run.error:
                    counts["failed_runs"] += 1
                    error_types.add(run.error.split(":", 1)[0])
                counts["unresolved"] += sum(
                    bool(ref.unresolved_variables) for ref in run.file_references
                )
    passed = all(value == 0 for value in counts.values())
    return {
        "model": tcf.name,  # public model basename only
        "status": "passed_syntactic_parity" if passed else "failed_or_unsupported",
        "documented_run_combinations": len(flags),
        "distinct_complete_flag_signatures": len({
            tuple(sorted(flag.items())) if isinstance(flag, dict) else flag
            for flag in flags
        }),
        "trials": trials,
        "counts": counts,
        "error_types": sorted(error_types),
        "modes": {
            name: {
                "wall_seconds_by_trial": [round(v["total_seconds"], 6) for v in samples],
                "median_wall_seconds": median(v["total_seconds"] for v in samples),
                "last_trial_counters": samples[-1],
            }
            for name, samples in sample.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--tcf", action="append", help="Public tutorial TCF basename (repeatable)")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be >= 1")
    bundle = args.bundle.absolute()
    if args.output is not None and args.output.absolute().is_relative_to(bundle):
        parser.error("--output cannot be inside the public fixture checkout")
    if not (bundle / "examples.zip").is_file():
        print(json.dumps({"status": "unavailable", "reason": "public tutorial bundle absent"}))
        return 2
    manifest, baseline = verify_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix="pytuflow-p4-public-") as directory:
        root = Path(directory)
        extract_verified(bundle, root)
        cases = discover_cases(root, baseline)
        if args.tcf is not None:
            names = set(args.tcf)
            cases = {path: flags for path, flags in cases.items()
                     if Path(path).name in names}
            if names != {Path(path).name for path in cases}:
                raise ValueError("Requested public TCF is absent from verified bundle")
        records = []
        for name, flags in cases.items():
            try:
                record = inspect_model(root / name, flags, args.trials)
            except Exception as exc:
                record = {
                    "model": Path(name).name,
                    "status": "failed_or_unsupported",
                    "error_type": type(exc).__name__,
                }
            records.append(record)
    totals = {
        key: sum(rec.get("counts", {}).get(key, 0) for rec in records)
        for key in ("missing", "extra", "failed_runs", "unresolved")
    }
    successful = sum(rec["status"] == "passed_syntactic_parity" for rec in records)
    accepted = bool(records) and successful == len(records) and not any(totals.values())
    summary = {
        "status": "passed_syntactic_parity" if accepted else "failed_or_unsupported",
        "scope": "public tutorial parser only; no GIS/BC/raster materialisation",
        "archive_sha256": manifest["archive_sha256"],
        "public_member_count": len(manifest["files"]),
        "baseline_tcf_count": len(baseline),
        "baseline_run_count": sum(baseline.values()),
        "tested_tcfs": len(records),
        "accepted_tcfs": successful,
        "tested_documented_runs": sum(rec.get("documented_run_combinations", 0) for rec in records),
        "trials": args.trials,
        "modes": list(MODES),
        "counts": totals,
        "python_version": platform.python_version(),
        "results": records,
    }
    if args.output:
        target = args.output.absolute()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": summary["status"],
        "tested_tcfs": summary["tested_tcfs"],
        "accepted_tcfs": summary["accepted_tcfs"],
        "tested_documented_runs": summary["tested_documented_runs"],
        "trials": args.trials,
        "counts": totals,
        "output": str(args.output) if args.output else None,
    }))
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
