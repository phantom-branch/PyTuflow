"""Read-only discovery of scenario and event requirements from parsed TUFLOW models.

A model's parsed scopes, event definitions and variable tokens can reveal
scenario/event *candidates* and referenced -sN/-eN slots. They cannot prove
that every combination is a valid simulation. This inventory does not create
contexts, run the solver or open additional model input files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ._tmf.cf.tcf import TCF

FlagKind = Literal["scenario", "event"]
EvidenceOrigin = Literal["conditional_scope", "event_definition", "model_default", "slot_reference"]

_SLOT = re.compile(r"~(?P<kind>[sSeE])(?P<index>[1-9]?)~")


@dataclass(frozen=True, slots=True)
class FlagEvidence:
    """One observed model declaration or flag reference, with provenance."""

    kind: FlagKind
    origin: EvidenceOrigin
    value: str | None
    slot: str | None
    owner_control_file: Path | None
    line_number: int | None
    negated: bool = False


@dataclass(frozen=True, slots=True)
class EventDefinition:
    """Named TEF event and its parsed substitution-variable names."""

    name: str
    variables: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FlagDiscovery:
    """A conservative inventory, not a list of verified runnable contexts.

    scenario_names include names mentioned in negative and else-if conditions,
    not just positive conditions. Event names can come from TEF definitions or
    conditional scopes. Slot references are usage evidence, not a mapping of
    specific scenario/event labels to flag positions.
    """

    scenario_names: tuple[str, ...]
    event_names: tuple[str, ...]
    scenario_slots: tuple[str, ...]
    event_slots: tuple[str, ...]
    default_scenarios: tuple[str, ...]
    event_definitions: tuple[EventDefinition, ...]
    evidence: tuple[FlagEvidence, ...]
    limitations: tuple[str, ...]


def _normalise_slot(match: re.Match[str]) -> tuple[FlagKind, str]:
    kind: FlagKind = "scenario" if match.group("kind").casefold() == "s" else "event"
    return kind, (("S" if kind == "scenario" else "E") + (match.group("index") or "1"))


def _read_slots(text: object) -> tuple[tuple[FlagKind, str], ...]:
    return tuple(dict.fromkeys(_normalise_slot(m) for m in _SLOT.finditer(str(text))))


def _values(text: str) -> tuple[str, ...]:
    """Lexically separate TUFLOW named alternatives, not run combinations."""
    return tuple(s.strip() for s in re.split(r"[|,]", text) if s.strip())


def _model_input_tree(model: TCF):
    """Walk already constructed build states once, without reading file paths."""
    visited = set()
    pending = [model]
    while pending:
        control = pending.pop()
        if id(control) in visited:
            continue
        visited.add(id(control))
        inputs = getattr(control, "inputs", ())
        if inputs is None:
            continue
        for inp in inputs:
            yield control, inp
            children = [
                child for child in getattr(inp, "cf", ())
                if hasattr(child, "inputs") and hasattr(child, "fpath")
            ]
            pending.extend(reversed(children))


def discover_model_flags(model: TCF) -> FlagDiscovery:
    """Inventory declared/referenced scenario and event flags from parsed data.

    No new control files are opened: only build-state inputs and the already
    assembled `TCF.config.event_db` are read. Does not infer slot-to-value
    assignments, generate Cartesian products, or certify any runnable context.
    """
    scenario_names: dict[str, str] = {}
    event_names: dict[str, str] = {}
    defaults: dict[str, str] = {}
    scenario_slots: dict[str, str] = {}
    event_slots: dict[str, str] = {}
    defined: list[EventDefinition] = []
    evidence: list[FlagEvidence] = []
    limitations: dict[str, str] = {}
    seen_evidence: set[FlagEvidence] = set()

    def record(
        kind: FlagKind, origin: EvidenceOrigin, *,
        value: str | None = None, slot: str | None = None,
        owner: Path | None = None, line: int | None = None, negated: bool = False,
    ) -> None:
        if value is not None:
            value = value.strip()
            if not value:
                return
            (scenario_names if kind == "scenario" else event_names).setdefault(
                value.casefold(), value
            )
        if slot is not None:
            (scenario_slots if kind == "scenario" else event_slots).setdefault(
                slot, slot
            )
        item = FlagEvidence(kind, origin, value, slot, owner, line, negated)
        if item not in seen_evidence:
            seen_evidence.add(item)
            evidence.append(item)

    def slots(text: object, owner: Path | None, line: int | None) -> None:
        for kind, slot in _read_slots(text):
            record(kind, "slot_reference", slot=slot, owner=owner, line=line)

    root_path = getattr(model, "fpath", None)
    root_path = Path(root_path) if root_path else None
    if root_path:
        slots(root_path.name, root_path, None)

    database = getattr(getattr(model, "config", None), "event_db", None)
    if database is not None:
        for name, values in database.items():
            event = str(name).strip()
            if not event:
                continue
            variables = (
                tuple(str(variable) for variable in values)
                if isinstance(values, dict) else ()
            )
            defined.append(EventDefinition(event, variables))
            record("event", "event_definition", value=event)
            for variable in variables:
                slots(variable, None, None)

    for control, inp in _model_input_tree(model):
        origin = getattr(getattr(inp, "_command", None), "parent", None)
        owner = Path(origin) if origin else getattr(control, "fpath", None)
        owner = Path(owner) if owner else None
        line = getattr(inp, "line_number", None)
        line = line if isinstance(line, int) and line > 0 else None
        lhs = str(getattr(inp, "lhs", "") or "").strip().casefold()
        rhs = str(getattr(inp, "rhs", "") or "")

        # Model Scenarios defaults belong to the setup, not to a user-selected
        # -s1/-s2 slot. They are not a schedule of runs.
        if lhs == "model scenarios":
            for option in _values(rhs):
                defaults.setdefault(option.casefold(), option)
                record("scenario", "model_default", value=option, owner=owner, line=line)

        slots(rhs, owner, line)
        for scope in getattr(inp, "scope", ()) or ():
            kind_name = str(getattr(scope, "type", "")).strip().casefold()
            if kind_name not in {"scenario", "event"}:
                continue
            kind: FlagKind = "scenario" if kind_name == "scenario" else "event"
            for option in getattr(scope, "names", ()) or ():
                # The parser's negative marker is retained on the Scope;
                # negative names still demonstrate a dependency on that name.
                if getattr(scope, "known", False) and option:
                    record(
                        kind, "conditional_scope", value=str(option),
                        owner=owner, line=line,
                        negated=bool(getattr(scope, "_neg", False)),
                    )
            variable = getattr(scope, "var", None)
            if variable:
                slots(variable, owner, line)
            if not getattr(scope, "known", True):
                limitations.setdefault(
                    "dynamic-scopes",
                    "Some scenario/event scopes depend on unresolved variables",
                )

        if lhs in {
            "geometry control file", "bc control file",
            "estry control file", "event file", "read file",
            "swmm control file", "ad control file",
        } and ("<<" in rhs or _read_slots(rhs)):
            limitations.setdefault(
                "conditional-includes",
                "Dynamic included control files may require particular run flags; "
                "only already parsed child control files are inspected",
            )

    return FlagDiscovery(
        tuple(scenario_names.values()),
        tuple(event_names.values()),
        tuple(sorted(scenario_slots.values())),
        tuple(sorted(event_slots.values())),
        tuple(defaults.values()),
        tuple(defined),
        tuple(evidence),
        tuple(limitations.values()),
    )
