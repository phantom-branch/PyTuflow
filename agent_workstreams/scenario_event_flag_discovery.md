# Read-only scenario/event flag discovery

**Status:** new optional library capability; does not replace the authoritative TUFLOW parser, control-file context evaluation or simulation command planning.

The existing PyTUFLOW scenario example demonstrates how to interrogate parsed `Scope` objects, select a `TCF.context('-s1 EXG -e1 Q100')` and retrieve parsed `TCF.event_database()`. It does **not** automatically establish the supported flag list or certify all possible flag combinations.

## Use

```python
from pytuflow import TCF

tcf = TCF("model.tcf")
inventory = tcf.discover_flags()

print(inventory.scenario_names)  # observed If Scenario names and Model Scenarios defaults
print(inventory.event_names)     # TEF definitions and If Event names
print(inventory.scenario_slots)  # references to ~s~, ~s1~, ... ~s9~
print(inventory.event_slots)     # references to ~e~, ~e1~, ... ~e9~
print(inventory.event_definitions)
for source in inventory.evidence:
    print(source.kind, source.value, source.slot, source.owner_control_file, source.line_number)
```

An equivalent standalone call is `pytuflow.flag_discovery.discover_model_flags(tcf)`.

## Contract and boundaries

| Evidence | Interpretation | What it **cannot** prove |
| --- | --- | --- |
| `Scope('SCENARIO', 'EXG | DEV')` | `EXG` and `DEV` are referenced as scenario names | That either can be used in `-s1` specifically |
| Negated/Else scope | Name is mentioned in a conditional | That selecting it activates that branch |
| `Model Scenarios == EXG | DEV` | Default scenario names used in model setup | That each is a separate run configuration |
| `Define Event` in an already parsed TEF | Named event defined by the model and its variables | The required event flag position, duration, or compatible scenario |
| `<<~s2~>>` / `<<~e1~>>` in a parsed command | Slots `S2` / `E1` are referenced by syntax | What exact values are valid for those slots |
| Dynamic included control files | Only already loaded and parsed children are inventoried | That all possible dynamic include branches were inspected |

- **No Cartesian product:** discovery never constructs candidate `-sN`/`-eN` combinations. Consumers must supply the intended runs or use a separate, explicitly bounded planning API with complete provenance and validation.
- **No added I/O:** after parsing the model, discovery reads only existing build-state inputs/scopes and `config.event_db`; no `Path.stat/open/glob`, SQLite, QGIS, TUFLOW solver calls or re-parsing source files.
- **Snapshot semantics:** a discovery call reflects the model's currently parsed build state; reload/reparse after source file changes.
- **Read-only:** no mutation of `Input` instances, `Context`, `EventDatabase`, `TCFConfig` or cached branch evaluation.
- **Provenance:** `FlagEvidence` includes origin category, value/slot, owning control file and source line where the parser exposes one. Unresolved dynamic scope and include limitations are returned instead of invented values.
- **Ownership:** PyTUFLOW owns parsing and syntactic flag discovery. ryan-tools owns BAT/CMD run arguments, workflow-level scheduling, result display and optional comparison to declared inventory.
- **Compatibility:** this fork currently tests Windows Python 3.12 and 3.14 and Ubuntu Python 3.12. Keep code compatible with the separate curated upstream-C Python 3.11 baseline where practical.

## Acceptance

- Test real parsed TCF + TEF and simulated scope references, negative and else paths, default scenarios, `S1/S2/S9` and `E1/E9` tokens.
- Ensure identical repeat reads, no further filesystem probes and immutable records; source provenance and deduplication retained.
- Existing context/scopes and real TCF parser tests must remain unchanged.
- Dedicated hosted CI and wheel/import checks before approval. The currently separate optional physical validation PR #43 must not be retargeted, merged or altered by this PR.
