"""Minimal memoised context for immutable fragment projection.

Uses existing Context semantics for events, scenarios and Set Variable blocks.
No compiled control-tree, mutable input-group prototype or batch-command
template is constructed. Every cache is local to one run Context.
"""

from __future__ import annotations

from typing import Any

from .context import Context
from .scope import ScopeList


def raw_class_attribute(cls: type, name: str) -> object | None:
    """Inspect class dispatch without invoking a possibly custom descriptor."""
    for owner in type.__getattribute__(cls, "__mro__"):
        namespace = type.__getattribute__(owner, "__dict__")
        if name in namespace:
            return namespace[name]
    return None


class FragmentContextBase(Context):
    """Only the per-run scope/translation state needed by fragment projection."""

    def __init__(self, run_flags: str | dict[str, str], *, config: Any) -> None:
        self._batch_active = False
        self._batch_scopes: ScopeList | None = None
        self._batch_scope_decisions: dict[int, tuple[object, bool]] = {}
        self._batch_translations: dict[str, str] = {}
        self.translation_hits = 0
        self.translation_misses = 0
        self.scope_builds = 0
        self.scope_hits = 0
        super().__init__(run_flags, config=config)
        self._batch_active = True

    def _invalidate(self) -> None:
        self._batch_scopes = None
        self._batch_scope_decisions.clear()
        self._batch_translations.clear()

    def load_context_from_dict(self, context: dict) -> None:
        was_active = self._batch_active
        self._batch_active = False
        self._invalidate()
        try:
            super().load_context_from_dict(context)
        finally:
            self._invalidate()
            self._batch_active = was_active

    def load_events(self, event_db: Any) -> None:
        # Event definitions become visible sequentially while being loaded.
        was_active = self._batch_active
        self._batch_active = False
        self._invalidate()
        try:
            super().load_events(event_db)
        finally:
            self._invalidate()
            self._batch_active = was_active

    def load_variables(self, var_map: Any) -> None:
        self._invalidate()
        try:
            super().load_variables(var_map)
        finally:
            self._invalidate()

    @property
    def available_scopes(self) -> ScopeList:
        if not self._batch_active:
            return super().available_scopes
        if self._batch_scopes is None:
            self._batch_scopes = super().available_scopes
            self.scope_builds += 1
        else:
            self.scope_hits += 1
        return self._batch_scopes

    def in_context_by_scope(self, req_scope: ScopeList) -> bool:
        if not self._batch_active:
            return super().in_context_by_scope(req_scope)
        saved = self._batch_scope_decisions.get(id(req_scope))
        if saved is not None and saved[0] is req_scope:
            return saved[1]
        result = super().in_context_by_scope(req_scope)
        self._batch_scope_decisions[id(req_scope)] = (req_scope, result)
        return result
