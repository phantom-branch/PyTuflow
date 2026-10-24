"""Retain complete, PRIVATE cProfile evidence for synchronous diagnostic work.

This helper is test/developer tooling, not a native benchmark or a sanitiser.
The action must consume any lazy work inside its call. Reports retain full
source paths; never publish captures made with private model inputs.
"""

import cProfile
import json
import platform
import pstats
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from time import perf_counter


def capture_profile[T](
    action: Callable[[], T],
    *,
    output_dir: Path | None = None,
    provenance: dict[str, object] | None = None,
) -> tuple[T, cProfile.Profile]:
    """Profile one synchronous action, saving full evidence even if it raises.

    Output must be a new directory outside this repository. A supplied provenance
    mapping is retained as caller-provided context, not verified source identity.
    An existing profiling hook is never replaced. Returned iterators are rejected
    rather than presenting generator creation as a profile of generator work.
    """
    if (sys.getprofile() is not None
            or sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) is not None):
        raise RuntimeError('An existing profiling hook is active')
    destination = output_dir.absolute() if output_dir is not None else None
    metadata: dict[str, object] = {
        'schema_version': 1,
        'reports_complete': False,
        'action_returned': False,
        'accepted_for_benchmark': False,
        'privacy': 'PRIVATE: full source paths and caller information are retained',
        'python_version': sys.version,
        'platform': platform.system(),
        'machine': platform.machine(),
        'thread_scope': 'calling thread only',
        'provenance_verification': 'caller supplied; not verified by this helper',
        'provenance': dict(provenance or {}),
        'timing_note': 'Instrumented diagnostic time; not a speedup measurement',
        'self_time_note': 'Function self time excludes profiled subcalls',
        'cumulative_time_note': 'Inclusive function/caller times overlap; do not sum',
    }
    # Validate metadata before creating files or invoking the workload.
    initial_metadata = json.dumps(metadata, indent=2, allow_nan=False)
    if destination is not None:
        # Physical containment is intentional: a linked report directory must
        # not put private artifacts inside the source checkout.
        repository = Path(__file__).resolve().parents[1]
        if destination.resolve().is_relative_to(repository):
            raise ValueError('Profile output must be outside the source repository')
        destination.mkdir(parents=True, exist_ok=False)
        (destination / 'metadata.json').write_text(initial_metadata + '\n', encoding='utf-8')

    profiler = cProfile.Profile()
    failure: BaseException | None = None
    started = perf_counter()
    profiler.enable()
    try:
        result = action()
        if isinstance(result, Iterator):
            raise TypeError('Consume iterator work inside the profiled action')
        metadata['action_returned'] = True
    except BaseException as error:
        failure = error
        metadata['exception_type'] = type(error).__name__
        raise
    finally:
        profiler.disable()
        metadata['instrumented_wall_seconds'] = perf_counter() - started
        if destination is not None:
            try:
                # Save raw data first; a later formatting error must not destroy it.
                profiler.dump_stats(str(destination / 'profile.pstats'))
                for filename, sort_key, view in (
                    ('self.txt', pstats.SortKey.TIME, 'stats'),
                    ('cumulative.txt', pstats.SortKey.CUMULATIVE, 'stats'),
                    ('callers.txt', pstats.SortKey.CUMULATIVE, 'callers'),
                    ('callees.txt', pstats.SortKey.CUMULATIVE, 'callees'),
                ):
                    with (destination / filename).open('w', encoding='utf-8') as stream:
                        stats = pstats.Stats(profiler, stream=stream).sort_stats(sort_key)
                        # Do not strip directories: equal basenames can otherwise
                        # merge distinct functions and corrupt caller attribution.
                        if view == 'stats':
                            stats.print_stats()
                        elif view == 'callers':
                            stats.print_callers()
                        else:
                            stats.print_callees()
                metadata['reports_complete'] = True
                (destination / 'metadata.json').write_text(
                    json.dumps(metadata, indent=2, allow_nan=False) + '\n', encoding='utf-8',
                )
            except Exception as report_error:
                if failure is None:
                    raise
                # Keep the workload's original failure authoritative.
                failure.add_note(f'Profile report retention also failed: {type(report_error).__name__}')
    return result, profiler
