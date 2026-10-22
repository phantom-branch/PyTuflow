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
- **The private engineering datasets reside only on the SMB share.** No agent
  may copy, upload, archive, embed, commit or publish any native model files,
  fragments, identifying directory paths or derived model content in GitHub,
  test fixtures, logs, CI artifacts or PR attachments. Validate them in place
  using read-only code on the authorised workstation.
- **Public performance fixtures are restricted to the TUFLOW tutorial dataset.**
  Minimal in-memory/temporary synthetic unit fixtures may still test correctness,
  but must not be used to claim representative production speedups.
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
| **P3 — public tutorial differential/performance harness** | P2: `feat/batch-compiled-control-tree` (PR #9); initial harness work can proceed in parallel | `tests/benchmark_batch_dependencies.py`, `tests/profile_batch_dependencies.py`, public TUFLOW tutorial fixture adapters/tests only | Benchmark only checked-in/licensed TUFLOW tutorial data and valid tutorial configurations; record actual distinct-context count, unique dependencies, memory, CPU/phase timings and exact provenance parity. If scaling to 120/240/440/500 requested runs by repeating valid tutorial flag combinations, label these as *repeated-run stress tests* rather than 120/240/440/500 distinct runs. Unit tests may use tiny synthetic inputs, but not as representative speedup evidence. | Yes; no SMB access required |
| **P4 — integration of P1/P2/P3** | P3: `test/batch-tutorial-benchmarks` (PR #7), after P2; merge independent P1/PR #8 | Integrator resolves any P1/P2 conflicts, extends parity tests | Consolidate validated parser optimisation stack. Never silently discard P1 fixes while adopting P2. | After P1/P2 implementation |

**Shared-file ownership:** Only P2 modifies `batch_dependencies.py` after P0.
P1 owns `tcf_run_state.py` run-index internals and should not touch the
compiled graph. P3 owns measurement harness files. Avoid parallel pushes to
the same branch. Start P1/PR #8 and P2/PR #9 as independent sibling branches above P0.
P3/PR #7 is **now stacked on P2** so its final compiler benchmarks test
actual P2 behaviour; an independent agent can develop the public tutorial
harness concurrently, then merge P2's latest implementation before comparing.
P4/PR #10 is stacked on P3 and later merges the independent P1 branch.
Review exact changed files throughout. This retains parallel coding without
prematurely claiming a compiled-tree benchmark.

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
SMB measurements and native-model differential checks for that agent. Native
models **stay on SMB**; benchmark code may be pulled to the workstation but
private inputs, identifiable model fragments, paths and generated data must
never be uploaded to GitHub. A native result is publishable only as a
non-identifying aggregate (timings, counts, settings and source SHAs) when
approved; keep detailed/local reports private. Other agents use only the
public TUFLOW tutorial dataset for performance benchmarks, plus small synthetic
fixtures for focused correctness tests. No other agent should attempt SMB
access or make claims about native speedups.

1. **B0 — interim baseline and remaining private checks (SMB agent):**
   the 22 October 2026 three-trial results are already recorded in ryan-tools
   PR #143 and PyTUFLOW PR #5. Use those revision-labelled results as the
   interim baseline; do not wait for or request any upload of native model data.
   Keep the exact private run flags, paths and local reports on SMB; record
   source SHAs, non-identifying run counts, Windows/Python versions, trial
   order, warm-cache policy, and three repeated equal-work runs. Separate initial parse,
   contexts/batch compilation, reference collection, wildcard resolution,
   GIS/database/raster inspection, final inventory and reporting. Capture
   operation counts and peak RSS. Keep the existing 440-run historical
   single-pair result explicitly revision-labelled; do not mix revisions.
2. **B1 — parser-only comparison (SMB agent, after P1/P2/P4 stabilise):**
   benchmark the same authorised native P/B/M480 (and any separately approved
   further model) flags using baseline individual deferred, PR #5 cached batch
   and optimised compiled batch, with exact per-run reference and activation
   identity. Do not upload models to CI or fabricate unavailable native sizes.
3. **B2 — end-to-end private consumer comparison (SMB agent, after C1–C3):**
   benchmark identical full preflight including primary and secondary GIS,
   layers, active BC feature/declaration joins, raster/NetCDF and wildcard
   sources. No partial subset can be accepted as parity.
4. **B3 — concurrency/tuning (SMB agent, only if B2 shows I/O limits):**
   compare network scan threshold, sparse direct-stat versus bounded directory
   listings, and sequential/4/8-worker I/O on the *same share*. Record median,
   variance, SMB ops, peak memory and impact on NAS load. No default change
   if evidence is inconclusive or slower.

These are **separate benchmarking sessions**, not simultaneous tests by
multiple agents. New benchmark **summary results**, not datasets, may update
this workstream after the authorised agent finishes each stage. Do not
retroactively alter the interim baseline or block independent coding.

### Recorded interim benchmark (22 October 2026; not PR #6 timings)

As published in [ryan-tools PR #143](https://github.com/Chain-Frost/ryan-tools/pull/143#issuecomment-6343549927)
(and the PyTUFLOW PR #5 evaluation record), source parser `a9f654c1`,
consumer `2e03c0b1`, Python 3.14, three alternating warm-cache trials:

| Model | Storage | Runs | Eager median | Individual deferred median | Batch median |
| --- | --- | ---: | ---: | ---: | ---: |
| P | local SSD | 4 | 1.234 s | 0.852 s | 0.688 s |
| B | local SSD | 240 | 62.640 s | 40.876 s | 26.285 s |
| M480 | local SSD | 480 | 118.843 s | 65.007 s | 45.223 s |
| M480 | private SMB | 480 | 229.062 s | 91.844 s | 70.014 s |

All four *diagnostic* suites matched materialised
`(run, flags, normalised command, physical path, layer)` identities and had
zero collection/inventory findings. At the time of publication the **M480 SMB
separate public-preflight comparison was still pending**; local P/B/M480 public
comparisons passed. These timings include parse, reference materialisation,
identity normalisation and shared inventory, but exclude process startup,
report writing and separate public-preflight raster-header checks. They are
not full launcher timings. Do not relabel these as timings from this PR or
assume later code-head parity. The original 42-run external requirement was
withdrawn; a later distinct 42-command network experiment must be explicitly
labelled rather than silently restored as a required gate.

### Public TUFLOW tutorial benchmark protocol

Use only the existing tutorial dataset already permitted in the public test
repository. Do not copy SMB sources into test-data, even in ZIP/GPKG form.
Preserve genuine tutorial TCFs and supported event/scenario combinations.
For repeated-run throughput tests, record both **requested runs** and
**distinct complete/relevant context signatures**; duplicate flags primarily
exercise whole-run memoisation and cannot establish speedups for 500 distinct
simulations. Attribute scans, BC rows, GeoPackage and raster headers must be
covered by the tutorial cases that truly exercise them; report any uncovered
native-only behaviour as a deferred SMB gate.

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
  entries). Confirm the public 161-TCF/174-run tutorial replay; the authorised
  SMB agent performs native P/B/M480 checks at scheduled checkpoints. Do not
  invent availability of additional native models or use CI as a proxy.
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
2. P1/PR #8 and P2/PR #9 are sibling child PRs from P0; P3/PR #7 is now
   based on P2/PR #9 and can build its harness while graph work progresses.
   P4/PR #10 is based on P3/PR #7 and later merges P1. Stage C1
   independently in ryan-tools.
3. Use the already-posted 22 October aggregate benchmark evidence as the
   interim B0 baseline. The designated SMB agent completes its remaining
   checks in place and carries out B1/B2/B3 at later implementation milestones.
   **There is no planned upload of private SMB model data.**
