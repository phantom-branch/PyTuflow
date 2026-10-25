"""A bounded external typing consumer for PyTUFLOW's installed wheel.

Static-check only. Do not execute this module: the examples use nonexistent
input files to exercise constructor signatures without running a solver.
"""

from pathlib import Path
from datetime import datetime
from typing import assert_type

from numpy import float64
from numpy.ma.core import MaskedConstant

from pytuflow import (
    Context,
    FVProject,
    HPCProject,
    NCGrid,
    ResData,
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
    assert_type(ResData().format(), str)
    assert_type(ResData().getTimeSeriesData('Channel_1', 'Q')[0], bool)
    assert_type(NCMesh(path), NCMesh)
    assert_type(XMDF(path, twodm=path), XMDF)
    assert_type(HPCProject, type[HPCProject])
    assert_type(FVProject, type[FVProject])
    assert_type(binary_registry.get("2026.1"), str)
    pytuflow_logging.set_logging_level("DEBUG")


def consume_legacy_payloads(reader: ResData) -> None:
    """Keep heterogeneous, polygon and missing-value returns visible to callers."""
    assert_type(reader.timesteps(), list[float | None] | list[datetime])
    assert_type(reader.load(Path("synthetic.tpc")), tuple[bool, str])
    assert_type(reader.getTimeSeriesData("channel", "CF")[2][1],
                list[float | str | None] | list[list[float | str | None]])
    value = reader.getTimeSeriesData("channel", "Q")[2][1][0]
    if not isinstance(value, list):
        # A numeric-looking result is not a promise that arithmetic is safe.
        value + 1  # type: ignore[operator]
    profile = reader.getLongProfileData("max", "Culverts and Pipes", "channel")[2]
    assert_type(profile, tuple[list[float | float64 | MaskedConstant],
                               list[float | float64 | MaskedConstant]]
                | list[list[tuple[float, float]]])
    if isinstance(profile, list):
        assert_type(profile[0][0], tuple[float, float])
    assert_type(reader.getPipes(), list[list[tuple[float, float] | tuple[()]]])
    assert_type(reader.referenceTime(), datetime | None)
