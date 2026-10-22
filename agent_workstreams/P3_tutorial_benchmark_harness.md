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

## Benchmark evidence now available — 22 October 2026

**This section records historical results for the P3 agent to use as a
profiling and regression-planning baseline. It is NOT validation of this
documentation-only PR or the future compiled-tree implementation.**

The designated SMB-capable agent has completed three sequential,
rotating-order **warm-cache** trials per supplied model. All five workloads
have exact materialised `(run, flags, normalised command, physical path,
layer)` identity parity across eager, individual deferred and batch,
zero missing/unresolved input findings, and matching successful separate
public individual/batch preflight checked paths and issues.

Source provenance: PyTUFLOW **1.2.6**, exact parser
`a9f654c1ec0812fc70035e227fb2f9f12290f449`, ryan-tools consumer
diagnostic `2e03c0b110a272d9c6a05cc6da3bc08817130164`, Windows Python
3.14. These timings are **NOT** from the newer parser commits
`37a69b3`, `f3325b8`, PR #6, PR #7 or the pending PR #9 graph.

| Workload | Storage | Runs | Eager median | Individual deferred median | Current cached batch median |
| --- | --- | ---: | ---: | ---: | ---: |
| P | SSD | 4 | 1.234 s | 0.852 s | 0.688 s |
| B | SSD | 240 | 62.640 s | 40.876 s | 26.285 s |
| M480 | SSD | 480 | 118.843 s | 65.007 s | 45.223 s |
| M480 | SMB | 480 | 229.062 s | 91.844 s | 70.014 s |
| N42 | SMB | 42 | 80.892 s | 40.232 s | 16.818 s |

M480 cached batch is **30.4% faster than individual deferred on SSD**
and **23.8% faster on SMB** for this diagnostic workload, but must not
be described as equivalent launcher runtime or cold-cache improvement.
The extra N42 benchmark is now completed; the earlier owner's withdrawn
42-run *acceptance requirement* is not reintroduced.

**What the final phase measurements imply for this PR:**

- The M480 SSD **batch-call** median is 43.708 s, comprising 34.597 s
  context construction, 2.936 s reference collection and 4.480 s
  database projection. Phase medians are independent; they need not
  add to the call median. This makes repeated context construction,
  not a conjectured wildcard-network bottleneck, P3's **highest priority
  PyTUFLOW profiling dimension**.
- M480 SSD batch still constructs **480 run contexts and 28,327
  commands**, reusing **3,353 command templates**. Explicitly instrument
  per-run context counts, immutable node evaluations, run-state
  constructors, command-template clones, graph hits, bypass reasons and
  relevant-context signature counts when comparing new P2 code.
- M480 SMB batch context call **43.595 s** versus SSD **43.708 s**,
  despite diagnostic total **70.014 s SMB** versus **45.223 s SSD**.
  Therefore keep parser/context CPU time separate from downstream
  path identity / GIS / filesystem inspection time. Do **not** attribute
  the entire SMB residual to PyTUFLOW or infer benefits from threading
  its CPU-bound graph evaluator.
- Last-trial M480 eager-context audit counted **6,253 SQLite connects,
  13,454 glob events, 1,440 scandir events** per storage location.
  Individual deferred contexts and the batch call recorded none of those
  selected events. Audit hooks omit some native/stat I/O and must be
  labelled accordingly; retain explicit no-I/O spy tests.
- M480 compared **12,480 per-run identities and 49 distinct paths**;
  N42 compared **1,922 identities and 196 paths**. Report both per-run
  reference volume and physically unique resources rather than treating
  those quantities interchangeably.
- For M480, highest sampled RSS across three trials was
  **344.3/341.9/341.5 MiB** (SSD eager/deferred/batch) and
  **342.1/339.5/341.0 MiB** (SMB). RSS was sampled approximately
  every 20 ms and is not an exact allocation peak or controlled proof
  of memory savings. Label measurement method, interval and GC policy.

The complete approved aggregate evidence, timing ranges, phase caveats,
revision notes and test gates are recorded in
[ryan-tools PR #143's final benchmark record](https://github.com/Chain-Frost/ryan-tools/blob/feat/tuflow-run-preflight/docs/work/2026-10-22-tuflow-batch-preflight-optimisation.md#final-native-benchmark-results-2026-10-22)
and the [PyTUFLOW PR #5 evaluation](https://github.com/phantom-branch/PyTuflow/blob/feat/batch-dependency-context-cache/deferred_batch_resolution_plan.md#final-native-benchmark-results-2026-10-22).
Use only anonymised aggregate findings; **all five native models and local
reports remain on SMB/local storage** and P3 must not access them.

**Direct P3 requirements derived from this evidence:**

1. Provide consistent phase timing around initial parse, control-graph
   compilation, context resolution, immutable reference projection and
   database activation/source projection. Count contexts built, command
   constructions, input run-state constructions, graph nodes skipped,
   scope/signature hits and fallbacks. Prefer instrumented counters or
   narrow spy checks over inferring avoided I/O from elapsed time.
2. Compare same-code-head individual deferred versus cached batch versus
   compiled batch (once P2 exists), using the **same public tutorial
   model/run combinations and warm-cache trial order**. Existing P3
   fixtures cannot create a true historical PR #5 versus future graph
   comparison in one checkout; use explicit checked-out source SHAs if
   cross-revision comparisons are deliberately performed, and never
   combine timings from unrelated machines or configurations.
3. Produce a clear machine-readable summary with source SHA, Python
   version, model identifier **only if public**, requested versus truly
   distinct complete/relevant flags, per-run reference totals, unique
   paths, three trial times and medians, counts, errors, and peak-RSS
   methodology. Fail the benchmark acceptance on *missing or extra*
   identities, unresolved inputs, incorrect owner/activation order or
   run-specific state leakage; do not replace failures with partial
   timings.
4. The public tutorial archive has **161 TCFs / 174 documented
   combinations**, not a native 480-run shared-TCF ensemble. Repeating
   tutorial flags to reach 480 or 500 mostly tests duplicate-context
   reuse. Include at least one *actual multi-context tutorial TCF*
   where available and explicitly report the number of genuinely
   distinct contexts; do not claim P2's 500-distinct-context graph
   performance has been proved using the tutorial data.
5. Publish no SMB-derived code fixtures or dumps. Leave native
   B1/B2/B3 performance rechecks to the designated separate SMB
   agent after P1/P2/P4 implementation milestones. The completed B0
   benchmark is sufficient to prioritise context construction now.

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
   database source projection and total, **particularly the 34.597 s M480
   SSD context-construction hotspot**; report command constructors/clones,
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

