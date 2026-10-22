# P4 agent prompt — Validate the integrated PyTUFLOW optimisation stack

**Draft PR:** `feat/batch-optimisation-integration`, **base** `test/batch-tutorial-benchmarks` (PR #7), which targets `feat/batch-compiled-control-tree` (PR #9), then `feat/batch-run-activation-index` (PR #8), then PR #6. PR #5 has already merged into `master`. This PR is a **future integration gate**, not an independent fourth implementation track.

## Agent prompt (execute only after the prerequisite PRs are implementation-complete)

Validate the **already integrated** P1 per-run activation index
[PR #8](https://github.com/phantom-branch/PyTuflow/pull/8),
P2 compiled immutable control tree
[PR #9](https://github.com/phantom-branch/PyTuflow/pull/9),
and P3 public tutorial benchmark
[PR #7](https://github.com/phantom-branch/PyTuflow/pull/7).
Preserve their respective implementations, tests, metadata and history.
Read `batch_evaluation_workstreams.md`, the three agent handoff documents,
latest source and review threads. Do not merge any PR to `master`, publish
packages or launch solver simulations.

### Integration algorithm and sequencing

1. **Do not approve merging until P1/P2/P3 implementation is complete**, exact-head Windows focused tests pass and relevant review findings are addressed.
2. Synchronise this integration branch with the **latest P3/PR #7** head,
   which must already contain P2/PR #9 and P1/PR #8 by ancestry.
   Do not reset, force-push or overwrite another agent's work.
3. **Do not merge PR #8 a second time.** Confirm `git merge-base --is-ancestor`
   for `#6 → #8 → #9 → #7 → #10`. P1's `tcf_run_state.py` and focused tests
   are already inherited through PR #9. Preserve those semantics while P2's
   graph handles reusing invariant command nodes.
4. Retain P3's tutorial benchmarking implementation, already inherited from
   the parent PR #7; do NOT merge that branch a second time. Verify P3's
   benchmark test expectations against P2's graph counters and keep its
   latest commits in this branch.
5. Resolve any overlapping tests/docs deliberately. Cross-compare all
   changes and verify no feature from P1/P2/P3 was silently lost. Keep the
   PRs draft until integration review decisions.
6. Verify no input (including file-free commands) is reordered/dropped,
   active BC database UUIDs retain exact command activation time, unknown
   cases bypass optimisations rather than disappearing, and failed runs emit
   no partial dependencies.
7. Compare original eager / single deferred / PR #5 cached batch /
   integrated optimised batch on **identical public TUFLOW tutorial cases**
   with complete per-run command UUID, line, owner, source role, path,
   GPKG layer and database activation/source identity including missing AND
   extra entries. Run real attribute/materialisation acceptance through the
   separately maintained ryan-tools consumer; do not relabel parser-only
   identity parity as physical-materialisation parity.
8. Measure graph evaluations, `InputRunState` and `Command` allocations,
   skipped constructors, cache hits/misses/bypasses, elapsed phase timings
   and memory peak in reproducible same-runner trials. Label repeated
   tutorial combinations separately from genuinely distinct contexts.
9. Coordinate downstream ordered-input adapter readiness with
   [ryan-tools PR #143](https://github.com/Chain-Frost/ryan-tools/pull/143)
   and its supporting BC selection PR #151. **Do not modify ryan-tools
   production consumer files in this PyTUFLOW integration PR.**
10. Handoff the exact merged code SHAs to the **single SMB-capable agent**
    for later in-place native B1/B2 validation. **Never request or upload
    private SMB datasets.** Only approved non-identifying aggregate results
    may appear on GitHub.

### Explicit constraints

- Keep this PR draft and based on P3/PR #7; the exact ancestry is
  `master` (merged #5) → #6 → #8 → #9 → #7 → #10.
  PR #8 is **not** a sibling and must **not** be merged again.
- No persistent or cross-invocation caching; all caches are invocation-local.
- Preserve Windows lexical network-drive/UNC paths, source provenance,
  existing eager/single-deferred APIs and fail-closed ambiguity behaviour.
- No TUFLOW solver launches, model edits, packaging release, consumer repin or
  Linux parity expansion.
- Public performance evidence: verified TUFLOW tutorial dataset only.
  Tiny synthetic test data may verify correctness and counters but not
  production speedups. **One separate SMB agent** exclusively executes
  native-project benchmarks on its own authorised share.
- This integration PR should eventually contain **working integrated code**,
  not just this markdown plan. No merge until exact-head CI and evidence
  gates are complete.

## PowerShell commands (from existing PyTUFLOW checkout)

```powershell
git fetch origin
git switch feat/batch-optimisation-integration
git pull --ff-only origin feat/batch-optimisation-integration
# Confirm exact upstream ancestry and latest branch heads.
git fetch origin feat/batch-ordered-dependency-plan feat/batch-run-activation-index feat/batch-compiled-control-tree test/batch-tutorial-benchmarks
$links = @(
    @('feat/batch-ordered-dependency-plan','feat/batch-run-activation-index'),
    @('feat/batch-run-activation-index','feat/batch-compiled-control-tree'),
    @('feat/batch-compiled-control-tree','test/batch-tutorial-benchmarks')
)
foreach ($pair in $links) {
    git merge-base --is-ancestor "origin/$($pair[0])" "origin/$($pair[1])"
    if ($LASTEXITCODE -ne 0) { throw "Broken PR ancestry: $($pair -join ' -> ')" }
}
# Refresh PR #10 only when its parent PR #7 has changed.
# Native GitHub stacks require linear history: rebase this layer on its parent.
gh stack rebase --upstack --no-trunk --remote origin
# PR #8 is already contained in PR #9. Do not merge it again.
git rev-parse HEAD
py -3.14 -m pip install -e . pytest
py -3.14 -m compileall -q pytuflow/_tmf
py -3.14 -m pytest -q tests/test_batch_ordered_inputs.py tests/test_batch_activation_index.py tests/test_compiled_control_tree.py tests/test_batch_dependencies.py tests/test_compiled_dependency_plan.py tests/test_deferred_file_references.py tests/test_deferred_database_parity.py
py -3.14 -m pytest -q tests/tmf/test_cf_context.py tests/tmf/test_context.py tests/tmf/test_xs_db_from_cf.py
git diff --check
git status --short
```

Run `py -3.14 -m pytest -q tests/test_tutorial_benchmark.py` as well as the
public tutorial benchmark under its **actual documented CLI**. Do not guess a path, test dataset location or successful result.
Windows 3.12/3.14 exact-head CI plus the public 161-TCF/174-run consumer
replay must be checked before accepting this PR.

### PR handoff

Report source-branch commit SHAs, integration SHA and exact merge strategy,
test/CI URLs, all differences (or an exact no-difference proof), benchmark
data scope/trial parameters, unknown/unsupported fallbacks and outstanding
native SMB validation. Do not trigger Codex review until the full
integration and relevant tests are ready; do not merge or publish.


## PR #7 synchronisation and merge repair - 2026-10-23

Merged the current PR #7 head `8367c90ad4067168204500d7c6a8099ff7f7f712` into the
integration branch, preserving PR #10's raw benchmark docstring for Windows paths.
The restored scenario-projection tests exposed a semantic mismatch: scenario READs
were classified as generic DEFINE/conditional commands, and ELSE branch types were
not accepted by the scenario-only whole-model proof. A separate conditional marker
now permits that narrow proof while leaving general command-template reuse disabled
for conditional READs. DEFINE blocks, event conditions, unknown scopes and dynamic
paths retain their conservative bypass. Added DEFINE/nested-DEFINE regressions and
updated the old negative scenario test to retain an event-dependent path.

This repairs integration of the new batch optimisation; it does not change original
eager context behaviour. Local Windows/Python 3.14 validation: **266 parser/integration
tests and 68 consumer tests pass**; compileall and whitespace checks pass. Public
four-mode tutorial replay, materialised consumer replay and native SMB benchmarks
are rerun against a retained snapshot of the resulting integration commit. Older
4b9505a/1d022c2 results remain revision-specific, not acceptance for this merge.

### Native stack repair

The initial integration merge was retained locally as `backup/pr10-5053a07`.
GitHub still rejected the stack because PR #7 was based on an older PR #9.
PR #7 was rebased onto PR #9 (`204c9e0`), preserving its 30 benchmark commits;
PR #10 was then rebased onto PR #7. The two conditional-proof conflicts were
resolved with the tested integration contents. Explicit lease-protected pushes
published PR #7 `66872d5` and PR #10 `5b11415`. Both now report mergeable.
No PR was merged. Original PR #7 is retained as `backup/pr7-8367c90`.

PR #10 `5b11415` has exactly the same Git tree as retained benchmark snapshot
`5053a07`: `53f09c3d7f97d356c4f1ca3f258c5657afbceb8f`.
The full verified public 161-TCF / 174-run parser replay passes in all four
modes (three rotated trials), and the separate materialised consumer
eager/deferred/batch replay passes. Native SMB trials are still in progress;
do not infer native performance from the public fixture. Hosted exact-head
checks are queued, not yet accepted. Subsequent documentation commits do not
change the parser source used for these checks.
