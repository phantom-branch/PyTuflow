"""Read-only, one-process dependency benchmark for a local TUFLOW model.

Runs exactly one requested producer mode. Launch a FRESH Python process for
each timing sample and alternate mode order externally (ABBA/BAAB). Prints
aggregates only; never prints or saves model paths, run flags or records.

Examples (from repo root):
  python tests/benchmark_scope_driven_dependencies.py --tcf MODEL.tcf --flags-file flags.json --mode scope --verify
  python tests/benchmark_scope_driven_dependencies.py --tcf MODEL.tcf --flags-file flags.json --mode fragments --verify
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from pytuflow import TCF
from pytuflow._tmf.scope_driven_dependencies import collect_scope_dependencies

MODES = ("scope", "fragments", "batch-graph-off", "batch-uncached")


def _evaluate(model: TCF, flags: list[str | dict[str, str]], mode: str):
    if mode == "scope":
        return collect_scope_dependencies(model, flags)
    if mode == "fragments":
        return model.collect_file_dependencies(flags)
    if mode == "batch-graph-off":
        return model.collect_batch_dependencies(flags, compile_tree=False)
    if mode == "batch-uncached":
        return model.collect_batch_dependencies(
            flags, cache_scopes=False, compile_tree=False
        )
    raise ValueError("Unknown mode")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tcf", type=Path, required=True)
    parser.add_argument("--flags-file", type=Path, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Compare full per-run public records with fragment evaluator after timing",
    )
    args = parser.parse_args()
    flags = json.loads(args.flags_file.read_text(encoding="utf-8"))
    if not isinstance(flags, list) or not all(
        isinstance(item, str)
        or (
            isinstance(item, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in item.items())
        )
        for item in flags
    ):
        parser.error("Expected JSON array of flag strings or string-to-string dictionaries")

    parse_started = perf_counter()
    model = TCF(args.tcf)
    parse_seconds = perf_counter() - parse_started

    collect_started = perf_counter()
    result = _evaluate(model, flags, args.mode)
    collect_seconds = perf_counter() - collect_started
    report: dict[str, str | bool | int | float | list[int]] = {
        "mode": args.mode,
        "parse_seconds": round(parse_seconds, 6),
        "collect_seconds": round(collect_seconds, 6),
        "run_count": len(result.runs),
        "failed_runs": sum(run.error is not None for run in result.runs),
        "file_references": sum(len(run.file_references) for run in result.runs),
        "source_records": sum(len(run.database_sources) for run in result.runs),
        "activations": sum(len(run.database_activations) for run in result.runs),
        "input_references": sum(len(run.input_references) for run in result.runs),
        "ordered_inputs": sum(len(run.ordered_inputs) for run in result.runs),
    }
    if args.verify:
        reference = (
            result if args.mode == "fragments"
            else model.collect_file_dependencies(flags)
        )
        differences = [
            i
            for i, (actual, expected) in enumerate(
                zip(result.runs, reference.runs, strict=True)
            )
            if actual != expected
        ]
        report["parity"] = not differences
        report["different_run_indices"] = differences
    print(json.dumps(report, sort_keys=True))
    return 1 if report.get("parity") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
