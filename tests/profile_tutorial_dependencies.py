"""Profile public tutorial dependency discovery; cProfile timings are NOT speedup evidence.

    py -3.14 tests/profile_tutorial_dependencies.py --bundle E:\public-tutorial --tcf EG16_~s1~_~s2~_002.tcf

Verifies and temporarily extracts the public fixture. Does not execute TUFLOW,
any .bat file, a model solver or user-supplied private input.
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import io
import json
import pstats
import sys
import tempfile
from pathlib import Path

from benchmark_tutorial_dependencies import (
    discover_cases,
    extract_verified,
    measure,
    verify_bundle,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--tcf", required=True, help="Exact public tutorial TCF filename")
    parser.add_argument("--runs", type=int, help="Repeated-combination stress run count")
    parser.add_argument("--functions", type=int, default=35)
    args = parser.parse_args(argv)
    if args.functions < 1 or (args.runs is not None and args.runs < 1):
        parser.error("--functions and --runs must be positive")
    bundle = args.bundle.absolute()
    if not (bundle / "examples.zip").is_file():
        print(json.dumps({"status": "unavailable", "reason": "public tutorial archive not installed"}))
        return 2
    _, baseline = verify_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix="pytuflow-public-profile-", ignore_cleanup_errors=True) as temp:
        root = Path(temp)
        extract_verified(bundle, root)
        cases = discover_cases(root, baseline)
        chosen = [
            (name, flags) for name, flags in cases.items()
            if Path(name).name == args.tcf
        ]
        if len(chosen) != 1:
            parser.error("Select exactly one TCF present in the public baseline")
        name, flags = chosen[0]
        gc.collect()
        profiler = cProfile.Profile()
        profiler.enable()
        result = measure(root / name, flags, requested_runs=args.runs, trials=1)
        profiler.disable()
        # Never represent profiler-instrumented durations as runtime evidence.
        text = io.StringIO()
        pstats.Stats(profiler, stream=text).strip_dirs().sort_stats(
            pstats.SortKey.CUMULATIVE
        ).print_stats(args.functions)
        summary = {
            "status": result["status"],
            "model": result["model"],
            "requested_runs": result["requested_runs"],
            "distinct_complete_flags": result["distinct_complete_flag_signatures"],
            "compiled_tree_status": result["compiled_tree_status"],
            "differences": result["differences_across_trials"],
            "cached_counters": result["modes"]["batch_cached"]["trials_detail"][0]["counters"],
            "profiling_note": "cProfile changes wall time; use separate 3-trial benchmark for performance",
        }
        print(json.dumps(summary, indent=2))
        print(text.getvalue())
        return 0 if result["status"] == "passed_syntactic_parity" else 1


if __name__ == "__main__":
    sys.exit(main())
