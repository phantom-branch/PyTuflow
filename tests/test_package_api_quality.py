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

        missing = Path(os.environ["PYTUFLOW_W7_LOG_DIR"]) / "missing" / "pytuflow_logs.log"
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


def test_legacy_results_module_does_not_append_package_path() -> None:
    process = _run_python(
        """
        import sys
        from pathlib import Path

        previous = list(sys.path)
        import pytuflow
        from pytuflow import ResData, TPC, INFO

        assert callable(ResData)
        assert callable(TPC)
        assert callable(INFO)
        package_directory = str(Path(pytuflow.__file__).parent.absolute())
        assert package_directory not in sys.path[len(previous):]
        """
    )
    _assert_success(process)


def test_public_imports_leave_global_module_search_path_unchanged() -> None:
    process = _run_python(
        """
        import sys
        from pathlib import Path

        previous = list(sys.path)
        from pytuflow import TCF, TGC, Context, TuflowPath, XMDF, NCMesh
        import pytuflow

        for public_class in (TCF, TGC, Context, TuflowPath, XMDF, NCMesh):
            assert callable(public_class)
            assert public_class.__module__.startswith("pytuflow.")
        package_directory = Path(pytuflow.__file__).parent.absolute()
        added = sys.path[len(previous):]
        assert str(package_directory) not in added
        assert str(package_directory / "_tmf") not in added
        """
    )
    _assert_success(process)


def test_uncreated_legacy_log_filename_is_accepted(tmp_path: Path) -> None:
    """Legacy TMF callers pass a log filename which does not exist yet."""
    process = _run_python(
        """
        import logging
        import os
        from pathlib import Path
        from pytuflow._tmf.logging_ import set_logging_level

        directory = Path(os.environ["PYTUFLOW_W7_LOG_DIR"])
        requested = directory / "legacy-name-does-not-exist.log"
        assert not requested.exists()
        set_logging_level("INFO", requested)
        logging.getLogger("pytuflow").info("legacy-path-probe")
        logfile = directory / "pytuflow_logs.log"
        assert logfile.exists()
        assert "legacy-path-probe" in logfile.read_text(encoding="utf-8")
        assert not requested.exists()
        """,
        log_directory=tmp_path,
    )
    _assert_success(process)


def test_deferred_result_reader_public_exports_and_identity() -> None:
    process = _run_python(
        """
        import pytuflow
        from pytuflow import _outputs

        expected = ("INFO", "TPC", "GPKG1D", "GPKG2D", "GPKGRL",
                    "FMTS", "FVBCTide", "HydTablesCheck", "BCTablesCheck",
                    "CrossSections", "DATCrossSections", "XMDF", "NCMesh",
                    "CATCHJson", "DAT", "NCGrid", "LP2D", "MapOutput",
                    "TimeSeries", "TabularOutput", "Mesh", "Grid",
                    "GridMesh", "Output", "FormatConvention")
        assert set(expected) == set(_outputs.__all__)
        assert set(expected).issubset(set(pytuflow.__all__))
        for name in expected:
            root_value = getattr(pytuflow, name)
            package_value = getattr(_outputs, name)
            assert root_value is package_value, name
            assert root_value.__module__.startswith("pytuflow."), name
        assert "XMDF" in dir(pytuflow)
        assert "XMDF" in dir(_outputs)
        for mod in (pytuflow, _outputs):
            try:
                getattr(mod, "nonexistent_w7_reader")
            except AttributeError:
                pass
            else:
                raise AssertionError("Unknown result export unexpectedly resolved")
        """
    )
    _assert_success(process)


def test_legacy_star_import_still_exposes_result_readers() -> None:
    process = _run_python(
        """
        namespace = {}
        exec("from pytuflow import *", namespace)
        for name in ("TCF", "TPC", "INFO", "XMDF", "NCMesh", "NCGrid",
                     "HPCProject", "FVProject", "TuflowBinaries", "FMDAT"):
            assert name in namespace
            assert callable(namespace[name]), name
        """
    )
    _assert_success(process)


def test_supported_public_constructor_type_hints_resolve() -> None:
    process = _run_python(
        """
        from typing import get_type_hints

        from pytuflow import NCGrid, NCMesh, XMDF, Context, TuflowBinaries
        from pytuflow._pytuflow_types import PathLike

        for reader in (NCGrid, NCMesh, XMDF):
            annotations = get_type_hints(reader.__init__)
            assert annotations.get("fpath") == PathLike, reader.__name__
        context_hints = get_type_hints(Context.__init__)
        assert "context" in context_hints
        registry_hints = get_type_hints(TuflowBinaries.get)
        assert registry_hints.get("item") is str
        """
    )
    _assert_success(process)


def test_rotating_file_handler_deduplicates_lexical_aliases(tmp_path: Path) -> None:
    process = _run_python(
        """
        import logging
        import os
        from pathlib import Path
        from pytuflow import pytuflow_logging

        root = Path(os.environ["PYTUFLOW_W7_LOG_DIR"])
        logs = root / "logs"
        logs.mkdir()
        logger = logging.getLogger("pytuflow")
        pytuflow_logging.set_logging_level("INFO", logs)
        pytuflow_logging.set_logging_level("INFO", logs / ".." / "logs")

        if os.name == "nt":
            pytuflow_logging.set_logging_level("INFO", Path(str(logs).swapcase()))

        handlers = [
            h for h in logger.handlers
            if getattr(h, "_pytuflow_owned_file", None) is not None
        ]
        assert len(handlers) == 1, handlers
        logger.info("W7-DEDUPLICATION-SENTINEL")
        handlers[0].flush()
        contents = (logs / "pytuflow_logs.log").read_text(encoding="utf-8")
        assert contents.count("W7-DEDUPLICATION-SENTINEL") == 1
        """,
        log_directory=tmp_path,
    )
    _assert_success(process)
