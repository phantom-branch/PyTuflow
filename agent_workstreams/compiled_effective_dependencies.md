# Compiled effective dependencies and context preparation

Status: implemented and measured; retain both optimisations in draft pending final review and remaining CI.
Updated: 27 October 2026 (Australia/Perth).

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

## Implementation

`compiled_scope.py` freezes literal built-in scenario/event alternatives once per parsed
scope-list identity. It evaluates conjunctions/negation against normalised flag memberships,
without allocating temporary scopes for every comparison. This operates during event loading
as well as variable selection, preserving visibility of event-definition keys in source order.
It does not share mutable Context instances or duplicate BatchContext's decision cache.
Unknown/variable/extended scopes and changed built-in scope definitions use the ordinary path.
Flag and variable loading invalidate the per-context membership representation.

`effective_dependencies.py` freezes expression variable closure, all possible ordered/scoped
assignment dependencies and distinct scope predicates. Unknown/cyclic lineage uses full keys.
Raw transitive effective bindings conservatively distinguish contexts, even when an intermediate
translation happens to coincide. All database cells remain represented. A variable-only
certificate checks every successive substitution pass for active TEF tokens, including tokens
assembled across variable boundaries. Certificates are reused only for identical bindings and
ordered token names. Participating TEF substitutions retain the complete original full key;
no assumption is made about cascading event values or variables introduced by them.

Each selected parsed control file has a separate manifest. Include filenames resolve using the
existing translator/constructor and `select_deferred_children`; the compact key includes resolved
reference paths and the ordered identity/path/signature of each selected source. Missing,
unparsed or ambiguous selection raises the existing error before result lookup. Repeated
selection shares only immutable descriptors/references and parsed read-only source identities.
Selections and fragments publish together after complete run success. Both remain bounded to
10,000 entries and one synchronous collection invocation. A new collection recompiles after
parsed-model changes; external file edits require reparsing, as with the ordinary evaluator.

The private `_Plan` switches `use_scopes` and `use_manifests` permit independent tests and
measurements without changing `TCF.collect_file_dependencies()` or its result dataclasses.
General Scope equality, preparation ordering, command constructors, deferred database ownership,
include matching and public output formats retain their existing authority.

## Explicit fallback boundaries

- Custom model/input/include hooks and unsupported input subclasses retain whole-run ordinary fallback.
- Unknown/cyclic variable closure, malformed tokens, dynamic/variable scopes and participating TEF
  substitutions retain complete subtree keys with reason counters on the invocation-local plan.
- Unproven runtime bindings and unresolved selected flags retain ordinary scope/full-key evaluation.
- `Read File` is parsed inline by PyTUFLOW, separately from ControlFileInput. Dynamic inline TRD
  filenames use an explicit whole-run fallback. This preserves the existing ordinary outputs;
  it does not repair the ordinary parser's pre-existing inline selection/nesting limitations.
  Generic supported control-file includes with TRD/TSCF sources use the new selected-source mechanism.
- Parsed sources must remain read-only during one synchronous collection. No persistent cache,
  mutable Context sharing, solver, multiprocessing or first-run prioritisation is introduced.

## Validation at final production source `3812ed5`

Forty-nine new scope/include regressions pass. Final local validation passes 557 combined
parser/deferred/context tests and 119 actual consumer tests, zero skips. Ruff check/format and
strict Pyright pass for all three production modules. Custom Context membership/available-scope
hooks disable compiled predicates; custom translation hooks retain full subtree keys.
The strict check explicitly documents intentional imports of the parent's retained private
original methods; it does not suppress unknown-type diagnostics globally.

The retained private 480-context workload passes complete public-record parity in uncached,
cached, parent-fragment, preparation-only, manifest-only and combined modes. The common SHA-256
is `68ceba1fb5e865c8d3894165c8e99eb2d73096dfda9609dc2307f5959a8d8d93` on SSD. This preserves
all dataclass fields, UUIDs, ordering, file/layer identities, database activations and selectors.
The final source checkpoint repeats all three candidate parity modes before native measurement.

The benchmark consumer is pinned to `a710f24ffb1698e949937f56a0212b6ae599e54e`. The relevant
consumer implementation and tests are byte-identical to current [ryan-tools #161](https://github.com/Chain-Frost/ryan-tools/pull/161)
head `04999e77d497173294f43e137dedbd0bde60d88a` (verified using Git diff). No consumer checkout
or dependency pin is changed. Hosted Windows Python 3.12/3.14 checks run on this draft PR.

## Native evidence and retention recommendation

[Sanitised evidence bundle](evidence/2026-10-26-compiled-effective-dependencies/README.md)
contains every native timing, operation/phase attribution, parity hashes, environment, source
and input stability receipts, limitations and audit runners. Raw model/configuration paths,
flags, commands, records, CSVs and profiles remain private. No TUFLOW solver was executed.

| Final source comparison | Storage | Parent median s | Candidate median s | Reduction |
| --- | --- | ---: | ---: | ---: |
| Preparation independently | SSD | 18.146228 | 5.577046 | 69.27% |
| Manifests independently | SSD | 19.122716 | 15.826504 | 17.24% |
| Combined | SSD | 18.534318 | 3.713377 | 79.96% |
| Combined | Warm SMB | 18.856490 | 4.170430 | 77.88% |

Each final row is its own balanced ABBA/BAAB block with two samples per condition. Earlier
source `9acdfa6` has two independent blocks per optimisation and combined mode (24 trials),
followed by 16 intermediate custom-hook trials at `9d70faf` and 16 corrected-source trials at `3812ed5`. Four preparation pilot trials are
retained separately. Do not pool source revisions, compare across storage locations or infer
incremental savings by subtracting medians from different blocks. Background load and CPU/cache
conditions remain uncontrolled; no formal statistical-significance or cold-storage claim.

All 60 native passes retain 480 contexts, 50 paths, 24 headers and 480 column selections, zero
issues and zero whole-run fallbacks. Baseline/candidate process CPU falls with elapsed time.
Combined peak working set decreases from 208.191 to 202.281 MiB on SSD and 206.910 to 201.793 MiB on SMB. One separate plan-construction observation rises from 1.970 to 5.666 ms;
that cost is included in native collection. The manifest reduces full subtree keys 24,495 to
2,880, with 21,615 compact keys and explicit participating-TEF fallbacks. Scope constructions
fall 5,877,564 to 38,863, expansions 5,511,000 to 18,048 and comparisons 6,164,954 to 4,034.

The invariant TGC uses one effective variable and five distinct predicates rather than signing
20 expressions/20 scope lists on every lookup. Selected reference paths and parsed-file identity
remain in its key. TGC/TBC each evaluate once and reuse 479 times; TEF still evaluates 480 times.
The separate phase diagnostic reports context/dependency CPU 17.390625 to 2.703125 s; event,
variable, signature and fragment phase details are in the bundle and excluded from native timing.

**Recommendation: retain A and B in this draft.** Both improve independently in repeated matched
comparisons, complete output parity passes and compilation/memory overhead is acceptable for
this workload. Generic supported variable-dependent includes retain selected source identity;
unproven dynamic inline Read File constructs remain a documented ordinary fallback.

## Delivery and remaining gates

Draft [PR #41](https://github.com/phantom-branch/PyTuflow/pull/41) targets
`perf/consolidated-smb-preflight` and explicitly depends on #39. The parent branch, consumer
checkout and pre-existing local `.gitignore` edit were preserved. No extra PR/worktree,
virtual environment, model edit, solver, merge, release or production multiprocessing.

At earlier source `9d70faf`, Windows Python 3.12/3.14 combined contracts and paired consumer,
deferred tests, complete public example parity, integration differential and fast source
contracts pass. Original-library/wheel CI was still running when this evidence was written.
The final documentation head runs the combined Windows matrix again. The PR description is the
live receipt for exact-head CI and the newly requested Codex review; keep this PR draft until
those gates finish and any findings are resolved. No Windows 3.12 interpreter is installed
locally; its validation is hosted. Linux execution and cold-storage behaviour remain unmeasured.


## Review corrections

The first exact-head Codex review found that selected flag/event-definition alternatives such as
`A | !B` lost the negative status of the exploded `!B` component. Fixed in `3812ed5` by retaining
only positive exploded membership alternatives, matching ordinary comparison rules. Both direct
scope and complete variable/dependency result regressions pass; the P2 thread is addressed and resolved.

A separate reproduced collision involved late Unicode TEF filename substitutions. Token proofs,
expression binding guards, full keys and filename-selection guards now match Context's uppercase
replacement-key lookup, including final sigma, dotless i and long s. These fixtures compare complete
ordinary uncached, ordinary cached and fragment outputs. TEF-dependent inline Read File names also
receive explicit ordinary fallback. All native parity/timing checks were repeated after these fixes;
pre-review data remain separately labelled and do not establish correctness of the earlier source.

The final-source local suite passes 557 tests and the paired consumer suite passes 119, zero skips.
A new review of the final documentation head is requested after publishing these corrected receipts.
