"""Complete-record selection contracts for variable-dependent includes."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytuflow import TCF


def assert_parity(model: TCF, flags: list[str]):
    uncached = model.collect_batch_dependencies(flags, cache_scopes=False)
    cached = model.collect_batch_dependencies(flags)
    fragments = model.collect_file_dependencies(flags)
    assert uncached.runs == cached.runs == fragments.runs
    return fragments


@pytest.mark.parametrize(
    "command,suffix",
    [
        ("Geometry Control File", "tgc"),
        ("BC Control File", "tbc"),
        ("Geometry Control File", "trd"),
        ("Event File", "tef"),
        ("ESTRY Control File", "ecf"),
        ("Geometry Control File", "tscf"),
    ],
)
@pytest.mark.parametrize(
    "filename,assignments,slot",
    [
        ("<<~s1~>>", "", "s1"),
        ("<<~e1~>>", "", "e1"),
        (
            "<<Alias>>",
            "Set Variable Alias == <<Next>>\nSet Variable Next == <<~s1~>>\n",
            "s1",
        ),
    ],
)
def test_selected_source_identity(
    tmp_path: Path,
    command: str,
    suffix: str,
    filename: str,
    assignments: str,
    slot: str,
) -> None:
    for name in ("EXG", "DEV"):
        (tmp_path / f"design_{name}_03.{suffix}").write_text(
            f"Read GIS Code == {name}.shp\n"
        )
    top = tmp_path / "model.tcf"
    top.write_text(
        assignments
        + "Set Variable VarCellSize == 32\n"
        + f"{command} == design_{filename}_03.{suffix}\n"
    )
    model = TCF(top)
    result = assert_parity(
        model,
        [f"-{slot} EXG -e2 rain1", f"-{slot} DEV -e2 rain2", f"-{slot} EXG -e2 rain3"],
    )
    assert result.passed
    for run, name in zip(result.runs, ("EXG", "DEV", "EXG"), strict=True):
        names = [ref.path_pattern.name for ref in run.file_references]
        assert f"design_{name}_03.{suffix}" in names
        assert f"{name}.shp" in names
    assert result.fragment_reuses > 0


def test_nested_variable_selected_files(tmp_path: Path) -> None:
    for name in ("EXG", "DEV"):
        (tmp_path / f"nested_{name}.trd").write_text(f"Read GIS Code == {name}.shp\n")
    (tmp_path / "geometry.tgc").write_text(
        "Geometry Control File == nested_<<~s1~>>.trd\n"
    )
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == geometry.tgc\n")
    result = assert_parity(TCF(top), ["-s1 EXG", "-s1 DEV", "-s1 EXG"])
    assert result.passed
    assert [run.file_references[-1].path_pattern.name for run in result.runs] == [
        "EXG.shp",
        "DEV.shp",
        "EXG.shp",
    ]


def test_missing_selected_file_does_not_reuse_prior_result(tmp_path: Path) -> None:
    (tmp_path / "design_EXG.tgc").write_text("Read GIS Code == EXG.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == design_<<~s1~>>.tgc\n")
    model = TCF(top)
    result = assert_parity(model, ["-s1 EXG", "-s1 MISSING", "-s1 EXG"])
    assert result.runs[0].error is None
    assert result.runs[1].error
    assert result.runs[2].error is None
    assert not result.runs[1].ordered_inputs


def test_wildcard_include_preserves_all_matched_sources_and_order(
    tmp_path: Path,
) -> None:
    for name in ("first", "second"):
        (tmp_path / f"geometry_{name}.tgc").write_text(f"Read GIS Code == {name}.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == geometry_*.tgc\n")
    result = assert_parity(TCF(top), ["-e1 A", "-e1 B"])
    assert result.passed
    assert {ref.path_pattern.name for ref in result.runs[0].file_references} >= {
        "first.shp",
        "second.shp",
    }
    assert result.runs[0].ordered_inputs == result.runs[1].ordered_inputs


def test_selected_child_has_its_own_dependency_manifest(tmp_path: Path) -> None:
    from pytuflow._tmf.fragment_dependencies import _Plan

    (tmp_path / "design_EXG.tgc").write_text("Read GIS Code == fixed.shp\n")
    (tmp_path / "design_DEV.tgc").write_text("Read GIS Code == <<~e1~>>.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == design_<<~s1~>>.tgc\n")
    model = TCF(top)
    plan = _Plan(model)
    manifests = {
        Path(child.fpath).stem: plan.file_manifests[id(child)]
        for child in plan.children[id(model.inputs[0])]
    }
    assert manifests["design_EXG"].variables == ()
    assert manifests["design_DEV"].variables == ("E1",)
    result = assert_parity(model, ["-s1 EXG -e1 A", "-s1 EXG -e1 B", "-s1 DEV -e1 B"])
    assert result.passed
    assert result.fragment_reuses > 0


def test_assembled_event_token_uses_full_key(tmp_path: Path) -> None:
    from pytuflow._tmf.cf.cf_run_state import prepare_run_context
    from pytuflow._tmf.fragment_dependencies import _FragmentContext, _Plan

    (tmp_path / "events.tef").write_text(
        "Define Event == A\n BC Event Source == _rain_ | first\nEnd Define\n"
        "Define Event == B\n BC Event Source == _rain_ | second\nEnd Define\n"
    )
    top = tmp_path / "model.tcf"
    top.write_text(
        "Event File == events.tef\nSet Variable Part == ain\nRead GIS Code == _r<<Part>>_.shp\n"
    )
    model = TCF(top)
    result = assert_parity(model, ["-e1 A", "-e1 B", "-e1 A"])
    assert result.passed
    assert [r.file_references[-1].path_pattern.name for r in result.runs] == [
        "first.shp",
        "second.shp",
        "first.shp",
    ]
    plan = _Plan(model)
    ctx = _FragmentContext("-e1 A", model.config, plan.expressions, plan.scope_program)
    ctx._batch_variable_assignments = plan.assignments
    prepare_run_context(model, ctx)
    plan._key(model.inputs[-1], ctx)
    assert plan.manifest_fallbacks["event-substitution"]


def test_unknown_and_cyclic_lineage_use_full_key(tmp_path: Path) -> None:
    from pytuflow._tmf.fragment_dependencies import _Plan

    top = tmp_path / "model.tcf"
    top.write_text(
        "Set Variable A == <<B>>\nSet Variable B == <<A>>\nRead GIS Code == <<A>>.shp\n"
    )
    model = TCF(top)
    plan = _Plan(model)
    assert plan.manifests[id(model.inputs[-1])].fallback_reason == "cyclic-variable"
    result = assert_parity(model, ["-e1 A", "-e1 B"])
    assert not result.passed


def test_case_spelling_uses_the_existing_path_policy(tmp_path: Path) -> None:
    (tmp_path / "design_EXG.tgc").write_text("Read GIS Code == EXG.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == design_<<~s1~>>.tgc\n")
    result = assert_parity(TCF(top), ["-s1 EXG", "-s1 exg", "-s1 EXG"])
    assert result.passed
    assert [r.file_references[0].path_pattern.name for r in result.runs] == [
        "design_EXG.tgc",
        "design_exg.tgc",
        "design_EXG.tgc",
    ]


def test_dynamic_inline_read_file_uses_explicit_fallback(tmp_path: Path) -> None:
    for name in ("EXG", "DEV"):
        (tmp_path / f"design_{name}.trd").write_text(f"Read GIS Code == {name}.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Read File == design_<<~s1~>>.trd\n")
    result = assert_parity(TCF(top), ["-s1 EXG", "-s1 DEV"])
    assert result.fallback_runs == 2
    assert (
        result.fallback_reason
        == "Dynamic inline Read File requires the ordinary evaluator"
    )


def test_independent_optimisations_and_parent_full_key_have_complete_parity(
    tmp_path: Path,
) -> None:
    from typing import Any
    from unittest.mock import patch

    from pytuflow._tmf.fragment_dependencies import _Plan
    from tests.test_fragment_dependencies import model_files

    model = model_files(tmp_path)
    flags = ["-s1 DEV -e1 Q10", "-s1 EXG -e1 Q100", "-s1 DEV -e1 Q10"]
    expected = assert_parity(model, flags).runs
    original = _Plan.__init__
    for scopes, manifests in (
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    ):

        def configure(
            self: Any,
            source: Any,
            use_scopes: bool = scopes,
            use_manifests: bool = manifests,
        ) -> None:
            original(self, source, use_scopes=use_scopes, use_manifests=use_manifests)

        with patch.object(_Plan, "__init__", configure):
            assert model.collect_file_dependencies(flags).runs == expected


def test_different_selected_files_with_identical_contents_keep_uuid_provenance(
    tmp_path: Path,
) -> None:
    for name in ("EXG", "DEV"):
        (tmp_path / f"design_{name}.tgc").write_text(
            "Read GIS Code == same.gpkg >> codes\n"
        )
    top = tmp_path / "model.tcf"
    top.write_text(
        "Set Variable VarCellSize == 32\nGeometry Control File == design_<<~s1~>>.tgc\n"
    )
    result = assert_parity(TCF(top), ["-s1 EXG", "-s1 DEV", "-s1 EXG"])
    assert result.passed
    uuids = [run.ordered_inputs[-1].input_uuid for run in result.runs]
    assert uuids[0] != uuids[1]
    assert uuids[0] == uuids[2]


def test_ambiguous_cached_source_retains_ordinary_error(tmp_path: Path) -> None:
    from typing import Any

    (tmp_path / "geometry.tgc").write_text("Read GIS Code == code.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == geometry.tgc\n")
    model = TCF(top)
    include: Any = model.inputs[0]
    include.cf.append(include.cf[0])
    include._cf_loaded_paths.append(include._cf_loaded_paths[0])
    result = assert_parity(model, ["-e1 A", "-e1 B"])
    assert not result.passed
    assert all("Ambiguous cached child" in (run.error or "") for run in result.runs)


def test_changed_parsed_model_gets_fresh_manifests(tmp_path: Path) -> None:
    (tmp_path / "geometry.tgc").write_text("Read GIS Code == first.shp\n")
    top = tmp_path / "model.tcf"
    top.write_text("Geometry Control File == geometry.tgc\n")
    model = TCF(top)
    first = assert_parity(model, ["-e1 A"])
    model.inputs[0].cf[0].inputs[0].rhs = "second.shp"
    second = assert_parity(model, ["-e1 A"])
    assert first.runs[0].file_references[-1].path_pattern.name == "first.shp"
    assert second.runs[0].file_references[-1].path_pattern.name == "second.shp"


def test_custom_translation_hook_retains_full_key(tmp_path: Path) -> None:
    from unittest.mock import patch

    from pytuflow._tmf.context import Context
    from pytuflow._tmf.fragment_dependencies import _FragmentContext, _Plan

    top = tmp_path / "model.tcf"
    top.write_text("Read GIS Code == code.shp\n")
    model = TCF(top)
    original = Context.translate
    with patch.object(Context, "translate", lambda self, text: original(self, text)):
        plan = _Plan(model)
        ctx = _FragmentContext(
            "-e1 A", model.config, plan.expressions, plan.scope_program
        )
        assert plan._key(model.inputs[0], ctx)[1][0] != "manifest"
        assert plan.manifest_fallbacks["custom-context-translation"] == 1
    assert_parity(model, ["-e1 A", "-e1 B"])
