"""Public logging API and handler lifecycle regression tests for W7."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _run_python(source: str, *, log_directory: Path | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if log_directory is not None:
        environment["PYTUFLOW_W7_LOG_DIR"] = str(log_directory)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True,
        check=False,
        text=True,
        env=environment,
        timeout=40,
    )


def _assert_success(process: subprocess.CompletedProcess[str]) -> None:
    assert process.returncode == 0, (
        f"exit={process.returncode}\nstdout={process.stdout}\nstderr={process.stderr}"
    )


def test_public_logging_levels_and_no_duplicate_console_handler() -> None:
    process = _run_python(
        """
        import logging
        import pytuflow
        from pytuflow import pytuflow_logging

        logger = logging.getLogger("pytuflow")
        owned = lambda: [
            h for h in logger.handlers
            if getattr(h, "_pytuflow_owned_console", False)
        ]
        assert len(owned()) == 1
        pytuflow_logging.set_logging_level("INFO")
        pytuflow_logging.set_logging_level("DEBUG")
        pytuflow.set_logging_level("DEBUG")
        assert logger.level == logging.DEBUG
        assert len(owned()) == 1
        assert owned()[0].level == logging.DEBUG
        logger.info("w7-info-probe")
        logger.debug("w7-debug-probe")
        """
    )
    _assert_success(process)
    assert process.stdout.count("w7-info-probe") == 1
    assert process.stdout.count("w7-debug-probe") == 1


def test_application_handler_is_not_reconfigured() -> None:
    process = _run_python(
        """
        import io
        import logging

        logger = logging.getLogger("pytuflow")
        stream = io.StringIO()
        application_handler = logging.StreamHandler(stream)
        application_handler.setLevel(logging.INFO)
        logger.addHandler(application_handler)

        import pytuflow
        from pytuflow import pytuflow_logging

        assert not any(
            getattr(h, "_pytuflow_owned_console", False)
            for h in logger.handlers
        )
        pytuflow_logging.set_logging_level("DEBUG")
        assert logger.level == logging.DEBUG
        assert application_handler.level == logging.INFO
        assert len(logger.handlers) == 1
        logger.info("application-handler-probe")
        assert "application-handler-probe" in stream.getvalue()
        """
    )
    _assert_success(process)


def test_rotating_file_handler_is_real_and_idempotent(tmp_path: Path) -> None:
    process = _run_python(
        """
        import logging
        import os
        from pathlib import Path
        from logging.handlers import RotatingFileHandler

        import pytuflow
        from pytuflow import pytuflow_logging

        directory = Path(os.environ["PYTUFLOW_W7_LOG_DIR"])
        logger = logging.getLogger("pytuflow")
        pytuflow_logging.set_logging_level("DEBUG", directory)
        pytuflow.set_logging_level("DEBUG", directory)

        owned = [
            handler for handler in logger.handlers
            if getattr(handler, "_pytuflow_owned_file", None)
        ]
        assert len(owned) == 1
        assert isinstance(owned[0], RotatingFileHandler)
        assert owned[0].maxBytes == 51200
        assert owned[0].backupCount == 2
        for _ in range(20):
            logger.info("W7-ROTATION-" + "x" * 3500)
        owned[0].flush()
        assert (directory / "pytuflow_logs.log").exists()
        assert (directory / "pytuflow_logs.log.1").exists()
        """,
        log_directory=tmp_path,
    )
    _assert_success(process)


def test_missing_logging_directory_fails_without_new_handler(tmp_path: Path) -> None:
    process = _run_python(
        """
        import logging
        import os
        from pathlib import Path
        from pytuflow import pytuflow_logging

        missing = Path(os.environ["PYTUFLOW_W7_LOG_DIR"]) / "missing"
        try:
            pytuflow_logging.set_logging_level("INFO", missing)
        except ValueError as exception:
            assert "does not exist" in str(exception)
        else:
            raise AssertionError("Missing log directory was accepted")

        assert not any(
            getattr(handler, "_pytuflow_owned_file", None)
            for handler in logging.getLogger("pytuflow").handlers
        )
        """,
        log_directory=tmp_path,
    )
    _assert_success(process)


def test_public_logging_annotation_resolves() -> None:
    process = _run_python(
        """
        from typing import Literal, get_args, get_origin, get_type_hints

        from pytuflow import pytuflow_logging
        from pytuflow._tmf.logging_ import set_logging_level as legacy_logging

        annotation = get_type_hints(pytuflow_logging.set_logging_level)["level"]
        assert get_origin(annotation) is Literal
        assert set(get_args(annotation)) == {
            "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        }
        assert "level" in get_type_hints(legacy_logging)
        """
    )
    _assert_success(process)
