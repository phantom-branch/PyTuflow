"""Differential contracts for the fragment-first, graph-independent evaluator.

This experiment deliberately leaves the legacy compiled batch API unchanged
for strict same-revision comparisons and benchmark controls.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import BatchDependencyRun as LegacyRun
from pytuflow._tmf.dependency_records import BatchDependencyRun
from pytuflow._tmf.fragment_dependencies import (
    ExpressionPool,
    _FragmentContext,
)
from pytuflow._tmf.settings import TCFConfig


def test_original_batch_dataclass_identity_is_preserved() -> None:
    assert BatchDependencyRun is LegacyRun


def test_fragment_context_has_no_compiled_batch_state() -> None:
    ctx = _FragmentContext("-s1 DEV -e1 Q10", TCFConfig(), ExpressionPool())
    assert not hasattr(ctx, "_batch_compiled_tree")
    assert not hasattr(ctx, "_batch_input_group_cache")
    assert not hasattr(ctx, "batch_command")
    assert not hasattr(ctx, "batch_input_state")
    assert ctx._batch_active


def test_conditional_variables_tef_and_database_ownership_match_batch(tmp_path: Path) -> None:
    (tmp_path / "event.tef").write_text(
        "Define Event == A\n BC Event Source == _event_ | alpha\nEnd Define\n"
        "Define Event == B\n BC Event Source == _event_ | beta\nEnd Define\n",
        encoding="utf-8",
    )
    (tmp_path / "tgc.tgc").write_text(
        "Read Grid Zpts == <<PREFIX>>_<<EVENT>>.tif\n"
        "If Event == B\n Read GIS Code == selected.shp\nEnd If\n",
        encoding="utf-8",
    )
    (tmp_path / "bc.csv").write_text(
        "Name,Source,Column 1,Column 2\nQ,flow__event_.csv,Time,Flow\n",
        encoding="utf-8",
    )
    (tmp_path / "model.tcf").write_text(
        "Event File == event.tef\n"
        "If Scenario == DEV\n Set Variable PREFIX == dev\n"
        "Else\n Set Variable PREFIX == exg\nEnd If\n"
        "Set Variable EVENT == _event_\n"
        "Geometry Control File == tgc.tgc\n"
        "BC Database == bc.csv\nRead GIS BC == bc.shp\n",
        encoding="utf-8",
    )
    model = TCF(tmp_path / "model.tcf")
    flags = [
        "-s1 DEV -e1 A",
        "-s1 EXG -e1 A",
        "-s1 DEV -e1 B",
        "-s1 EXG -e1 B",
    ]
    fast = model.collect_file_dependencies(flags)
    graph_disabled = model.collect_batch_dependencies(flags, compile_tree=False)
    uncached = model.collect_batch_dependencies(
        flags, cache_scopes=False, compile_tree=False
    )
    assert fast.passed and graph_disabled.passed and uncached.passed
    assert fast.fallback_runs == 0
    assert fast.runs == graph_disabled.runs == uncached.runs
    filenames = [
        {ref.path_pattern.name for ref in case.file_references}
        for case in fast.runs
    ]
    assert "dev_alpha.tif" in filenames[0]
    assert "exg_alpha.tif" in filenames[1]
    assert "dev_beta.tif" in filenames[2]
    assert "selected.shp" not in filenames[0]
    assert "selected.shp" in filenames[2]
    assert {
        source.path_pattern.name
        for case in fast.runs
        for source in case.database_sources
    } == {"flow_alpha.csv", "flow_beta.csv"}


def test_fallback_does_not_use_batch_graph_and_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "model.tcf").write_text(
        "Read Grid Zpts == keep.tif\n"
        "If Scenario == BAD\n PAUSE\nEnd If\n",
        encoding="utf-8",
    )
    model = TCF(tmp_path / "model.tcf")
    target = model.inputs[0]
    saved = target.context

    def custom(*args, **kwargs):
        return saved(*args, **kwargs)

    # The compiled-fragment safety guard must reject an input with a custom
    # dispatch hook; the fallback uses only the original RunState path.
    target.context = custom
    result = model.collect_file_dependencies(["-s1 BAD", "-s1 GOOD"])
    expected = model.collect_batch_dependencies(
        ["-s1 BAD", "-s1 GOOD"], cache_scopes=False, compile_tree=False
    )
    assert result.fallback_runs == 2
    assert result.runs == expected.runs
    assert result.runs[0].error is not None
    assert result.runs[0].file_references == ()
    assert result.runs[1].error is None


def test_fast_evaluation_never_opens_source_files_after_parse(tmp_path: Path) -> None:
    (tmp_path / "model.tcf").write_text(
        "Read Grid Zpts == grid_<<~s1~>>.tif\n",
        encoding="utf-8",
    )
    model = TCF(tmp_path / "model.tcf")
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
    ):
        result = model.collect_file_dependencies(["-s1 DEV", "-s1 EXG"])
    assert result.passed


def test_fresh_import_fragment_path_does_not_import_graph_modules(tmp_path: Path) -> None:
    model_path = tmp_path / "model.tcf"
    model_path.write_text("Read Grid Zpts == terrain.tif\n", encoding="utf-8")
    # A separate interpreter is essential: other test modules may have
    # already imported the legacy batch collector in this test process.
    script = """
import importlib.abc, sys
blocked = {
    'pytuflow._tmf.batch_dependencies',
    'pytuflow._tmf.compiled_control_tree',
    'pytuflow._tmf.compiled_dependency_plan',
    'pytuflow._tmf.group_input_reuse',
}
class BlockGraph(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in blocked:
            raise RuntimeError('unexpected legacy graph import: ' + fullname)
        return None
sys.meta_path.insert(0, BlockGraph())
from pytuflow import TCF
model = TCF(sys.argv[1])
result = model.collect_file_dependencies(['-e1 A', '-e1 B'])
assert result.passed and result.fallback_runs == 0
assert not (blocked & sys.modules.keys())
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(model_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
