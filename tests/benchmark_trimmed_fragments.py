"""Uninstrumented single-process producer sample for trimmed fragment PR.

Run each invocation in a fresh Python process. Compare with the *same script*
at the pinned original master SHA, using a frozen external JSON flag array.
The script never prints file paths, run flag values or record contents.

Example:
    python tests/benchmark_trimmed_fragments.py --tcf MODEL.tcf --flags-file PRIVATE.json --mode fragments --verify
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from pytuflow import TCF


def evaluate(model: TCF, flags: list[str | dict[str, str]], mode: str):
    if mode == "fragments":
        return model.collect_file_dependencies(flags)
    if mode == "batch-graph-off":
        return model.collect_batch_dependencies(flags, compile_tree=False)
    if mode == "batch-uncached":
        return model.collect_batch_dependencies(
            flags, cache_scopes=False, compile_tree=False
        )
    raise ValueError("Unsupported evaluator")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tcf", type=Path, required=True)
    parser.add_argument("--flags-file", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("fragments", "batch-graph-off", "batch-uncached"),
        default="fragments",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Compare complete run records with uncached reference after timing",
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
        parser.error(
            "Expected an ordered JSON array of flag strings or string dictionaries"
        )

    started = perf_counter()
    model = TCF(args.tcf)
    parse_seconds = perf_counter() - started
    started = perf_counter()
    result = evaluate(model, flags, args.mode)
    collect_seconds = perf_counter() - started
    totals = {
        "mode": args.mode,
        "parse_seconds": round(parse_seconds, 6),
        "collect_seconds": round(collect_seconds, 6),
        "runs": len(result.runs),
        "failures": sum(run.error is not None for run in result.runs),
        "fallback_runs": getattr(result, "fallback_runs", 0),
        "fragment_evaluations": getattr(result, "fragment_evaluations", None),
        "fragment_reuses": getattr(result, "fragment_reuses", None),
        "references": sum(len(run.file_references) for run in result.runs),
        "input_references": sum(len(run.input_references) for run in result.runs),
        "commands": sum(len(run.ordered_inputs) for run in result.runs),
        "activations": sum(len(run.database_activations) for run in result.runs),
        "sources": sum(len(run.database_sources) for run in result.runs),
    }
    if args.verify:
        expected = model.collect_batch_dependencies(
            flags, cache_scopes=False, compile_tree=False
        )
        mismatches = [
            index
            for index, (candidate, reference) in enumerate(
                zip(result.runs, expected.runs, strict=True)
            )
            if candidate != reference
        ]
        totals["parity"] = not mismatches
        totals["difference_count"] = len(mismatches)
    print(json.dumps(totals, sort_keys=True))
    return 1 if totals.get("parity") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
