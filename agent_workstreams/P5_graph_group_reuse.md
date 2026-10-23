# P5: Reuse proven input groups in mixed control-file graphs

**Updated:** 2026-10-23. **PR:** #12, remains draft.
**Current implementation:** bounded scenario/variable proof and isolation fixes,
the authoritative reference-count contract merged from #13, and constructor
eligibility guards. **263 focused/integration tests pass** on each of Python
3.12.14 and 3.14.8 locally. The previous `84f1f38` source passed all eight active
hosted checks and Codex review; the final constructor correction requires its
own Windows/public checks. Final source and CI links are recorded in PR #12.
**Performance status:** no native timing or speedup is established for the new
implementation. Retained benchmarks validate an earlier source only.
**Pre-P5 baseline:** `master` at `3de5cd954a5bf6739377937c8ff2fe3341e86bfc`.

## Why the graph was avoiding so little repeated work

The graph was built and indexed, but the original partial-group proof rejected
every conditional input and every variable-derived input. It accepted only
literal, global `READ GIS CODE` / `READ GRID ZPTS` leaves. Whole-model shortcuts
required the complete model to consist of supported literal READs, so ordinary
settings, variables, includes and BC commands prevented them in mixed models.
The broad READ eligibility count did not describe the narrower set of inputs
whose constructors could actually be bypassed.

The retained [workstation benchmark and file-sharing report](P5_benchmark_results_2026-10-23.md)
shows that eligible M480 groups matched correctly: four seeds and 1,916 reuses.
Other visits included 3,840 scenario-conditioned READs, all rejected despite
fixed scenario selections, and 24,480 non-READ states. This was limited proof
coverage rather than a demonstrated path-spelling or lookup failure. Equal
required-file lists alone remain insufficient proof of reusable run state.

## Implemented proof and isolation

`compiled_control_tree.py` now compiles an immutable per-input group plan once
per invocation. It records source ownership, command part/line metadata,
configuration, ordered branches, DEFINE-block metadata and transitive variable
dependencies. Every node has a candidate plan or a bounded static exclusion
reason. Non-candidates no longer repeat the full eligibility checks on each visit.

`group_input_reuse.py` supports these independently proven leaves in mixed models:

- Global literal inputs supported by the original cache.
- Inputs under known literal scenario conditions, including nested branches,
  ELSE and negation. Ordinary control-file traversal still decides activation;
  reuse retains exact scenario slot numbers/order and values.
- Variable-derived inputs where `CompiledVariablePlan` proves an acyclic
  transitive lineage. Keys retain the resolved RHS, all relevant variable
  values and ordered identities of their active declarations. Equal final
  paths without matching provenance do not establish reuse.

Runtime proof validates the compiled source snapshot and requires one resolved
literal path whose expansion is stable. Event text markers are checked in the
raw expression and relevant variable values. Uncertain or changed inputs use
ordinary evaluation. The cache remains invocation-local, bounded to 10,000
successfully certified signatures, and seeded only by complete successful runs.
Failed runs return no partial dependencies.

The supported commands remain **`READ GIS CODE` and `READ GRID ZPTS`**, with
single explicit `.shp`, `.tif`, `.asc` or `.flt` results. General event expressions,
real DEFINE blocks, BC/database inputs, wildcards, multipart values, GeoPackage
selectors and spatial databases remain outside this proof. A whole control-file
subtree is not skipped merely because its file inventory matches.

Two additional isolation defects are corrected:

- GRID's plain mutable `_rs.cf` list was still shared: resetting the outer
  run state's `cf` or GIS's `_cf` did not reset it. Each GRID clone now owns
  an independent empty `cf` list.
- Ordinary construction aliases nonempty `Command.define_blocks` to the parsed
  source. Eligible batch seeds now detach that list and every mutable block
  before returning. Exemplars and reuse clones also independently copy blocks
  and scopes, including `Scope.names` and exact ELSE/negation metadata.
  `Scope` needs explicit allocation because its constructor dispatch cannot
  be reconstructed with ordinary shallow `copy()`.

Commands, expanders, configuration snapshots, contexts and lazy GIS/grid state
are rebound or independently copied. Ordinary eager construction is unchanged.

### Constructor eligibility correction before merge

The original GIS/GRID group cache could bypass a source input's custom
`context()` method after one successful run, suppressing later per-run errors.
The group proof now records the exact input class and original constructor
function, captured when that function's module is defined. Compilation rejects
instance/class overrides and methods bound to another input; runtime lookup
checks the same function and bound owner before reusing a leaf prototype.
Static invariant/scenario whole-model classification also requires a valid
input-group proof, so a preinstalled custom constructor cannot bypass that
eligibility check through a different graph shortcut.

This correction is limited to the existing `READ GIS CODE` / `READ GRID ZPTS`
coverage. The focused constructor-guard regressions cover preinstalled hooks
in mixed, literal and scenario models, and hooks replaced during iteration of
a mixed model using leaf-group reuse. Revalidating an already-cached whole-model
projection or an identical-flag result after a caller mutates sources mid-batch
remains separate follow-up work; those pre-existing caches retain their
read-only-invocation assumption. Setting-state reuse and `Inputs.append()`
optimisation also remain follow-ups rather than expanding this correction.

## Diagnostics and cache preparation

| Metric | Meaning |
| --- | --- |
| `compiled_graph_eligible_reads` | Broader syntax/variable command-plan eligibility |
| `compiled_input_group_candidates` | Inputs passing the static constructor-reuse proof |
| `input_group_bypass_reasons` | Bounded counts of static exclusions |
| `input_group_fallbacks` | Runtime proof, isolation, clone, certification and capacity fallbacks |
| `input_group_state_reuses` | Actual independently cloned group states |
| `invariant_projection_reuses` | Whole-run immutable projection reuse |
| `input_runstates_constructed` / `input_runstates_elided` | Constructor attempts and bypasses, including failed-run work |
| `failed_run_input_runstates_*` | Work belonging to subsequently failed projections |
| `input_group_cache_bypass_reason` | Why no prototype cache was prepared |

Runtime `ineligible` is the aggregate of detailed `ineligible_*` categories; do
not add it to those categories. A lookup, candidate or prototype is not itself
a constructor elision or a speedup. Cost diagnostics separate runtime key/proof,
cloning, successful-run certification and normal construction. They overlap
other phases and must not be summed into the top-level total. Normal constructor
timing includes nested constructors and is not exclusive CPU time.

Prototype-cache preparation is bypassed for zero candidates, sized batches of
at most one run, and existing complete invariant projection shortcuts.
Unknown-length iterators remain streaming without consuming future flags to
find their length. Graph-off retains the established non-graph batch caches for
the same-head differential.

## Earlier results and current evidence

The immutable [2026-10-23 benchmark report](P5_benchmark_results_2026-10-23.md)
records parser source `c305a6d`; its parser/benchmark code is identical at passing
CI source `eebbb16` and results-only commit `2b8ddb9`. Those results validate the
narrower implementation, not the expanded code above.

| Earlier workload | Graph-off median, s | Graph-on median, s | Constructors elided |
| --- | ---: | ---: | ---: |
| M480, 480 distinct runs on SMB | 42.895 | 42.790 | 1,916 / 31,680 |
| N42, 42 distinct runs on SMB | 11.310 | 11.367 | 0 / 4,148 |

Those differences established no meaningful graph speedup. Earlier public
161-TCF/174-run and native parser/materialised/preflight gates passed at their
recorded sources. Existing batch-cache gains remain separate from the graph.

Current confirmed local evidence is **263 passing focused/integration tests on
each of Python 3.12.14 and 3.14.8**, including the 18 constructor-guard regressions
and existing graph correctness tests covering
scenario/variable provenance, mutable-state isolation, failed contexts and
conservative exclusions. Compilation and diff checks also pass. The expanded
500-distinct-event mixed fixture
elides 997 constructors through three proven signatures. This is a synthetic
correctness/work-avoidance result, not a timing claim. Windows/public hosted CI
is pending; record the final source and terminal CI links in the PR after completion.

## Disposition of the benchmark recommendations

The implementation boundary is explicit:

- **PyTUFLOW** owns the parser dependency graph, scope/variable proofs, run-state
  construction and isolation, and public API counters.
- **ryan-tools** consumes that public API and owns materialisation of GIS,
  database and file references, physical-identity diagnostics, inventory and
  reporting. It must not duplicate parser proofs or depend on parser-private
  graph/cache internals.

| Recommendation | Current disposition |
| --- | --- |
| Prove fixed-scenario groups in mixed models | Implemented for supported leaves with exact slots and branch provenance |
| Retain transitive variable/settings dependencies | Implemented with relevant values, active declarations and configuration snapshots |
| Separate proof, certification, cloning and construction costs | Diagnostics added; command coverage remains limited to the two proven classes |
| Avoid single-run and zero-candidate preparation | Implemented with explicit bypass reasons and preserved iterator streaming |
| Memoise `Path.resolve()` in the consumer diagnostic | Delivered in ryan-tools #143 at `144e1e4`; six regressions and hosted parity pass |
| Investigate older eager/shared compatibility differences | Confirmed stale NetCDF rainfall and Q/QO fixture expectations; test/documentation follow-up, no parser behaviour change required |

The earlier consumer diagnostic's 12,480 physical-identity resolutions for 49
normalised targets were not production graph I/O. The companion PR #143 change
preserves mapped-drive/UNC and linked-path identity checks with invocation-local
caches. Consumer [#156](https://github.com/Chain-Frost/ryan-tools/pull/156) is now
integrated into [#143](https://github.com/Chain-Frost/ryan-tools/pull/143) at
`298fb13`, after five green workflows and a clean refreshed Codex review.
The reference-count contract from #13 is included here; dependency publication
and consumer default changes remain separate decisions.

Another unoptimised construction hotspot is `Inputs.append()` in
`pytuflow/_tmf/inp/inputs.py`: every append rebuilds and searches parent UUID lists
for edit/undo index bookkeeping, producing quadratic list work as a control-file
input collection grows. Group cloning still traverses this append path. Profile
its public-workload contribution and preserve editing/index semantics before
changing it separately. No gain from that unimplemented optimisation is claimed.

The pre-P5 canonical-upstream differences remain
`test_control_file::test_load_rainfall_database`,
`test_input::test_input_files_ref_in_gis` and
`test_input_context::test_input_files_ref_in_gis`. Retain the three-way Windows
comparison of canonical upstream, pre-P5 fork and current head. Earlier green
differential CI meant no new P5 regressions, not a fully passing absolute
upstream suite. The deferred/batch API remains fork-only.

## Next workstation validation

Use the final source after focused/integration checks pass and record both
parser and consumer revisions. Follow
[tests/TUTORIAL_BENCHMARK.md](../tests/TUTORIAL_BENCHMARK.md) for the verified
public archive, four-mode differential, separate materialised replay and
profiling limits. From the PyTUFLOW checkout, with `$Bundle` set to the documented
public fixture location:

~~~powershell
py -3.14 -m pytest -q tests/test_compiled_control_tree.py tests/test_batch_integration.py tests/test_tutorial_benchmark.py
py -3.14 tests/benchmark_tutorial_dependencies.py --bundle $Bundle --trials 3 --output "$env:TEMP\pytuflow-p5-expanded-public.json"
~~~

The owner will use a different model on another SMB server. Treat it as a new
workload, with one fixed TCF and exported run list, anonymous label, exact parser
and consumer revisions, and Python/storage details. Existing `run_local_checks`
in ryan-tools compares eager, individual deferred and batch materialisation,
rotates the three modes across trials, and checks public-preflight parity.
This establishes a new end-to-end baseline; it does not isolate graph speedup.
Report missing/extra identities, order/provenance differences, failed runs and
fallback reasons before interpreting timings. Keep detailed reports locally.

The public parser benchmark supports same-source graph-off/on comparisons.
The native consumer runner currently has no graph-off switch; add that control
as a focused consumer-tooling follow-up before claiming a native graph-only
speedup. Old M480/N42 timings are historical context, not a control for changed
models, servers or source revisions. Further append and literal-setting reuse
will be reviewed in separate follow-up PRs against the frozen baseline.

Publish anonymised aggregates only. Native data, detailed reports, identifying
paths and source fragments remain on the workstation. Launchers are read as
text; no launcher or solver is executed. Publishing a package or changing the
consumer's production dependency is outside this parser change.
