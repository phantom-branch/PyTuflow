"""Opt-in pytest recorder used only by run_regression.py, never auto-loaded.

Keep existing pytest warning policy and original assertions. Record the actual
collected IDs and all phases, and expose capability skips with exact IDs.
"""

import argparse
from collections import Counter
import importlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePath
import platform
import re
import subprocess
import sys
import traceback

import pytest


GROUP_PATHS = {
    "time_series": "tests/test_time_series.py",
    "python_mesh": "tests/test_map_output_pymesh.py",
    "tmf": "tests/tmf",
    "project": "tests/project",
    "fm": "tests/fm_lib",
    "qgis": "tests/test_map_output.py",
}
RUNTIME_MODULES = (
    "numpy", "pandas", "packaging", "dbfread", "pyproj", "h5py",
    "pyvista", "vtk", "geopandas", "shapely", "netCDF4", "rasterio",
    "pygltflib", "pyogrio",
)
OGR_TESTS = (
    "test_write_shp_points", "test_write_shp_lines", "test_write_gpkg_points",
    "test_write_gpkg_polygons", "test_write_mode_w_overwrites_layer",
    "test_write_mode_rplus_updates_existing_layer", "test_write_mode_rplus_creates_layer_if_missing",
    "test_auto_field_creation", "test_context_manager_closes_on_exit", "test_wkb_geometry_input",
)


def environment() -> dict:
    packages = {}
    # Respect sys.path order when --target dependencies are used locally.
    for distribution in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", distribution.metadata["Name"]).lower()
        packages.setdefault(name, distribution.version)
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
        "packages": dict(sorted(packages.items())),
    }


def capabilities(group: str) -> tuple[dict, dict, list[str]]:
    available, details, missing = {}, {}, []
    for name in (*RUNTIME_MODULES, "osgeo.ogr"):
        try:
            module = importlib.import_module(name)
            available[name] = True
            details[name] = {"origin": getattr(module, "__file__", None)}
        except Exception as error:
            available[name] = False
            details[name] = {"error": f"{type(error).__name__}: {error}"}
            if name in RUNTIME_MODULES:
                missing.append(name)
    if group == "qgis":
        try:
            from qgis.core import Qgis, QgsApplication, QgsProviderRegistry

            app = QgsApplication.instance() or QgsApplication([], False)
            app.initQgis()
            providers = QgsProviderRegistry.instance().providerList()
            available["qgis"] = "mdal" in providers
            details["qgis"] = {"version": Qgis.QGIS_VERSION, "providers": providers}
            if not available["qgis"]:
                missing.append("qgis MDAL provider")
            # Keep the real application alive; repeated provider shutdown can crash QGIS.
            capabilities.qgis_application = app
        except Exception as error:
            available["qgis"] = False
            details["qgis"] = {"error": f"{type(error).__name__}: {error}"}
            missing.append("qgis")
    return available, details, missing


def skip_contract(available: dict) -> dict[str, str]:
    allowed = {}
    if not available.get("osgeo.ogr"):
        allowed.update({
            f"tests/tmf/test_gis.py::TestOGRWrite::{name}": "Skipped: GDAL not available"
            for name in OGR_TESTS
        })
        # The inherited test silently returns without osgeo. Make that visible.
        allowed["tests/tmf/test_input.py::test_input_attrs_3"] = "Skipped: GDAL not available"
    if os.name != "posix":
        allowed["tests/tmf/test_fv_cf.py::test_load_command_with_absolute_fpath_linux"] = (
            "Skipped: Test is for linux only"
        )
    return allowed


def normalise_failure_signature(reason: str, source: PurePath, temporary: PurePath) -> str:
    """Remove only known per-run paths, preserving diagnostic path differences.

    Windows may expand a short username such as RUNNER~1 in Path.resolve().
    Relative diagnostics may also contain that alias without the original
    absolute prefix. Replace the exact generated temporary basename only at
    path-component boundaries; retain aliases, relative depth and filenames.
    """
    signature = reason
    for path, replacement in ((source, "<snapshot>"), (temporary, "<temporary>")):
        forms = {str(path), path.as_posix(), str(path).replace("\\", "\\\\")}
        for spelling in sorted(forms, key=len, reverse=True):
            signature = signature.replace(spelling, replacement)
    if temporary.name:
        component = rf"(?<=[\\/]){re.escape(temporary.name)}(?=[\\/])"
        signature = re.sub(component, "<temporary-name>", signature)
    return signature


class Recorder:
    def __init__(self, report: dict, source: Path, cache: Path):
        self.report = report
        self.source = source
        self.cache = cache
        self.patches = pytest.MonkeyPatch()

    def pytest_collection_modifyitems(self, items):
        for item in items:
            item.user_properties.append(("nodeid", item.nodeid))
            if item.nodeid == "tests/tmf/test_input.py::test_input_attrs_3" and not self.report["capabilities"]["osgeo.ogr"]:
                item.add_marker(pytest.mark.skip(reason="GDAL not available"))
        self.report["collected"] = [item.nodeid for item in items]

    def pytest_collectreport(self, report):
        if report.failed:
            self.report["collection_errors"].append({"nodeid": report.nodeid, "reason": str(report.longrepr)})
        elif report.skipped:
            # A skipped module could otherwise disappear before item collection.
            self.report["collection_errors"].append({"nodeid": report.nodeid, "reason": str(report.longrepr)})

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        result = yield
        event = result.get_result()
        record = self.report["tests"].setdefault(item.nodeid, {"outcome": "passed", "reason": "", "phases": {}})
        phase = {"outcome": event.outcome}
        if event.failed:
            phase["failure_type"] = type(call.excinfo.value).__name__ if call.excinfo else "UnknownFailure"
            phase["reason"] = str(call.excinfo.value) if call.excinfo else str(event.longrepr)
            signature = normalise_failure_signature(phase["reason"], self.source, self.cache.parent)
            record.update(
                outcome="failed" if event.when == "call" else "error",
                reason=phase["reason"], failure_type=phase["failure_type"],
                failure_signature=signature, phase=event.when,
            )
        elif event.skipped and record["outcome"] == "passed":
            reason = str(event.longrepr[2]) if isinstance(event.longrepr, tuple) else str(event.longrepr)
            record.update(outcome="xfail" if hasattr(event, "wasxfail") else "skipped", reason=reason)
            phase["reason"] = reason
        elif hasattr(event, "wasxfail") and record["outcome"] == "passed":
            record.update(outcome="xpass", reason=str(event.wasxfail))
        record["phases"][event.when] = phase

    @pytest.fixture(scope="session", autouse=True)
    def isolated_project_cache(self):
        from pytuflow.project.config import settings
        from pytuflow.project.template import manager

        self.patches.setattr(manager, "CACHE_ROOT", self.cache)
        self.patches.setattr(settings, "CACHE_ROOT", self.cache)
        original_run = subprocess.run

        def isolated_run(command, *args, **kwargs):
            # The three inspected legacy CLI sites use this precise command.
            # Preserve all arguments and do not intercept unrelated subprocesses.
            if isinstance(command, (list, tuple)) and list(command[:3]) == [sys.executable, "-m", "pytuflow.project"]:
                command = [
                    sys.executable, str(Path(__file__).with_name("project_cli.py")),
                    "--source-root", str(self.source), "--cache-root", str(self.cache),
                    "--", *command[3:],
                ]
            return original_run(command, *args, **kwargs)

        self.patches.setattr(subprocess, "run", isolated_run)
        yield
        self.patches.undo()


def main() -> int:
    # Dependency probes must not pre-import libraries into pytest's process:
    # that would bypass the inherited warnings-as-errors collection policy.
    if len(sys.argv) == 4 and sys.argv[1] == "--capability-probe":
        available, details, missing = capabilities(sys.argv[2])
        Path(sys.argv[3]).write_text(json.dumps({"available": available, "details": details, "missing": missing}), encoding="utf-8")
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=GROUP_PATHS, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--temporary", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.absolute()
    sys.path.insert(0, str(source))
    os.chdir(source)
    capability_path = args.temporary / "capabilities.json"
    capability_run = subprocess.run(
        [sys.executable, str(Path(__file__).absolute()), "--capability-probe", args.group, str(capability_path)],
        text=True, capture_output=True, timeout=180,
    )
    if capability_run.returncode != 0 or not capability_path.is_file():
        print(capability_run.stdout, capability_run.stderr)
        raise RuntimeError("Capability subprocess did not produce complete evidence")
    capability_result = json.loads(capability_path.read_text(encoding="utf-8"))
    available, details, missing = (capability_result[name] for name in ("available", "details", "missing"))
    report = {
        "required": True, "status": "pending", "pytest_exit_code": None,
        "collected": [], "tests": {}, "collection_errors": [],
        "junit": args.junit.name, "capabilities": available,
        "required_capabilities": [*RUNTIME_MODULES, *(["qgis"] if args.group == "qgis" else [])],
        "optional_capabilities": {"osgeo.ogr": "Legacy OGR-only TMF cases have explicit skip IDs; GeoPandas and pyogrio remain required"},
        "capability_details": details, "allowed_skips": skip_contract(available),
        "capability_probe_output": {"stdout": capability_run.stdout, "stderr": capability_run.stderr},
        "environment": environment(), "import_origin": None,
        "isolation": {"fixture_copy": str(source), "cache_root": str(args.temporary / "templates")},
    }
    result = 2
    try:
        if missing:
            report["status"] = "capability_unavailable"
            report["reason"] = "Missing required capabilities: " + ", ".join(missing)
        else:
            plugin = Recorder(report, source, args.temporary / "templates")
            command = [
                "-ra", "-q", "--tb=short", "-c", str(source / "pyproject.toml"),
                "-o", "cache_dir=" + str(args.temporary / "pytest-cache"),
                "--basetemp=" + str(args.temporary / "pytest-tmp"),
                "--junitxml=" + str(args.junit), GROUP_PATHS[args.group],
            ]
            report["pytest_arguments"] = command
            result = int(pytest.main(command, plugins=[plugin]))
            report["pytest_exit_code"] = result
            report["status"] = "collection_error" if report["collection_errors"] else "completed"
            package = sys.modules.get("pytuflow")
            report["import_origin"] = getattr(package, "__file__", None)
            if report["import_origin"] is None or not Path(report["import_origin"]).absolute().is_relative_to(source / "pytuflow"):
                report["status"] = "origin_error"
                report["reason"] = "Tests did not import PyTUFLOW from the selected source snapshot"
                result = 2
            if not report["collected"] or not args.junit.is_file():
                report["status"] = "incomplete"
                result = 2
    except Exception:
        report["status"] = "harness_error"
        report["reason"] = traceback.format_exc()
        result = 2
    finally:
        report["counts"] = dict(Counter(item["outcome"] for item in report["tests"].values()))
        report["collected_count"] = len(report["collected"])
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
