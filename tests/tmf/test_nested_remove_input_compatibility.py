"""Guard the upstream root-to-child remove-input API against W1 save regressions.

This is an existing upstream editing feature, not an undo redesign.
"""
from pathlib import Path

import pytest

from pytuflow._tmf.cf.tcf import TCF


@pytest.mark.parametrize("increment", [None, "auto"], ids=["inplace", "increment"])
def test_root_removes_input_in_loaded_child_and_saves_its_owner(
    tmp_path: Path, increment: str | None,
) -> None:
    root_path = tmp_path / "model_010.tcf"
    root_path.write_bytes(
        b"Geometry Control File == geom_a_001.tgc\n"
        b"Geometry Control File == geom_b_001.tgc\n"
    )
    child_a = tmp_path / "geom_a_001.tgc"
    child_b = tmp_path / "geom_b_001.tgc"
    child_a.write_bytes(b"Cell Size == 5\nSet Code == 1\n")
    untouched_bytes = b"Cell Size == 10\nSet Code == 2\n"
    child_b.write_bytes(untouched_bytes)

    model = TCF(root_path)
    refs = model.find_input("Geometry Control File", recursive=False)
    assert len(refs) == 2
    first = refs[0].cf[0]
    second = refs[1].cf[0]
    target = first.find_input("Set Code")[0]
    original_uuid = target.uuid

    # Original upstream wrongly traversed target.cf (empty for a setting)
    # instead of the encountered child-reference.cf.
    assert model.remove_input(target) is target
    assert target.uuid == original_uuid
    assert target.parent is first
    assert not first.find_input("Set Code")
    assert second.find_input("Set Code")[0].rhs == "2"
    assert model.dirty
    assert first.dirty
    assert not second.dirty

    model.write(increment)

    expected_root = tmp_path / ("model_011.tcf" if increment else "model_010.tcf")
    expected_a = tmp_path / ("geom_a_011.tgc" if increment else "geom_a_001.tgc")
    assert model.fpath == expected_root
    assert refs[0].cf[0] is first
    assert refs[1].cf[0] is second
    assert b"Set Code == 1" not in expected_a.read_bytes()
    assert b"Cell Size == 5" in expected_a.read_bytes()
    assert child_b.read_bytes() == untouched_bytes
    assert not (tmp_path / "geom_b_011.tgc").exists()
    assert b"geom_b_001.tgc" in expected_root.read_bytes()
    assert b"geom_a_" in expected_root.read_bytes()

    reloaded = TCF(expected_root)
    reloaded_refs = reloaded.find_input("Geometry Control File", recursive=False)
    reloaded_a, reloaded_b = (ref.cf[0] for ref in reloaded_refs)
    assert not reloaded_a.find_input("Set Code")
    assert reloaded_a.find_input("Cell Size")[0].rhs == "5"
    assert reloaded_b.find_input("Set Code")[0].rhs == "2"


@pytest.mark.parametrize("increment", [None, "auto"], ids=["inplace", "increment"])
def test_root_removes_exact_second_child_with_equal_commands(
    tmp_path: Path, increment: str | None,
) -> None:
    root_path = tmp_path / "model_010.tcf"
    root_path.write_bytes(
        b"Geometry Control File == geom_a_001.tgc\n"
        b"Geometry Control File == geom_b_001.tgc\n"
    )
    a_path = tmp_path / "geom_a_001.tgc"
    b_path = tmp_path / "geom_b_001.tgc"
    sibling_bytes = b"Cell Size == 5\nSet Code == 1\n"
    a_path.write_bytes(sibling_bytes)
    b_path.write_bytes(b"Cell Size == 10\nSet Code == 1\n")

    model = TCF(root_path)
    refs = model.find_input("Geometry Control File", recursive=False)
    first, second = (ref.cf[0] for ref in refs)
    sibling = first.find_input("Set Code")[0]
    target = second.find_input("Set Code")[0]
    assert target is not sibling
    assert target == sibling  # Inherited value equality must not select owner.
    assert model.remove_input(target) is target
    assert second.find_input("Set Code") == []
    assert first.find_input("Set Code")[0] is sibling
    assert target.parent is second
    assert second.dirty and not first.dirty
    model.write(increment)

    expected_root = tmp_path / ("model_011.tcf" if increment else "model_010.tcf")
    expected_b = tmp_path / ("geom_b_011.tgc" if increment else "geom_b_001.tgc")
    assert b"Set Code" not in expected_b.read_bytes()
    assert a_path.read_bytes() == sibling_bytes
    assert not (tmp_path / "geom_a_011.tgc").exists()
    reloaded = TCF(expected_root)
    parsed = reloaded.find_input("Geometry Control File", recursive=False)
    assert parsed[0].cf[0].find_input("Set Code")[0].rhs == "1"
    assert parsed[1].cf[0].find_input("Set Code") == []


def test_root_removes_exact_repeated_input_in_one_owner(tmp_path: Path) -> None:
    root_path = tmp_path / "model_010.tcf"
    root_path.write_bytes(b"Geometry Control File == geom_001.tgc\n")
    child_path = tmp_path / "geom_001.tgc"
    child_path.write_bytes(b"Set Code == 1\nSet Code == 1\n")
    model = TCF(root_path)
    child = model.find_input("Geometry Control File")[0].cf[0]
    first, second = child.find_input("Set Code")
    assert first == second and first is not second
    assert model.remove_input(second) is second
    assert child.find_input("Set Code") == [first]
    assert child.find_input("Set Code")[0] is first
    model.write(None)
    assert child_path.read_bytes().count(b"Set Code == 1") == 1
    assert len(TCF(root_path).find_input("Set Code")) == 1
