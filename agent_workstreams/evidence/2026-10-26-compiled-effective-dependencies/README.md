# Compiled dependency and preparation evidence

Completed 27 October 2026 (Australia/Perth); campaign started 26 October.

Draft [PyTUFLOW #41](https://github.com/phantom-branch/PyTuflow/pull/41) depends on [#39](https://github.com/phantom-branch/PyTuflow/pull/39).
Parent `36ad04b`; final production source `3812ed5`; consumer `a710f24` (relevant code/tests identical to current PR #161 `04999e7`).

## Native matched comparisons

| Source `3812ed5` | Storage | Parent median s | Candidate median s | Reduction | Parent / candidate CPU s | Peak MiB, parent / candidate |
| --- | --- | ---: | ---: | ---: | --- | --- |
| scope | SSD | 18.146228 | 5.577046 | 69.27% | 18.101562 / 5.578125 | 207.863 / 208.234 |
| manifest | SSD | 19.122716 | 15.826504 | 17.24% | 19.085938 / 15.835938 | 208.189 / 202.293 |
| combined | SSD | 18.534318 | 3.713377 | 79.96% | 18.531250 / 3.687500 | 208.191 / 202.281 |
| combined | SMB | 18.856490 | 4.170430 | 77.88% | 18.460938 / 3.656250 | 206.910 / 201.793 |

Each row is a separate same-storage matched block: two fresh-process samples per condition.
Use the ranges and sample SDs in [summary.json](summary.json); do not compare medians across rows to infer incremental benefit.
The 24 earlier native samples at `9acdfa6` comprise ABBA/BAAB per independent optimisation and combined mode.
They show median reductions of 70.9% (preparation), 12.7% (manifests), and 79.6% (combined).
Intermediate `9d70faf` adds custom Context hook guards and retains its own 16 trials.
Final `3812ed5` fixes the reviewed negative-alternative bug and a reproduced Unicode TEF selection collision.
Its 16 new trials and full-record parity supersede earlier sources for correctness/retention. Earlier numbers remain historical workload evidence.
Four initial preparation-only pilot timings at `824b6ba` are retained separately. No favourable-pass selection or cross-SHA pooling.

All 60 native trials completed 480 contexts, 50 paths, 24 headers and 480 selectors, zero issues/fallbacks.
All processes use normal Python 3.14.6, one worker and the same frozen consumer/options/flag order.
The boundary is the preflight call through report completion; imports/process startup are excluded.
No observers or profiler ran during native timing. Inputs were guarded before/after each trial.
Normalised Python source bytes match Git archives; original model/database bytes and flags match across storage copies.

## Complete output parity

All six fresh SSD modes (uncached, cached, parent fragments, preparation, manifests and combined) produce identical
complete 480-record serialisations. SMB uncached, parent fragments and combined records also match.
[parity.json](parity.json) retains hashes without records or model paths. Fresh SMB ordinary-cached mode was not repeated.
Deterministic UUID generation is restricted to parity parsing and restored before evaluation.

## Operation attribution

| Operation | Parent | Preparation | Manifests | Combined |
| --- | ---: | ---: | ---: | ---: |
| Full subtree keys | 24,495 | 24,495 | 2,880 | 2,880 |
| Compact signatures | 0 | 0 | 21,615 | 21,615 |
| Compact hits | 0 | 0 | 21,501 | 21,501 |
| Compact misses | 0 | 0 | 114 | 114 |
| Scope membership calls | 387,002 | 2,402 | 361,615 | 2,402 |
| Scope constructions | 5,877,564 | 40,740 | 5,590,227 | 38,863 |
| Scope expansions | 5,511,000 | 18,048 | 5,202,057 | 18,048 |
| Scope comparisons | 6,164,954 | 4,034 | 6,096,457 | 4,034 |
| Fragment evaluations | 2,494 | 2,494 | 1,096 | 1,096 |
| Fragment reuses | 22,001 | 22,001 | 23,399 | 23,399 |

The corrected combined candidate retains 2,880 full-key fallbacks for participating event substitutions.
TGC: one evaluation / 479 reuses; TBC: one / 479; TEF: 480 / zero, unchanged from parent.
The TGC formerly signed 20 expressions/20 scope lists per lookup. Its selected-file manifest uses one variable
and five distinct predicates, plus the resolved include path and selected parsed source identity.
The initial variable-only TEF-independence certificate examines 19 child expressions once per distinct binding/token-name signature.

Before production changes, preparation counted exactly 125,280 membership calls: 54,720 event eligibility,
54,240 scenario-variable selection, 10,560 event-variable selection, 4,320 combined selection and 1,440 global selection.
Those preparation checks constructed 1,580,160 temporary scopes. Variable-dependent scopes contribute zero on this workload.
High-level eligibility calls remain 38,880; they now execute compiled predicates without repeated expansion/equality.
[preparation-baseline.json](preparation-baseline.json) and [operations.json](operations.json) preserve the categories.

Separate process-clock diagnostics ([phase-cpu.json](phase-cpu.json)) show context/dependency CPU
17.390625 to 2.703125 s, event preparation 1.468750 to 0.156250 s, variable preparation 1.984375 to 0.015625 s,
signature generation 2.656250 to 0.593750 s and exclusive fragment evaluation 11.015625 to 1.656250 s.
These observed phase clocks are finite-resolution diagnostics, not native acceptance timings.
One unprofiled plan compilation took 1.970 ms parent versus 5.666 ms combined; compilation is included in native totals.
Combined and manifest peak working sets decrease; preparation alone increases by 0.371 MiB in the corrected block.

## Recommendation and remaining gates

Retain both optimisations in this draft: full provenance parity, independent repeated native improvements and
acceptable measured compilation/memory support retention on these warm workloads. Do not merge or release.
Cold storage, arbitrary models, Linux runtime behaviour and production multiprocessing have no new acceptance claim.
Custom hooks, unknown/cyclic variables, participating TEF substitutions and uncertain scopes retain conservative fallbacks.
Dynamic inline `Read File` uses whole-run ordinary fallback; generic supported TRD/TSCF includes use selected-file manifests.

Local validation: 557 parser/deferred/context tests and 119 actual PR #161 consumer tests pass, zero skips.
Ruff check/format and scoped strict Pyright pass. Earlier source-head Windows 3.12/3.14 combined, deferred, example parity
and integration CI pass; corrected-source combined/example checks also pass. Final documentation-head CI and
the new exact-head review remain separate gates; live status is in the PR description.
The PR description records live final-head CI/review status so this immutable evidence does not move the reviewed head.

## Reproduction and privacy

[protocol.json](protocol.json), [environment.json](environment.json), [source-guards.json](source-guards.json),
[timings.json](timings.json) and [stability.json](stability.json) retain sanitised protocol, hashes, individual trials and guards.
Audit scripts in `audit/` take private configuration/workload files; no configuration values, paths, flags, command lists,
records, CSVs or profiles are included. Native and diagnostic processes run separately. The selected source snapshots
are ordinary Git archives outside the checkout, not additional worktrees or environments.
The negation P2 finding is addressed in `3812ed5`, with flag/event-definition and full variable-selection regressions.
Unicode final sigma, dotless i and long s cases verify both direct TEF values and late filename-selection cascades.
Context replacement normalises keys with `upper()`; generic lower/casefold equivalence alone is insufficient.
Isolated operation profiles retain their source labels; the combined profile/phase clocks were repeated at the corrected source.

Audit source files have a `.txt` suffix to distinguish retained runners from package/tests.
`artifact-hashes.json` uses canonical UTF-8 LF text bytes, allowing normal Windows checkout line endings.
