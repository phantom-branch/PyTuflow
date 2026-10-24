"""Profile SYNTHETIC parsed-TCF work; never use these timings as native speedups.

    python tests/profile_batch_dependencies.py --runs 120 --static-inputs 20

Add --output with a NEW directory outside the repository to retain PRIVATE raw
pstats and complete self/cumulative/caller/callee tables. All three existing
parity-equivalent modes are profiled together. The profile also includes fixture
creation, parsing, parity assertions and cleanup; it does not isolate graph
policy or exclusive control-file phases. The benchmark's mode timers have a
different boundary. No native model inputs or solver are used by this script.
"""

import argparse
import io
import pstats
from pathlib import Path

from profile_capture import capture_profile


def positive_integer(value: str) -> int:
    """Validate positive CLI counts before importing or running the benchmark."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def nonnegative_integer(value: str) -> int:
    """Validate synthetic input counts before invoking the workload."""
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError('must be a nonnegative integer')
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=positive_integer, default=120)
    parser.add_argument('--static-inputs', type=nonnegative_integer, default=20)
    parser.add_argument('--functions', type=positive_integer, default=30)
    parser.add_argument('--output', type=Path, help='New PRIVATE report directory outside the repository')
    args = parser.parse_args()
    # Keep --help and evidence-helper tests independent of GIS/package imports.
    from benchmark_batch_dependencies import benchmark

    outcome, profiler = capture_profile(
        lambda: benchmark(args.runs, trials=1, static_inputs=args.static_inputs),
        output_dir=args.output,
        provenance={
            'workload': 'existing synthetic three-mode benchmark',
            'runs': args.runs,
            'static_inputs': args.static_inputs,
            'graph_policy': 'existing benchmark defaults; not a graph comparison',
            'source_revision': 'not verified; record checkout identity separately',
        },
    )
    print('Exact reference parity:', outcome['parity'])
    print('Cache counters:', outcome['cached_context_counters'])
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).sort_stats(
        pstats.SortKey.CUMULATIVE,
    ).print_stats(args.functions)
    print(output.getvalue())
    if args.output is not None:
        print('PRIVATE profile evidence:', args.output.absolute())


if __name__ == '__main__':
    main()
