"""PRIVATE opt-in attribution of fragment hits, time and referenced filenames.

The trace is an instrumented diagnostic, never a production timing benchmark.
It observes one synchronous invocation without altering evaluated keys, immutable
fragments, scope/event decisions or public outputs. Source/control-file paths,
command text and resolved file patterns are written ONLY to local CSVs when the
caller explicitly requests private attribution; never commit those reports.

A fragment may contain many descendant references. Repeated cached-fragment
associations are NOT disk opens, stat calls or independent file resolutions.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any
from unittest.mock import patch


@dataclass(slots=True)
class _Source:
    slot: int
    kind: str
    owner_control_file: str
    line: int | None
    command_name: str
    command_text: str
    hits: int = 0
    misses: int = 0
    key_ns: int = 0
    eval_exclusive_ns: int = 0
    hit_exclusive_ns: list[int] = field(default_factory=list)
    miss_exclusive_ns: list[int] = field(default_factory=list)
    fragment_ids: set[int] = field(default_factory=set)


@dataclass(slots=True)
class _Frame:
    started_ns: int
    slot: int
    children_ns: int = 0
    key_ns: int = 0
    hit: bool | None = None


@dataclass(frozen=True, slots=True)
class _Link:
    pattern: str
    layer: str
    kind: str
    relation: str


@dataclass(slots=True)
class _Fragment:
    source_object: Any
    serial: int
    links: tuple[_Link, ...]


@dataclass(frozen=True, slots=True)
class _Lookup:
    context: int
    slot: int
    fragment_id: int
    hit: bool
    key_ns: int
    eval_inclusive_ns: int
    eval_exclusive_ns: int


def _percentile(values: list[int], fraction: float) -> float:
    """Nearest-rank percentile in milliseconds, with an empty result of zero."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[max(0, int((len(ordered) - 1) * fraction))] / 1_000_000, 6)


class PrivateFragmentAttribution:
    """Capture a bounded-sized trace per lookup and cached-fragment path mapping."""

    def __init__(self) -> None:
        self._used = False
        self._context = 0
        self._frames: list[_Frame] = []
        self._sources: dict[int, _Source] = {}
        self._fragments: dict[int, _Fragment] = {}
        self._lookups: list[_Lookup] = []
        self.failed_calls = 0

    def _source(self, inp: Any) -> _Source:
        key = id(inp)
        row = self._sources.get(key)
        if row is not None:
            return row
        command = inp._command
        number = getattr(command, "line_number", None)
        row = _Source(
            slot=len(self._sources) + 1,
            kind=type(inp).__name__,
            owner_control_file=str(getattr(command, "parent", "")),
            line=number if isinstance(number, int) else None,
            command_name=str(getattr(command, "command_orig", "") or ""),
            command_text=str(getattr(command, "original_text", "") or ""),
        )
        self._sources[key] = row
        return row

    def _fragment(self, result: Any, inp: Any) -> _Fragment:
        key = id(result)
        cached = self._fragments.get(key)
        if cached is not None and cached.source_object is result:
            return cached

        owner_uuid = str(inp.uuid)
        links: set[_Link] = set()
        for entry in result.references:
            ref = entry.reference
            links.add(
                _Link(
                    str(ref.path_pattern),
                    str(ref.layer_pattern or ""),
                    "primary",
                    "direct" if str(entry.input_uuid) == owner_uuid else "descendant",
                )
            )
        for ref in result.sources:
            links.add(
                _Link(
                    str(ref.path_pattern),
                    str(ref.layer_pattern or ""),
                    "secondary_database_source",
                    "direct" if str(ref.input_uuid) == owner_uuid else "descendant_or_indirect",
                )
            )
        cached = _Fragment(result, len(self._fragments) + 1, tuple(sorted(
            links, key=lambda item: (item.pattern, item.layer, item.kind, item.relation)
        )))
        self._fragments[key] = cached
        return cached

    @contextmanager
    def observe(self) -> Iterator[None]:
        """Patch only the calling thread's run and restore hooks on any exit."""
        if self._used:
            raise RuntimeError("Create a new private fragment attribution probe for each invocation")
        self._used = True
        from pytuflow._tmf import fragment_dependencies as fragment

        original_key = fragment._Plan._key
        original_evaluate = fragment._Plan.evaluate
        original_context_init = fragment._FragmentContext.__init__

        def observed_context_init(ctx: Any, *args: Any, **kwargs: Any) -> None:
            original_context_init(ctx, *args, **kwargs)
            self._context += 1

        def observed_key(plan: Any, inp: Any, ctx: Any) -> Any:
            started = perf_counter_ns()
            try:
                key = original_key(plan, inp, ctx)
            except BaseException:
                # Propagate the exact original exception, without returning
                # a synthetic key or changing parser failure behaviour.
                raise
            elapsed = perf_counter_ns() - started
            if self._frames:
                frame = self._frames[-1]
                frame.key_ns += elapsed
                frame.hit = key in plan.cache or key in plan.pending
            return key

        def observed_evaluate(plan: Any, inp: Any, ctx: Any) -> Any:
            source = self._source(inp)
            frame = _Frame(perf_counter_ns(), source.slot)
            self._frames.append(frame)
            result: Any = None
            succeeded = False
            try:
                result = original_evaluate(plan, inp, ctx)
                succeeded = True
                return result
            finally:
                # Subtract the inclusive timings of recursive evaluate calls.
                # The residual includes key construction and observer overhead.
                inclusive_ns = perf_counter_ns() - frame.started_ns
                self._frames.pop()
                if self._frames:
                    self._frames[-1].children_ns += inclusive_ns
                if succeeded and frame.hit is not None:
                    exclusive_ns = max(0, inclusive_ns - frame.children_ns)
                    source.key_ns += frame.key_ns
                    source.eval_exclusive_ns += exclusive_ns
                    if frame.hit:
                        source.hits += 1
                        source.hit_exclusive_ns.append(exclusive_ns)
                    else:
                        source.misses += 1
                        source.miss_exclusive_ns.append(exclusive_ns)
                    resolved = self._fragment(result, inp)
                    source.fragment_ids.add(resolved.serial)
                    self._lookups.append(
                        _Lookup(
                            self._context,
                            source.slot,
                            resolved.serial,
                            frame.hit,
                            frame.key_ns,
                            inclusive_ns,
                            exclusive_ns,
                        )
                    )
                else:
                    self.failed_calls += 1

        with (
            patch.object(fragment._FragmentContext, "__init__", observed_context_init),
            patch.object(fragment._Plan, "_key", observed_key),
            patch.object(fragment._Plan, "evaluate", observed_evaluate),
        ):
            yield

    def summary(self, result: Any) -> dict[str, Any]:
        """Safe-to-share counters ONLY; never include private command/file strings."""
        hits = sum(source.hits for source in self._sources.values())
        misses = sum(source.misses for source in self._sources.values())
        if result.fallback_runs == 0 and self.failed_calls == 0 and (
            hits != result.fragment_reuses or misses != result.fragment_evaluations
        ):
            raise AssertionError("Per-source trace counts differ from parser fragment counters")
        names = {
            (link.pattern, link.layer, link.kind)
            for fragment in self._fragments.values()
            for link in fragment.links
        }
        return {
            "schema_version": 1,
            "private_file_attribution_available": True,
            "raw_paths_and_commands_present_in_private_csvs": True,
            "safe_to_publish_only_this_aggregate": True,
            "instrumented_not_production_timing": True,
            "cache_hits": hits,
            "cache_misses": misses,
            "lookup_trace_rows": len(self._lookups),
            "source_input_slots": len(self._sources),
            "cached_fragment_objects_observed": len(self._fragments),
            "distinct_resolved_patterns_in_fragment_links": len(names),
            "failed_evaluate_calls": self.failed_calls,
            "source_key_inclusive_ms": round(
                sum(source.key_ns for source in self._sources.values()) / 1_000_000, 4
            ),
            "source_evaluate_exclusive_ms": round(
                sum(source.eval_exclusive_ns for source in self._sources.values()) / 1_000_000, 4
            ),
            "note": (
                "Fragment links can overlap between parents and descendants. "
                "Counts are cache attribution, NOT file reads, stat calls or distinct "
                "filesystem-resolution operations. Timings include tracing overhead."
            ),
        }

    def write_private(self, destination: Path, result: Any) -> None:
        """Write explicit, locally scoped CSVs after caller verifies full parity."""
        if not destination.is_dir():
            raise FileNotFoundError("Private diagnostic output directory does not exist")
        self.summary(result)

        rows = sorted(self._sources.values(), key=lambda s: s.slot)
        files: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
        fragment_entries: dict[int, _Fragment] = {
            frag.serial: frag for frag in self._fragments.values()
        }
        by_fragment: dict[int, set[int]] = defaultdict(set)
        for event in self._lookups:
            by_fragment[event.fragment_id].add(event.slot)
            links = {
                (link.pattern, link.layer, link.kind, link.relation)
                for link in fragment_entries[event.fragment_id].links
            }
            for pattern, layer, kind, relation in links:
                stats = files[(pattern, layer, kind)]
                stats["fragment_lookup_associations"] += 1
                stats["fragment_hit_associations" if event.hit else "fragment_miss_associations"] += 1
                stats["direct_associations" if relation == "direct" else "descendant_associations"] += 1
                # Non-additive, whole-fragment cost associated with every
                # referenced pattern. It MUST NOT be described as independent
                # file work or summed across paths to estimate elapsed time.
                stats["associated_key_ns"] += event.key_ns
                stats["associated_evaluate_exclusive_ns"] += event.eval_exclusive_ns
                stats["associated_hit_exclusive_ns" if event.hit else "associated_miss_exclusive_ns"] += (
                    event.eval_exclusive_ns
                )

        # These count references in completed run outputs, not cache lookups,
        # and do not open or stat any referenced file.
        for run in result.runs:
            for ref in run.file_references:
                files[(str(ref.path_pattern), str(ref.layer_pattern or ""), "primary")][
                    "logical_run_references"
                ] += 1
            for ref in run.database_sources:
                files[(str(ref.path_pattern), str(ref.layer_pattern or ""), "secondary_database_source")][
                    "logical_database_source_rows"
                ] += 1

        def write(name: str, fieldnames: tuple[str, ...], lines: Iterator[dict[str, Any]]) -> None:
            with (destination / name).open("x", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
                writer.writeheader()
                writer.writerows(lines)

        write(
            "private_input_totals.csv",
            (
                "input_slot", "input_type", "owner_control_file", "source_line",
                "command_name", "command_text", "lookups", "hits", "misses",
                "distinct_fragment_objects", "key_inclusive_ms",
                "evaluate_exclusive_ms", "hit_exclusive_total_ms", "miss_exclusive_total_ms",
                "median_hit_exclusive_ms", "p95_hit_exclusive_ms",
                "median_miss_exclusive_ms", "p95_miss_exclusive_ms",
            ),
            (
                {
                    "input_slot": s.slot,
                    "input_type": s.kind,
                    "owner_control_file": s.owner_control_file,
                    "source_line": s.line,
                    "command_name": s.command_name,
                    "command_text": s.command_text,
                    "lookups": s.hits + s.misses,
                    "hits": s.hits,
                    "misses": s.misses,
                    "distinct_fragment_objects": len(s.fragment_ids),
                    "key_inclusive_ms": round(s.key_ns / 1_000_000, 6),
                    "evaluate_exclusive_ms": round(s.eval_exclusive_ns / 1_000_000, 6),
                    "hit_exclusive_total_ms": round(sum(s.hit_exclusive_ns) / 1_000_000, 6),
                    "miss_exclusive_total_ms": round(sum(s.miss_exclusive_ns) / 1_000_000, 6),
                    "median_hit_exclusive_ms": round(median(s.hit_exclusive_ns) / 1_000_000, 6)
                    if s.hit_exclusive_ns else 0.0,
                    "p95_hit_exclusive_ms": _percentile(s.hit_exclusive_ns, 0.95),
                    "median_miss_exclusive_ms": round(median(s.miss_exclusive_ns) / 1_000_000, 6)
                    if s.miss_exclusive_ns else 0.0,
                    "p95_miss_exclusive_ms": _percentile(s.miss_exclusive_ns, 0.95),
                }
                for s in rows
            ),
        )

        write(
            "private_lookup_trace.csv",
            (
                "context_ordinal", "input_slot", "fragment_id", "cache_result",
                "key_ms", "evaluate_inclusive_ms", "evaluate_exclusive_ms",
            ),
            (
                {
                    "context_ordinal": event.context,
                    "input_slot": event.slot,
                    "fragment_id": event.fragment_id,
                    "cache_result": "hit" if event.hit else "miss",
                    "key_ms": round(event.key_ns / 1_000_000, 6),
                    "evaluate_inclusive_ms": round(event.eval_inclusive_ns / 1_000_000, 6),
                    "evaluate_exclusive_ms": round(event.eval_exclusive_ns / 1_000_000, 6),
                }
                for event in self._lookups
            ),
        )

        slot_to_source = {s.slot: s for s in rows}
        write(
            "private_fragment_files.csv",
            (
                "fragment_id", "input_slot", "owner_control_file", "source_line",
                "resolved_file_pattern", "layer_pattern", "reference_kind", "relationship",
            ),
            (
                {
                    "fragment_id": serial,
                    "input_slot": slot,
                    "owner_control_file": slot_to_source[slot].owner_control_file,
                    "source_line": slot_to_source[slot].line,
                    "resolved_file_pattern": link.pattern,
                    "layer_pattern": link.layer,
                    "reference_kind": link.kind,
                    "relationship": link.relation,
                }
                for serial, frag in sorted(fragment_entries.items())
                for slot in sorted(by_fragment[serial])
                for link in frag.links
            ),
        )
        write(
            "private_file_totals.csv",
            (
                "resolved_file_pattern", "layer_pattern", "reference_kind",
                "logical_run_references", "logical_database_source_rows",
                "fragment_lookup_associations", "fragment_hit_associations",
                "fragment_miss_associations", "direct_associations", "descendant_associations",
                "associated_key_ms", "associated_evaluate_exclusive_ms",
                "associated_hit_exclusive_ms", "associated_miss_exclusive_ms",
            ),
            (
                {
                    "resolved_file_pattern": pattern,
                    "layer_pattern": layer,
                    "reference_kind": kind,
                    **{
                        field: values.get(field, 0)
                        for field in (
                            "logical_run_references", "logical_database_source_rows",
                            "fragment_lookup_associations", "fragment_hit_associations",
                            "fragment_miss_associations", "direct_associations",
                            "descendant_associations",
                        )
                    },
                    "associated_key_ms": round(values["associated_key_ns"] / 1_000_000, 6),
                    "associated_evaluate_exclusive_ms": round(
                        values["associated_evaluate_exclusive_ns"] / 1_000_000, 6
                    ),
                    "associated_hit_exclusive_ms": round(
                        values["associated_hit_exclusive_ns"] / 1_000_000, 6
                    ),
                    "associated_miss_exclusive_ms": round(
                        values["associated_miss_exclusive_ns"] / 1_000_000, 6
                    ),
                }
                for (pattern, layer, kind), values in sorted(files.items())
            ),
        )
