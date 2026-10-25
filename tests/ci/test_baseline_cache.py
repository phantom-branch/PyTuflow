"""Content-addressed W5 baseline reuse must reject incomplete or changed evidence."""

from pathlib import Path
from unittest.mock import patch

import pytest

from ci.baseline_cache import cache_key, verify_baselines
from ci.compare_regression import ReportError


UPSTREAM = "a" * 40
FORK = "b" * 40


def _example_report(sha: str, label: str) -> dict:
    return {
        "label": label,
        "source": {"sha": sha, "checkout_unchanged": True},
        "environment": {"python": "3.14.9", "packages": {"pytest": "9.0.3"}},
        "harness": {
            "implementation_sha256": "harness-v1",
            "shared_test_overlays_sha256": {"fixture": "sha256"},
        },
        "groups": {
            "time_series": {}, "python_mesh": {}, "tmf": {}, "project": {},
            "fm": {}, "qgis": {},
        },
    }


def test_key_changes_on_source_environment_and_harness(tmp_path: Path) -> None:
    # Use deterministic mock state; this is a cache-identity test, not an
    # expensive installed-dependency or PyTUFLOW import test.
    with (
        patch("ci.baseline_cache.environment", return_value={"python": "3.14.9"}),
        patch("ci.baseline_cache.harness_fingerprint", return_value="sha-harness"),
        patch("ci.baseline_cache.expected_overlays", return_value={"fixture": "sha-fixture"}),
        patch.dict("os.environ", {"RUNNER_OS": "Windows", "ImageVersion": "20261024"}, clear=False),
    ):
        key = cache_key(tmp_path, UPSTREAM, FORK)
        assert key == cache_key(tmp_path, UPSTREAM, FORK)
        assert key != cache_key(tmp_path, UPSTREAM, "c" * 40)
        with patch("ci.baseline_cache.harness_fingerprint", return_value="new-harness"):
            assert key != cache_key(tmp_path, UPSTREAM, FORK)
        with patch("ci.baseline_cache.environment", return_value={"python": "3.12.10"}):
            assert key != cache_key(tmp_path, UPSTREAM, FORK)
        with patch.dict("os.environ", {"ImageVersion": "20261025"}):
            assert key != cache_key(tmp_path, UPSTREAM, FORK)


def test_cache_miss_or_missing_junit_cannot_authorise_reuse(tmp_path: Path) -> None:
    with pytest.raises(ReportError):
        verify_baselines(tmp_path, tmp_path, UPSTREAM, FORK)


@pytest.mark.parametrize(("property_name", "wrong"), [
    ("sha", "c" * 40),
    ("label", "candidate"),
    ("environment", {"python": "3.12"}),
    ("implementation_sha256", "changed"),
    ("shared_test_overlays_sha256", {"fixture": "changed"}),
])
def test_mismatched_cached_metadata_fails_closed(
    tmp_path: Path, property_name: str, wrong: object,
) -> None:
    upstream = _example_report(UPSTREAM, "upstream")
    fork = _example_report(FORK, "fork-baseline")
    target = upstream
    if property_name == "sha":
        target["source"]["sha"] = wrong
    elif property_name == "implementation_sha256":
        target["harness"]["implementation_sha256"] = wrong
    elif property_name == "shared_test_overlays_sha256":
        target["harness"]["shared_test_overlays_sha256"] = wrong
    else:
        target[property_name] = wrong

    def load_mock(path: Path, required_groups: list[str]) -> dict:
        assert required_groups == ["time_series", "python_mesh", "tmf", "project", "fm"]
        return upstream if path.parent.name == "upstream" else fork

    with (
        patch("ci.baseline_cache.load_report", side_effect=load_mock),
        patch("ci.baseline_cache.environment", return_value={"python": "3.14.9", "packages": {"pytest": "9.0.3"}}),
        patch("ci.baseline_cache.harness_fingerprint", return_value="harness-v1"),
        patch("ci.baseline_cache.expected_overlays", return_value={"fixture": "sha256"}),
    ):
        with pytest.raises(ReportError):
            verify_baselines(tmp_path, tmp_path, UPSTREAM, FORK)


def test_valid_matching_reports_can_be_reused(tmp_path: Path) -> None:
    reports = {
        "upstream": _example_report(UPSTREAM, "upstream"),
        "baseline": _example_report(FORK, "fork-baseline"),
    }

    def load_mock(path: Path, required_groups: list[str]) -> dict:
        assert path.name == "report.json"
        return reports[path.parent.name]

    with (
        patch("ci.baseline_cache.load_report", side_effect=load_mock),
        patch("ci.baseline_cache.environment", return_value={"python": "3.14.9", "packages": {"pytest": "9.0.3"}}),
        patch("ci.baseline_cache.harness_fingerprint", return_value="harness-v1"),
        patch("ci.baseline_cache.expected_overlays", return_value={"fixture": "sha256"}),
    ):
        verify_baselines(tmp_path, tmp_path, UPSTREAM, FORK)
