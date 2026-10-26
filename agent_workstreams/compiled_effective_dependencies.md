# Compiled effective dependencies and context preparation

Status: implementation in progress; performance acceptance pending.

This draft is stacked on [PyTUFLOW #39](https://github.com/phantom-branch/PyTuflow/pull/39),
parent `36ad04bd7cb045c48f3b77e8794c48a956c90c06`. Do not merge or retarget independently.

## Baseline and proof boundary

The parent stores immutable complete-subtree fragments. Its key translates every unique
descendant expression and evaluates every descendant scope list. Effective expression
values retain transitive bindings when a later pass can expose another variable or TEF
replacement. Database table cells participate in keys, preserving selectors and ownership.
Failed runs discard pending fragments. Invocation-local plans assume read-only parsed sources.

Preparation loads events during Context initialisation, before scoped Set Variable selection.
Variables are collected in traversal order with last-applicable assignment precedence, then
loaded together. Event selection can observe earlier event replacements, so mutable prepared
contexts cannot be shared. BatchContext disables its ordinary memoisation during event loading.

`ScopeList.contains` expands both operands, constructs temporary Scope objects and compares
case-insensitive names. Negated scopes and the preceding alternatives encoded by Else If/Else
must retain their existing semantics. A compiled predicate must either reproduce those rules
or use the ordinary evaluator. General Scope equality is outside this change.

The new selection tests compare complete uncached, cached and fragment records from one parsed
model. Twenty baseline cases pass, covering scenario/event slots, transitive filename aliases,
repeated selections, changed source identity with unchanged cell size, nested includes and a
missing selected source. Geometry, boundary, ESTRY, event and generic supported include classes
are exercised. `Read File` is a separate inline parser construct, not a ControlFileInput;
its pre-existing expansion semantics must not be inferred from ordinary include behaviour.

## Measurement protocol

Use normal Windows Python 3.14, one worker, the same frozen consumer and retained private
480-context workload. No solver, model changes, virtual environment or worktree. Native
fresh-process timings are separate from cProfile and preparation counters. Publish aggregates
only. Compare parent, preparation-only, manifests-only and combined candidates; retain neither
production optimisation without complete parity and reproducible CPU/wall improvement.

The fresh parent profile completed 480 contexts, 50 paths, 24 headers and 480 selectors with
zero issues/fallbacks. Its instrumented duration is diagnostic only. Preparation categorisation
is collected separately with `tests/context_preparation_probe.py`; raw profiles and records
remain outside the repository. Exact metrics and acceptance results will be added below.
