"""Copy isolation and extension behaviour at configuration snapshot boundaries."""

import pytest

from pytuflow._tmf.event import EventDatabase
from pytuflow._tmf.misc.case_insensitive_dict import CaseInsDict
from pytuflow._tmf.settings import (
    FVCConfig,
    TCFConfig,
    _FVParseContext,
    _ParseContext,
    from_config,
)


def ordinary_copy(source: EventDatabase) -> EventDatabase:
    """Pre-optimisation insertion contract, including case-alias merges."""
    result = EventDatabase()
    for key, value in source.items():
        result[key] = value.copy() if isinstance(value, dict) else value
    result.inputs = source.inputs.copy()
    return result


def test_copy_isolates_each_mapping_and_inputs_but_preserves_shallow_depth():
    nested = {"shared": []}
    source = EventDatabase(
        {"Rain": {"_RF_": "original", "nested": nested}, "Wind": {"_W_": "old"}}
    )
    declaration = object()
    source.inputs.append(declaration)
    first, second = source.copy(), source.copy()
    first["RAIN"]["_RF_"] = "changed"
    source["wind"]["_W_"] = "source changed"
    first["New"] = {"_N_": "new"}
    first.inputs.append(object())
    source.inputs.append(object())

    assert source["rain"]["_RF_"] == second["rain"]["_RF_"] == "original"
    assert first["wind"]["_W_"] == second["wind"]["_W_"] == "old"
    assert "new" not in source and "new" not in second
    assert list(second) == ["Rain", "Wind"]
    assert second.inputs == [declaration]
    assert first["rain"]["nested"] is second["rain"]["nested"] is nested


def test_constructor_case_aliases_still_merge_in_order():
    source = EventDatabase({"Rain": {"a": 1, "b": 2}, "RAIN": {"b": 3, "c": 4}})
    copied = source.copy()
    assert (
        list(copied.items())
        == list(ordinary_copy(source).items())
        == [("Rain", {"a": 1, "b": 3, "c": 4})]
    )
    assert copied["rAiN"] == {"a": 1, "b": 3, "c": 4}
    assert len(source) == 2


def test_copy_repairs_stale_lookup_index_without_mutating_source():
    source = EventDatabase({"Rain": {"a": 1}, "Wind": {"b": 2}})
    source.pop("Wind")
    dict.__setitem__(source, "Snow", {"c": 3})
    copied = source.copy()
    assert list(copied.items()) == list(ordinary_copy(source).items())
    assert "wind" not in copied and copied["snow"] == {"c": 3}
    assert "wind" in source and "snow" not in source


@pytest.mark.parametrize(
    "factory", [TCFConfig, FVCConfig, _ParseContext, _FVParseContext]
)
def test_config_snapshots_keep_event_state_independent_and_variables_shared(factory):
    source = factory()
    source.event_db["Rain"] = {"_RF_": "original"}
    source.event_db.inputs.append(object())
    source.variables["Alias"] = "<<~s1~>>"
    first, second = from_config(source), from_config(source)
    assert type(first) is (
        FVCConfig if factory in (FVCConfig, _FVParseContext) else TCFConfig
    )
    first.event_db["rain"]["_RF_"] = "first"
    first.event_db.inputs.clear()
    source.event_db["New"] = {"_N_": "source only"}
    assert (
        source.event_db["rain"]["_RF_"] == second.event_db["rain"]["_RF_"] == "original"
    )
    assert "new" not in first.event_db and "new" not in second.event_db
    assert len(second.event_db.inputs) == 1
    assert first.variables is second.variables is source.variables


def test_config_subclass_and_its_event_copy_hook_remain_authoritative():
    calls = []

    class ExtendedDatabase(EventDatabase):
        def items(self):
            calls.append("items")
            return super().items()

    class ExtendedConfig(TCFConfig):
        pass

    source = ExtendedConfig()
    source.event_db = ExtendedDatabase({"Rain": {"a": 1}})
    copied = from_config(source)
    assert type(copied) is ExtendedConfig
    assert type(copied.event_db) is EventDatabase
    assert calls == ["items"]


def test_instance_items_hook_is_called_once(monkeypatch: pytest.MonkeyPatch):
    source = EventDatabase({"Unused": {"x": 0}})
    calls = []

    def items():
        calls.append("items")
        return {"Selected": {"x": 1}}.items()

    monkeypatch.setattr(source, "items", items)
    copied = source.copy()
    assert calls == ["items"]
    assert list(copied) == ["Selected"]


@pytest.mark.parametrize("owner", [EventDatabase, CaseInsDict])
def test_modified_insertion_hook_is_not_bypassed(
    owner, monkeypatch: pytest.MonkeyPatch
):
    source = EventDatabase({"Rain": {"a": 1}, "Wind": {"b": 2}})
    calls = []
    original = owner.__setitem__

    def insert(self, key, value):
        calls.append(key)
        return original(self, key, value)

    monkeypatch.setattr(owner, "__setitem__", insert)
    expected = ordinary_copy(source)
    expected_calls = calls.copy()
    calls.clear()
    copied = source.copy()
    assert calls == expected_calls == ["Rain", "Wind"]
    assert list(copied.items()) == list(expected.items())


def test_custom_value_and_input_copy_callbacks_run_once():
    calls = []

    class Value(dict):
        def copy(self):
            calls.append("value")
            return super().copy()

    class Inputs(list):
        def copy(self):
            calls.append("inputs")
            return super().copy()

    source = EventDatabase({"Rain": Value(a=1)})
    source.inputs = Inputs([object()])
    copied = source.copy()
    assert calls == ["value", "inputs"]
    assert copied["rain"] == {"a": 1}
    assert copied.inputs is not source.inputs


def test_custom_string_key_keeps_normalisation_callbacks():
    calls = []

    class Key(str):
        def __str__(self):
            calls.append("str")
            return super().__str__()

    source = EventDatabase({Key("Rain"): {"a": 1}})
    calls.clear()
    expected = ordinary_copy(source)
    expected_calls = calls.copy()
    calls.clear()
    copied = source.copy()
    assert calls == expected_calls
    assert list(copied.items()) == list(expected.items())


def test_non_mapping_values_and_existing_alias_errors_are_preserved():
    shared = [object()]
    source = EventDatabase({"Rain": shared})
    assert source.copy()["rain"] is shared
    broken = EventDatabase({"Rain": None, "RAIN": {"a": 1}})
    with pytest.raises(AttributeError):
        ordinary_copy(broken)
    with pytest.raises(AttributeError):
        broken.copy()
