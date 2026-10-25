"""Stable public result-reader exports with deferred module imports.

These names remain available through both `pytuflow._outputs` and the
root `pytuflow` package. Import each result reader when it is requested.
"""

from importlib import import_module
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    # Keep names visible to static analysers without loading readers at import.
    from .info import INFO as INFO
    from .tpc import TPC as TPC
    from .gpkg_1d import GPKG1D as GPKG1D
    from .gpkg_2d import GPKG2D as GPKG2D
    from .gpkg_rl import GPKGRL as GPKGRL
    from .fm_ts import FMTS as FMTS
    from .fv_bc_tide import FVBCTide as FVBCTide
    from .hyd_tables_check import HydTablesCheck as HydTablesCheck
    from .bc_tables_check import BCTablesCheck as BCTablesCheck
    from .cross_sections import CrossSections as CrossSections
    from .fm_dat import DATCrossSections as DATCrossSections
    from .xmdf import XMDF as XMDF
    from .nc_mesh import NCMesh as NCMesh
    from .catch_json import CATCHJson as CATCHJson
    from .dat import DAT as DAT
    from .nc_grid import NCGrid as NCGrid
    from .lp2d import LP2D as LP2D
    from .map_output import MapOutput as MapOutput
    from .time_series import TimeSeries as TimeSeries
    from .tabular_output import TabularOutput as TabularOutput
    from .mesh import Mesh as Mesh
    from .grid import Grid as Grid
    from .grid_mesh import GridMesh as GridMesh
    from .output import Output as Output
    from .pymesh import FormatConvention as FormatConvention


_EXPORT_MODULES = {
    "INFO": ".info",
    "TPC": ".tpc",
    "GPKG1D": ".gpkg_1d",
    "GPKG2D": ".gpkg_2d",
    "GPKGRL": ".gpkg_rl",
    "FMTS": ".fm_ts",
    "FVBCTide": ".fv_bc_tide",
    "HydTablesCheck": ".hyd_tables_check",
    "BCTablesCheck": ".bc_tables_check",
    "CrossSections": ".cross_sections",
    "DATCrossSections": ".fm_dat",
    "XMDF": ".xmdf",
    "NCMesh": ".nc_mesh",
    "CATCHJson": ".catch_json",
    "DAT": ".dat",
    "NCGrid": ".nc_grid",
    "LP2D": ".lp2d",
    "MapOutput": ".map_output",
    "TimeSeries": ".time_series",
    "TabularOutput": ".tabular_output",
    "Mesh": ".mesh",
    "Grid": ".grid",
    "GridMesh": ".grid_mesh",
    "Output": ".output",
    "FormatConvention": ".pymesh",
}

__all__ = tuple(_EXPORT_MODULES)


def __getattr__(name: str):
    try:
        module = _EXPORT_MODULES[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
