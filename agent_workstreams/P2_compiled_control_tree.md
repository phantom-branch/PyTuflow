# P2 agent prompt — Compile and evaluate immutable control-tree dependencies

**Target draft PR:** this branch targets `feat/batch-ordered-dependency-plan` (PR #6). Separate agent from P1 and P3.

## Agent instruction (execute without further clarification)

Inspect current PR #5/#6 code, `compiled_dependency_plan.py`,
`batch_dependencies.py`, `cf_run_state.py`, `inp_run_state.py`,
`context.py`, tests, profiling results and `batch_evaluation_workstreams.md`.
The objective is to avoid constructing the **same invariant input run-state
and command** for hundreds of distinct event/scenario combinations, not merely
speed up `stat()`, cloning or full-run duplicate-flag caching.

The present partial variable DAG and READ command templates are already in PR
#5. Build on them; do not replace PyTUFLOW with another TUFLOW parser.

**Implement in stages:**
1. Compile an immutable ordered tree/graph of input/conditional/variable/READ nodes from already-parsed BuildState once per batch. Each node retains input UUID, original ordinal, owner, line number and relevant configuration/command role.
2. Track **transitive** dependencies on scenario slots, event flags, TEF/event placeholders, scoped/ordered `Set Variable` declarations, control-file branches, DEFINE, BC database activation and command settings. Reuse only a node for which context equivalence is provable. The key must contain every relevant input value plus active declaration/ordering when needed; unrelated flags must not defeat safe reuse.
3. Prove that reusable nodes cannot alter the command stream, variable map, mutable context, GIS layer selection or downstream database activations. Explicitly bypass unresolved `<<...>>`, `~`, dynamic `>>` GPKG selector, unknown sources, cycles, non-idempotent/specialised commands and any command lacking a complete dependency signature.
4. Reduce repeated `InputRunState` and full `Command` allocations in the opt-in batch API when invariance is proven, while preserving per-run provenance in immutable `BatchInputReference`, `BatchInputCommand`, activation and source records. Return distinct mutable state if ever exposed; do not leak mutable prototypes.
5. Preserve stable invalid/error handling: one failed run has NO partial references. A later new batch after changes to the parsed model recompiles and sees the changes. No filesystem/GIS probe after initial parse.
6. Add focused graph/normalisation/branch/regression tests for 500 **distinct** event flags, nested TGC/TBC/ECF, scenario-specific variables, TEF expansion, conflicting scoped declarations, multiple active BC databases and failure/bypass cases. Instrument graph nodes/evaluations, constructors skipped and bypasses separately.
7. Compare complete per-run syntactic dependency **and provenance** sets in eager/individual-deferred/cached-batch where relevant, then hand off materialised parity to the ryan-tools consumer stack; do not claim that an identical partial inventory passes.

**Owned:** NEW `pytuflow/_tmf/compiled_control_tree.py`, `pytuflow/_tmf/compiled_dependency_plan.py`, `pytuflow/_tmf/batch_dependencies.py`, NEW `tests/test_compiled_control_tree.py`, relevant existing graph/batch tests.

**Avoid editing:** `cf/tcf_run_state.py` (P1 ownership), tutorial benchmark scripts (P3), consumer ryan-tools files. If unavoidable, leave a precise coordination note rather than conflicting independent pushes.

**Expected outcome:** measurable reduction in invariant node evaluation / command construction for **500 distinct flags**, without any omitted/extra reference, reordered activation, or unrecognised file/attribute dependency. If safe run-state elision cannot be proven for certain classes, leave them on the previous resolver and report the exact boundary; correctness outranks a speedup.

## Windows commands (PowerShell)

```powershell
git fetch origin
git switch feat/batch-compiled-control-tree
git pull --ff-only origin feat/batch-compiled-control-tree
git rev-parse HEAD
py -3.14 -m pip install -e . pytest
py -3.14 -m compileall -q pytuflow/_tmf
py -3.14 -m pytest -q tests/test_compiled_dependency_plan.py tests/test_batch_dependencies.py tests/test_batch_ordered_inputs.py tests/test_deferred_file_references.py tests/test_deferred_database_parity.py
py -3.14 -m pytest -q tests/tmf/test_cf_context.py tests/tmf/test_context.py tests/tmf/test_xs_db_from_cf.py
git diff --check
git status --short
```

Include any new focused test file in the actual validation command. Run Windows
3.12 parity via CI. Do not use the existing synthetic standalone benchmark to
claim representative performance; P3 owns the tutorial-based measurement.
You may use synthetic fixtures **only for differential correctness and
operation-counter assertions**, not for production speedup claims.

### Mandatory constraints

- Base this work on **PyTUFLOW PR #6**, branch `feat/batch-ordered-dependency-plan`; do **not** target `master` or commit to PR #5/#6.
- Keep this PR **draft** while developing. Do not merge, publish, repin a consumer dependency, run a TUFLOW executable or modify project inputs.
- Maintain eager and single-run deferred API behaviour, including per-run error/fail-closed semantics.
- Retain input UUIDs, original sequence/line/control-file owner, event/scenario/TEF scope and active BC declaration ordering.
- **All caches are invocation-local.** No disk, persistent, cross-invocation or module-global resource/result caching.
- No private SMB files or identifiers in GitHub, attachments, logs, test fixtures, benchmark outputs or CI. Only the separate SMB agent accesses that share. For public performance benchmarks, use the TUFLOW tutorial data, never a private model or synthetic performance fixture.
- Do not expand the Linux acceptance scope; Windows 3.12 and 3.14 are the parser CI targets. Unknown or unsupported cases must use the original resolver or fail closed.
- Do not use `Path.resolve()` merely to absolutise Windows/UNC paths; respect original lexical paths.
- Never treat syntactic input-reference parity as proof of GIS/BC/raster materialisation parity. The downstream ryan-tools PR #143 and supporting BC PR #151 own the consumer integration.

### Agent handoff requirements

Every implementation commit/PR update must include what changed, exact-head SHA,
focused test and CI links, exact parity results (including missing AND extra
records), counted constructor/lookup operations where applicable, known
limitations, and the next action. Do not merge and do not request Codex review
until the code scope is implementation-complete. If PR #6 advances while
working, fetch/reconcile it without overwriting parallel agents' files.

