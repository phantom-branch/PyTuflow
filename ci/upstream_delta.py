"""Read-only inventory of a frozen canonical-upstream -> fork candidate delta.

This tool does *not* test correctness or decide which changes belong upstream.
Run it only in a clean normal checkout with both exact commits available.
Output is path/category metadata: no absolute machine paths or test-success claims.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path
import subprocess
from typing import Any


_SHA = re.compile(r"^[0-9a-f]{40}$")


def run_git(repo: Path, *args: str) -> bytes:
    """Call git with separate arguments; never execute shell input."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    ).stdout


def commit_sha(repo: Path, reference: str) -> str:
    sha = run_git(repo, "rev-parse", "--verify", reference + "^{commit}").decode().strip()
    if not _SHA.fullmatch(sha):
        raise ValueError(f"Git did not return a complete commit SHA for {reference!r}")
    return sha


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Unable to test commit ancestry (exit {result.returncode})")
    return result.returncode == 0


def classify(path: str) -> str:
    """Classify file location only. No inferred upstream suitability."""
    if path.startswith("pytuflow/"):
        return "production"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith(("ci/", ".github/workflows/")):
        return "ci"
    if path.startswith(("docs/", "agent_workstreams/")) or path.endswith((".md", ".rst")):
        return "documentation"
    if path in {"pyproject.toml", "hatch_build.py", "MANIFEST.in", "requirements-dev.txt"}:
        return "packaging"
    return "other"


def parse_name_status(payload: bytes) -> list[dict[str, str]]:
    """Parse git diff --name-status -z including rename/copy source names."""
    if not payload:
        return []
    parts = payload.decode("utf-8", errors="surrogateescape").split("\0")
    if parts[-1] != "":
        raise ValueError("Incomplete NUL-terminated git diff record")
    parts.pop()
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(parts):
        status = parts[index]
        index += 1
        if not re.fullmatch(r"[ACDMRTUXB][0-9]*", status):
            raise ValueError(f"Unexpected git diff status: {status!r}")
        count = 2 if status.startswith(("R", "C")) else 1
        if len(parts) - index < count:
            raise ValueError("Truncated git diff filename record")
        names = parts[index:index + count]
        index += count
        if not all(names):
            raise ValueError("Git diff contains an empty path")
        target = names[-1]
        record = {"status": status, "path": target, "category": classify(target)}
        if count == 2:
            record["previous_path"] = names[0]
        entries.append(record)
    return entries


def inventory(repo: Path, upstream_ref: str, candidate_ref: str) -> dict[str, Any]:
    """Create a deterministic source-diff report without changing the checkout."""
    upstream = commit_sha(repo, upstream_ref)
    candidate = commit_sha(repo, candidate_ref)
    changes = parse_name_status(
        run_git(repo, "diff", "--name-status", "-z", "--find-renames", upstream, candidate)
    )
    groups = Counter(entry["category"] for entry in changes)
    return {
        "schema_version": 1,
        "status": "inventory_only",
        "validated_test_results": False,
        "canonical_upstream_sha": upstream,
        "fork_candidate_sha": candidate,
        "upstream_ancestor_of_candidate": is_ancestor(repo, upstream, candidate),
        "changed_file_count": len(changes),
        "categories": dict(sorted(groups.items())),
        "changes": changes,
        "disposition": "human_review_required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--upstream-ref", required=True)
    parser.add_argument("--candidate-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repository.absolute()
    report = args.output.absolute()
    if not (repo / ".git").exists():
        parser.error("Repository must be a normal Git checkout with .git metadata")
    if report.is_relative_to(repo):
        parser.error("Output must be outside the source checkout")
    if report.exists():
        parser.error("Output already exists; use a fresh report path")
    if run_git(repo, "status", "--porcelain", "-z"):
        parser.error("Source checkout is dirty; use an unchanged commit checkout")
    if not report.parent.is_dir():
        parser.error("Report parent directory must already exist")
    try:
        result = inventory(repo, args.upstream_ref, args.candidate_ref)
    except (subprocess.CalledProcessError, ValueError, RuntimeError) as exc:
        parser.error(f"Cannot inventory exact source refs: {exc}")
    with report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print(
        f"Inventory-only: {result['changed_file_count']} files, "
        f"{len(result['categories'])} categories; "
        f"upstream-ancestor={result['upstream_ancestor_of_candidate']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
