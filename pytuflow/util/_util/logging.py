"""Configuration of the library-owned pytuflow logging handlers.

Applications may install their own handlers before importing pytuflow. Only
handlers marked as library-owned are modified by this module.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from ..._pytuflow_types import PathLike


LoggingLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LOG_FILE_NAME = "pytuflow_logs.log"
_MAX_LOG_BYTES = 51200
_BACKUP_COUNT = 2
_FILE_FORMAT = "%(asctime)s %(module)-25s %(funcName)-25s line:%(lineno)-4d %(levelname)-8s %(message)s"


def set_logging_level(
    level: LoggingLevel = "WARNING",
    log_to_file: PathLike | None = None,
) -> None:
    """Set the library logger level and configure an optional rotating log file.

    The library-owned console handler follows the configured level. Existing
    application-owned handlers retain their individual levels and formatters.
    Reconfiguring the same file is idempotent. `log_to_file` may be an
    existing directory or a path naming an existing or future file in an
    existing directory. The output filename is always pytuflow_logs.log for
    compatibility. Parent directories are never created implicitly.
    """
    logger = logging.getLogger("pytuflow")
    level_name = str(level).upper()
    if level_name not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level_name = "WARNING"
    log_level = getattr(logging, level_name)

    if log_to_file is not None:
        location = Path(log_to_file)
        if location.is_dir():
            directory = location
        elif location.parent.is_dir():
            # Historically callers could supply an as-yet-uncreated filename.
            # The library writes its fixed name beside that path.
            directory = location.parent
        else:
            raise ValueError(f"File path for log file handler does not exist at {log_to_file}")

        filename = (directory / _LOG_FILE_NAME).absolute()
        # Lexically collapse . and .. and Windows case aliases without
        # resolving symlinks, UNC paths or network targets.
        identifier = os.path.normcase(os.path.normpath(str(filename)))
        if not any(
            getattr(handler, "_pytuflow_owned_file", None) == identifier
            for handler in logger.handlers
        ):
            handler = RotatingFileHandler(
                filename,
                mode="a",
                maxBytes=_MAX_LOG_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter(_FILE_FORMAT))
            handler._pytuflow_owned_file = identifier
            logger.addHandler(handler)

    logger.setLevel(log_level)
    for handler in logger.handlers:
        if getattr(handler, "_pytuflow_owned_console", False):
            handler.setLevel(log_level)
