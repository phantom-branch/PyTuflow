"""Parity checks for the legacy TUFLOW.py typing-only façade.

Avoid importing QGIS/MDAL or creating result files: the authoritative
contract is the original Python interface, not example model data.
"""

from __future__ import annotations

import ast
from pathlib import Path


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
