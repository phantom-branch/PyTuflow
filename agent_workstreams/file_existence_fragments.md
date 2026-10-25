# File-existence dependency fragments

2026-10-25. Needs review: local implementation and correctness validation complete.
Owner: ChatGPT. Next review: 2026-11-01.

User-authorized scope: reuse geometry/boundary/invariant evaluations across batch
runs using relevant scenario/event/TEF/Set Variable bindings. The later owner-authorized bounded benchmark is recorded below.
Target is 50% less elapsed time; the later paired consumer measurement is recorded below.

Public API: TCF.collect_file_dependencies(flags). Results preserve ordered command,
reference and database-activation records. TBC control files are distinct from
bc_dbase source tables. The consumer retains file/layer existence and essential
GIS-linked file discovery, but omits raster data validation.

The plan shares immutable fragments and expression results within one synchronous
read-only invocation, bounded per pool. It composes nested control-file fragments
without a full mutable run tree. Known leaves use the established evaluator on
cache misses. Complex TEF replacement retains Context.translate semantics.
Caches are keyed by effective substitutions and scope decisions; unresolved chains
also retain transitive bindings. A failed run cannot certify partial fragments.
Unsupported/custom input types or AD ownership use the established batch evaluator
with fallback counts/reason. No custom callbacks or cross-invocation cache.

The first implementation still computes subtree signatures for each run and binds
flat ordered output records per run. It does not yet supply a persistent immutable
source IR, effect-summary compiler, partial custom-node fallback or lazy public
run-state facades. Those are extension opportunities, not completed features.

Validation: 15 new correctness tests plus 92 existing batch/deferred tests pass on
normal Windows Python 3.14.6. Constructor-count regression proves three input-state
initializations for 20 runs sharing invariant geometry. No timing assertions.
Strict typing passes for the new module/tests; three touched legacy files retain
25 default-Pyright findings versus 28 on the base, with no added messages.

Delivery: local clone E:/Github/PyTuflow-batch-existence, branch
feat/batch-file-fragments, base ee44350. The implementation milestone is committed locally on this branch; not pushed.
Consumer: E:/Github/ryan-tools-batch-existence, same branch name; authoritative
cross-repository handoff is docs/work/2026-10-25-batch-file-fragments.md there.

Both wheels build. Final installed-pair consumer tests: 83 passed, zero skips. Copied-wrapper functional smoke passes. See the authoritative consumer record for commands, artifacts and limits.

## Bounded consumer benchmark and milestone

Owner authorized a ten-minute maximum. Four fresh-process 480-run file-only
invocations completed in 127.72 seconds. Reuse off: 41.527174 / 42.566088 s;
reuse on: 19.804411 / 18.621055 s. Median reduction: 54.31%. Each checked
50 paths with zero issues and matching consumer report projections; fragment
runs recorded 66,290 reuses and zero fallbacks. Two trials per condition,
uncontrolled cache/load, and no new full parser provenance gate limit inference.
The consumer handoff owns sanitized evidence and the paired parser commit ID.
No additional benchmark ran while creating this checkpoint.
