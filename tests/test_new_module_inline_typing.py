"""Typing contract for newly implemented production helpers, Python 3.12 baseline.

These checks are deliberately source-only and do not import optional GIS
packages or alter runtime behaviour. New modules should expose complete
inline annotations, not companion .pyi files.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PACKAGE = Path(__file__).absolute().parents[1] / "pytuflow"
FULLY_TYPED_NEW_MODULES = (
    "_outputs/_backend_capability.py",
    "_tmf/compiled_dependency_plan.py",
    "_tmf/deferred_database.py",
    "_tmf/file_reference.py",
)


def _unannotated_signatures(tree: ast.Module) -> list[str]:
    """Return any callable signature missing an explicit type annotation."""
    untyped: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.returns is None:
            untyped.append(f"{node.name}: return annotation")
        positional = [*node.args.posonlyargs, *node.args.args]
        for argument in [*positional, *node.args.kwonlyargs]:
            if argument.arg in {"self", "cls"}:
                continue
            if argument.annotation is None:
                untyped.append(f"{node.name}: {argument.arg}")
        for argument in (node.args.vararg, node.args.kwarg):
            if argument is not None and argument.annotation is None:
                untyped.append(f"{node.name}: {argument.arg}")
    return untyped


@pytest.mark.parametrize("module", FULLY_TYPED_NEW_MODULES)
def test_new_helper_modules_use_complete_inline_annotations(module: str) -> None:
    path = PACKAGE / module
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path), feature_version=(3, 10))
    assert not _unannotated_signatures(tree), (
        f"{module}: incomplete inline annotations: "
        f"{_unannotated_signatures(tree)}"
    )
    assert not path.with_suffix(".pyi").exists(), (
        f"{module}: new production code must use inline typing"
    )


def test_deferred_database_type_only_imports_do_not_change_execution() -> None:
    path = PACKAGE / "_tmf/deferred_database.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any(node.module == "pandas" for node in imports)
    assert any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "TYPE_CHECKING"
        for node in tree.body
    )
