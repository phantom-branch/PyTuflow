"""Opt-in, anonymous fragment-cache attribution for parsed read-only batches.

This is diagnostic code, not a benchmark or a production optimisation.
Observed counters/timings include instrumentation overhead. The ordinary
preflight API, model, run order and parser cache keys are left unchanged.

No paths, flags, source values, UUIDs or complete keys enter the report.
The calling thread must have exclusive use of the parser during capture.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter_ns
from typing import Any
from unittest.mock import patch


@dataclass(slots=True)
class _InputRow:
    slot: int
    kind: str
    lookups: int = 0
    hits: int = 0
    misses: int = 0
    key_ns: int = 0
    first_local_misses: int = 0
    repeated_local_misses: int = 0
    _local_signatures: set[tuple[Any, ...]] = field(default_factory=set, repr=False)


class FragmentEvaluationProbe:
    """Measure key cost, per-source misses and immutable output rebasing."""

    def __init__(self) -> None:
        self._used = False
        self._inputs: dict[int, _InputRow] = {}
        self._runs: list[dict[str, int]] = []
        self.lookup_ns = 0
        self.key_errors = 0
        self.join_calls = 0
        self.join_fragments = 0
        self.join_commands_rebased = 0
        self.join_references_rebased = 0
        self.join_activations_rebased = 0

    @contextmanager
    def observe(self) -> Iterator[None]:
        """Capture exactly one synchronous fragment invocation, restoring hooks."""
        if self._used:
            raise RuntimeError("Create a fresh fragment probe for each invocation")
        self._used = True
        from pytuflow._tmf import fragment_dependencies as fragment

        original_key = fragment._Plan._key
        original_context_init = fragment._FragmentContext.__init__
        original_join = fragment._join

        def observed_context_init(ctx: Any, *args: Any, **kwargs: Any) -> None:
            self._runs.append({"lookups": 0, "hits": 0, "misses": 0})
            original_context_init(ctx, *args, **kwargs)

        def observed_key(plan: Any, inp: Any, ctx: Any) -> Any:
            started = perf_counter_ns()
            try:
                key = original_key(plan, inp, ctx)
            except Exception:
                self.key_errors += 1
                raise
            elapsed = perf_counter_ns() - started
            self.lookup_ns += elapsed

            identity = id(inp)
            row = self._inputs.get(identity)
            if row is None:
                row = _InputRow(len(self._inputs) + 1, type(inp).__name__)
                self._inputs[identity] = row
            row.lookups += 1
            row.key_ns += elapsed
            hit = key in plan.cache or key in plan.pending
            if hit:
                row.hits += 1
            else:
                row.misses += 1
                # The first expression/scope pair describes this input
                # itself; the remaining key components describe descendants
                # (or loaded database rows). A new *subtree* key with an
                # already seen local signature identifies descendant-driven
                # churn. Retain values only in this private probe; never emit
                # them in the JSON report.
                values, scopes = key[1]
                local = (values[0], scopes[0])
                if local in row._local_signatures:
                    row.repeated_local_misses += 1
                else:
                    row.first_local_misses += 1
                    row._local_signatures.add(local)
            if self._runs:
                recent = self._runs[-1]
                recent["lookups"] += 1
                recent["hits" if hit else "misses"] += 1
            return key

        def observed_join(fragments: Iterable[Any]) -> Any:
            self.join_calls += 1

            def inspect() -> Iterator[Any]:
                offset = 0
                for item in fragments:
                    self.join_fragments += 1
                    if offset:
                        # Each frozen record is copied with an offset by _join.
                        self.join_commands_rebased += len(item.commands)
                        self.join_references_rebased += len(item.references)
                        self.join_activations_rebased += len(item.activations)
                    offset += len(item.commands)
                    yield item

            # Keep the original lazy traversal and the original _join. A
            # timer around _join would include nested fragment evaluation.
            return original_join(inspect())

        with (
            patch.object(fragment._Plan, "_key", observed_key),
            patch.object(fragment._FragmentContext, "__init__", observed_context_init),
            patch.object(fragment, "_join", observed_join),
        ):
            yield

    def snapshot(self, result: Any, *, top: int = 20) -> dict[str, Any]:
        """Emit aggregate and anonymous per-input data, never source identities."""
        rows = list(self._inputs.values())
        misses = sum(row.misses for row in rows)
        hits = sum(row.hits for row in rows)
        if self.key_errors == 0 and result.fallback_runs == 0:
            if (misses, hits) != (result.fragment_evaluations, result.fragment_reuses):
                raise AssertionError("Instrumented key totals differ from parser counters")

        kinds: dict[str, Counter[str]] = {}
        for row in rows:
            stats = kinds.setdefault(row.kind, Counter())
            stats.update({
                "inputs": 1,
                "lookups": row.lookups,
                "hits": row.hits,
                "misses": row.misses,
                "new_local_signature_misses": row.first_local_misses,
                "repeated_local_signature_misses": row.repeated_local_misses,
                "key_ns": row.key_ns,
            })
        misses_per_run = [run["misses"] for run in self._runs]
        ordered = sorted(rows, key=lambda row: (-row.misses, -row.key_ns, row.slot))
        return {
            "schema_version": 1,
            "accepted_for_benchmark": False,
            "instrumentation_overhead_included": True,
            "source_paths_or_flags_retained": False,
            "public_projection_passed": result.passed,
            "run_count": len(result.runs),
            "contexts_constructed": len(self._runs),
            "fallback_runs": result.fallback_runs,
            "key_errors": self.key_errors,
            "lookups": hits + misses,
            "hits": hits,
            "misses": misses,
            "misses_with_new_local_signature": sum(row.first_local_misses for row in rows),
            "misses_with_reused_local_signature": sum(row.repeated_local_misses for row in rows),
            "local_signature_note": (
                "Repeated local signatures on a new subtree key indicate varying descendants/database rows; "
                "this is not proof that the parent evaluation may be removed"
            ),
            "hit_rate_percent": round(100 * hits / (hits + misses), 3) if hits + misses else 0.0,
            "key_inclusive_ns": self.lookup_ns,
            "key_time_warning": (
                "Key timings include nested translate/scope calls and instrumentation; "
                "not exclusive CPU time"
            ),
            "misses_per_context": {
                "minimum": min(misses_per_run, default=0),
                "maximum": max(misses_per_run, default=0),
                "first": misses_per_run[0] if misses_per_run else 0,
                "last": misses_per_run[-1] if misses_per_run else 0,
            },
            "joins": {
                "calls": self.join_calls,
                "fragments": self.join_fragments,
                "commands_rebased": self.join_commands_rebased,
                "references_rebased": self.join_references_rebased,
                "activations_rebased": self.join_activations_rebased,
                "rebases_warning": "Counts include nested joins; no exclusive wall time is attributed",
            },
            "by_input_type": {
                kind: dict(values)
                for kind, values in sorted(kinds.items())
            },
            "top_anonymous_input_slots": [
                {
                    "slot": row.slot,
                    "input_type": row.kind,
                    "lookups": row.lookups,
                    "hits": row.hits,
                    "misses": row.misses,
                    "new_local_signature_misses": row.first_local_misses,
                    "repeated_local_signature_misses": row.repeated_local_misses,
                    "key_inclusive_ns": row.key_ns,
                }
                for row in ordered[:top]
            ],
        }
