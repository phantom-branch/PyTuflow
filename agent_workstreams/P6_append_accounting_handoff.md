# P6 draft: construction-local input append accounting

**Status:** draft follow-up; native performance validation pending.
**Branch:** `perf/batch-append-accounting`.
**Branch base:** PR #12 merged into `master` at
`e162c04330d24c37bee3ade94479cc4602651060`. Its tree is identical to the tested
source `126ec64e221908f5327ee9dc9d372c8084afaf12`, including the original
constructor guards and PR #13 reference counts. This work is independent of
setting-state reuse and must stay reviewable as its own PR.

## Agent handoff prompt

Continue this draft PyTUFLOW append-accounting PR from the baseline above.
The objective is to remove repeated parent UUID scans while a deferred batch
privately constructs a fresh control-file input list, preserving the existing
public and editing semantics. Inspect the current branch and repository
guidance before changing anything; compare the final diff to the recorded
baseline and keep this scope bounded.

The implementation and focused coverage are in:

- `pytuflow/_tmf/inp/inputs.py`: private `_ContextAppendRecorder`.
- `pytuflow/_tmf/cf/cf_run_state.py`: recorder lifetime, constructor trust and
  recursion boundary.
- `pytuflow/_tmf/batch_dependencies.py`: descriptor-free context callback
  proof, scope/data proofs and definition-time batch callback snapshot.
- `pytuflow/_tmf/context.py`, `event.py`: original inherited-context and
  event-database callback definitions used by that proof.
- `pytuflow/_tmf/scope.py`, `abc/bld_state.py`, `inp/inp_build_state.py`:
  original scope callbacks and input scope getters used by the raw proof.
- `pytuflow/_tmf/inp/cf.py`, `db.py`, `block.py`: original-constructor aliases.
  The baseline already supplies the GIS and base-input aliases.
- `tests/test_input_append_accounting.py`; regression selections in
  `.github/workflows/deferred-file-references.yml` and
  `.github/workflows/batch-integration-acceptance.yml`.

Preserve these contracts:

1. Enable the recorder only for an exact, active `BatchContext` with deferred
   file resolution, a fresh empty collection and a safe construction context.
   Discard it before returning the run state. Keep ordinary/eager contexts and
   public `Inputs.append()` on their existing live lookup path.
2. Preserve first-match UUID accounting for duplicates, independent visible
   and hidden indices, excluded block handling, ordering and historical index
   snapshots. Public UUID edits, exposed hidden-list edits, insert/remove,
   comment/uncomment, copy and undo must retain their existing behaviour.
3. Trust only the listed concrete input classes, their original constructor
   function bound to that exact input, and exact `Command`, `EventCommand` or
   `FVCommand` classes. Definition-time aliases must remain authoritative;
   never capture a replacement method as a new trusted baseline. An unknown
   constructor disables recorder use across the shared batch context before
   invocation. Perform this check only after scope selection and PAUSE handling;
   do not evaluate unsupported constructor descriptors while checking trust.
   The actual `BatchContext.batch_input_state` factory must also be the original
   method bound to that exact context. Retire the recorder before retrieving a
   replaced class descriptor or invoking a noncanonical/rebound factory.
   Collection length, owner identity and exact UUID guards must fall back to
   public append when violated.
4. Retire the enclosing recorder before invoking `ControlFileInput` or its FV
   block descendants: a child control's custom context hook can mutate its
   parent. Fresh child collections can still create independent recorders.
   Identify this boundary by input type; reading generic `inp.cf` can trigger
   lazy GIS I/O and is prohibited here.
5. Prove the complete context callback surface before creating a recorder and
   before each input's scope check. Translation, command construction,
   reference collection, resolution, variable declarations and scope callbacks
   must retain their original class definitions and current-context binding.
   Include inherited `Context` implementations reached through `super()` and
   the event database's `event_variables()`/`items()` chain. Inspect raw class
   and instance dictionaries; do not execute a getter while checking trust.
   Unsupported callbacks retain normal invocation through public append.
6. Before retrieving or evaluating an input's scope, prove its original scope
   getter and raw scope data, including cached available scopes. Custom scope
   containers/objects, rebound callbacks, descriptors and non-primitive scope
   values retire the recorder without changing evaluation/access counts.
   Validate scope-producing flags, variable/event mappings and declaration
   scopes once before a fresh recorder exists. This uses the existing stable
   source contract and does not rescan prior input UUIDs. Internal writer-only
   `_BlockScope` objects conservatively use public append.

Finish the focused correctness review and investigate any concrete failures.
Run the focused append and existing constructor-guard tests on supported
Python versions, plus the relevant ordered-input/edit regressions. Use the
Windows CI selections for archive-dependent compatibility checks. Keep the
draft until review and required checks are complete.

Then coordinate parser-only profiling and parity checks on the new model the
user owns, using the designated authorised workstation. Compare this branch
with the exact source baseline using identical model contents and distinct
run flags; report parse time separately, preserve ordered commands/UUIDs and
references, and check failure parity before interpreting timings. Use repeated
sequential trials and record source revisions. Keep private paths, inputs and
detailed reports on that workstation; publish anonymised aggregates. Do not
execute a launcher or solver. Native timing and a useful end-to-end benefit
remain unestablished until this work is done.

Do not add parser command coverage, setting-state reuse, broader projection
cache invalidation, a persistent UUID cache, new consumer behaviour or
ryan-tools changes to this PR. Record unrelated findings for separate work.
Summarise the final diff, tests, remaining risks and native evidence in the PR.

## Current evidence and reproduction

The initial extracted branch passed **50 tests on Python 3.14.8**: the 12 append
regressions, 18 baseline constructor-guard regressions and 20 existing ordered
input/edit tests. Two existing archive-dependent tests were deselected locally;
their Windows checks remain required. `git diff --check` passes.

```console
python -m pytest -q tests/test_input_append_accounting.py tests/test_group_constructor_guards.py
python -m pytest -q tests/test_batch_ordered_inputs.py tests/tmf/test_inputs.py tests/tmf/test_altered_inputs.py
```

For the local synthetic/edit selection, the second command was run with
`-k 'not remove_input_undo_2 and not undo_after_write'`. The isolated extraction
was tested against the recorded baseline without setting-state reuse.

The deterministic probe appends 500 fresh inputs: existing public append reads
UUIDs **377,750** times; the private recorder reads them **500** times, with
identical index history. The focused test gates linear work and parity rather
than machine-dependent duration. These counts establish avoided work only;
they are not a timing result or a claim of native model speedup.

Prior independent review covered class/instance constructor overrides, nested
control hooks, duplicate UUIDs, hidden inputs, live mutation and lazy GIS access.
An unrelated pre-existing blank-TCF append/edit history issue remains outside
this optimisation; the edit/undo regression uses an ordinarily parsed TCF.

### Independent review, 23 October 2026

The review reproduced an extension-hook regression: append trust checks read
`inp.context` before scenario selection. A custom constructor descriptor in an
inactive branch could raise where ordinary deferred construction correctly
skipped it; a selected unsupported descriptor was evaluated an extra time.

The guard now runs after scope selection and PAUSE handling, verifies the
class method before reading its bound method, and retires the local recorder
when a constructor is unsupported. Four regressions cover selected/inactive
scenarios and both a custom subclass and an overridden class descriptor.
They preserve constructor-access counts, complete input order/UUIDs and append
history relative to individual deferred construction.

That correction passed **54 focused append/constructor/edit tests on Python
3.14.8**, with the same two archive-dependent cases deselected locally. The
full integration-contract selection also passes **279 tests**: 277 passed in
the sandbox and the two RSS-sampling tests passed when rerun with host process
visibility (`psutil` cannot see the sandbox's process ID). Compilation and
`git diff --check` pass.

Hosted Windows checks also passed at `1acfb24d08b70b68c51995f9d4984e60871ea6f7`:
[integration](https://github.com/phantom-branch/PyTuflow/actions/runs/39909060780),
[reference contracts](https://github.com/phantom-branch/PyTuflow/actions/runs/39909060795),
and [materialised parity](https://github.com/phantom-branch/PyTuflow/actions/runs/39909060977).
That evidence predates the factory correction below and must not be presented
as hosted acceptance of the updated code.

Native performance validation remains outstanding; the recorded 500-append
count is still component evidence only. Hosted Windows checks and refreshed
Codex review must be checked at the updated head before native benchmarking.

### Codex review follow-up: batch factory identity

[Review finding](https://github.com/phantom-branch/PyTuflow/pull/14#discussion_r4356644124)
identified that an exact `BatchContext` can still override or rebind its
`batch_input_state` method. The input's own canonical `context` method did not
prove that the factory actually invoked was safe. A custom factory could alter
an earlier input's UUID without changing either collection length, leaving
the recorder's first-position maps stale. The reproduction yielded append
history `[(0, 0), (1, 1)]` where public append yielded `[(0, 0), (0, 0)]`.

The initial fix captured the factory function at definition time, checked the
exact class attribute before retrieving a replacement descriptor, and validated
the single retrieved method's original function and bound context before
invoking it. Unsupported factories retired the local recorder and disabled
recorder use through the shared context. Scope selection and PAUSE handling
still happened first, and descriptor access counts remained unchanged.

Six additional cases cover instance overrides, class overrides, descriptor
overrides, a descriptor that mutates UUIDs but returns the canonical bound
function, a canonical function rebound to another owner, and preservation of
the canonical recorder path. That focused Python 3.14.8 selection passed **60
tests**, with the same two archive-dependent editing cases deselected. The
complete integration-contract selection passed **285 tests** with host process
visibility for RSS sampling. The 500-append linear UUID-access regression,
compilation and whitespace checks remain green. Independent cross-review
found no further issue with this guard. Updated hosted acceptance and refreshed
Codex review remain to be checked; no native timing claim is made by this
correction.

### Codex review follow-up: context callback chain

[Review finding](https://github.com/phantom-branch/PyTuflow/pull/14#discussion_r4356705358)
showed that a canonical factory still calls overridable context hooks before
append. Rebound translation/command hooks can mutate earlier UUIDs; independent
inspection reproduced the same history corruption through scope selection,
resolution and cached-reference callbacks. The factory-only check is therefore
superseded by a single context dispatch proof.

The new proof compares raw, definition-time `Context`/`BatchContext` attribute
snapshots and inheritance, including the original implementations invoked by
`super()`. It checks instance shadows without binding them, permitting only an
original method explicitly bound to its current owner. The event database is
read from the verified raw context dictionary and must retain its exact class,
original `event_variables()` and inherited `items()` callbacks, and ordinary
attribute access. Both instance namespaces must be ordinary dictionaries;
assigned dictionary subclasses are rejected before their membership/index/get
methods can run. Standard event workloads remain eligible.

The check runs after context setup but before recorder creation, then before
each scope lookup, including scopes that will be inactive. It never evaluates
a property or adds a callback invocation. Retirement uses the raw context
dictionary captured when the recorder was created, so a later replacement
`__dict__` getter is not executed by the guard. The ordinary-context import
boundary, scope/PAUSE behaviour and existing constructor/recursion guards are
preserved.

Comparing complete context class snapshots is deliberately conservative:
even an unrelated class metadata change can disable the recorder. This is a
bounded append-construction proof, not a redesign of graph-cache invalidation
or support for arbitrary mutation of private cache objects during a batch.
The extra proof cost requires native measurement; the linear UUID-access count
alone does not establish an elapsed-time benefit.

Twenty-one added cases cover instance and inherited callbacks, mutating
descriptors (including getters returning the canonical method), inactive and
late-installed scope callbacks, same/wrong-owner binding, a public batch READ
that invokes the declaration signature, event callbacks, and canonical event
eligibility. The final two cases reject custom instance-namespace dictionaries
without invoking their membership, index or `get` methods.

The final focused Python 3.14.8 selection passed **81 tests**, with the same two
archive-dependent editing cases deselected. The full integration-contract
selection passed **304 tests** with host process visibility before only the
last exact-dictionary guard and its two proof cases were added; it was not
rerun after that narrow addition. The focused rerun includes the existing
500-append linear UUID-access regression. Production compilation and
`git diff --check` pass. Independent callback-inventory and code review found
no further defect within this bounded trust proof. Updated-head hosted Windows
checks and refreshed Codex review were pending at that handoff. The subsequent
head `63ad7024ffe1870bd26662baf90fcd05b5f37d7b` passed all three hosted workflows:
[integration](https://github.com/phantom-branch/PyTuflow/actions/runs/39911961298),
[reference contracts](https://github.com/phantom-branch/PyTuflow/actions/runs/39911961335),
and [materialised parity](https://github.com/phantom-branch/PyTuflow/actions/runs/39911961328).
Those checks predate the public-scope correction below and do not establish
acceptance of the updated code. Native timing remains pending.

### Codex review follow-up: public scope and event data

[Review finding](https://github.com/phantom-branch/PyTuflow/pull/14#discussion_r4356805039)
showed that canonical context callbacks can still dispatch through public
scope objects. The scope setter preserves `ScopeList`/`Scope` subclasses;
membership, resolution, negation and comparison callbacks can edit an earlier
parent UUID before append. Ten active/inactive reproductions failed on the
previous head with stale history while scope selection and callback traces
otherwise matched public append. Independent review also reproduced custom
scope-name containers, scenario string values and nested event-entry mappings.

The guard now proves the input's original scope getter before the normal
getter call, then inspects the raw scope list, supported built-in scope types,
original callbacks and plain name/flag values. Cached available scopes receive
the same data check. These checks do not call scope membership, resolution,
comparison or property callbacks. Unknown or modified scope behavior retains
its original evaluation order through public append, including inactive input
getters. Canonical scenario and event scopes remain eligible.

Before each fresh recorder is created, a bounded preflight checks public
scenario/event flag values, variable/event dictionaries, nested event-entry
dictionaries and compiled variable-declaration scopes. An event-scoped later
declaration can be inspected while an earlier READ is constructed, so proving
only the current input is insufficient. This preflight inspects raw data once
under the existing stable-source contract; it does not repeatedly scan previous
input UUIDs or redesign active-batch cache invalidation. Namespace keys must be
exact strings, checked before membership/index lookup, because public variable
loading can retain string subclasses with custom equality/hash behavior.

Definition-time scope class snapshots cover inherited callbacks and replacement
descriptors. The private writer-only `_BlockScope`, custom containers/scopes,
non-primitive public data and changed class metadata conservatively disable
append accounting. Their parser behavior remains delegated to the existing
scope and construction paths. Native elapsed-time benefit remains unproven;
the extra guard work must be included in the candidate benchmark.

Nineteen additional regression cases cover the public extension seams above,
including exact callback traces and scope getter counts, inactive branches,
canonical scenario/event recorder eligibility, cached available scopes, the
later event-scoped declaration, nested event entries and a public variable key
whose custom comparison would otherwise execute during the proof. The final
frozen-tree Python 3.14.8 selection passed **100 focused tests**, with the same
two archive-dependent editing cases deselected, and **325 integration-contract
tests** with host process visibility. Production/test compilation and
`git diff --check` pass. Independent review found no residual defect within
this bounded public callback/data seam. Updated-head hosted Windows checks and
refreshed Codex review are required for this correction; native validation is
still outstanding and the PR remains draft.
