# PR #39 — identify the remaining fragment-evaluation and key costs

Date: 26 October 2026. Owner: PyTUFLOW PR #39.
This investigation, any justified optimisation, tests and evidence stay on this existing PR.
No branch stack, new upstream PR, runner-first scheduling, solver run, or merge is authorised.

## Why 5,256 evaluations may or may not be excessive

In the accepted 480-run, 50-path / 24-CSV-header workload, the old parser counted:

| Operation | Batch count | Per run |
| --- | ---: | ---: |
| Fragment evaluations (cache misses) | 5,256 | 10.95 |
| Fragment reuses (cache hits) | 66,290 | 138.10 |
| Total fragment key lookups | 71,546 | 149.05 |

The hit rate is 92.65%. Misses are different effective subtree signatures,
not file opens, failures, or one-for-one distinct physical files. Their
necessity depends on scope, event, variable and included-child changes.

The current _Plan._key collects all descendant expressions and scope predicates
for a parent subtree, including possible inactive branches. A dynamic descendant
can force an ancestor signature to miss, even if most sibling input states are
reused. Every cache hit also forms a key; an evaluation-count reduction is not
necessarily a wall-time reduction. Neither constructor cost nor network I/O can
be inferred from the counters.

## Read-only diagnostic added to this PR

The opt-in files are:

- tests/fragment_evaluation_probe.py — scoped, reversible wrapper around
  _Plan._key and _join plus run-context construction counts.
- tests/profile_fragment_evaluations.py — private 1–2,000-context CLI,
  complete ordinary-vs-fragment public-projection parity gate and optional
  cProfile with only code basenames and function names reported.
- tests/test_fragment_evaluation_probe.py — deterministic count/parity,
  fallback, source-redaction and CLI contracts.

These instruments are **not imported by production code**, do not modify
fragment cache keys or normal collection, and use no additional worker threads.
The diagnostic reports anonymous source slots and built-in input types, without
paths, UUIDs, flags, model names, expanded values, or source lists.

## Native execution — authorised SMB agent only

Run with Python 3.14 in the ordinary repository checkout; do not create a venv
or move the model from the SMB source. Export the exact retained 480 parser
context flags to a **private** JSON array of flag strings or dictionaries,
preserving order and duplicates (not the BAT's solver commands).

PowerShell, using private environment variables populated locally:

    python -m tests.profile_fragment_evaluations --tcf $env:TCF_PATH --runs-json $env:RUNS_JSON --output $env:PRIVATE_PROBE_OUTPUT

It will perform fragment collection under a temporary diagnostic wrapper,
then independently compute ordinary batch dependencies and require exact equality
for all 480 complete public run records. Output is
fragment_diagnostic.json in a new local folder.

For functional attribution, select a representative **separate** private
24-context JSON with both reused and varying scenario/event signatures and use
a second new local output directory:

    python -m tests.profile_fragment_evaluations --tcf $env:TCF_PATH --runs-json $env:SAMPLE_RUNS_JSON --output $env:PRIVATE_PROFILE_OUTPUT --cprofile

Report the histogram/top anonymous input slots and by-input-type misses and key
costs; also the number of command/reference/activation records that _join must
rebase. The probe now splits misses between **new local expression/scope signatures**
and **already-seen local signatures with new whole-subtree keys**. The latter
provides evidence of dynamic descendants (or database rows) forcing parent
re-evaluation, but does not by itself prove that those misses can be removed.
Use cProfile self time (not nested cumulative) to discriminate _Plan._key,
CompiledExpression.bindings, _FragmentContext.translate, scope evaluation,
_join and dataclasses.replace. Inclusive timings overlap; profiling and wrappers
alter performance and must NEVER be compared to uninstrumented wall-time baselines.

Do not publish private raw source model paths, input names, flags, records or
manifests to GitHub. Sanitise aggregate numbers before leaving a PR comment.
The JSON is designed to omit these, but manually inspect it before uploading.

## Decision gates and implementation choices

1. If ~11 misses/run are mostly distinct variable/event-dependent signatures,
   preserve them. Changing cache-key equivalence to reduce the numerical count
   without proof can silently reuse the wrong file and is unacceptable.
2. If most misses are *parent/include* fragments whose own command/reference
   stays invariant but a descendant changes, consider separating a proven
   immutable local parent fragment from the descendant composition. Preserve
   exact deferred child selection and database ownership/activation semantics.
3. If cache hits dominate cost, prioritise cheaper **safe signature computation**
   and scope handling, not speculative more caching. The previous per-run
   signature memo measured 18.47 s vs 18.56 s and did not show a speedup.
4. If repeated _join rebase counts are substantial, consider retaining
   immutable offset-bound descriptors at safe recurring offsets, with a bounded
   cache and complete public identity/order parity. Do not substitute a lazy
   incomplete result or change TCF.collect_file_dependencies's public API.
5. For any candidate, require strict tests for TEF cascades, Set Variable,
   scenario/event scopes, multiple active BC databases, fallback/errors,
   provenance, and no physical source opens while evaluating fragments.
   Verify exact paired ryan-tools #161 consumer code.
6. Only after that, use the existing frozen SMB 480-run plan for a short,
   balanced, uninstrumented, separate-process A/B/B/A comparison, with complete
   public provenance. The instrumentation's own wall times are invalid for this
   comparison. Decline changes that do not produce a reproducible improvement.

Release/merge: withheld pending exact-head CI, Codex review, corrected historical
review-thread resolution, native provenance and any accepted measured change.

## New SMB workload result — 26 October 2026

The supplied command list did not contain the stated 480 simulations. A
read-only parse found 456 active `START` commands, zero duplicate contexts and
one root TCF. The expected 480-way parameter product has 24 combinations absent
from the supplied list. This investigation used the 456 commands actually
present, in their exact order; it did not invent the absent contexts or execute
the command list/TUFLOW. Private paths, flags, source metadata, hashes and the
complete manifest remain in local evidence only.

Environment: Python 3.14.5; PyTUFLOW started at
`fd25c858975f1559206354d562319d27039055b7`; ryan-tools PR #161 was validated at
`a710f24ffb1698e949937f56a0212b6ae599e54e`.

| Metric | Result |
| --- | ---: |
| Simulation items | 456 present (480 expected; 24 absent from supplied list) |
| Distinct root TCFs | 1 |
| Fragment evaluations | 5,016 |
| Fragment reuses | 62,954 |
| Cache hit rate | 92.620% |
| Evaluations per run | 11.000 |
| Lookups per run | 149.057 |
| New local signature misses | 1,830 |
| Descendant/database-row-driven misses | 3,186 |
| Dominant miss types | Database 2,280; Folder 1,368; Control file 914 |
| Key-generation cost, representative 24 | 0.0187 s self; 1.7019 s inclusive |
| Join/rebinding overhead, representative 24 | `_join` 0.0056 s self; `dataclasses.replace` 0.0018 s self / 0.0132 s inclusive |
| Baseline execution time | 16.101, 16.221, 16.298, 16.421 s; median 16.259 s |
| Candidate execution time | 38.089 s for rejected structural experiment; remaining trials stopped |
| Full provenance parity | Passed, complete ordinary versus fragment records for all 456 |
| Test/consumer status | 95 PyTUFLOW tests and 119 ryan-tools #161 tests passed on Python 3.14 |

The cache stabilised strongly after the first contexts: 434 of 456 runs reached
the observed floor of 10 evaluations, the final run also had 10, and only one
run (the first) had 175. The remaining miss histogram was five runs at 11,
eight at 20, one at 21, three at 32, and one each at 34, 35, 42 and 58.
There were no fallback runs, key errors, failed fragments or unsupported inputs
in this workload.

The 5,016 misses are not primarily a simple cache defect. Three dynamic folder
inputs account for 1,368 genuinely new signatures. Five database inputs account
for 2,280 misses, of which 2,273 reuse the command's local signature but differ
in conservatively keyed database rows. Two control-file parents are forced to
miss on every run by varying descendants, accounting for 912 of the 914
control-file misses.

The 24-context cProfile separated self from inclusive time. `_Plan._key` and
`_Plan.evaluate` had only 0.0187 s and 0.0128 s self time respectively;
`CompiledExpression.bindings` had 0.0173 s self / 0.0762 s inclusive;
`_FragmentContext.translate` had 0.0109 s self / 0.1520 s inclusive. Scope
membership dominated the nested key path at about 2.06 s inclusive, while
rebinding was small. `_join`'s 2.6047 s inclusive time is chiefly nested child
evaluation and must not be read as join overhead.

Two safe-looking candidates were tested and rejected:

1. An extra per-run scope-result cache reduced calls only to an already-cached
   `BatchContext` wrapper and left underlying scope work unchanged.
2. Separating each control-file command's local fragment from child composition
   preserved full provenance and reduced evaluations from 5,016 to 4,106, but
   it destroyed valuable whole-subtree reuse. Lookups rose from 67,970 to
   79,800, join calls increased, and one clean process regressed from the
   16.259 s baseline median to 38.089 s. The experiment was removed.

Accordingly, no production optimisation is retained. Reducing the counter alone
would be actively misleading on this workload. A future structural attempt is
only worthwhile if it preserves whole-subtree reuse while avoiding repeated
ancestor signature work; database-row key reduction would require a proof that
row selection, BC ownership and event-dependent columns remain exact.

Diagnostic reporting was extended to retain anonymous per-context progression
and focused cProfile records for key, evaluation, translation, scope, join and
`dataclasses.replace` costs. Public APIs and production collection behaviour are
unchanged. Ruff could not execute under local application control. Scoped
Pyright had no new findings; three findings remain in pre-existing diagnostic
lines. Hosted Windows 3.12/3.14 CI and a fresh Codex review are required on the
published head.


## Private per-input and per-filename cache attribution (26 October 2026)

An additional **opt-in, private-only** diagnostic maps individual fragment-cache
lookups to their original source control-file command and the resolved file/layer
patterns held by the cached immutable fragment. Production PyTUFLOW, its cache
and the ryan-tools consumer remain unchanged.

Use a NEW local report folder outside the repo and a private explicit run-flags
JSON from the user's actual 456 simulation commands. Do not fabricate the 24
missing combinations; a future complete 480-command set may be used as supplied.

```powershell
python -m tests.profile_fragment_evaluations --tcf $env:TCF_PATH --runs-json $env:RUNS_JSON --output $env:PRIVATE_PROBE_OUTPUT --private-file-attribution
```

The ordinary-vs-fragment per-run provenance check must pass before writing the
private CSVs. No BAT/CMD/TUFLOW solver is executed.

| Output | Purpose | Disclosure |
| --- | --- | --- |
| ``fragment_diagnostic.json`` | Anonymised global counts and a private-trace summary | Safe aggregate; no filenames |
| ``private_input_totals.csv`` | Source control-file path/line, command, lookups, hits/misses, total key time, nested-adjusted evaluation time, p50/p95 hit/miss times | PRIVATE |
| ``private_lookup_trace.csv`` | One row per hit/miss: run ordinal, input slot, fragment ID, key time, inclusive and exclusive evaluation time | PRIVATE JOIN KEY |
| ``private_fragment_files.csv`` | Fragment ID to resolved file/layer pattern, linked source input and direct/descendant ownership | PRIVATE |
| ``private_file_totals.csv`` | Resolved file/layer, emitted logical references, hit/miss associations and non-additive associated timing | PRIVATE |

Join ``input_slot`` to source rows and ``fragment_id`` to fragment/file mappings.
Sort sources by ``key_inclusive_ms``, ``hit_exclusive_total_ms`` and ``hits``;
check corresponding resolved filename associations. The trace has ~68k records
on the last reported 456-run input plan, but paths are factored into separate
CSV tables rather than repeated on every lookup.

**Interpretation matters:**

- A fragment hit is a Python cache reuse, not a physical file open/stat/scan.
- Fragment references include complete descendant subtrees: a single hit can
  be associated with many file patterns. Parent and child associations overlap.
- File-level ``associated_*_ms`` is the whole fragment cost associated with
  each resolved filename for correlation; it is **not additive across files**
  and is not time spent accessing that file.
- ``logical_run_references`` and ``logical_database_source_rows`` are separate
  syntactic-dependency counts from completed runs, not cache-lookups or I/O.
- Exclusive evaluator time subtracts nested fragment evaluation, but includes
  key work and tracing overhead. Instrumented measurements cannot establish a
  production speedup against prior ~16-second clean wall-time benchmarks.
- The private CSVs contain actual source filenames, raw source command texts
  and resolved paths. **Never publish, attach to PR #39, or paste these CSVs into
  public review.** Only sanitised aggregate summaries may be published.
- This opt-in instrumentation operates only in the calling process and patches
  parser entry points temporarily; no production API or consumer behaviour changes.

The new code is ``tests/fragment_filename_attribution.py``, called from the
existing CLI with ``--private-file-attribution``. Host-side tests exercise
counters, file/source joins, redaction, fallback and patch restoration. The
private SMB trace itself must run on the user's own Windows environment.

If timing suggests a candidate improvement, validate unchanged full provenance,
then compare separate uninstrumented A/B/B/A trials. Do not optimise merely to
reduce the number of cache hits or report per-file costs from these associations.
