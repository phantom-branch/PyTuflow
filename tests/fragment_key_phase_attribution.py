"""PRIVATE opt-in breakdown of fragment key construction for invariant commands.

Measures only calls *inside* _Plan._key. The phases are nested:
FragmentContext.translate includes ExpressionPool.translate and possibly
Context.translate/CompiledExpression.bindings; BatchContext scope processing
includes ScopeList.contains. Inclusive phase timings MUST NOT be added.

No production parser functionality or cache-key equality is changed. The
measurement wrappers impose significant overhead and are not valid for
unmonitored speed comparisons. Private commands/source paths remain local.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter_ns
from typing import Any
from unittest.mock import patch


_PHASES = (
    "fragment_translate",
    "pool_translate",
    "context_translate",
    "bindings",
    "expression_evaluate",
    "scope_decision",
    "scope_contains",
)


@dataclass(slots=True)
class _SourcePhase:
    slot: int
    kind: str
    command_name: str
    owner_control_file: str
    source_line: int | None
    command_text: str
    key_calls: int = 0
    key_ns: int = 0
    phase_ns: Counter[str] = field(default_factory=Counter)
    phase_calls: Counter[str] = field(default_factory=Counter)


class PrivateKeyPhaseAttribution:
    """Break source-command key work into nested translation and scope calls."""

    def __init__(self) -> None:
        self._used = False
        self._sources: dict[int, _SourcePhase] = {}
        self._current: _SourcePhase | None = None
        self.key_errors = 0

    def _source(self, inp: Any) -> _SourcePhase:
        key = id(inp)
        source = self._sources.get(key)
        if source is None:
            cmd = inp._command
            line = getattr(cmd, "line_number", None)
            source = _SourcePhase(
                len(self._sources) + 1,
                type(inp).__name__,
                str(getattr(cmd, "command_orig", "") or ""),
                str(getattr(cmd, "parent", "") or ""),
                line if isinstance(line, int) else None,
                str(getattr(cmd, "original_text", "") or ""),
            )
            self._sources[key] = source
        return source

    def _timed[T](self, callback: Callable[..., T], phase: str) -> Callable[..., T]:
        def observe(*args: Any, **kwargs: Any) -> T:
            source = self._current
            if source is None:
                return callback(*args, **kwargs)
            start = perf_counter_ns()
            try:
                return callback(*args, **kwargs)
            finally:
                source.phase_ns[phase] += perf_counter_ns() - start
                source.phase_calls[phase] += 1
        return observe

    @contextmanager
    def observe(self) -> Iterator[None]:
        """Temporarily intercept only the supported built-in parser functions."""
        if self._used:
            raise RuntimeError("Create a new private key-phase probe for each invocation")
        self._used = True

        from pytuflow._tmf import fragment_dependencies as fragment
        from pytuflow._tmf.batch_dependencies import BatchContext
        from pytuflow._tmf.context import Context
        from pytuflow._tmf.scope import ScopeList

        original_key = fragment._Plan._key

        def observed_key(plan: Any, inp: Any, ctx: Any) -> Any:
            source = self._source(inp)
            previous = self._current
            self._current = source
            start = perf_counter_ns()
            try:
                return original_key(plan, inp, ctx)
            except BaseException:
                self.key_errors += 1
                raise
            finally:
                source.key_ns += perf_counter_ns() - start
                source.key_calls += 1
                self._current = previous

        with (
            patch.object(fragment._Plan, "_key", observed_key),
            patch.object(
                fragment._FragmentContext, "translate",
                self._timed(fragment._FragmentContext.translate, "fragment_translate"),
            ),
            patch.object(
                fragment.ExpressionPool, "translate",
                self._timed(fragment.ExpressionPool.translate, "pool_translate"),
            ),
            patch.object(Context, "translate", self._timed(Context.translate, "context_translate")),
            patch.object(
                fragment.CompiledExpression, "bindings",
                self._timed(fragment.CompiledExpression.bindings, "bindings"),
            ),
            patch.object(
                fragment.CompiledExpression, "evaluate",
                self._timed(fragment.CompiledExpression.evaluate, "expression_evaluate"),
            ),
            patch.object(
                BatchContext, "in_context_by_scope",
                self._timed(BatchContext.in_context_by_scope, "scope_decision"),
            ),
            patch.object(
                ScopeList, "contains",
                self._timed(ScopeList.contains, "scope_contains"),
            ),
        ):
            yield

    def snapshot(self, result: Any) -> dict[str, Any]:
        """Anonymous aggregate and hotspot slots; no filenames or raw values."""
        count = sum(row.key_calls for row in self._sources.values())
        expected = result.fragment_evaluations + result.fragment_reuses
        if self.key_errors == 0 and result.fallback_runs == 0 and count != expected:
            raise AssertionError(f"Key phase count {count} does not match {expected}")
        by_kind: dict[str, Counter[str]] = defaultdict(Counter)
        for row in self._sources.values():
            group = by_kind[row.kind]
            group["slots"] += 1
            group["key_calls"] += row.key_calls
            group["key_ns"] += row.key_ns
            for phase in _PHASES:
                group[f"{phase}_ns"] += row.phase_ns[phase]
                group[f"{phase}_calls"] += row.phase_calls[phase]

        def project(row: _SourcePhase) -> dict[str, Any]:
            return {
                "slot": row.slot,
                "input_type": row.kind,
                "key_calls": row.key_calls,
                "key_inclusive_ms": round(row.key_ns / 1_000_000, 6),
                "translation_inclusive_ms": round(row.phase_ns["fragment_translate"] / 1_000_000, 6),
                "scope_inclusive_ms": round(row.phase_ns["scope_decision"] / 1_000_000, 6),
                "bindings_inclusive_ms": round(row.phase_ns["bindings"] / 1_000_000, 6),
                "scope_contains_inclusive_ms": round(row.phase_ns["scope_contains"] / 1_000_000, 6),
            }

        return {
            "schema_version": 1,
            "safe_aggregate_only": True,
            "key_calls": count,
            "key_errors": self.key_errors,
            "instrumentation_overhead_included": True,
            "phase_warning": (
                "Phase timings are inclusive/nested and overlap; never sum "
                "child timings or equate them to uninstrumented production cost."
            ),
            "by_input_type": {
                kind: {
                    "slots": counters["slots"],
                    "key_calls": counters["key_calls"],
                    "key_inclusive_ms": round(counters["key_ns"] / 1_000_000, 6),
                    **{
                        phase: {
                            "calls": counters[f"{phase}_calls"],
                            "inclusive_ms": round(counters[f"{phase}_ns"] / 1_000_000, 6),
                        }
                        for phase in _PHASES
                    },
                }
                for kind, counters in sorted(by_kind.items())
            },
            "top_anonymous_key_slots": [
                project(row)
                for row in sorted(
                    self._sources.values(),
                    key=lambda item: (-item.key_ns, item.slot),
                )[:30]
            ],
        }

    def write_private(self, destination: Path, result: Any) -> None:
        """Source/control-file names and raw text must NEVER enter git/PRs."""
        if not destination.is_dir():
            raise FileNotFoundError("Create a private output folder before writing")
        self.snapshot(result)
        fields = (
            "input_slot", "input_type", "source_control_file", "source_line", "command_name",
            "command_text", "key_calls", "key_inclusive_ms",
            *tuple(f"{phase}_calls" for phase in _PHASES),
            *tuple(f"{phase}_inclusive_ms" for phase in _PHASES),
        )
        with (destination / "private_key_phases_by_input.csv").open(
            "x", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in sorted(self._sources.values(), key=lambda item: item.slot):
                writer.writerow({
                    "input_slot": row.slot,
                    "input_type": row.kind,
                    "source_control_file": row.owner_control_file,
                    "source_line": row.source_line,
                    "command_name": row.command_name,
                    "command_text": row.command_text,
                    "key_calls": row.key_calls,
                    "key_inclusive_ms": round(row.key_ns / 1_000_000, 6),
                    **{f"{phase}_calls": row.phase_calls[phase] for phase in _PHASES},
                    **{
                        f"{phase}_inclusive_ms": round(row.phase_ns[phase] / 1_000_000, 6)
                        for phase in _PHASES
                    },
                })
