# Cross-repository ryan-tools audit for PyTUFLOW performance PR #39

**Audit date:** 25 October 2026. **Central record/owner:** this PR (#39).
Actual external implementation remains owned by the respective
[ryan-tools](https://github.com/Chain-Frost/ryan-tools) PR until explicitly
merged or replaced. This ledger is not proof of new SMB performance.

## Existing integration foundations

- [ryan-tools #143](https://github.com/Chain-Frost/ryan-tools/pull/143) —
  event-aware preflight consumer: **merged**.
- [ryan-tools #156](https://github.com/Chain-Frost/ryan-tools/pull/156) —
  ordered batch inputs and BC activation ownership: **merged**.
- These are the existing authoritative consumer boundaries and must remain
  correct when optimising or adding read-ahead. No duplicate PR is needed.
- [ryan-tools #137](https://github.com/Chain-Frost/ryan-tools/pull/137)
  is a broader distribution/scripts remediation programme, with no TUFLOW
  Python source in its changed-file list at this checkpoint. Keep separate.
  Merging ryan-tools main may trigger the repository's automatic PyPI
  publishing: **do not merge benchmark tools just to reduce open PR count
  without considering release policy**.

## Active related ryan-tools PRs and dispositions

| PR | Head at audit | Confirmed state | Disposition and accountable boundary |
| --- | --- | --- | --- |
| [#158](https://github.com/Chain-Frost/ryan-tools/pull/158), native four-mode graph benchmark | `742b1d9481e25a9ed306bab524ce4da0fde2ab3b` | Draft; all five latest workflows successful, Codex clean, no unresolved threads. Executable frozen benchmark implementation is `f1f7958b79f3ffe84ba8ac0b04658f27c311460a`. | **Keep as benchmark infrastructure.** Use frozen diagnostic/known baselines for #39 native comparisons. Once acceptance is recorded, merge through the normal ryan-tools release policy or archive as independently reusable diagnostic; do **not** copy this benchmark tool into PyTUFLOW production. |
| [#160](https://github.com/Chain-Frost/ryan-tools/pull/160), stateful command/multi-TCF planning | `23c71935f32dd9435b6bc1487b44990f61e02d2a` | Draft, all three latest workflows successful and Codex clean, one old inline thread unresolved despite a corrected six-test comment-continuation case. | **Finish separately as functional correctness.** Resolve the review thread on proof, validate final parser provenance and route to a separate ryan-tools main merge. Not a direct #39 optimisation or reason to widen performance scope. Preserve 480-run / one-TCF and 240-run / two-TCF plan accuracy evidence; no model execution. |
| [#161](https://github.com/Chain-Frost/ryan-tools/pull/161), bounded single-worker I/O read-ahead | `f97e7f69eba97c4041ce41c41ba768af0855d1d1` | Draft; dedicated streaming/integration, fast, batch and hosted tests passed, **overall Python CI failed**: Policy/strict Pyright has **11 errors** in `tests/orchestrators/tuflow/test_streaming_io_probe.py`; two Codex threads (test data setup, wildcard directory exclusion) have fixes acknowledged but are still unresolved. | **Keep as the critical #39 dependent experiment.** Repair strict typing of test doubles and optional `on_run` consumer path without `Any` blanket suppression or assuming the installed PyTUFLOW already exposes an unmerged feature. Revalidate against exact #39 parser head; replay all applicable CI, resolve review threads after evidence, then benchmark on authorised Windows/SMB. This is NOT production readiness. |
| [#159](https://github.com/Chain-Frost/ryan-tools/pull/159), background advisory checker/GPU warnings | `dfd891bcf74eef8f95169f22eb2a34e3c8f4bb5d` | Draft; **four documentation files only**, no runtime implementation/tests; stacked on old #158 parent. Its intended behaviour is to start checking asynchronously and keep simulation launch nonblocking, with true failure and full issue reporting. Existing GPU sharing check is already present. | **Retain as independent runner backlog, not an SMB throughput optimisation.** Do not stack/merge the old #158 parent to deliver docs. The runner background behaviour may improve *time to first solver launch* but cannot establish faster total file validation. Once requirements are centrally recorded and a real runner PR exists, close this docs-only scaffold as superseded, preserving its link. No runner launch, GPU policy or solver change in #39. |

### Benchmark evidence that must not be conflated

- [Accepted #158 four-mode baseline](https://github.com/Chain-Frost/ryan-tools/pull/158#issuecomment-6367217192):
  480 runs, 8,160 materialised run/reference identities, 158 unique files,
  complete four-trial acceptance, unchanged production parser
  `e162c04330d24c37bee3ade94479cc4602651060`, frozen consumer
  `f1f7958`. Approximate mode medians: eager **117.72 s**,
  deferred **37.74 s**, graph-off **30.62 s**, graph-on **30.72 s**.
  Graph-on was ~0.10 s slower by median: **no demonstrated graph speedup**.
- [Separate SMB_PC2 run](https://github.com/Chain-Frost/ryan-tools/pull/158#issuecomment-6370804698):
  480 runs, **12,480 identities, 49 files** and only three completed trials;
  fourth interrupted. Its incomplete four-trial protocol must NOT be called
  accepted nor combined with the 158-file workload.
- [PyTUFLOW #14](https://github.com/phantom-branch/PyTuflow/pull/14)
  component optimisation decreased append/UUID enumerations, but the matched
  native campaign showed ~2.0–3.8% slower elapsed median.
- [PyTUFLOW #15](https://github.com/phantom-branch/PyTuflow/pull/15)
  proved a large synthetic constructor reduction; no accepted end-to-end
  benefit on the target SMB workload.
- [PyTUFLOW #25](https://github.com/phantom-branch/PyTuflow/pull/25)
  profiled six contexts, attributing wall time mainly to parser processing,
  scope evaluation, event processing and configuration handling. The observer
  imposed ~5.8–6.1× apparent slowdown, so instrumented calls are NOT
  uninstrumented workload latencies.

## Combined end-to-end pipeline and owner boundaries

```text
.bat / command list planning          ryan-tools #160 (independent scope)
               |
               v
RunRequest + effective TCF / flags     merged ryan-tools #143/#156
               |
               v
PyTUFLOW parse / scope / event / compiled tree / append
                                      PyTUFLOW #39 (P6, P7)
               |
               v
Completed immutable per-run projection PyTUFLOW #39 (P10 on_run)
               |
               +----> bounded read-only Path.stat pilot
               |      ryan-tools #161, one worker, opt-in
               v
Authoritative physical GIS/GPKG/raster/BC/paths
                                      merged ryan-tools consumer
               |
               v
Completeness and warnings/report       existing authoritative preflight
```

The `on_run` callback is **synchronous**, not a background checker by
itself. The #161 bounded worker may overlap *some* literal `Path.stat`
calls with subsequent context construction, but it may also double I/O
when the authoritative pass runs. Wildcard parents, dynamic folders, database
and GPKG selectors, interpolated tokens and GIS metadata require the full
consumer and cannot be guessed.

### Testable hypothesis for the observed 40-second preflight

The number of unique network files is insufficient to predict total time.
Measure: total references (with ordering/UUID ownership) per context,
different physical paths, path metadata call counts, expensive SMB directory
enumerations, SQLite/GPKG connects, actual byte reads and per-phase parser
CPU/context/consumer materialisation. Distinguish *first-result time*,
*first-launch time*, *full preflight completion* and *authoritative input
validation completion*. Do not label reduced launch delay as a reduction
in parser or network time.

All accepted native comparisons require the **same physical workload**,
matching parser + ryan-tools SHA, complete four-mode identities/provenance,
full authoritative preflight and balanced repeated uninstrumented times.
Private NAS paths, model identities and raw reports remain local.

## Next steps and close/merge policy

1. Complete [PyTUFLOW #39](https://github.com/phantom-branch/PyTuflow/pull/39)
   combined correctness and strict original-library/wheel gate; allow Codex
   review to finish. Do not claim native SMB benefit yet.
2. Prioritise **ryan-tools #161**: fix its 11 strict Pyright errors and
   verify the already fixed two review findings; repeat controlled Windows
   package/integration checks, including proper hosted dataset setup.
3. Use **#158's frozen accepted diagnostic** for uninstrumented baseline
   comparisons. Match independent P6/P7 vs combined P6–P10. Use #161 with
   and without the bounded worker as a separate consumer experiment.
   Do not merge #158 to main merely to run this benchmark if that would
   publish a new package unintentionally.
4. Complete **#160** independently when ready, because stateful BAT/TCF
   planning affects input correctness; benchmark only if its presence
   changes the measured workload.
5. Keep **#159 runner/advisory checks separate** until a fully tested
   nonblocking implementation exists. No automatic solver launch or GPU
   behaviours in #39.
6. **Source PyTUFLOW PRs #14/#15/#24/#25/#28** were transplanted into #39
   as reviewable commits and combined regression tests. Once exact-head
   receipt of those components is verified, close their *PRs* as
   **superseded by #39**, retaining their branches, comments and evidence;
   no production merge is implied by this administrative closure.
7. Do not close [PyTUFLOW #4](https://github.com/phantom-branch/PyTuflow/pull/4)
   until all other PR work is complete (explicit user instruction).

## Independent companion work

ryan-tools #137 (package/distribution and general script maintenance) and
RORB / QGIS utilities #118/#119/#145/#154 are outside #39, even where
their Git histories cross. These should not become performance prerequisites.
If ryan-tools release automation publishes from `main`, factor that into
merge decisions for #158/#160/#161; no release was authorised by this audit.

**Evidence status:** Audited from exact PR head metadata, changed files,
current-hosted workflow conclusions, Codex threads and published benchmark
comments. This is a living assessment; refresh SHA/CI and revalidate before
any actual runtime release or upstream submission.
