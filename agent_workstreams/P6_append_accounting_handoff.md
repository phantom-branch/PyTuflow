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
   invocation. Collection length, owner identity and exact UUID guards must
   fall back to public append when violated.
4. Retire the enclosing recorder before invoking `ControlFileInput` or its FV
   block descendants: a child control's custom context hook can mutate its
   parent. Fresh child collections can still create independent recorders.
   Identify this boundary by input type; reading generic `inp.cf` can trigger
   lazy GIS I/O and is prohibited here.

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

The extracted branch passes **50 tests on Python 3.14.8**: the 12 append
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
