"""Exercise runner isolation and incomplete-result handling with tiny public fixtures."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci import run_regression
from ci.regression_probe import normalise_failure_signature


class FailureSignatureTests(unittest.TestCase):
    def signature(self, text: str, temporary_name: str = "pytuflow-tmf-aaaa1111") -> str:
        temporary = PureWindowsPath("C:/Users/RUNNER~1/AppData/Local/Temp") / temporary_name
        return normalise_failure_signature(text, temporary / "source", temporary)

    def test_windows_short_long_and_escaped_paths_have_stable_run_identity(self):
        template = (
            "assert WindowsPath('C:/Users/runneradmin/AppData/Local/Temp/{name}/source/model/flow.csv') "
            "== WindowsPath('C:/Users/RUNNER~1/AppData/Local/Temp/{name}/source/model/flow.csv')\n"
            "canonical='C:\\\\Users\\\\runneradmin\\\\AppData\\\\Local\\\\Temp\\\\{name}\\\\source\\\\model\\\\flow.csv'"
        )
        left = self.signature(template.format(name="pytuflow-tmf-aaaa1111"))
        right = self.signature(template.format(name="pytuflow-tmf-bbbb2222"), "pytuflow-tmf-bbbb2222")
        self.assertEqual(left, right)
        self.assertIn("C:/Users/runneradmin", left)
        self.assertIn("<snapshot>/model/flow.csv", left)
        self.assertIn("<temporary-name>", left)

    def test_relative_depth_alias_and_model_filename_remain_significant(self):
        path = r"Read File == ..\..\RUNNER~1\AppData\Local\Temp\pytuflow-tmf-aaaa1111\source\model\flow.csv"
        result = self.signature(path)
        self.assertIn(r"..\..\RUNNER~1", result)
        self.assertIn(r"<temporary-name>\source\model\flow.csv", result)
        self.assertNotEqual(result, self.signature(path.replace("flow.csv", "depth.csv")))
        self.assertNotEqual(result, self.signature(path.replace(r"..\..\RUNNER~1", r"..\..\..\RUNNER~1")))
        self.assertNotEqual(result, self.signature(path.replace("RUNNER~1", "runneradmin")))

    def test_only_exact_generated_directory_components_are_replaced(self):
        text = (
            "C:/model/not-pytuflow-tmf-aaaa1111/flow.csv; "
            "C:/model/pytuflow-tmf-aaaa1111-extra/flow.csv; "
            "C:/model/pytuflow-tmf-aaaa1111.csv; depth=0.75"
        )
        self.assertEqual(self.signature(text), text)

    def test_hexadecimal_values_and_filenames_remain_significant(self):
        for left, right in (
            ("Unsupported bitmask 0x10", "Unsupported bitmask 0x20"),
            ("Missing grid_0x10.asc", "Missing grid_0x20.asc"),
        ):
            self.assertEqual(self.signature(left), left)
            self.assertEqual(self.signature(right), right)
            self.assertNotEqual(self.signature(left), self.signature(right))


class RegressionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "repository"
        self.source.mkdir()
        for relative, contents in {
            "pytuflow/__init__.py": "sentinel = 'committed source'\n",
            "tests/fixtures/public.txt": "immutable reference\n",
            "tests/fm_lib/integration_tests/test_conversion.py": "# Original conversion test\n",
            "tests/fm_lib/common/compare_txt.py": "# Original text comparison helper\n",
        }.items():
            destination = self.source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents, encoding="utf-8")
        self.git("init", "--quiet")
        self.git("add", ".")
        self.git("-c", "user.name=Regression fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "Generated public test fixture")
        self.output = self.root / "reports"

    def git(self, *arguments: str) -> str:
        return subprocess.check_output(["git", "-C", str(self.source), *arguments], text=True, stderr=subprocess.STDOUT).strip()

    def arguments(self, *extra: str) -> list[str]:
        return [
            "run_regression.py", "--source", str(self.source), "--ref", "HEAD",
            "--label", "generated-fixture", "--report-dir", str(self.output), *extra,
        ]

    def invoke(self, *extra: str) -> int:
        with patch.object(sys, "argv", self.arguments(*extra)), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return run_regression.main()

    def write_probe_record(self, command: list[str], outcome: str = "passed") -> None:
        def argument(name: str) -> str:
            return command[command.index(name) + 1]

        record = {
            "required": True, "status": "completed", "pytest_exit_code": int(outcome != "passed"),
            "collected": ["tests/test_generated.py::test_fixture"],
            "tests": {"tests/test_generated.py::test_fixture": {"outcome": outcome}},
            "collection_errors": [], "counts": {outcome: 1},
            "junit": Path(argument("--junit")).name,
            "environment": {"python": "3.14.5", "platform": "Windows", "packages": {"pytest": "9.0.3"}},
        }
        Path(argument("--report")).write_text(json.dumps(record), encoding="utf-8")

    def test_snapshot_uses_commit_and_copies_fixtures_without_mutating_source(self):
        original = self.source / "pytuflow/__init__.py"
        original.write_text("sentinel = 'uncommitted work'\n", encoding="utf-8")
        before = self.git("status", "--porcelain")
        harness = self.root / "harness"
        for relative in run_regression.SHARED_TEST_FILES:
            target = harness / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Shared harness overlay\n", encoding="utf-8")
        snapshot = self.root / "snapshot"
        overlays = run_regression.snapshot(self.source, "HEAD", snapshot, harness)
        self.assertIn("committed source", (snapshot / "pytuflow/__init__.py").read_text(encoding="utf-8"))
        (snapshot / "tests/fixtures/public.txt").write_text("generated output\n", encoding="utf-8")
        self.assertEqual((self.source / "tests/fixtures/public.txt").read_text(encoding="utf-8"), "immutable reference\n")
        self.assertEqual(original.read_text(encoding="utf-8"), "sentinel = 'uncommitted work'\n")
        self.assertEqual(before, self.git("status", "--porcelain"))
        self.assertEqual(overlays, {
            relative: hashlib.sha256((harness / relative).read_bytes()).hexdigest()
            for relative in run_regression.SHARED_TEST_FILES
        })

    def test_duplicate_groups_are_refused_before_execution(self):
        with self.assertRaises(SystemExit) as result:
            self.invoke("--group", "tmf", "--group", "tmf")
        self.assertEqual(result.exception.code, 2)
        self.assertFalse((self.output / "report.json").exists())

    def test_stale_report_directory_is_refused_and_preserved(self):
        self.output.mkdir()
        stale = self.output / "report.json"
        stale.write_text("previous result", encoding="utf-8")
        with self.assertRaises(SystemExit) as result:
            self.invoke("--group", "tmf")
        self.assertEqual(result.exception.code, 2)
        self.assertEqual(stale.read_text(encoding="utf-8"), "previous result")

    def test_report_directory_inside_source_checkout_is_refused(self):
        self.output = self.source / "reports"
        with self.assertRaises(SystemExit) as result:
            self.invoke("--group", "tmf")
        self.assertEqual(result.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_missing_probe_report_cannot_be_a_successful_run(self):
        original_run = subprocess.run

        def run(command, *args, **kwargs):
            if len(command) > 1 and Path(command[1]).name == "regression_probe.py":
                return subprocess.CompletedProcess(command, 0)
            return original_run(command, *args, **kwargs)

        with patch.object(subprocess, "run", run):
            result = self.invoke("--group", "tmf")
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 1)
        self.assertEqual(report["raw_status"], "failed")
        self.assertEqual(report["groups"]["tmf"]["status"], "incomplete")

    def test_timeout_retains_failed_group_evidence(self):
        original_run = subprocess.run

        def run(command, *args, **kwargs):
            if len(command) > 1 and Path(command[1]).name == "regression_probe.py":
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return original_run(command, *args, **kwargs)

        with patch.object(subprocess, "run", run):
            result = self.invoke("--group", "tmf", "--timeout", "1")
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 1)
        self.assertEqual(report["groups"]["tmf"]["process_exit_code"], 124)
        self.assertIn("exceeded 1s timeout", (self.output / "tmf.log").read_text(encoding="utf-8"))

    def test_nonzero_child_exit_survives_completed_pytest_record(self):
        original_run = subprocess.run

        def run(command, *args, **kwargs):
            if len(command) > 1 and Path(command[1]).name == "regression_probe.py":
                self.write_probe_record(command)
                return subprocess.CompletedProcess(command, 1)
            return original_run(command, *args, **kwargs)

        with patch.object(subprocess, "run", run):
            result = self.invoke("--group", "tmf")
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 1)
        self.assertEqual(report["raw_status"], "failed")
        self.assertEqual(report["groups"]["tmf"]["pytest_exit_code"], 0)
        self.assertEqual(report["groups"]["tmf"]["process_exit_code"], 1)

    def test_source_mutation_is_detected_even_when_git_status_does_not_change(self):
        original = self.source / "pytuflow/__init__.py"
        original.write_text("sentinel = 'first uncommitted value'\n", encoding="utf-8")
        before = self.git("status", "--porcelain")
        original_run = subprocess.run

        def run(command, *args, **kwargs):
            if len(command) > 1 and Path(command[1]).name == "regression_probe.py":
                self.write_probe_record(command)
                original.write_text("sentinel = 'changed uncommitted value'\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)
            return original_run(command, *args, **kwargs)

        with patch.object(subprocess, "run", run):
            result = self.invoke("--group", "tmf")
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(before, self.git("status", "--porcelain"))
        self.assertEqual(result, 1)
        self.assertIs(report["source"]["checkout_unchanged"], False)

    def test_external_pytest_selection_and_plugins_do_not_reach_child(self):
        original_run = subprocess.run
        captured = {}

        def run(command, *args, **kwargs):
            if len(command) > 1 and Path(command[1]).name == "regression_probe.py":
                captured.update(kwargs["env"])
                self.write_probe_record(command)
                return subprocess.CompletedProcess(command, 0)
            return original_run(command, *args, **kwargs)

        with patch.dict(os.environ, {"PYTEST_ADDOPTS": "-k only_one_test", "PYTEST_PLUGINS": "unrelated_plugin"}), patch.object(subprocess, "run", run):
            self.invoke("--group", "tmf")
        self.assertFalse(captured.get("PYTEST_ADDOPTS"))
        self.assertFalse(captured.get("PYTEST_PLUGINS"))
        self.assertEqual(captured["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")

    def test_dependency_preflight_does_not_preimport_away_warning_errors(self):
        source = self.root / "warning-fixture"
        source.mkdir()
        (source / "pytuflow").mkdir()
        (source / "pytuflow/__init__.py").write_text("", encoding="utf-8")
        (source / "tests").mkdir()
        (source / "tests/test_time_series.py").write_text(
            "import pytuflow\nimport warning_dependency\ndef test_fixture():\n    assert True\n", encoding="utf-8",
        )
        (source / "warning_dependency.py").write_text(
            "import warnings\nwarnings.warn('intentional capability warning', UserWarning)\n", encoding="utf-8",
        )
        (source / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\nfilterwarnings = ["error"]\n', encoding="utf-8",
        )
        repository = Path(run_regression.__file__).absolute().parent.parent
        wrapper = self.root / "synthetic_probe.py"
        wrapper.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(repository)!r})\n"
            "from ci import regression_probe as probe\n"
            "probe.RUNTIME_MODULES = ('warning_dependency',)\n"
            "probe.__file__ = __file__\n"
            "raise SystemExit(probe.main())\n", encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(filter(None, (str(source), environment.get("PYTHONPATH", ""))))
        environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        environment.pop("PYTEST_ADDOPTS", None)
        environment.pop("PYTEST_PLUGINS", None)
        report_path = self.root / "warning-report.json"
        completed = subprocess.run([
            sys.executable, str(wrapper), "--group", "time_series", "--source-root", str(source),
            "--report", str(report_path), "--junit", str(self.root / "warning.xml"),
            "--temporary", str(self.root),
        ], env=environment, cwd=self.root, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(report_path.is_file(), completed.stdout + completed.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["capabilities"]["warning_dependency"])
        self.assertTrue(report["collection_errors"], report)
        self.assertIn("intentional capability warning", json.dumps(report["collection_errors"]))
        self.assertIn("intentional capability warning", report["capability_probe_output"]["stderr"])


if __name__ == "__main__":
    unittest.main()
