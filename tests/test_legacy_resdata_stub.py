"""Parity checks for the legacy TUFLOW.py typing-only façade.

Avoid importing QGIS/MDAL or creating result files: the authoritative
contract is the original Python interface, not example model data.
"""

from __future__ import annotations

import ast
import inspect
import types
from pathlib import Path
from typing import get_args, get_origin

import numpy as np
import pytest


PACKAGE = Path(__file__).absolute().parents[1] / "pytuflow"
IMPLEMENTATION = PACKAGE / "TUFLOW.py"
STUB = PACKAGE / "TUFLOW.pyi"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _resdata(tree: ast.Module) -> ast.ClassDef:
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "ResData"]
    assert len(classes) == 1
    return classes[0]


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {node.name: node for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _signature_shape(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple:
    args = func.args
    positional = [argument.arg for argument in args.posonlyargs + args.args]
    keywords = [argument.arg for argument in args.kwonlyargs]
    return (
        tuple(argument.arg for argument in args.posonlyargs),
        tuple(positional),
        args.vararg.arg if args.vararg else None,
        tuple(keywords),
        args.kwarg.arg if args.kwarg else None,
        tuple(ast.unparse(expr) for expr in args.defaults),
        tuple(ast.unparse(expr) if expr is not None else None
              for expr in args.kw_defaults),
    )


def test_stub_covers_entire_legacy_resdata_method_surface() -> None:
    source = _methods(_resdata(_tree(IMPLEMENTATION)))
    stub = _methods(_resdata(_tree(STUB)))
    assert source, "Legacy reader methods were not found"
    assert set(stub) == set(source), "Stub omits or invents methods"
    for name, implementation_method in source.items():
        assert _signature_shape(stub[name]) == _signature_shape(implementation_method), name


def test_stub_preserves_implicit_runtime_module_exports() -> None:
    """TUFLOW.py has no __all__, and the root package imports it with *."""
    source = _tree(IMPLEMENTATION)
    stub = _tree(STUB)
    original_imports = set()
    explicit_stub_exports = set()
    for node in source.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            original_imports.update(alias.asname or alias.name.split(".")[0]
                                    for alias in node.names
                                    if not (alias.asname or alias.name).startswith("_"))
    for node in stub.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            explicit_stub_exports.update(alias.asname for alias in node.names
                                         if alias.asname and alias.asname == alias.name)
    original_public_classes = {node.name for node in source.body
                               if isinstance(node, ast.ClassDef)
                               and not node.name.startswith("_")}
    stub_public_classes = {node.name for node in stub.body
                           if isinstance(node, ast.ClassDef)
                           and not node.name.startswith("_")}
    assert original_public_classes == stub_public_classes == {"ResData"}
    assert original_imports <= explicit_stub_exports
    assert original_imports == {"os", "warnings", "ResData_GPKG"}


def test_stub_uses_only_python_310_syntax() -> None:
    ast.parse(STUB.read_text(encoding="utf-8"), feature_version=(3, 10))
    assert "Any" not in (alias.name for node in _tree(STUB).body
                         if isinstance(node, ast.ImportFrom)
                         for alias in node.names)


def _stub_namespace() -> dict:
    namespace = {"__package__": "pytuflow"}
    exec(compile(STUB.read_text(encoding="utf-8"), str(STUB), "exec"), namespace)
    return namespace


def _accepts(value: object, annotation: object) -> bool:
    """Check concrete synthetic outputs against the stub's nested containers."""
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is types.UnionType:
        return any(_accepts(value, item) for item in args)
    if origin is list:
        return isinstance(value, list) and all(_accepts(item, args[0]) for item in value)
    if origin is tuple:
        return (isinstance(value, tuple) and len(value) == len(args)
                and all(_accepts(item, kind) for item, kind in zip(value, args)))
    if annotation is float:
        return isinstance(value, (float, int))
    return isinstance(value, annotation)


def _reader(backend=None, format_="2016"):
    from pytuflow.TUFLOW import ResData

    with pytest.warns(DeprecationWarning):
        reader = ResData()
    reader._res = backend
    reader._format = format_
    return reader


def test_runtime_surface_signatures_and_root_identity() -> None:
    import pytuflow
    from pytuflow.TUFLOW import ResData

    assert pytuflow.ResData is ResData
    stub_class = _stub_namespace()["ResData"]
    for name in _methods(_resdata(_tree(STUB))):
        actual = inspect.signature(getattr(ResData, name))
        declared = inspect.signature(getattr(stub_class, name))
        assert [(p.name, p.kind, p.default) for p in actual.parameters.values()] == [
            (p.name, p.kind, p.default) for p in declared.parameters.values()
        ], name


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("strings", [False, True])
def test_series_preserves_strings_and_masked_values(nested, strings) -> None:
    from pytuflow.TUFLOW_results import ResData

    backend = ResData()
    backend.Data_1D.NF.Header = []
    values = np.ma.array([["A", "B"], ["C", "D"]] if strings else
                         [[1., 2.], [3., 4.]], mask=[[False, True], [True, False]])
    if nested:
        backend.Data_1D.CL.loaded = True
        backend.Data_1D.CL.Header = ["channel", "channel"]
        backend.Data_1D.CL.uID = ["channel"]
        backend.Data_1D.CL.nCols = [2]
        backend.Data_1D.CL.Values = values
        result_type = "CL"
    else:
        series = backend.Data_1D.CF if strings else backend.Data_1D.Q
        series.loaded = True
        series.Header = ["channel", "other"]
        series.Values = values
        result_type = "CF" if strings else "Q"
    # No H/V/E/Q/A timing data is needed to exercise the independent y conversion.
    if not strings and not nested:
        backend.Data_1D.Q.Values = np.ma.column_stack((np.zeros(2), np.arange(2), values[:, 0]))
        backend.Data_1D.Q.Header = ["step", "time", "channel"]
    reader = _reader(backend)
    error, message, (times, payload) = reader.getTimeSeriesData("channel", result_type, "1D")
    assert (error, message) == (False, "")
    expected = [["A", None], [None, "D"]] if strings else [[1., None], [None, 4.]]
    assert payload == (expected if nested else expected[0])
    assert _accepts((error, message, (times, payload)), _stub_namespace()["_SeriesResult"])


def test_csv_flow_regime_loader_retains_string_payload(tmp_path) -> None:
    from pytuflow.TUFLOW_results import ResData

    path = tmp_path / "regime.csv"
    path.write_text("Step,Time,F channel\n1,0,A\n2,1,B\n", encoding="utf-8")
    backend = ResData()
    backend.Data_1D.NF.Header = []
    assert backend.Data_1D.CF.load(str(path), "F", "synthetic") == (False, "")
    result = _reader(backend).getTimeSeriesData("channel", "CF", "1D")
    assert result == (False, "", ([], ["A", "B"]))
    assert _accepts(result, _stub_namespace()["_SeriesResult"])


def test_tpc_profile_returns_polygons_and_xy_without_conversion(monkeypatch) -> None:
    from pytuflow.TUFLOW_results import ResData

    backend = ResData()
    backend.LP.chan_list = ["channel"]
    backend.LP.culv_verts = [[(0., 1.), (2., 1.), (2., 3.), (0., 3.)]]
    backend.LP.dist_chan_inverts = [0., 2.]
    backend.LP.chan_inv = [1., 1.]
    backend.LP.Hmax = [np.float64(2.), np.ma.masked]
    monkeypatch.setattr(backend, "getLPConnectivity", lambda *_: (False, None))
    monkeypatch.setattr(backend, "getLPStaticData", lambda: (False, None))
    reader = _reader(backend)
    polygons = reader.getLongProfileData("max", "Culverts and Pipes", "channel")
    assert polygons == (False, "", backend.LP.culv_verts)
    assert polygons[2] is not backend.LP.culv_verts
    assert reader.getPipes() == backend.LP.culv_verts
    assert _accepts(polygons, _stub_namespace()["_ProfileResult"])
    for result_type in ("Bed Level", "H"):
        result = reader.getLongProfileData("max", result_type, "channel")
        assert _accepts(result, _stub_namespace()["_ProfileResult"])
    assert reader.getLongProfileData("max", "unknown", "channel")[0] is True


def test_unloaded_contracts_and_masked_timesteps() -> None:
    from pytuflow.TUFLOW_results import ResData

    reader = _reader()
    assert reader.timesteps() == []
    assert reader.referenceTime() is None
    assert reader.getTimeSeriesData("x", "Q") == (True, "No results loaded", ([], []))
    assert reader.getLongProfileData(0., "H", "x") == (True, "No results loaded", ([], []))
    assert reader.getPipes() == [[()]]
    backend = ResData()
    backend.Data_1D.H.loaded = True
    backend.Data_1D.H.Values = np.ma.array([[1., 0., 2.], [2., 1., 3.]],
                                         mask=[[False, False, False], [False, True, False]])
    reader._res = backend
    assert reader.timesteps() == [0., None]
    assert _accepts(reader.timesteps(), _stub_namespace()["_Times"])


def test_2013_and_gpkg_profile_shapes_and_reference_time() -> None:
    from datetime import datetime
    from pytuflow.TUFLOW_results2013 import ResData
    from pytuflow.tuflow_results_gpkg import ResData_GPKG

    old = ResData()
    old.LP.dist_chan_inverts = [0., 1.]
    old.LP.chan_inv = [2., 3.]
    assert old.getLongPlotXY("Bed Level", 0.) == (False, "", ([0., 1.], [2., 3.]))
    # 2013 has neither a reference_time attribute nor domain-aware timeSteps.
    with pytest.raises(AttributeError):
        _reader(old, "2013").referenceTime()
    with pytest.raises(TypeError):
        _reader(old, "2013").timesteps()
    with pytest.warns(DeprecationWarning):
        gpkg = ResData_GPKG()
    gpkg.LP.node_list = []
    gpkg.LP.dist_chan_inverts = []
    result = gpkg.getLongPlotXY("Water Level", 0.)
    assert result == (False, "", ([], []))
    assert _accepts(result, _stub_namespace()["_ProfileResult"])
    reader = _reader(gpkg)
    assert isinstance(reader.referenceTime(), datetime)
    assert reader.getPipes() == [[()]]


def test_gpkg_numeric_array_and_unloaded_timesteps() -> None:
    import sqlite3
    from pytuflow.tuflow_results_gpkg import ResData_GPKG

    with pytest.warns(DeprecationWarning):
        backend = ResData_GPKG()
    # An in-memory cursor lets the original cache path return its real ndarray.
    with sqlite3.connect(":memory:") as connection:
        backend._cur = connection.cursor()
        backend._saved_results[backend.create_key("channel", "Flow")] = np.array([1., 2.])
        success, values, message = backend.getTSData("channel", "Q", "1D")
        assert (success, message) == (True, "")
        assert isinstance(values, np.ndarray)
        assert values.tolist() == [1., 2.]
        # The façade always supplies domain=; the legacy GPKG method does not accept it.
        with pytest.raises(TypeError):
            _reader(backend).timesteps()
        backend._cur = None


def test_tpc_load_message_and_path_source(tmp_path) -> None:
    path = tmp_path / "empty.tpc"
    path.write_text("Simulation ID == synthetic\nReference Time == 2020-01-01 00:00:00\n", encoding="utf-8")
    reader = _reader()
    assert reader.load(path) == (False, "")
    assert reader.source() is path
