"""Gate fork-wide legacy TMF compatibility against a pinned upstream checkout.

A failing upstream baseline is reported, never concealed. Only *additional*
fork failures/skips, changed failure categories, or lost upstream test cases
fail this differential. New tests on the fork must pass.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET


def cases(file: Path) -> dict[tuple[str, str], tuple[str, str]]:
    result = {}
    for case in ET.parse(file).iter("testcase"):
        key = (case.get("classname", ""), case.get("name", ""))
        if key in result:
            raise ValueError(f"Duplicate JUnit test case: {key}")
        failures = [child for child in case if child.tag in {"failure", "error"}]
        skipped = [child for child in case if child.tag == "skipped"]
        if failures:
            item = failures[0]
            result[key] = ("failed", item.get("type", "") or (item.get("message", "").split(":")[0]))
        elif skipped:
            result[key] = ("skipped", "")
        else:
            result[key] = ("passed", "")
    if not result:
        raise ValueError(f"No tests recorded in {file}")
    return result


def compare(upstream: Path, fork: Path) -> tuple[list[str], dict[str, Counter]]:
    upstream_cases = cases(upstream)
    fork_cases = cases(fork)
    problems = []
    for key, baseline in upstream_cases.items():
        current = fork_cases.get(key)
        if current is None:
            problems.append(f"Removed upstream case: {key}")
        elif current[0] != baseline[0] and current[0] != "passed":
            problems.append(f"Regression: {key}: upstream={baseline}, fork={current}")
        elif baseline[0] == current[0] == "failed" and baseline[1] != current[1]:
            problems.append(f"Changed failure category: {key}: upstream={baseline}, fork={current}")
    for key, current in fork_cases.items():
        if key not in upstream_cases and current[0] != "passed":
            problems.append(f"New failing or skipped fork test: {key}: {current}")
    return problems, {
        "upstream": Counter(kind for kind, _ in upstream_cases.values()),
        "fork": Counter(kind for kind, _ in fork_cases.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--fork", type=Path, required=True)
    args = parser.parse_args()
    problems, counts = compare(args.upstream, args.fork)
    for name, summary in counts.items():
        print(f"{name}: " + ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    for problem in problems:
        print(problem)
    print(f"New compatibility regressions: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
