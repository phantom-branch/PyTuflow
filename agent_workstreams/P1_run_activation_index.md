# P1 agent prompt — Index per-run inputs and database activations

**Target draft PR:** create/open this branch against `feat/batch-ordered-dependency-plan` (PyTUFLOW PR #6). This branch is intended for ONE agent; do not edit sibling P2/P3 branches.

## Agent instruction (execute without further clarification)

Review current PR #6, PR #5, `batch_evaluation_workstreams.md`, and the latest tests/review comments. Implement a **per-evaluated-run ordered lookup index** so database accessors do not repeatedly traverse the same TCF/TGC/TBC/ECF run inputs for every database activation.

Current hotspots:
- `pytuflow/_tmf/cf/tcf_run_state.py`: `deferred_database_activations()` calls `self.find_input()` and walks references.
- `deferred_database_sources_for_activation(input_uuid)` calls `self.find_input()` again for EACH activation (potentially O(A*N) run-input traversal).
- Nested control-file/command provenance and activation sequence must remain accurate; a `BatchDependencyRun.ordered_inputs` descriptor stream is now exposed by PR #6.

**Implement:**
1. Design a narrowly-scoped, per-run immutable/snapshot index by command ordinal, UUID and active database activation. Never share mutable `InputRunState` objects across runs. For existing mutable/public run-state API, either compute a safe fresh snapshot per operation or constrain reuse to the synchronous batch lifecycle with explicit invalidation/immutability assumptions. Do not introduce a stale persistent cache.
2. Make activation/source accessors reuse that index without walking all inputs for each UUID. Preserve the authoritative input-order semantics of `find_input()`; avoid accidental order changes from grouping.
3. Preserve repeated BC database declarations, AD/hydraulic BC distinction, active row scope, ownership and line numbers, missing/duplicate UUID rejection and correct fail-closed behaviour.
4. Add regression tests for multiple/nested control files, activation UUID ordering, zero-reference commands, duplicate and missing IDs, both successful and invalid scenarios. Compare exact `FileReference`, `DeferredDatabaseActivation`, `DeferredDatabaseSource` and error projection between existing individual deferred and batch modes. No filesystem probing after parse.
5. Instrument lookup/traversal counts in focused tests and measure on the **public TUFLOW tutorial** only if performance measurements help. Do not make a speedup claim from synthetic unit tests.
6. Update public docs only if the API changes. Keep the current external accessor signatures backward-compatible. Avoid touching `batch_dependencies.py` or `compiled_dependency_plan.py` owned by P2; if an interface change would require them, document the exact proposal in the PR and coordinate later.

**Owned files:** `pytuflow/_tmf/cf/tcf_run_state.py`, optionally a NEW private run-index helper, NEW focused test module (for example `tests/test_batch_activation_index.py`). Existing tests may be extended only if necessary.

**Not owned:** `pytuflow/_tmf/batch_dependencies.py`, `compiled_dependency_plan.py`, `tests/benchmark_batch_dependencies.py`, `tests/profile_batch_dependencies.py`, consumer `ryan-tools` source.

## Windows commands (PowerShell; from an existing PyTUFLOW checkout)

```powershell
git fetch origin
git switch feat/batch-run-activation-index
git pull --ff-only origin feat/batch-run-activation-index
git rev-parse HEAD
py -3.14 -m pip install -e . pytest
py -3.14 -m compileall -q pytuflow/_tmf
py -3.14 -m pytest -q tests/test_batch_ordered_inputs.py tests/test_batch_dependencies.py tests/test_deferred_database_parity.py tests/test_deferred_file_references.py
py -3.14 -m pytest -q tests/tmf/test_cf_context.py tests/tmf/test_context.py tests/tmf/test_xs_db_from_cf.py
git diff --check
git status --short
```

Optional: run the same focused tests on Windows Python 3.12 (`py -3.12`). If
an interpreter is not installed, report that rather than substituting an
untested environment. Once implementation is committed, push ONLY this
branch; CI on the draft PR must pass at the exact commit under review.

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

