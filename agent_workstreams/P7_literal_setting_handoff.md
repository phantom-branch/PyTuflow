# P7 — Literal SettingInput reuse

This is a self-contained agent prompt for reviewing and completing this draft
follow-up. The implementation is already present; continue from it rather than
reimplementing the parent work.

## Branch, base and objective

Work in the **PyTUFLOW** repository on `perf/literal-setting-reuse`. The branch
starts from PR #12's merge into `master` at
`e162c04330d24c37bee3ade94479cc4602651060`. Its tree is identical to the tested
source `126ec64e221908f5327ee9dc9d372c8084afaf12`, including the constructor
guards and PR #13 `reference_count` contract. Preserve those contracts and
update onto later `master` changes without importing another optimisation
workstream.

Reduce repeated construction of proven, state-neutral, literal **exact
`SettingInput`** leaves during deferred batch collection. Keep ordinary parser
traversal authoritative for activation, ordering, declarations, failures and
context side effects. This is a parser optimisation behind the existing
`collect_batch_dependencies()` API; it does not introduce a consumer API.

Keep this PR separate from the `Inputs.append()` optimisation and from any
redesign of runtime whole-model or identical-flag projection invalidation.

## Implementation and ownership

The production changes are confined to:

- `pytuflow/_tmf/compiled_control_tree.py`: compile a distinct literal-setting
  group kind using the existing source, configuration, branch and constructor
  proof boundaries.
- `pytuflow/_tmf/group_input_reuse.py`: validate the setting kind at runtime and
  clone independent setting states from successful-run prototypes.

`tests/test_setting_group_reuse.py` adds 29 regression cases. The parent
`tests/test_group_constructor_guards.py` keeps all 18 constructor assertions;
its mixed-model companion changes from literal `Set Code == 0` to dynamic
`Viscosity == <<E1>>` so those tests continue isolating the READ candidate.
The two existing contract workflows include the new setting module in their
path filters and explicit test selections.

Do not change `Inputs`, append recording, consumer materialisation, database
selection rules, physical file checks, public diagnostics or launcher handling
as part of this PR.

## Proof boundary to preserve

1. Require `type(inp) is SettingInput` and `type(command) is Command`. Exact
   type is deliberate: a subclass can introduce constructor or load effects.
   Retain the parent's definition-time constructor identity, bound-function
   and bound-owner checks at compile time and every group reuse. A hook or
   source-class replacement must take the ordinary path.
2. Plain `SettingInput` has a no-op load hook. Accept only nonempty literal
   scalar/tuple text with no variable, event, wildcard, selector or multipart
   syntax. The runtime translation must be resolved, stable and unchanged
   from the literal source. Runtime event markers can be ordinary words, so
   inspect the active event-marker set as well as visible token syntax.
3. Exclude specialised inputs, including `TimeInput`; declarations such as
   `Set Variable`; structural/DEFINE markers; `PAUSE`; file/folder values;
   variable/event-dependent expressions; dynamic scopes; empty settings; and
   settings associated with a spatial database. Do not widen this boundary
   merely to increase a candidate counter.
4. Permit only the existing proved global/scenario scope forms. Preserve
   branch order, ELSE/negation and exact scenario-slot provenance. The ordinary
   context evaluator selects active inputs before consulting the group cache.
5. Compare source identity, UUID, command text/value, line/part ownership,
   configuration and branch snapshots before reuse. Group keys include the
   setting kind. Existing GIS CODE / GRID ZPTS eligibility remains intact.
6. Keep prototypes invocation-local and bounded. A complete successful run
   must certify a prototype; failed or partial runs cannot seed later reuse.
7. Give every returned state independent mutable command, configuration,
   expander, scope, block, file-map and child-list state. In particular, plain
   `SettingInput.cf` is a list and must be reset independently. Do not add
   GIS-only lazy state to plain settings. Retain existing public build-source
   links while keeping the per-run internals independent.
8. Preserve streaming flag consumption and per-run provenance. Do not consume
   an iterator to discover its size or future flags, and do not share mutable
   run-state objects across runs.
9. Construction/proof/reuse must perform no new post-parse filesystem or GIS
   inspection. Do not introduce path canonicalisation or physical existence
   work into this parser optimisation.

## Current validation

On the isolated setting-only checkout based on the exact revision above,
Linux Python **3.14.8** passed the following on **2026-10-23**:

```text
python -m pytest -q tests/test_setting_group_reuse.py tests/test_group_constructor_guards.py tests/test_compiled_control_tree.py tests/test_batch_integration.py
107 passed in 26.08s
```

This comprises the 29 new setting cases, 18 parent constructor cases and the
existing compiled-tree/integration cases. The imported package location was
checked to be this isolated worktree. `git diff --check` also passed. The
earlier combined-worktree test results are not a substitute for this isolated
result.

Hosted Windows acceptance at implementation revision
`b25c235a9b0f291ddf19293280c347ea7e7580ac` passed on **2026-10-23**:

- [Batch integration acceptance](https://github.com/phantom-branch/PyTuflow/actions/runs/39904079389),
  including Windows Python 3.12/3.14 contracts and the complete public
  **161-TCF / 174-run four-mode graph differential**.
- [Deferred reference contracts](https://github.com/phantom-branch/PyTuflow/actions/runs/39904079715).
- [Materialised example-model parity](https://github.com/phantom-branch/PyTuflow/actions/runs/39904079796).

Independent review on **2026-10-23** checked the exact input/command types,
constructor function and bound-owner guards, event-marker exclusion,
scenario provenance, successful-run certification, configuration copying and
mutable setting-state isolation. No concrete correctness defect was found.
The same focused selection was repeated from this isolated checkout with
Python **3.14.8**: **107 passed in 28.70s**. No parser or test changes were
needed during this review.
Native performance evaluation remains outstanding; the hosted results do not
establish a speedup on the newly selected SMB workload.

On Windows, rerun the same focused selection with `py -3.14 -m pytest`, then
the existing hosted deferred-reference and batch-integration workflows. Their
public tutorial, reference ownership, database parity and upstream comparison
gates remain required; do not replace a failing comparison with a reduced
test list.

The new tests cover 500 distinct contexts with graph/off/uncached value and
complete-result parity; numeric tuples; scenario branches; mutable-state
isolation; failed-run certification; source and constructor changes;
subclasses; empty/dynamic/specialised values; arbitrary event markers; and no
filesystem probes after parsing. The 500-context case certifies five setting
signatures and elides 1,995 constructions while preserving six ordered inputs
per run.

An isolated **public-command component** also selected 15 unchanged exact
`SettingInput` lines from `runs/EG16_~e1~_004.tcf` in the existing public
`examples.zip` fixture and evaluated 300 distinct event contexts. Graph-off
constructed 4,500 states; graph-on constructed 15 and elided 4,485. All six
rotated off/on evaluations had equal complete `batch.runs` results. Parsing
was outside the comparison. Archive SHA256:

```text
e374c8e072679fc6c4dc11e63b270caa1101b6aebb84d70060872cdd1b0aa7d6
```

These are component operation counts, **not a new native-model speed claim or
an acceptance result**. Do not use constructor-elision counts alone to claim
an elapsed-time improvement. Proof, cloning, certification, parsing and
consumer materialisation costs still require measurement on the selected
native case. The old M480/N42 results are historical evidence only.

## Bounded next review

Review the existing patch for the proof boundaries and mutable-state isolation
above. Confirm exact `SettingInput` construction has no state effect that is
lost by reuse, including scenario-conditioned settings. Retain the constructor
guard regressions and verify that this branch does not depend on append
optimisation. Resolve a concrete defect with the smallest correction; open a
separate follow-up for another input type, broader cache architecture or
consumer performance work.

After local and hosted tests pass, complete the native evaluation below before
requesting merge. Record source revisions, Python version, mode order, run
count, parity, constructor metrics, phase times, elapsed time and sampled RSS.
Keep the PR a draft while those acceptance steps remain outstanding.

## Native evaluation on the newly selected SMB model

The user will select a suitable different model on a different SMB server.
No private paths have been supplied for this prompt. Use only these
placeholders in public material: `<model.tcf>`, `<exported-commands.txt>`,
`<expected-run-count>`, `<pytuflow-checkout>` and `<private-report-directory>`.
Use the anonymous label **`SMB-new`**. Keep native data, paths, command exports
and detailed reports local and outside both repositories.

The four-mode consumer diagnostic is implemented separately in
[ryan-tools #158](https://github.com/Chain-Frost/ryan-tools/pull/158). Its
initial implementation revision
`9cd839247c430dbd9a2ec4a7e2187f1e80cea91d` passed hosted Windows archive acceptance;
a clean-source acceptance review fix is being finalised. Consult that PR's
[work record](https://github.com/Chain-Frost/ryan-tools/blob/test/native-graph-benchmark-controls/docs/work/2026-10-23-tuflow-native-graph-benchmark.md)
for the final verified consumer revision before beginning native acceptance.

Once that diagnostic is accepted, use its checkout with the following
representative gate, replacing the placeholders locally:

```text
py -3.14 -m tests.fixtures.tuflow_example_repro.run_local_checks --tcf "<model.tcf>" --commands-file "<exported-commands.txt>" --expect-runs <expected-run-count> --label SMB-new --pytuflow-checkout "<pytuflow-checkout>" --output "<private-report-directory>" --batch --graph-compare --repeats 4 --storage-and-cache-conditions "<anonymous actual storage/cache conditions>" --representative-only
```

After representative first/middle/last runs pass, remove
`--representative-only` for the complete run set with balanced four-mode
rotation: eager, individual deferred, cached batch graph-off and cached batch
graph-on. Keep `cache_scopes=True` and the other batch caches enabled in both
batch modes. Never execute the exported launcher or a solver. Require
complete materialised identity parity, matching public preflight paths/issues
and no accepted partial collections.

Hold the model, exported run set, selected source revision and storage location
fixed within each trial. For parent-versus-draft comparisons, record each exact
checkout and use the same model, runs, consumer revision and storage in both
members of every comparison. Both parser and consumer checkouts must be clean
for benchmark acceptance. Report parse and evaluation/materialisation
phases separately. Comparing a new SMB model with old M480/N42 timings does not
isolate this PR's effect.

**Public-preflight boundary:** the consumer `check_simulation_inputs()` API
has no graph switch. The diagnostic retains a separate, untimed
individual/default-batch public-preflight gate; it is not graph-off/on public
preflight timing. Only the parser's public `compile_tree=False/True`
differential isolates graph contribution. Record both actual Git revisions,
effective modes and complete parity. Compare this PR and append-accounting
PR #14 individually against the same frozen parser baseline and consumer
revision before testing their combination. Do not modify the consumer
diagnostic inside this PyTUFLOW PR.

## Repository/API direction

PyTUFLOW owns parser semantics, activation/order/provenance, safe construction
reuse and the public batch contracts. ryan-tools consumes that API and owns
physical materialisation, unique-file validation, diagnostic instrumentation
and benchmark controls. A consumer improvement must not be implemented as a
second TUFLOW parser. If a missing API contract is found, specify it in a
separate PyTUFLOW change before depending on it in ryan-tools.

No consumer path-resolution changes belong in P7. Preserve ryan-tools'
preference for lexical `Path.absolute()` where canonical identity is not
required; any deliberate canonicalisation belongs in its consumer diagnostic
workstream, with the reason and reuse boundary made explicit.

## Separate follow-up: mutation during cached batches

Keep parsed build state stable during one cached batch invocation; make source
edits between separate calls. Existing whole-model and identical-flag
projection caches can retain a stale result if a caller edits source or swaps
constructors while a flag iterator is being consumed. That behaviour was
reproduced on master `3de5cd9`, PR #12 `84f1f38` and the reference-count merge
`b8d77d206a2ebd8c66738773dadc0814212aed40`. Editing between calls correctly
rebuilds proofs. `cache_scopes=False` observes the tested streamed edits;
`compile_tree=False` still retains identical-flag deduplication.

This draft preserves its per-input source/constructor guards but does not
redesign those complete-projection caches. The separate follow-up must choose
and document the mutation contract before implementing coordinated invalidation
of complete projections, variable plans and other source-derived caches.
Do not add an O(inputs)-per-run source scan or a partial invalidation scheme to
this setting-only PR as incidental scope.
