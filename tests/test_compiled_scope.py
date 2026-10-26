"""Compare compiled predicates to the original scope evaluator."""

from __future__ import annotations

from itertools import product
from typing import Any

from pytuflow._tmf.compiled_scope import ScopeProgram
from pytuflow._tmf.context import Context
from pytuflow._tmf.fragment_dependencies import ExpressionPool, _FragmentContext
from pytuflow._tmf.scope import Scope, ScopeList
from pytuflow._tmf.settings import TCFConfig


def test_literal_predicates_match_original_membership() -> None:
    program = ScopeProgram()
    for scenario, event, negative, kind in product(
        ("A", "B", "A | B", "!A"),
        ("Q10", "Q100"),
        (False, True),
        ("SCENARIO", "EVENT", "EVENT DEFINE"),
    ):
        scopes = ScopeList(
            [
                Scope(
                    kind,
                    ("!" if negative else "")
                    + ("A | B" if kind == "SCENARIO" else "Q10"),
                )
            ]
        )
        flags = {"s1": scenario, "e1": event}
        ordinary = Context(flags)
        compiled = _FragmentContext(flags, TCFConfig(), ExpressionPool(), program)
        assert compiled.in_context_by_scope(scopes) == ordinary.in_context_by_scope(
            scopes
        )


def test_event_definition_names_are_visible_in_order() -> None:
    ctx = _FragmentContext("-e1 rain", TCFConfig(), ExpressionPool(), ScopeProgram())
    scopes = ScopeList([Scope("EVENT", "_new_")])
    assert not ctx.in_context_by_scope(scopes)
    ctx.event_variables["_NEW_"] = "value"
    assert ctx.in_context_by_scope(scopes)
    ctx.event_variables.clear()
    assert not ctx.in_context_by_scope(scopes)


def test_flags_invalidate_membership() -> None:
    ctx = _FragmentContext("-s1 A", TCFConfig(), ExpressionPool(), ScopeProgram())
    scopes = ScopeList([Scope("SCENARIO", "B")])
    assert not ctx.in_context_by_scope(scopes)
    del ctx.S1
    ctx.var_map.pop("S1")
    ctx.load_context_from_dict({"s1": "B"})
    assert ctx.in_context_by_scope(scopes)


def test_unknown_variable_and_custom_scopes_fall_back() -> None:
    program = ScopeProgram()
    for scopes in (
        ScopeList([Scope("VARIABLE", "<<A>>")]),
        ScopeList([Scope("SCENARIO", "<<~s1~>>")]),
    ):
        assert program.compile(scopes) is None
    scope: Any = Scope("SCENARIO", "A")
    scope.resolvable = lambda: False
    assert program.compile(ScopeList([scope])) is None


def test_global_and_else_precedence_match_original() -> None:
    program = ScopeProgram()
    for flags in ("-s1 A", "-s1 B", "-s1 C", "-s1 A -s2 B"):
        ctx = _FragmentContext(flags, TCFConfig(), ExpressionPool(), program)
        ordinary = Context(flags)
        for scopes in (
            ScopeList([Scope("GLOBAL"), Scope("EVENT", "missing")]),
            ScopeList([Scope("SCENARIO", "!A"), Scope("SCENARIO", "B")]),
            ScopeList([Scope("SCENARIO", "!A"), Scope("SCENARIO", "!B")]),
            ScopeList([Scope("1D DOMAIN")]),
        ):
            assert ctx.in_context_by_scope(scopes) == ordinary.in_context_by_scope(
                scopes
            )
