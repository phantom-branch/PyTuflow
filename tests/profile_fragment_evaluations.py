"""Diagnose fragment misses and key/output costs without running TUFLOW.

Usage:
    python -m tests.profile_fragment_evaluations --tcf MODEL.tcf --runs-json FLAGS.json --output PRIVATE_NEW_DIR
    python -m tests.profile_fragment_evaluations --help

FLAGS.json is a private JSON array of context flag strings or dictionaries.
The report contains anonymous input slots, counts and optional code-function
timings, never model paths, flags, source references or UUIDs. Keep the original
flags, source manifests and any profiler artifacts local. The instrumented
elapsed times MUST NOT be used to claim production performance improvements.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
from pathlib import Path
from typing import Any, cast

if __package__:
    from .fragment_evaluation_probe import FragmentEvaluationProbe
else:
    from fragment_evaluation_probe import FragmentEvaluationProbe


def load_run_flags(path: Path) -> list[str | dict[str, str]]:
    """Read contexts as DATA, without interpreting BAT/CMD or shell commands."""
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not 1 <= len(value) <= 2000:
        raise ValueError("Provide between one and 2,000 explicit run contexts")
    for item in value:
        if isinstance(item, str) and item.strip():
            continue
        if (
            isinstance(item, dict)
            and bool(item)
            and all(
                isinstance(key, str)
                and key.strip()
                and isinstance(val, str)
                and val.strip()
                for key, val in item.items()
            )
        ):
            continue
        raise ValueError("Every context must be a nonempty string or dictionary of strings")
    return value


def top_functions(profile: cProfile.Profile, *, limit: int = 35) -> list[dict[str, Any]]:
    """Output only module basenames/function names; never private checkout paths."""
    records: list[dict[str, Any]] = []
    stats = cast(Any, pstats.Stats(profile)).stats
    for (filename, line, function), (primitive, calls, self_s, inclusive_s, _) in stats.items():
        path = filename.replace("\\", "/").lower()
        if "/pytuflow/_tmf/" not in path:
            continue
        records.append(
            {
                "module": filename.replace("\\", "/").rsplit("/", 1)[-1],
                "line": line,
                "function": function,
                "calls": calls,
                "primitive_calls": primitive,
                "self_seconds": round(self_s, 6),
                "inclusive_seconds": round(inclusive_s, 6),
            }
        )
    records.sort(key=lambda row: row["self_seconds"], reverse=True)
    return records[:limit]


def focus_functions(profile: cProfile.Profile) -> list[dict[str, Any]]:
    """Return requested hot-path records even when they miss the top-N list."""
    selected = {
        "fragment_dependencies.py": {
            "_key",
            "evaluate",
            "bindings",
            "translate",
            "_join",
        },
        "batch_dependencies.py": {
            "in_context_by_scope",
            "_append_dependency_record",
        },
        "context.py": {"in_context_by_scope", "translate"},
        "dataclasses.py": {"replace"},
    }
    records: list[dict[str, Any]] = []
    stats = cast(Any, pstats.Stats(profile)).stats
    for (filename, line, function), (primitive, calls, self_s, inclusive_s, _) in stats.items():
        module = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if function not in selected.get(module, set()):
            continue
        records.append(
            {
                "module": module,
                "line": line,
                "function": function,
                "calls": calls,
                "primitive_calls": primitive,
                "self_seconds": round(self_s, 6),
                "inclusive_seconds": round(inclusive_s, 6),
            }
        )
    records.sort(key=lambda row: (row["module"], row["line"], row["function"]))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tcf", type=Path, required=True, help="Existing local parsed-model TCF")
    parser.add_argument("--runs-json", type=Path, required=True, help="Private JSON array of run flags")
    parser.add_argument("--output", type=Path, required=True, help="New local report folder OUTSIDE this checkout")
    parser.add_argument("--cprofile", action="store_true", help="Include overhead-heavy Python function attribution")
    args = parser.parse_args()

    flags = load_run_flags(args.runs_json)
    output = args.output.absolute()
    root = Path(__file__).absolute().parents[1]
    if output.is_relative_to(root):
        raise ValueError("The report must be outside the source checkout")
    if output.exists():
        raise FileExistsError("The report folder must be new; do not overwrite existing evidence")

    from pytuflow import TCF

    model = TCF(args.tcf.absolute())
    probe = FragmentEvaluationProbe()
    profiler = cProfile.Profile() if args.cprofile else None
    try:
        with probe.observe():
            if profiler is not None:
                profiler.enable()
            try:
                fragments = model.collect_file_dependencies(flags)
            finally:
                if profiler is not None:
                    profiler.disable()
        # Untimed, independent complete parser contract. Same parsed model
        # ensures stable original UUIDs and allows exact public-run comparison.
        ordinary = model.collect_batch_dependencies(flags)
        if fragments.runs != ordinary.runs or not fragments.passed:
            raise RuntimeError("Full ordinary-versus-fragment run provenance parity failed")
        report = probe.snapshot(fragments)
        report["ordinary_full_run_parity"] = True
        report["parser_evaluations"] = fragments.fragment_evaluations
        report["parser_reuses"] = fragments.fragment_reuses
        report["note"] = "Instrumented diagnostics only; not a native or accepted production benchmark"
        if profiler is not None:
            report["profile_top_self_time"] = top_functions(profiler)
            report["profile_focus_functions"] = focus_functions(profiler)
            report["profile_warning"] = "Python profiling substantially distorts wall time and may include nested calls"
    except Exception:
        # Never publish an incomplete report as successful diagnostics.
        raise

    output.mkdir(parents=True, exist_ok=False)
    (output / "fragment_diagnostic.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(
        "Complete parity passed; anonymous fragment breakdown created. "
        f"Lookups={report['lookups']}, misses={report['misses']}, "
        f"hits={report['hits']}. Instrumented counts only."
    )


if __name__ == "__main__":
    main()
