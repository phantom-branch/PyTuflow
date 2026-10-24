# P8: retain construction-profile evidence

| Field | Value |
| --- | --- |
| Status | Evidence-retention implementation complete; Windows validation and review pending |
| Updated | 2026-10-24 |
| Next review | 2026-10-25, or when exact-head hosted checks complete |
| Branch | `test/retain-construction-profile-evidence` |
| Base | `master` at `e162c04330d24c37bee3ade94479cc4602651060` |
| Scope | Developer profiling evidence only; no parser/cache/consumer changes |

## Why this independent change

The [retained native profile](https://github.com/Chain-Frost/ryan-tools/pull/158#issuecomment-6364640607)
had only its cumulative top 50 printed. No raw profile or caller table survived,
so absent functions and caller-specific costs could not be recovered. This
bounded implementation prevents that evidence loss in future approved captures;
it does not request a replay to reconstruct the missing historical data.

The [SMB_PC2 observation](https://github.com/Chain-Frost/ryan-tools/pull/158#issuecomment-6370804698)
is supplementary: three completed four-mode trials passed, plus a separate
untimed public preflight, but the fourth trial was stopped and the original
summary remains unaccepted. Graph-off preceded graph-on in every retained trial.
Its small graph difference is descriptive, not a robust causal speedup. Do not
mix its 12,480 identities / 49 files with the earlier accepted workload's
8,160 identities / 158 files, even though both have 480 distinct runs.

## Implemented

- [capture helper](../tests/profile_capture.py): raw `profile.pstats`, complete
  self/cumulative/caller/callee tables, and explicit private/incomplete metadata.
- [existing synthetic CLI](../tests/profile_batch_dependencies.py): optional
  `--output` directory; existing workload and mode selection remain unchanged.
- [focused tests](../tests/test_profile_capture.py): success, exception,
  KeyboardInterrupt/SystemExit, report failures, recursion counts, distinct
  same-basename functions, lazy-work handling, output protection, existing
  classic/monitoring profilers, and CLI compatibility/argument validation.
- [Windows workflow](../.github/workflows/profile-evidence.yml): Python 3.12 and
  3.14 helper/CLI checks without GIS dependencies or native model access.

Outputs must use a new directory outside the source repository. Physical
containment deliberately follows links; actual I/O retains the supplied absolute
spelling. Existing directories are never overwritten. Raw data is saved before
formatting tables. Workload exceptions remain authoritative even when report
formatting also fails. Hard process termination/power loss cannot run `finally`
and is not promised to preserve a complete capture.

Directory stripping is not sanitisation: it can combine distinct functions
with identical basename/line/name keys. These reports therefore retain full
paths and are PRIVATE. Nothing uploads or automatically publishes them. Publish
only separately reviewed, anonymised aggregate extracts. Python's profiler
format is runtime/platform dependent: retain interpreter details with raw files.

## Usage and measurement boundary

For the existing synthetic diagnostic, from the source root:

```powershell
python tests/profile_batch_dependencies.py --runs 120 --static-inputs 20 --output "$env:TEMP\pytuflow-profile-unique"
```

Choose a fresh output name each time. This is a documented invocation, not a
request to launch a new benchmark. The CLI imports its benchmark before profiling;
its combined capture includes fixture creation, parsing, all three existing
modes, parity assertions and cleanup. It does not isolate graph-off/on.
`--functions` limits only console output, not retained tables. The helper profiles
only the calling thread. Lazy work must be consumed within the action; a returned
iterator is rejected rather than mislabelling its creation as evaluated work.

`action_returned` means the callable returned, not that semantic parity passed.
`reports_complete` means evidence was written, not that the workload succeeded.
`accepted_for_benchmark` is always false. Caller-supplied provenance is explicitly
unverified: this helper is not a native runner and does not verify Git heads,
import origins, clean sources, model identity or physical inventory. The existing
native protocol still owns those checks. Do not add a second TUFLOW parser or
infer acceptance from a profile report.

Self time excludes profiled subcalls; cumulative and caller timings overlap.
Neither is a direct estimate of a future optimisation's benefit. Retained
function-level self times do not implement exclusive per-TCF/TGC/TBC/TEF timing.
See the [Python profiling documentation](https://docs.python.org/3.14/library/profile.html).

## Validation and next action

Local Linux CPython 3.13.5: **23 focused tests passed**; CLI `--help`, compilation,
and whitespace checks passed. This validates the dependency-free helper and CLI
with controlled callbacks, not a real PyTUFLOW workload, Windows behaviour or
Python 3.14 performance. The connected GitHub read/write API was available, but
container GitHub DNS access was unavailable; no complete source checkout/package
installation was obtained locally. Hosted checks must supply their own evidence.
No native workload, solver or synthetic model benchmark was executed locally.

Next: inspect exact-head Windows checks and review this bounded evidence-retention
change. Keep the broader opt-in, nesting-aware control-file/operation attribution
scope separate, including bootstrap/event loading, actual generator consumption,
failures and measured overhead. Invariant subtree and database Source reuse also
remain separate proposals, not implementations in this PR.

[Append accounting #14](https://github.com/phantom-branch/PyTuflow/pull/14) and
[literal-setting reuse #15](https://github.com/phantom-branch/PyTuflow/pull/15)
remain independent, already implemented candidates with native benefit unmeasured.
Do not combine their branches, repeat the accepted baseline, claim this helper
validates either candidate, or use it to validate
[runner #159](https://github.com/Chain-Frost/ryan-tools/pull/159).
Preserve frozen native diagnostic `f1f7958b79f3ffe84ba8ac0b04658f27c311460a`.
No merge, release, repin, private data publication or `unsorted` work is authorised.
