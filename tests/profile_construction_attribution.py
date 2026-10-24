"""Bounded parser-only attribution for at most six explicitly selected contexts.

Run with --help before use. This is not a batch-file interpreter, native
benchmark acceptance, physical preflight, or permission to execute a solver.
"""

import argparse
from importlib import import_module
import json
from pathlib import Path
import re
import sys
from time import perf_counter_ns
from types import CodeType, FunctionType

if __package__:
    from .construction_attribution import Attribution, Target
else:
    from construction_attribution import Attribution, Target


def operation(module: str, name: str, qualname: str) -> str:
    """Named diagnostic boundaries; no inference of exclusive CPU instructions."""
    if 'database' in name and 'source' in name:
        return 'database_source_projection'
    if 'database' in name and 'activat' in name:
        return 'database_activation'
    if name == 'file_references' or module == 'file_reference':
        return 'file_reference_projection'
    if module == 'settings':
        return 'configuration_copy' if name == 'from_config' else 'configuration_other'
    if module == 'batch_dependencies' and not qualname.startswith('BatchContext.'):
        return 'batch_overhead' if name == 'collect_batch_dependencies' else 'batch_projection'
    if module in ('context', 'batch_dependencies'):
        named = {
            '__init__': 'context_bootstrap', 'load_events': 'event_loading',
            'load_variables': 'variable_loading', 'translate': 'translation',
            'available_scopes': 'scope_evaluation', 'in_context_by_scope': 'scope_evaluation',
            'variable_declaration_signature': 'variable_provenance',
            'batch_command': 'command_factory', 'batch_input_state': 'input_factory',
            'commit_input_groups': 'cache_certification',
            'cached_file_references': 'reference_cache',
            'collect_batch_dependencies': 'batch_overhead',
        }
        return named.get(name, 'context_other')
    if module == 'group_input_reuse':
        return {
            '_key': 'cache_key_proof', '_clone': 'state_clone',
            'try_reuse': 'cache_lookup', 'prepare_seed': 'cache_certification',
            'commit': 'cache_certification', '__init__': 'cache_preparation',
        }.get(name, 'cache_other')
    if module in ('compiled_control_tree', 'compiled_dependency_plan'):
        return 'cache_compilation' if name in ('compile', 'from_assignments', '__init__') else 'cache_proof'
    if module == 'scope':
        return 'scope_evaluation'
    if module == 'event':
        return 'event_processing'
    if module.startswith('parsers.'):
        if name == '__init__' and qualname.endswith('Command.__init__'):
            return 'command_construction'
        return 'parser_processing'
    if module == 'inp.inputs':
        return 'append_bookkeeping' if name == 'append' else 'input_collection'
    if module.startswith('inp.'):
        return 'input_construction' if name == '__init__' else 'input_processing'
    if module.startswith('cf.'):
        return 'control_file_evaluation' if name in ('context', '__init__', '_resolve_scope_in_context') else 'control_file_traversal'
    return 'tmf_other'


def parser_targets() -> tuple[list[tuple[CodeType, Target]], dict[type, str]]:
    """Observe actual definitions; never wrap or replace parser constructors."""
    prefix = 'pytuflow._tmf.'
    for module in ('batch_dependencies', 'file_reference', 'settings'):
        import_module(prefix + module)
    owners = {getattr(import_module(prefix + 'cf.' + kind.lower()), kind): kind
              for kind in ('TCF', 'TGC', 'TBC', 'TEF')}
    targets: list[tuple[CodeType, Target]] = []
    found: set[tuple[str, str]] = set()

    def add(function, module):
        if type(function) is not FunctionType or function.__module__ != prefix + module:
            return
        name = function.__name__
        owner = None
        if module.startswith('cf.') and name == 'context':
            owner = 'self'
        elif module == 'cf.cf_run_state' and name == '__init__':
            owner = 'build_state'
        targets.append((function.__code__, Target(operation(module, name, function.__qualname__), owner)))
        found.add((module, function.__qualname__))

    for full_name, module_object in tuple(sys.modules.items()):
        if not full_name.startswith(prefix) or module_object is None:
            continue
        module = full_name.removeprefix(prefix)
        if not (module in ('context', 'batch_dependencies', 'file_reference', 'settings', 'scope', 'event',
                            'compiled_control_tree', 'compiled_dependency_plan', 'group_input_reuse')
                or module.startswith(('cf.', 'inp.', 'parsers.', 'abc.'))):
            continue
        for value in tuple(vars(module_object).values()):
            add(value, module)
            if isinstance(value, type) and value.__module__ == full_name:
                for member in vars(value).values():
                    if isinstance(member, (staticmethod, classmethod)):
                        add(member.__func__, module)
                    elif isinstance(member, property):
                        add(member.fget, module)
                    else:
                        add(member, module)
    required = {
        ('batch_dependencies', 'BatchContext.__init__'),
        ('batch_dependencies', 'BatchContext.translate'),
        ('cf.cf_run_state', 'ControlFileRunState.__init__'),
        ('parsers.command', 'Command.__init__'), ('settings', 'from_config'),
    }
    if required - found:
        raise RuntimeError(f'Unsupported parser instrumentation surface: {sorted(required - found)}')
    return targets, owners


def load_runs(path: Path) -> list[dict[str, str]]:
    """Read explicit flags, preserving order and duplicate run rows; never execute."""
    runs = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(runs, list) or not 1 <= len(runs) <= 6:
        raise ValueError('Select between one and six contexts; full batches are refused')
    for run in runs:
        if not isinstance(run, dict) or not run:
            raise ValueError('Each context must be a nonempty event/scenario dictionary')
        if any(not re.fullmatch(r'-?[sSeE][1-9]?', key)
               or not isinstance(value, str) or not value for key, value in run.items()):
            raise ValueError('Only string-valued event/scenario flags are supported')
    return runs


def compare(model, runs, targets, owners, *, on_capture=None) -> dict[str, object]:
    """Four fresh API invocations on one stable parsed model; no shared batch caches.

    Reusing the parsed build state preserves UUID identity for exact public-run
    equality. This is not the fresh-model four-mode native acceptance protocol.
    """
    if not 1 <= len(runs) <= 6:
        raise ValueError('Select between one and six contexts; full batches are refused')
    results = {}
    elapsed = {}
    captures = {}
    order = ((False, False), (False, True), (True, True), (True, False))
    for graph, observed in order:
        label = f'graph_{"on" if graph else "off"}_{"observed" if observed else "plain"}'
        action = lambda: model.collect_batch_dependencies(runs, cache_scopes=True, compile_tree=graph)
        capture = Attribution(targets, owners) if observed else None
        started = perf_counter_ns()
        try:
            results[label] = capture.run(action) if capture is not None else action()
        finally:
            elapsed[label] = perf_counter_ns() - started
            if capture is not None and capture._used and not capture._active:
                captures[label] = capture.snapshot()
                if on_capture is not None:
                    original_error = sys.exception()
                    try:
                        on_capture(label, captures[label])
                    except BaseException as report_error:
                        if original_error is None:
                            raise
                        original_error.add_note(f'Attribution report failed: {type(report_error).__name__}')
        result = results[label]
        if not result.passed or len(result.runs) != len(runs):
            raise RuntimeError(f'Incomplete or failed parser projection in {label}')
    reference = results['graph_off_plain'].runs
    if any(result.runs != reference for result in results.values()):
        raise RuntimeError('Complete public run projections differ across observed/plain graph modes')
    return {
        'completed': True, 'public_projection_parity': True, 'run_count': len(runs),
        'accepted_for_benchmark': False, 'physical_preflight_performed': False,
        'parse_included': False, 'model_policy': 'one stable parsed model; fresh batch invocation caches',
        'order': [f'graph_{"on" if g else "off"}_{"observed" if o else "plain"}' for g, o in order],
        'elapsed_ns': elapsed,
        'observed_to_plain_ratio': {
            mode: elapsed[f'graph_{mode}_observed'] / elapsed[f'graph_{mode}_plain']
            for mode in ('off', 'on')
        },
        'ratio_warning': 'Single-pair observation including observer overhead and order/cache variation; not a speedup',
        'captures': captures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tcf', type=Path, required=True)
    parser.add_argument('--runs-json', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    runs = load_runs(args.runs_json)
    root = Path(__file__).absolute().parents[1]
    output = args.output.absolute()
    # Physical containment is deliberate; a linked path must not write into source.
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError('Choose a new private report directory outside this checkout')
    import pytuflow
    if not Path(pytuflow.__file__).resolve().is_relative_to((root / 'pytuflow').resolve()):
        raise RuntimeError('PyTUFLOW must import from this diagnostic checkout')
    targets, owners = parser_targets()
    output.mkdir(parents=True, exist_ok=False)
    summary = {'completed': False, 'accepted_for_benchmark': False, 'privacy': 'PRIVATE',
               'python': sys.version, 'registered_boundaries': len(targets),
               'source_provenance_verified': False, 'physical_preflight_performed': False}
    summary_file = output / 'summary.json'
    summary_file.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    def save_capture(label, report):
        (output / f'{label}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    try:
        started = perf_counter_ns()
        model = pytuflow.TCF(args.tcf.absolute())
        summary['parse_ns'] = perf_counter_ns() - started
        summary.update(compare(model, runs, targets, owners, on_capture=save_capture))
    except BaseException as exc:
        summary['error_type'] = type(exc).__name__
        raise
    finally:
        original_error = sys.exception()
        try:
            summary_file.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        except BaseException as report_error:
            if original_error is None:
                raise
            original_error.add_note(f'Summary write failed: {type(report_error).__name__}')
    print('Parser projection parity passed. Diagnostic only; no native acceptance or speedup claim.')


if __name__ == '__main__':
    main()
