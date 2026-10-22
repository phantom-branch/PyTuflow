# P3 agent prompt — Public TUFLOW tutorial differential and performance harness

**Target draft PR:** this branch targets `feat/batch-ordered-dependency-plan` (PR #6). A separate agent implements P1 and another P2; do not edit their source files.

## Agent instruction (execute without further clarification)

Review `tests/benchmark_batch_dependencies.py`, `tests/profile_batch_dependencies.py`,
existing 161-TCF/174-run consumer tutorial replay and
`batch_evaluation_workstreams.md`. Develop a reproducible Windows benchmark
and differential validator over **only the public TUFLOW tutorial example data**.

The authorised public example dataset is in the separate public
[ryan-tools-test-data](https://github.com/Chain-Frost/ryan-tools-test-data)
repository, pinned as the `tests/test_data` submodule from
[ryan-tools PR #143](https://github.com/Chain-Frost/ryan-tools/pull/143).
Its documented bundle `tuflow/example_input_preflight/` contains
`examples.zip`, `manifest.json`, `baseline.csv`: **161 TCFs / 174 run
combinations / 1,464 source files**. For available runner conventions see
`ryan-tools/tests/fixtures/tuflow_example_repro/README.md` and
`run_checks.py`. The dataset is **not bundled into PyTUFLOW**; support a
caller-specified existing public tutorial-bundle directory rather than an
imaginary PyTUFLOW fixture path. Do not commit extracted sources.

**Implement:**
1. Provide a deterministic read-only **public tutorial** benchmark entry
   point accepting a path to this permitted tutorial bundle. Validate the
   manifest/archive before use; safely extract to a temporary location only,
   without executing batch files or the solver. Prefer reuse of the existing
   public verification/extraction helpers when appropriate, but avoid making
   PyTUFLOW import ryan-tools production code or duplicating a TUFLOW parser.
2. Enumerate the actual valid tutorial event/scenario combinations. Compare
   individual deferred, PR #5-style cached batch and opt-in optimised batch
   against identical workload and full immutable reference/UUID/ordinal/
   owner/line/activation/source identities. Record both **missing and extra**
   results; invalid or unsupported examples are explicitly reported rather
   than silently dropped.
3. Benchmark parse, compiler, context/input creation, reference collection,
   database source projection and total; report command constructors/clones,
   graph hits/bypasses, requested runs, **distinct complete flag signatures**,
   distinct relevant-context signatures where available, peak RSS/sample
   limitations and three rotating warm-cache trials on the SAME workstation.
   Never compare unrelated runner/build revisions.
4. A test requesting 120/240/440/500 runs may repeat tutorial combinations,
   but MUST label itself a **repeated-combination throughput stress test**,
   not an equivalent 500-distinct-context production model. Display counts
   clearly and independently. If tutorial has insufficient valid distinct
   flags to exercise P2's distinct-flag optimisation, note the limitation.
5. Keep small synthetic or temporary data fixtures strictly for unit/correctness
   tests. The existing synthetic timing scripts must be clearly labelled
   microbenchmarks and must not be presented as representative native
   performance; replace their published/automatic performance gate with
   tutorial data if feasible, or explicitly separate them as correctness/
   instrumentation checks.
6. No proprietary inputs, network paths, archived private captures, solver
   binaries or uploaded SMB outputs. No persistent filesystem/result cache.
   Never write into the public tutorial input checkout; private/timing reports
   remain untracked outside it.
7. Build an optional CI invocation only if a public tutorial checkout is
   prepared. Missing optional fixture must produce an explicit unavailable/
   skipped status, **not a fabricated success**. Keep existing Windows 3.12/
   3.14 focused unit CI passing and clearly explain what CI exercised.

**Owned:** `tests/benchmark_batch_dependencies.py`,
`tests/profile_batch_dependencies.py`, NEW tutorial benchmark script and its
tests/docs; workflow path filters only as required. Do NOT touch PyTUFLOW
resolver/source modules owned by P1/P2.

## Windows commands (PowerShell)

```powershell
git fetch origin
git switch test/batch-tutorial-benchmarks
git pull --ff-only origin test/batch-tutorial-benchmarks
git rev-parse HEAD
py -3.14 -m pip install -e . pytest
py -3.14 -m pytest -q tests/test_batch_ordered_inputs.py tests/test_batch_dependencies.py tests/test_compiled_dependency_plan.py
# For public tutorial fixture verification, from the ryan-tools checkout:
git submodule update --init tests/test_data
py -3.14 -m tests.fixtures.tuflow_example_repro.run_checks --verify-only
# Use the new PyTUFLOW tutorial benchmark CLI against the verified directory.
# Document its actual CLI in this PR; do not invent a success result.
git diff --check
git status --short
```

Assume the `ryan-tools` checkout is available only if it actually is; otherwise
fetch the public test data in an approved non-proprietary location and report
any setup limitation. There is no dependency on the private SMB share. Once
P2 completes, restack/rebase this PR onto P2 (with coordination) before
integration; do not independently merge this benchmark PR.

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

