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
    identical_uncached_misses: int = 0
    _local_signatures: set[tuple[Any, ...]] = field(default_factory=set, repr=False)
    _complete_signatures: set[tuple[Any, ...]] = field(default_factory=set, repr=False)


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
                # Do not report repeated identical *complete* keys as
                # changing descendants: a failed run or a full 10,000-entry
                # cache can leave a key unevaluated/repeatedly uncached.
                # These signatures are retained in memory ONLY for the probe.
                if key in row._complete_signatures:
                    row.identical_uncached_misses += 1
                else:
                    row._complete_signatures.add(key)
                    # First expression/scope is the local input; remaining
                    # key components describe descendants/database rows.
                    if key[1][0] == "manifest":
                        # Compact keys separate local bindings/predicates from
                        # selected-file dependency signatures. Preserve selected
                        # source identity without attributing child changes to it.
                        selected = key[1][2]
                        selection = (selected[0], tuple(child[:2] for child in selected[1])) if selected else ()
                        local = key[1][1], selection
                    else:
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
        if (self.key_errors == 0 and result.fallback_runs == 0
                and (misses, hits) != (result.fragment_evaluations, result.fragment_reuses)):
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
                "identical_uncached_key_misses": row.identical_uncached_misses,
                "key_ns": row.key_ns,
            })
        misses_per_run = [run["misses"] for run in self._runs]
        lookups_per_run = [run["lookups"] for run in self._runs]
        hits_per_run = [run["hits"] for run in self._runs]
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
            "misses_with_identical_uncached_key": sum(row.identical_uncached_misses for row in rows),
            "local_signature_note": (
                "Only new complete keys with repeated local signatures may indicate changing "
                "descendants/database rows. Identical full keys repeatedly missing are separate "
                "and may reflect cache saturation or failed-run invalidation."
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
                "average": round(sum(misses_per_run) / len(misses_per_run), 3)
                if misses_per_run
                else 0.0,
            },
            "lookups_per_context": {
                "minimum": min(lookups_per_run, default=0),
                "maximum": max(lookups_per_run, default=0),
                "average": round(sum(lookups_per_run) / len(lookups_per_run), 3)
                if lookups_per_run
                else 0.0,
            },
            "hits_per_context": {
                "minimum": min(hits_per_run, default=0),
                "maximum": max(hits_per_run, default=0),
                "average": round(sum(hits_per_run) / len(hits_per_run), 3)
                if hits_per_run
                else 0.0,
            },
            # Context ordinals and aggregate counters are safe to publish and
            # show exactly where the invocation-local cache stabilises. Flags,
            # paths, values and source identities remain private.
            "run_progression": [
                {
                    "context": index,
                    "lookups": run["lookups"],
                    "hits": run["hits"],
                    "misses": run["misses"],
                }
                for index, run in enumerate(self._runs, start=1)
            ],
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
                    "identical_uncached_key_misses": row.identical_uncached_misses,
                    "key_inclusive_ns": row.key_ns,
                }
                for row in ordered[:top]
            ],
        }
