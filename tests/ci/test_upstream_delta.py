"""Small local-git tests of the read-only upstream scope inventory."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from ci.upstream_delta import classify, inventory, parse_name_status


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True,
    ).strip()


@pytest.fixture
def two_commits(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git(repo, "config", "user.email", "regression@example.invalid")
    git(repo, "config", "user.name", "Regression Test")
    (repo / "pytuflow").mkdir()
    (repo / "pytuflow" / "old.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "upstream")
    baseline = git(repo, "rev-parse", "HEAD")

    git(repo, "mv", "pytuflow/old.py", "pytuflow/new.py")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_example.py").write_text(
        "def test_example():\n    assert True\n", encoding="utf-8"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "candidate")
    return repo, baseline, git(repo, "rev-parse", "HEAD")


def test_status_parser_including_renames() -> None:
    entries = parse_name_status(b"R100\0old.py\0pytuflow/new.py\0A\0tests/test_example.py\0")
    assert entries == [
        {
            "status": "R100", "previous_path": "old.py",
            "path": "pytuflow/new.py", "category": "production",
        },
        {"status": "A", "path": "tests/test_example.py", "category": "tests"},
    ]


@pytest.mark.parametrize("bad", [b"M\0file.py", b"Z\0file.py\0", b"R100\0old.py\0"])
def test_invalid_diff_record_rejected(bad: bytes) -> None:
    with pytest.raises(ValueError):
        parse_name_status(bad)


def test_file_category_is_not_upstream_approval() -> None:
    assert classify("pytuflow/subsystem.py") == "production"
    assert classify("tests/contract.py") == "tests"
    assert classify(".github/workflows/test.yml") == "ci"
    assert classify("pyproject.toml") == "packaging"
    assert classify("agent_workstreams/handoff.md") == "documentation"
    assert classify("unclassified.bin") == "other"


def test_inventory_frozen_git_commits(two_commits: tuple[Path, str, str]) -> None:
    repo, upstream, candidate = two_commits
    report = inventory(repo, upstream, candidate)
    assert report["canonical_upstream_sha"] == upstream
    assert report["fork_candidate_sha"] == candidate
    assert report["upstream_ancestor_of_candidate"] is True
    assert report["changed_file_count"] == 2
    assert report["categories"] == {"production": 1, "tests": 1}
    assert report["status"] == "inventory_only"
    assert report["validated_test_results"] is False
    assert report["disposition"] == "human_review_required"
    assert not any(str(repo) in json.dumps(x) for x in report["changes"])


def test_cli_records_metadata_outside_checkout(two_commits: tuple[Path, str, str], tmp_path: Path) -> None:
    repo, upstream, candidate = two_commits
    output = tmp_path / "delta.json"
    script = Path(__file__).absolute().parents[2] / "ci" / "upstream_delta.py"
    proc = subprocess.run(
        [
            sys.executable, str(script), "--repository", str(repo),
            "--upstream-ref", upstream, "--candidate-ref", candidate,
            "--output", str(output),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["changed_file_count"] == 2
    assert "Inventory-only" in proc.stdout
    assert str(tmp_path) not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("blocked", ["inside", "existing", "dirty"])
def test_cli_rejects_unsafe_state(
    two_commits: tuple[Path, str, str], tmp_path: Path, blocked: str,
) -> None:
    repo, upstream, candidate = two_commits
    report = repo / "inside.json" if blocked == "inside" else tmp_path / "outside.json"
    if blocked == "existing":
        report.write_text("historical evidence", encoding="utf-8")
    elif blocked == "dirty":
        (repo / "README.md").write_text("not committed\n", encoding="utf-8")
    script = Path(__file__).absolute().parents[2] / "ci" / "upstream_delta.py"
    proc = subprocess.run(
        [
            sys.executable, str(script), "--repository", str(repo),
            "--upstream-ref", upstream, "--candidate-ref", candidate,
            "--output", str(report),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0
    if blocked == "existing":
        assert report.read_text(encoding="utf-8") == "historical evidence"
    else:
        assert not report.exists()
