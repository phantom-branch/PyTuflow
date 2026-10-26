"""Opt-in preparation attribution; instrumented CPU is not acceptance timing."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from time import process_time
from typing import Any
from unittest.mock import patch


@contextmanager
def preparation_probe():
    from pytuflow._tmf import context
    from pytuflow._tmf.cf import cf_run_state
    from pytuflow._tmf.scope import Scope, ScopeList

    counts: Counter[str] = Counter()
    seconds: Counter[str] = Counter()
    phase = 'evaluation'
    category = 'other'

    def timed(name, original):
        def call(*args, **kwargs):
            nonlocal phase
            previous = phase
            phase = name
            start = process_time()
            try:
                return original(*args, **kwargs)
            finally:
                seconds[name] += process_time() - start
                phase = previous
        return call

    original_scope = context.Context.in_context_by_scope

    def scope_call(self, scopes):
        nonlocal category
        previous = category
        kinds = {str(s.type).split(' (')[0] for s in scopes or ()}
        category = ('variable' if 'VARIABLE' in kinds else
                    'combined' if 'SCENARIO' in kinds and kinds & {'EVENT', 'EVENT DEFINE'} else
                    'scenario' if 'SCENARIO' in kinds else
                    'event' if kinds & {'EVENT', 'EVENT DEFINE'} else 'other')
        counts[f'{phase}.{category}.scope_calls'] += 1
        try:
            return original_scope(self, scopes)
        finally:
            category = previous

    def counted(name, original):
        def call(*args, **kwargs):
            counts[f'{phase}.{category}.{name}'] += 1
            return original(*args, **kwargs)
        return call

    with (patch.object(context.Context, 'load_events', timed('events', context.Context.load_events)),
          patch.object(cf_run_state, 'prepare_run_context', timed('variables', cf_run_state.prepare_run_context)),
          patch.object(context.Context, 'in_context_by_scope', scope_call),
          patch.object(ScopeList, 'contains', counted('membership', ScopeList.contains)),
          patch.object(Scope, '__init__', counted('constructions', Scope.__init__)),
          patch.object(Scope, 'explode', counted('expansions', Scope.explode)),
          patch.object(Scope, '__eq__', counted('comparisons', Scope.__eq__))):
        yield {'counts': counts, 'cpu_seconds': seconds}
