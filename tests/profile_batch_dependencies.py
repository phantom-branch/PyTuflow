"""Profile parsed-TCF deferred dependency work without launching TUFLOW.

    python tests/profile_batch_dependencies.py --runs 120 --static-inputs 20

This intentionally profiles all three parity-equivalent modes together to
identify CPU hot paths. Timings under cProfile are not speedup evidence.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats

from benchmark_batch_dependencies import benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=120)
    parser.add_argument('--static-inputs', type=int, default=20)
    parser.add_argument('--functions', type=int, default=30)
    args = parser.parse_args()
    profiler = cProfile.Profile()
    profiler.enable()
    outcome = benchmark(args.runs, trials=1, static_inputs=args.static_inputs)
    profiler.disable()

    print('Exact reference parity:', outcome['parity'])
    print('Cache counters:', outcome['cached_context_counters'])
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).strip_dirs().sort_stats(
        pstats.SortKey.CUMULATIVE
    ).print_stats(args.functions)
    print(output.getvalue())


if __name__ == '__main__':
    main()
