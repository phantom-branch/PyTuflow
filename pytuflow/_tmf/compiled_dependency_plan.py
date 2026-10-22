"""Immutable variable lineage and conservative batch command eligibility.

A plan is built once per collect_batch_dependencies() call, from parsed
Set Variable templates. It does not evaluate scopes, discover files or
rewrite the user's control-file values. Existing Context still decides
which declarations are active and how values expand for each run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VARIABLE = re.compile(r"<<([A-Za-z_][A-Za-z0-9_-]*)>>")


def _references(expression: str) -> tuple[str, ...] | None:
    """Return variables only when all token delimiters are well formed.

    GeoPackage layer syntax and event wildcards are intentionally excluded
    from the template optimiser. The ordinary deferred resolver handles them.
    """
    remaining = _VARIABLE.sub("", expression)
    if any(token in remaining for token in ("<<", ">>", "~")):
        return None
    return tuple(sorted({match.group(1).upper() for match in _VARIABLE.finditer(expression)}))


@dataclass(frozen=True, slots=True)
class CompiledReadDependency:
    """Syntax-only READ node with its proven transitive variable lineage."""

    direct_variables: tuple[str, ...]
    relevant_variables: tuple[str, ...]
    reusable: bool


@dataclass(frozen=True, slots=True)
class CompiledVariablePlan:
    """Acyclic portions of all parsed Set Variable declarations.

    Multiple scoped declarations with the same name are joined
    conservatively. One uncertain declaration invalidates that variable's
    reusable lineage, even if an individual run would not activate it.
    """

    dependencies: tuple[tuple[str, tuple[str, ...]], ...]
    reusable_variables: frozenset[str]
    transitive_dependencies: tuple[tuple[str, tuple[str, ...]], ...]

    @classmethod
    def from_assignments(
        cls, assignments: tuple[tuple[object, tuple[str, str]], ...] | None,
    ) -> CompiledVariablePlan:
        dependencies: dict[str, set[str]] = {}
        invalid: set[str] = set()
        for _, (raw_name, raw_value) in assignments or ():
            name = str(raw_name).upper()
            value = str(raw_value)
            # Context flag slots and event placeholders have special
            # semantics and may be supplied outside Set Variable. Never
            # certify their lineage solely from parsed declarations.
            if (
                not name
                or not name.replace("_", "A").replace("-", "A").isalnum()
                or re.fullmatch(r"[ES][0-9]?", name) is not None
            ):
                invalid.add(name)
            refs = _references(value)
            dependencies.setdefault(name, set())
            if refs is None:
                invalid.add(name)
            else:
                dependencies[name].update(refs)

        # A name is safe only when *every* possible declaration is known,
        # and each transitive dependency is itself safe. Cycles never enter.
        safe: set[str] = set()
        for _ in range(len(dependencies)):
            additions = {
                name for name, refs in dependencies.items()
                if name not in invalid and refs <= safe
            }
            next_safe = safe | additions
            if next_safe == safe:
                break
            safe = next_safe

        closures: dict[str, set[str]] = {}
        for name in sorted(safe):
            found: set[str] = set()
            pending = list(dependencies[name])
            while pending:
                current = pending.pop()
                if current not in found:
                    found.add(current)
                    pending.extend(dependencies[current])
            closures[name] = found

        return cls(
            tuple((k, tuple(sorted(v))) for k, v in sorted(dependencies.items())),
            frozenset(safe),
            tuple((k, tuple(sorted(v))) for k, v in sorted(closures.items())),
        )

    def compile_read(self, rhs: str) -> CompiledReadDependency:
        direct = _references(rhs)
        if direct is None:
            return CompiledReadDependency((), (), False)
        if not set(direct) <= self.reusable_variables:
            return CompiledReadDependency(direct, (), False)

        transitive = dict(self.transitive_dependencies)
        relevant = set(direct)
        for name in direct:
            relevant.update(transitive[name])
        return CompiledReadDependency(direct, tuple(sorted(relevant)), True)
