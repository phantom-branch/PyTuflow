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
rebase. Use cProfile self time (not nested cumulative) to discriminate _Plan._key,
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
