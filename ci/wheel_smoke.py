"""Validate an installed wheel without importing the source checkout.

Build with ``python -m build --no-isolation``, install the resulting wheel with
the job's interpreter, change to a temporary directory, then run::

    python -I /path/to/ci/wheel_smoke.py --source-root /path/to/checkout \
        --wheel /path/to/pytuflow.whl --report /path/to/wheel-smoke.json

No solver is launched. CLI probes redirect only the project's template cache
to a temporary directory; they invoke the installed module/entry-point target.
The script does not suppress warnings or substitute unavailable dependencies.
"""

import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.resources
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import tempfile
import traceback
import zipfile


PUBLIC_EXPORTS = (
    "TCF", "TGC", "TBC", "FVC", "ControlFile", "Context", "TuflowPath",
    "TPC", "INFO", "GPKG1D", "GPKG2D", "XMDF", "NCMesh", "NCGrid",
    "TimeSeries", "MapOutput", "HPCProject", "FVProject", "GXY", "FMDAT",
    "TuflowBinaries", "TuflowFVBinaries",
)
JSON_RESOURCES = (
    "_tmf/data/command_db.json",
    "_tmf/data/fv_blocks.json",
    "_fm/data/fm_units.json",
    "_outputs/data/ts_labels.json",
    "_outputs/data/data_type_name_alternatives.json",
    "project/data/defaults.json",
    "project/data/hpc_defaults.json",
    "project/data/fv_defaults.json",
    "project/data/rules.json",
    "project/data/empties/hpc_empties.json",
    "project/data/empties/fv_empties.json",
    "project/data/features/hpc/sgs.json",
    "project/data/features/fv/3d.json",
    "project/data/recipes/hpc/basic_2d.json",
    "project/data/recipes/fv/2d_hd.json",
)
TEXT_RESOURCES = (
    "project/data/templates/hpc/runs/${model_name}_${iter}.tcf",
    "project/data/templates/fv/runs/${model_name}_${iter}.fvc",
)


def require(condition: bool, message: str) -> None:
    """Keep checks active even when Python is run with optimisation enabled."""
    if not condition:
        raise RuntimeError(message)


def inside(path: Path, directory: Path) -> bool:
    return path.absolute().is_relative_to(directory.absolute())


def check_isolation(source_root: Path) -> dict:
    require(bool(sys.flags.isolated), "Run this script with Python -I.")
    require(not inside(Path.cwd(), source_root), "Working directory is inside the source checkout.")
    offending = [entry for entry in sys.path if entry and inside(Path(entry), source_root)]
    require(not offending, f"Source checkout is on sys.path: {offending}")
    return {"cwd": str(Path.cwd()), "isolated": sys.flags.isolated, "sys_path": sys.path}


def check_installed_wheel(source_root: Path, wheel: Path) -> dict:
    """Prove the imported distribution contains the exact supplied wheel files."""
    dist = importlib.metadata.distribution("pytuflow")
    files = dist.files
    require(bool(files), "Installed distribution has no RECORD file list.")
    direct_url = dist.read_text("direct_url.json")
    if direct_url:
        require(
            not json.loads(direct_url).get("dir_info", {}).get("editable", False),
            "Editable installations cannot establish wheel acceptance.",
        )
    recorded = {str(entry).replace("\\", "/") for entry in files}
    package_init = Path(dist.locate_file("pytuflow/__init__.py")).absolute()
    require(not inside(package_init, source_root), "Distribution points into the source checkout.")
    source_init = source_root / "pytuflow" / "__init__.py"
    if source_init.is_file() and package_init.is_file():
        require(not os.path.samefile(package_init, source_init), "Distribution aliases the source checkout.")
    require("pytuflow/__init__.py" in recorded, "Distribution RECORD omits pytuflow/__init__.py.")

    checked = []
    with zipfile.ZipFile(wheel) as archive:
        package_names = sorted(name for name in archive.namelist() if name.startswith("pytuflow/") and not name.endswith("/"))
        require("pytuflow/__init__.py" in package_names, "Wheel omits the public package.")
        for name in package_names:
            require(name in recorded, f"Installed RECORD omits wheel file: {name}")
            installed = Path(dist.locate_file(name)).absolute()
            require(inside(installed, package_init.parent), f"Installed file escapes package directory: {name}")
            require(installed.is_file(), f"Installed wheel file is missing: {name}")
            require(
                installed.read_bytes() == archive.read(name),
                f"Installed file differs from the supplied wheel: {name}",
            )
            checked.append(name)
    return {
        "distribution_version": dist.version,
        "distribution_package_init": str(package_init),
        "wheel": str(wheel),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "verified_package_file_count": len(checked),
        "direct_url": json.loads(direct_url) if direct_url else None,
    }


def check_public_imports(source_root: Path) -> dict:
    package = importlib.import_module("pytuflow")
    dist = importlib.metadata.distribution("pytuflow")
    expected = Path(dist.locate_file("pytuflow/__init__.py")).absolute()
    origin = Path(package.__file__).absolute()
    require(not inside(origin, source_root), f"Imported source checkout: {origin}")
    require(os.path.samefile(origin, expected), f"Import origin does not match installed distribution: {origin}")
    exports = {}
    for name in PUBLIC_EXPORTS:
        value = getattr(package, name)
        require(callable(value), f"Public export is not callable: {name}")
        exports[name] = value.__module__
    for name, module in tuple(sys.modules.items()):
        if name == "pytuflow" or name.startswith("pytuflow."):
            filename = getattr(module, "__file__", None)
            if filename:
                require(inside(Path(filename), expected.parent), f"Imported module is outside installed package: {name}: {filename}")
    require(package.__version__ == dist.version, "Imported version differs from installed metadata.")
    return {"pytuflow_file": str(origin), "version": package.__version__, "public_exports": exports}


def check_json_resource(name: str) -> dict:
    resource = importlib.resources.files("pytuflow").joinpath(name)
    data = resource.read_bytes()
    parsed = json.loads(data)
    require(isinstance(parsed, (dict, list)) and bool(parsed), f"Packaged JSON is empty or invalid: {name}")
    if "/empties/" in name:
        require(isinstance(parsed, dict) and bool(parsed.get("types")), f"Empty-file schema lacks types: {name}")
    return {"resource": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def check_text_resource(name: str) -> dict:
    resource = importlib.resources.files("pytuflow").joinpath(name)
    data = resource.read_bytes()
    text = data.decode("utf-8")
    require(bool(text.strip()) and "${" in text, f"Packaged template is empty or lacks variables: {name}")
    return {"resource": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def check_generated_model(directory: Path) -> dict:
    from pytuflow import TCF

    model_path = directory / "smoke.tcf"
    lines = ["Start Time == 0", "End Time == 1", "Timestep == 1"]
    model_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    model = TCF(model_path)
    require(model.loaded, "Generated control file did not load.")
    actual = [str(item) for item in model.inputs]
    require(actual == lines, f"Generated control-file inputs differ: {actual}")
    return {"input_count": len(actual), "inputs": actual, "solver_executed": False}


def cli_probe(kind: str, cache_root: Path) -> None:
    """Invoke installed CLI code with the same temporary cache fixture as tests."""
    from pytuflow.project.template import manager
    from pytuflow.project.config import settings

    manager.CACHE_ROOT = settings.CACHE_ROOT = cache_root
    sys.argv = ["pytuflow-project", "--help"]
    if kind == "module":
        runpy.run_module("pytuflow.project", run_name="__main__")
    else:
        entries = [
            entry for entry in importlib.metadata.distribution("pytuflow").entry_points
            if entry.group == "console_scripts" and entry.name == "pytuflow-project"
        ]
        require(len(entries) == 1, "Installed console entry point is missing or ambiguous.")
        require(entries[0].value == "pytuflow.project.__main__:main", "Unexpected project console entry point.")
        entries[0].load()()


def check_cli(kind: str, directory: Path) -> dict:
    command = [
        sys.executable, "-I", str(Path(__file__).absolute()), "--probe", kind,
        "--cache-root", str(directory / f"{kind}-templates"),
    ]
    result = subprocess.run(command, cwd=directory, text=True, capture_output=True, timeout=120)
    details = {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    require(result.returncode == 0, f"{kind} CLI help failed: {json.dumps(details)}")
    require("usage:" in result.stdout.lower() and "create" in result.stdout, f"{kind} CLI did not print project help: {details}")
    return details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--probe", choices=("module", "console-entry-point"), help=argparse.SUPPRESS)
    parser.add_argument("--cache-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        require(args.cache_root is not None, "CLI probe requires a temporary cache root.")
        cli_probe(args.probe, args.cache_root)
        return 0
    if any(value is None for value in (args.source_root, args.wheel, args.report)):
        parser.error("--source-root, --wheel and --report are required")
    source_root = args.source_root.absolute()
    wheel = args.wheel.absolute()
    report_path = args.report.absolute()
    report = {
        "schema_version": 1,
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "source_root": str(source_root),
        "dependencies": sorted(
            ({"name": dist.metadata["Name"], "version": dist.version} for dist in importlib.metadata.distributions()),
            key=lambda entry: (entry["name"] or "").lower(),
        ),
        "checks": [],
    }

    def check(name, function):
        try:
            details = function()
        except Exception as error:
            report["checks"].append({"id": name, "status": "failed", "error": str(error), "traceback": traceback.format_exc()})
            return False
        report["checks"].append({"id": name, "status": "passed", "details": details})
        return True

    isolated = check("isolated-outside-checkout", lambda: check_isolation(source_root))
    # Do not import anything after an isolation failure: that could run source
    # code and manufacture misleading wheel evidence.
    if isolated:
        installed = check("installed-wheel-files", lambda: check_installed_wheel(source_root, wheel))
        if installed:
            imported = check("public-imports-and-origin", lambda: check_public_imports(source_root))
            if imported:
                for name in JSON_RESOURCES:
                    check(f"json:{name}", lambda name=name: check_json_resource(name))
                for name in TEXT_RESOURCES:
                    check(f"template:{name}", lambda name=name: check_text_resource(name))
                with tempfile.TemporaryDirectory(prefix="pytuflow-wheel-") as temporary:
                    directory = Path(temporary)
                    check("generated-control-file", lambda: check_generated_model(directory))
                    for kind in ("module", "console-entry-point"):
                        check(f"cli-help:{kind}", lambda kind=kind: check_cli(kind, directory))
    failures = sum(check["status"] == "failed" for check in report["checks"])
    report["passed"] = len(report["checks"]) - failures
    report["failed"] = failures
    report["complete"] = failures == 0 and len(report["checks"]) == 6 + len(JSON_RESOURCES) + len(TEXT_RESOURCES)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "passed": report["passed"], "failed": failures, "complete": report["complete"]}))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
