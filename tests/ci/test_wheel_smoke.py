"""Fail-closed checks for the installed-wheel acceptance harness."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).absolute().parents[2] / "ci" / "wheel_smoke.py"
SPEC = importlib.util.spec_from_file_location("wheel_smoke", SCRIPT)
wheel_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wheel_smoke)


class WheelSmokeTests(unittest.TestCase):
    def test_nonisolated_invocation_fails_without_importing_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = directory / "report.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--source-root", str(directory / "source"),
                 "--wheel", str(directory / "missing.whl"), "--report", str(report)],
                cwd=directory, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual([check["id"] for check in data["checks"]], ["isolated-outside-checkout"])
            self.assertIn("Python -I", data["checks"][0]["error"])
            self.assertFalse(data["complete"])

    def test_source_working_directory_is_rejected_even_with_isolated_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = directory / "report.json"
            result = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "--source-root", str(directory),
                 "--wheel", str(directory / "missing.whl"), "--report", str(report)],
                cwd=directory, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(len(data["checks"]), 1)
            self.assertIn("Working directory", data["checks"][0]["error"])

    def test_editable_distribution_is_rejected(self):
        distribution = SimpleNamespace(
            files=[Path("pytuflow/__init__.py")],
            read_text=lambda _: '{"dir_info": {"editable": true}}',
        )
        with patch.object(wheel_smoke.importlib.metadata, "distribution", return_value=distribution):
            with self.assertRaisesRegex(RuntimeError, "Editable installations"):
                wheel_smoke.check_installed_wheel(Path("source"), Path("unused.whl"))

    def test_missing_record_is_rejected(self):
        with patch.object(wheel_smoke.importlib.metadata, "distribution", return_value=SimpleNamespace(files=None)):
            with self.assertRaisesRegex(RuntimeError, "no RECORD"):
                wheel_smoke.check_installed_wheel(Path("source"), Path("unused.whl"))

    def test_modified_installed_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            package = directory / "installed" / "pytuflow"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("changed\n", encoding="utf-8")
            wheel = directory / "package.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("pytuflow/__init__.py", "original\n")
            distribution = SimpleNamespace(
                files=[Path("pytuflow/__init__.py")],
                read_text=lambda _: None,
                locate_file=lambda name: directory / "installed" / name,
            )
            with patch.object(wheel_smoke.importlib.metadata, "distribution", return_value=distribution):
                with self.assertRaisesRegex(RuntimeError, "differs from the supplied wheel"):
                    wheel_smoke.check_installed_wheel(directory / "source", wheel)

    def test_missing_packaged_resource_is_not_a_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(wheel_smoke.importlib.resources, "files", return_value=Path(temporary)):
                with self.assertRaises(FileNotFoundError):
                    wheel_smoke.check_json_resource("missing.json")

    def test_schema_without_feature_types_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schema = root / "project" / "empties" / "hpc_empties.json"
            schema.parent.mkdir(parents=True)
            schema.write_text('{"unexpected": 1}', encoding="utf-8")
            with patch.object(wheel_smoke.importlib.resources, "files", return_value=root):
                with self.assertRaisesRegex(RuntimeError, "schema lacks types"):
                    wheel_smoke.check_json_resource("project/empties/hpc_empties.json")


if __name__ == "__main__":
    unittest.main()
