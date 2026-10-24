"""Regression coverage for large control files and stalled scope traversal."""

import io
from pathlib import Path

import pytest

from pytuflow._tmf.cf.tcf import TCF
from pytuflow._tmf.inp.inputs import Inputs
from pytuflow._tmf.scope_writer import ScopeWriter


def test_scope_writer_accepts_20000_real_commands(tmp_path: Path) -> None:
    source = tmp_path / "large.tcf"
    text = "Timestep == 1\n" * 20_000
    source.write_text(text, encoding="utf-8", newline="")
    control_file = TCF(source)
    control_file.write(None)

    assert len(control_file.inputs) == 20_000
    assert source.read_bytes() == text.encode("utf-8")


def test_scope_writer_preserves_nested_scope_transitions(tmp_path: Path) -> None:
    source = tmp_path / "nested.tcf"
    text = (
        "If Scenario == DEV\n"
        "    Timestep == 1\n"
        "    If Event == WET\n"
        "        Timestep == 2\n"
        "    Else\n"
        "        Timestep == 3\n"
        "    End If\n"
        "Else If Scenario == EXG\n"
        "    Timestep == 4\n"
        "Else\n"
        "    Timestep == 5\n"
        "End If\n"
        "Timestep == 6\n"
    )
    source.write_text(text, encoding="utf-8", newline="")
    control_file = TCF(source)
    output = io.StringIO()

    control_file.preview(output)

    assert output.getvalue() == text


def test_scope_writer_rejects_stalled_iterator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "stalled.tcf"
    source.write_text("Timestep == 1\n", encoding="utf-8")
    control_file = TCF(source)
    inputs = control_file.inputs
    calls = 0

    def stalled_next():
        nonlocal calls
        calls += 1
        return inputs[0]

    monkeypatch.setattr(inputs, "next", stalled_next)
    with pytest.raises(RuntimeError, match="no progress.*input index 0"):
        for _ in ScopeWriter().inputs(io.StringIO(), inputs):
            pass

    assert calls == 1


def test_scope_writer_rejects_cursor_rewind(tmp_path: Path) -> None:
    source = tmp_path / "rewind.tcf"
    source.write_text("Timestep == 1\nTimestep == 2\n", encoding="utf-8")
    inputs = TCF(source).inputs
    iterator = ScopeWriter().inputs(io.StringIO(), inputs)
    next(iterator)
    next(iterator)
    inputs.rewind(2)

    with pytest.raises(RuntimeError, match="no progress.*input index 0"):
        next(iterator)


def test_scope_writer_allows_repeated_input_objects(tmp_path: Path) -> None:
    source = tmp_path / "repeated.tcf"
    source.write_text("Timestep == 1\n", encoding="utf-8")
    inp = TCF(source).inputs[0]
    inputs = Inputs([inp, inp, inp])

    assert [item for item, _ in ScopeWriter().inputs(io.StringIO(), inputs)] == [inp, inp, inp]
