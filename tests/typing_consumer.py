"""A bounded external typing consumer for PyTUFLOW's installed wheel.

Static-check only. Do not execute this module: the examples use nonexistent
input files to exercise constructor signatures without running a solver.
"""

from pathlib import Path
from typing import assert_type

from pytuflow import (
    Context,
    FVProject,
    HPCProject,
    NCGrid,
    NCMesh,
    TCF,
    TuflowBinaries,
    XMDF,
    pytuflow_logging,
)


def consume_public_api(
    path: Path,
    model: TCF,
    context: Context,
    binary_registry: TuflowBinaries,
) -> None:
    """Check that selected public classes retain useful non-Any identities."""
    assert_type(model, TCF)
    assert_type(context, Context)
    assert_type(binary_registry, TuflowBinaries)
    assert_type(NCGrid(path), NCGrid)
    assert_type(NCMesh(path), NCMesh)
    assert_type(XMDF(path, twodm=path), XMDF)
    assert_type(HPCProject, type[HPCProject])
    assert_type(FVProject, type[FVProject])
    assert_type(binary_registry.get("2026.1"), str)
    pytuflow_logging.set_logging_level("DEBUG")
