"""Manual CPU benchmark for read-only, same-TCF deferred dependency collection.

Run from the repository root (no TUFLOW executable or external project files):
    python tests/benchmark_batch_dependencies.py --runs 500 --trials 3

This intentionally exercises distinct event flags, unlike a duplicate-flag
cache benchmark. It compares equivalent syntactic references and database
activations before reporting timings. Initial TCF parsing and package import
are excluded from the timing of each mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from pytuflow import TCF


def _baseline(model: TCF, flags: tuple[str, ...]):
    """Collect the same public fields as the batch API, without memoisation."""
    results = []
    start = perf_counter()
    for flag in flags:
        run = model.context(flag, file_resolution='deferred')
        refs = tuple(ref for inp in run.find_input() for ref in inp.file_references)
        activations = run.deferred_database_activations()
        sources = tuple(
            source
            for activation in activations
            for source in run.deferred_database_sources_for_activation(activation.input_uuid)
        )
        results.append((refs, activations, sources))
    return results, perf_counter() - start


def _batch(model: TCF, flags: tuple[str, ...], *, cache_scopes: bool):
    report = model.collect_batch_dependencies(flags, cache_scopes=cache_scopes)
    assert report.passed, [item.error for item in report.runs if item.error]
    return [
        (item.file_references, item.database_activations, item.database_sources)
        for item in report.runs
    ], report


def benchmark(runs: int, trials: int, static_inputs: int = 0) -> dict[str, object]:
    if runs < 1 or trials < 1 or static_inputs < 0:
        raise ValueError('runs/trials must be positive and static_inputs nonnegative')
    with TemporaryDirectory(prefix='pytuflow-batch-benchmark-') as directory:
        tcf_file = Path(directory) / 'ensemble.tcf'
        tcf_file.write_text(
            'Read GRID Zpts == grids/terrain.tif\n'
            'Read GIS Code == gis/2d_code_001.shp\n'
            'IF Scenario == DEV\n'
            '    Read GIS Mat == gis/2d_mat_DEV.gpkg >> 2d_mat_DEV\n'
            'ELSE\n'
            '    Read GIS Mat == gis/2d_mat_EXG.gpkg >> 2d_mat_EXG\n'
            'END IF\n' + ''.join(
                f'Read GIS Code == gis/static_{n:03d}.shp\n' for n in range(static_inputs)
            ),
            encoding='utf-8',
        )
        parsing = perf_counter()
        model = TCF(tcf_file)
        parse_seconds = perf_counter() - parsing

        # Every run has distinct e1 flags, even where its files are static.
        # A cache keyed to the complete flag string cannot accelerate this.
        flags = tuple(
            f'-s1 {"DEV" if i % 2 else "EXG"} -e1 TEST{i:05d}'
            for i in range(runs)
        )
        timings: dict[str, list[float]] = {
            'individual': [], 'batch_uncached': [], 'batch_cached': [],
        }
        counts: dict[str, int] = {}
        for trial in range(trials):
            # Rotate the order to reduce simple warm-cache order bias.
            order = ('individual', 'batch_uncached', 'batch_cached')
            order = order[trial % len(order):] + order[:trial % len(order)]
            baselines: dict[str, list[tuple]] = {}
            for mode in order:
                if mode == 'individual':
                    values, elapsed = _baseline(model, flags)
                else:
                    values, report = _batch(model, flags, cache_scopes=(mode == 'batch_cached'))
                    elapsed = report.elapsed_seconds
                    if mode == 'batch_cached':
                        counts = {
                            'scope_builds': report.scope_builds,
                            'scope_hits': report.scope_hits,
                            'translation_hits': report.translation_hits,
                            'translation_misses': report.translation_misses,
                            'contexts_constructed': report.contexts_constructed,
                            'contexts_reused': report.contexts_reused,
                            'cross_run_scope_hits': report.cross_run_scope_hits,
                            'cross_run_scope_misses': report.cross_run_scope_misses,
                            'cross_run_reference_hits': report.cross_run_reference_hits,
                            'cross_run_reference_misses': report.cross_run_reference_misses,
                        }
                baselines[mode] = values
                timings[mode].append(elapsed)
            assert baselines['individual'] == baselines['batch_uncached']
            assert baselines['individual'] == baselines['batch_cached'], (
                'Batch dependencies differ from individual deferred contexts'
            )
        return {
            'runs': runs,
            'trials': trials,
            'static_inputs': static_inputs,
            'parse_seconds': parse_seconds,
            'storage': 'local temporary directory, syntactic references only',
            'note': 'No physical GIS/file materialisation; do not claim end-to-end preflight speedup',
            'timings_seconds': {mode: {'trials': values, 'median': median(values)}
                                for mode, values in timings.items()},
            'cached_context_counters': counts,
            'parity': 'exact syntactic identity across tested modes',
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=500)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--static-inputs', type=int, default=0)
    options = parser.parse_args()
    print(json.dumps(benchmark(options.runs, options.trials, options.static_inputs), indent=2))
