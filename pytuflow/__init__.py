import sys
import logging

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
from ._outputs import *
from ._tmf import *
from ._fm import GXY, FMDAT
from .util import TuflowBinaries, TuflowFVBinaries, pytuflow_logging, misc
from .project import HPCProject, FVProject


name = 'PyTuflow'
__version__ = '1.2.6'
