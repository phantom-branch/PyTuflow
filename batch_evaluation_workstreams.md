# Shared-TCF batch evaluation: stacked implementation workstreams

**Status:** development; draft foundation PR based on PyTUFLOW PR #5.
**Baseline branch:** `feat/batch-dependency-context-cache` (PR #5, head `a9f654c1ec0812fc70035e227fb2f9f12290f449` at foundation creation).
**Companion consumer:** Chain-Frost/ryan-tools PR #143 (`feat/tuflow-run-preflight`), including the opt-in batch adapter that arrived through PR #148.

## Objective and non-negotiable boundaries

Optimise read-only validation of hundreds of simulations sharing a parsed TCF.
Correctness means *complete, exact per-run* file, layer, attribute, raster and
database-source dependencies with command, owner, ordering and scenario/event
provenance. Syntactic reference parity alone is not sufficient. Keep existing
eager and individual deferred APIs and all fail-closed behaviour.

- **No persistent or cross-invocation cache.** A model edit between batch calls
  must be visible. Compile/cache only within one synchronous batch or consumer
  preflight invocation.
- No solver, launcher, writes to engineering models, automatic merging, PyPI
  publishing, production pin changes or Linux acceptance work.
- Initial control-file reads and consumer materialisation may perform I/O.
  The PyTUFLOW batch evaluator performs no filesystem or GIS probes after parse.
- Windows Python 3.12/3.14 parity remains the parser acceptance platform.
  ryan-tools consumer development targets Python 3.14.
- Retain lexical mapped-drive/UNC paths. Do not use `Path.resolve()` merely
  to format or canonicalise a path. Physical-alias optimisation is a separate
  explicitly tested concern.
- Scope, event, TEF and Set Variable ordering, nested ownership and active
  BC declaration *feature-to-row* selection are correctness requirements,
  never removable optimisation barriers.
- Unknown/unsupported features fail closed; never treat a partial common
  inventory as a successful match.

## Stack topology and agent ownership

The independent branches below are designed to minimise conflicting edits.
**Each agent creates its own branch, opens a draft PR against the named base
branch (not master/main), and does not merge/publish.** The foundation remains
based on PR #5 until that PR merges; then retarget foundation to `master`
and leave descendants based on their immediate parent branches.

### PyTUFLOW stack

| Work package | Base branch / PR | Agent edits | Deliverable | May work concurrently? |
| --- | --- | --- | --- | --- |
| **P0 — foundation (this PR)** | PR #5: `feat/batch-dependency-context-cache` | `batch_dependencies.py`, `test_batch_ordered_inputs.py`, this plan | Add ordered, immutable active-input descriptors, including commands with no files. Reuse one `find_input()` traversal when projecting references. No consumer default changes. | Complete before dependent PRs |
| **P1 — active input/activation indexing** | P0: `feat/batch-ordered-dependency-plan` | `cf/tcf_run_state.py`, optional new private run-index module; focused tests | Replace repeated `find_input()` and UUID-by-UUID scans within one evaluated context with a stable ordinal/UUID lookup. Preserve database activation sequence; no global reuse of mutable run state. | Yes, alongside P2 (different files) |
| **P2 — immutable compiled control tree** | P0: `feat/batch-ordered-dependency-plan` | New `compiled_control_tree.py`, `compiled_dependency_plan.py`, `batch_dependencies.py`; own graph tests | Compile control/input nodes once, annotate exact relevant variables/scopes/events/settings, evaluate equivalent nodes per distinct relevant signature rather than reconstructing unchanged inputs 500 times. Keep conservative fallback and per-run provenance. | Yes, alongside P1; integration after each passes |
| **P3 — synthetic differential/performance harness** | P0: `feat/batch-ordered-dependency-plan` (rebase/retarget onto P2 before merge) | `tests/benchmark_batch_dependencies.py`, `tests/profile_batch_dependencies.py`, new test fixture modules only | Stable 120/240/440/500 distinct-flag synthetic fixtures, counters, identical-work comparison, memory peak, same-runner rotating three trials, exact reference/provenance diff. Measure parse separately. | Yes; no SMB access required |
| **P4 — integration of P1/P2/P3** | P2 branch once ready | Integrator resolves any P1/P2 conflicts, extends parity tests | Consolidate validated parser optimisation stack. Never silently discard P1 fixes while adopting P2. | After P1/P2 implementation |

**Shared-file ownership:** Only P2 modifies `batch_dependencies.py` after P0.
P1 owns `tcf_run_state.py` run-index internals and should not touch the
compiled graph. P3 owns measurement harness files. Avoid parallel pushes to
the same branch. Start P1/P2/P3 as independent siblings above P0; when
assembling a linear chain, rebase and retarget P1/P3 against the nominated
parent, reviewing exact changed files. This retains independent agent work
without prematurely serialising all development.

### ryan-tools consumer stack (separate repository)

| Work package | Base branch / PR | Agent edits | Deliverable | Concurrent? |
| --- | --- | --- | --- | --- |
| **C1 — shared filesystem inspection session** | ryan-tools PR #143: `feat/tuflow-run-preflight` | `functions/tuflow/dependency_index.py`, focused tests | Share bounded directory snapshots across primary wildcards, attribute wildcards and final file checks. Retain sparse targeted-stat fallback, 50,000-entry guard, no recursive walk. | Yes, alongside parser agents |
| **C2 — shared GIS/metadata inspection** | C1 branch | `functions/tuflow/gis_attribute_dependencies.py`, `dependency_index.py`, `raster_metadata_dependencies.py`, tests | Consolidate per-session GeoPackage metadata/layer/attribute reads; avoid redundant opens, select columns not geometry BLOBs, validate existence before expensive metadata where safe. | After C1 for shared files |
| **C3 — adopt ordered PyTUFLOW contract** | C2 branch after P0 available | `orchestrators/tuflow/batch_preflight_adapter.py`, `input_preflight.py`, tests | Consume `ordered_inputs` (including reference-free commands) to retain database activations and exact ordinals. Fail closed on old/incompatible API, check active BC feature-to-row selection. | Can prototype tests alongside C1 but integrate later |
| **C4 — bounded SMB I/O experiments** | C3 branch | Network-independent opt-in strategy, benchmark/test helpers | Benchmark targeted stat vs directory snapshots, and optionally sequential vs 4/8 bounded workers. Deterministic report ordering, thread-confined SQLite connections, no extra metadata read on success. Do not enable concurrency by default without native results. | Code can be prepared without SMB; acceptance later |

Do **not** put network directory enumeration/GeoPackage/GDAL I/O into
PyTUFLOW's compiled control tree. It belongs to the ryan-tools consumer
inspection stage, which already deduplicates physical files and retains
per-run origin information. Do not introduce a second TUFLOW parser.

## One SMB agent and staged real-world benchmarks

**Exactly one agent has access to the network drive.** Reserve all native
SMB measurements and native-model differential checks for that agent.
Other agents use synthetic local Windows fixtures or existing archived
161-TCF/174-run CI evidence. No other agent should attempt SMB access or
make claims about native speedups.

1. **B0 — baseline capture (SMB agent, after the next benchmark upload):**
   record exact PyTUFLOW and ryan-tools SHAs, run flags, network path context
   (redacted when necessary), Windows/Python versions, trial order, warm-cache
   policy, and three repeated equal-work runs. Separate initial parse,
   contexts/batch compilation, reference collection, wildcard resolution,
   GIS/database/raster inspection, final inventory and reporting. Capture
   operation counts and peak RSS. Keep the existing 440-run historical
   single-pair result explicitly revision-labelled; do not mix revisions.
2. **B1 — parser-only comparison (SMB agent, after P1/P2/P4 stabilise):**
   benchmark identical P/B/440/500 flag sets using baseline individual
   deferred, current PR #5 cached batch and optimised compiled batch, with
   byte/identity-equivalent references and activation streams.
3. **B2 — end-to-end consumer comparison (SMB agent, after C1–C3):**
   benchmark identical full preflight including primary and secondary GIS,
   layers, active BC feature/declaration joins, raster/NetCDF and wildcard
   sources. No partial subset can be accepted as parity.
4. **B3 — concurrency/tuning (SMB agent, only if B2 shows I/O limits):**
   compare network scan threshold, sparse direct-stat versus bounded directory
   listings, and sequential/4/8-worker I/O on the *same share*. Record median,
   variance, SMB ops, peak memory and impact on NAS load. No default change
   if evidence is inconclusive or slower.

These are **separate benchmarking sessions**, not simultaneous tests by
multiple agents. New evidence uploaded while P1/P2/C1 are underway should
first update the benchmark ledger, then inform prioritisation; it should not
retroactively change baseline figures or block independent coding.

## Should dependency evaluation and network inspection run on separate threads?

**Not initially.** Once the TCF is parsed, PyTUFLOW's batch projection is
mostly CPU-bound Python, so a second Python thread does not produce meaningful
parallel CPU speedup under the standard CPython GIL. A queue/heap pipeline
would also add cross-thread mutation, partial-inventory handling, backpressure
and deterministic provenance/error-routing complexity.

The existing two-phase design already assembles the complete dependency set
before checking each unique physical resource once. Retain that first.

Bounded threads are worth testing *inside the consumer I/O stage* for
independent SMB file metadata requests, because those operations can release
the GIL while blocked. Connection-per-worker SQLite safety and stable output
ordering are mandatory.

Only consider pipelined overlap (producer evaluating commands; consumer
inspecting complete immutable resource batches) if real SMB profiling shows
both substantial simultaneous CPU and network-I/O idle periods. Its correctness
must account for late-discovered dependencies from GIS attributes, secondary
databases and rainfall indexes. No file may be declared complete simply
because a provisional producer queue became empty. A heap is not needed
unless prioritisation itself is proven useful; a bounded queue with deduplication
and explicit completion barriers would be sufficient.

## Acceptance and handoff

- Every changed PR carries focused tests and exact-head Windows checks.
- Maintain eager / individual deferred / batch equality for exact
  **per-run** identities and issue results (including missing *and* extra
  entries). Confirm 161-TCF/174-run archived replay and native P/B/440/500
  as available, recording unavailable native checks as deferred.
- No filesystem/GIS probes during PyTUFLOW post-parse compilation; no repeated
  consumer physical opens when a per-session cache can safely share them.
- Track command constructors/clones and invariant-node evaluations, relevant
  signatures/hits, unique files, directory listings, direct stats, GIS opens,
  SQL statements, raster opens, memory peak and timing by phase.
- Preserve the distinction between existing PR #5 synthetic timing and actual
  SMB end-to-end performance.
- Retarget P0 from `feat/batch-dependency-context-cache` to `master` only
  **after PR #5 is merged**. Do not retarget the ryan-tools chain to `main`
  until the corresponding consumer base PR is merged.
- No persistent cache, no background monitoring, and no automatic publication.

## Immediate next tasks

1. Open P0 as a draft stacked on PR #5, allow focused CI to run, fix findings.
2. Start P1/P2/P3 as separate *agent-owned* child PRs from P0 with the file
   ownership defined above; stage C1 independently in ryan-tools.
3. Receive the next native benchmark upload, record as B0 evidence for the
   single SMB-capable agent. Schedule further native benchmarks after the
   corresponding implementation phases, rather than during parallel coding.
