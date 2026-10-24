import sys
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Public type references remain statically discoverable while reader
    # implementations are imported only when accessed at runtime.
    from ._outputs import (
        INFO,
        TPC,
        GPKG1D,
        GPKG2D,
        GPKGRL,
        FMTS,
        FVBCTide,
        HydTablesCheck,
        BCTablesCheck,
        CrossSections,
        DATCrossSections,
        XMDF,
        NCMesh,
        CATCHJson,
        DAT,
        NCGrid,
        LP2D,
        MapOutput,
        TimeSeries,
        TabularOutput,
        Mesh,
        Grid,
        GridMesh,
        Output,
        FormatConvention,
    )


# Setup default logging handler for pytuflow logger.
# If the user has already configured a handler, this block is skipped.
pytuflow_logger = logging.getLogger('pytuflow')
if not pytuflow_logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(module)-30s line:%(lineno)-4d %(levelname)-8s %(message)s"))
    ch.setStream(sys.stdout)
    ch.setLevel(logging.WARNING)
    ch._pytuflow_owned_console = True
    pytuflow_logger.addHandler(ch)


from .TUFLOW import *
from . import _outputs as _outputs_api
from ._tmf import *
from ._fm import GXY, FMDAT
from .util import TuflowBinaries, TuflowFVBinaries, pytuflow_logging, misc
from .project import HPCProject, FVProject


name = 'PyTuflow'
__version__ = '1.2.6'


# Preserve the historic from-pytuflow import surface without eagerly loading
# every result reader. The existing TMF/model exports remain unchanged here.
_OUTPUT_EXPORTS = frozenset(_outputs_api.__all__)
__all__ = tuple(dict.fromkeys(
    [name for name in globals() if not name.startswith("_")]
    + list(_outputs_api.__all__)
))


def __getattr__(name: str):
    if name in _OUTPUT_EXPORTS:
        value = getattr(_outputs_api, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | _OUTPUT_EXPORTS)
