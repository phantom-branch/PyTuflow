# [W2] Repair editing, undo history and project persistence

## Initial status

Draft scaffolding only: this PR currently adds a scoped work plan. Runtime changes and acceptance tests have not been implemented on this branch. Earlier review reproductions were isolated component checks, not full Windows/GIS integration validation.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `fix/model-editing-undo`.
- PR base: `fix/safe-model-saves`.
- Starting state: **Implementation follows W1**.
- Required parent: **W1**, [`fix/safe-model-saves`](https://github.com/phantom-branch/PyTuflow/tree/fix/safe-model-saves). The parent is initially a planning scaffold too. Reproduction tests and source investigation can start now; changes relying on the parent's contract must follow its implemented and validated checkpoint. Integrate that checkpoint before claiming dependent acceptance. Retarget to master only after the parent merges and the remaining diff is checked.
- Dependent work: W6 on `fix/include-roundtrip-fidelity`.
- Common regression/integration coordination: **W5**, `test/original-library-regression-ci`. Existing acceptance workflows must remain intact.

## Purpose

Scope-only draft; no implementation or acceptance pass is claimed. Repair nested edit dispatch and undo/reset invariants, then ensure feature insertion persists secondary files and honours existing overwrite/path-substitution policies. Base: W1 branch; W6 builds on W2.

## Scope

- Own original editing dispatch in pytuflow/_tmf/cf/cf_build_state.py, change-history invariants in pytuflow/_tmf/inp/altered_input.py and supporting Inputs/index handling in pytuflow/_tmf/inp/inputs.py.
- Correct recursive remove_input() and _add_input()/insert_input() traversal of the target's inp.cf instead of the encountered child control-file inp1.cf. Centralise owner lookup if it reduces inconsistent edit behaviour.
- Ensure each edit is recorded once at the authoritative root, grouped edits retain original order/identity, and parent/child dirty flags match changes. Review nested comment/uncomment paths only as needed to apply the same ownership contract.
- Restore history recording on every undo exit and exception; retain a usable current history block after reset; remove all members of an undone group from the correct history block.
- Fix project feature insertion in pytuflow/project/_common/project.py: _load_secondary_cfs() returns AppendDict values containing lists, but insert_feature_into() treats each value as a single control file and may skip dirty children. Reuse a consistent iterator/save path without writing the same file twice.
- Bounded project milestone: make create()/insert_feature_into() consistently honour existing interactive/skip/force choices for templates, projection files and empty GIS outputs; validate policy before writes and preserve skipped destinations. Do not broaden CRS behaviour or silently replace unrelated GeoPackage layers.
- Repair the discarded relative-variable mapping in project/_common/project.py feature rendering (make_relative() result is computed then ignored). Pass merged per-instance variables through make_relative() and render with its result, preserving intentional variable expressions and lexical cross-drive/UNC handling; inspect project/template/engine.py and project/_common/utils.py only as needed.
- Use W1's save contract for all persistence and failure handling. Do not redesign the staging/replacement layer or include representation.
- Add targeted regressions in tests/tmf/test_control_file.py, tests/tmf/test_altered_inputs.py, tests/tmf/test_inputs.py, tests/project/test_hpc_project.py and tests/project/test_fv_project.py as relevant.
- Preserve public editing APIs, scenario/event ownership, comments, UUID/provenance semantics and lexical absolute Windows paths.

## Acceptance criteria

- [ ] Through a loaded root TCF, locate a setting in a child TGC/TBC, insert/remove relative to it, undo once, save and reload; cover two levels of nesting and unchanged siblings.
- [ ] Exercise edit->undo->edit, empty reset->edit, populated reset->edit, child-only history followed by parent-only undo, grouped insertion with blank-line gaps, and exceptions thrown by an undo action.
- [ ] Assert _block is restored, one usable current history block remains, all group members are consumed exactly once, and second undo never replays an already-undone operation.
- [ ] Verify removal/restore retains intended source order, scope, parent ownership and identity; dirty/history state remains correct after W1 save failures and successes.
- [ ] Run real HPC and FV feature insertion using temporary project fixtures with multiple secondary files; verify intended changes persist after reload and untouched siblings remain byte-identical. Cover the list-valued secondary map directly.
- [ ] For create() and insert_feature_into(), test existing templates, projection datasets and empty GIS outputs under force, skip and interactive yes/no. Skip and interactive-no preserve content, sidecars/layers and CRS; force applies only to the intended output; invalid policy fails before mutations. Use temporary GIS fixtures and the supported installed provider, not a solver.
- [ ] Feature templates use relative substitutions computed from merged instance overrides. Test same-drive paths and explicit safe cross-drive/UNC behaviour without canonicalisation or implicit CRS changes; preserve unrelated GeoPackage layers.
- [ ] Pass affected TMF and project tests on Windows Python 3.12 and 3.14. Existing isolated-method reproductions document starting defects only; report exact installed-package test results and CI at the implementation SHA.
- [ ] Keep dependency/base linkage to W1 and report the editing contracts W6 can rely on; no deferred execution changes.

## Exclusions

- No safe-save implementation duplication; W1 owns staging, encoding and commit recovery.
- No Read File/include representation redesign; W6 owns it.
- No new broad undo/redo product, persistent history store or unrelated project generation features.
- No deferred/batch/graph/cache changes, solver launches, private data, package release or merge.
- No broad project-generator or CRS redesign beyond the scoped persistence, existing overwrite-policy consistency and discarded relative-substitution repairs.

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Implement W2 in phantom-branch/PyTuflow on the assigned W2 branch and existing draft PR. The draft starts with scope documentation only. It depends on W1, so the PR base must remain the W1 branch identified in the linked scope; W6 depends on W2. Use the actual PR/branch names and source SHAs recorded by the coordinator. Do the authorised implementation without asking for another confirmation.

Fetch current refs, inspect AGENTS.md or other applicable guidance and the latest linked W1 contract, then check out your assigned branch. Preserve concurrent work. Do not commit to W1, W6 or master, create a replacement PR, rewrite shared history, merge or release. Integrate newer W1 commits into your branch when necessary and retain the dependency link. If W1's implementation is not ready, proceed with independent editing tests/fixes and clearly record the writer integration item.

Repair the original editing and persistence defects, not deferred execution. In pytuflow/_tmf/cf/cf_build_state.py, remove_input() and _add_input() loop through each child input as inp1 but traverse inp.cf from the requested target. A setting inside a TGC therefore never reaches the intended child: isolated execution returned None for removal and raised ValueError for insertion. Use a clear owner traversal, preserve scenario/event scopes and control-file provenance, and ensure nested edits reach the actual owning object. Review comment/uncomment dispatch and duplicate parent/root recording only as required to establish the same contract.

In pytuflow/_tmf/inp/altered_input.py, undo() sets _block=True but has an early return before clearing it when the history only belongs to a different child. Future edits then stop being recorded. reset() pops the last history block without restoring a current block, so later operations can IndexError. Grouped undo tests membership in the outer list of history blocks instead of the current record list, leaving already-undone group members behind. Repair all exits and exceptions with reliable state restoration, preserve at least one current history block, consume a group exactly once, and avoid duplicate root/child recording. Examine pytuflow/_tmf/inp/inputs.py where index/order behaviour participates, but do not perform an unrelated container rewrite.

Fix the concrete project persistence error in pytuflow/project/_common/project.py. _load_secondary_cfs() returns an AppendDict whose values are lists. create() already iterates both levels, while insert_feature_into() treats a list as an individual cf and tests its dirty attribute; intended changes to secondary files can therefore be skipped. Make the saving path consistent, cover multiple secondary files and duplicate references, and rely on W1's completed save contract. Preserve the documented feature API. As a bounded second project milestone, make existing interactive/skip/force policy consistent across create() and insert_feature_into(), including projection files and empty GIS outputs currently written before template decisions. Validate choices before mutation; skip or interactive-no must preserve the affected destination, and force must apply only to intended outputs without destroying unrelated GeoPackage layers. Repair the feature-template path where make_relative() returns mod_variables that rendering ignores: run merged instance variables through make_relative() and render with that result. Inspect project/template/engine.py and project/_common/utils.py only as required. Do not broaden CRS rules or add unrelated generator features.

Before changing behaviour, add meaningful regressions using real temporary models/projects and the installed package. Existing component reproductions are evidence for prioritisation, not Windows integration passes. Extend tests/tmf/test_control_file.py, tests/tmf/test_altered_inputs.py and tests/tmf/test_inputs.py for nested insert/remove, grouped gaps, edit/undo/edit, reset/edit, parent-only undo with child-only history, and a failing undo callback. Verify order, UUID/provenance, scopes, dirty flags and recording state, not just list length. Add HPC/FV insertion persistence checks in tests/project/test_hpc_project.py and tests/project/test_fv_project.py. Save/reload the projects and check actual secondary-file contents and unchanged siblings. Test force/skip/interactive yes/no across templates, projection and empty GIS datasets with real temporary provider fixtures; confirm skipped content, sidecars, CRS and unrelated layers are preserved. Cover merged feature overrides in relative substitution, including explicit cross-drive/UNC handling.

Coordinate with W1 for staging/failure behaviour and leave include representation to W6. In-memory state after a failed save must be consistent with W1's declared contract. Preserve lexical network-drive/UNC paths; use Path.absolute() when an absolute path is necessary and introduce no resolve()/realpath calls. Use modern built-in generic annotations while preserving the package's tested Python versions.

Run the affected editing/project selections and relevant existing regressions on Windows Python 3.12 and 3.14, using hosted CI if local Windows is unavailable. Separate pre-existing failures, unavailable fixtures, skips and new regressions. Do not launch a solver, access private models, run SMB performance tests, modify deferred/batch/graph code, publish or merge.

Commit and push only to the assigned branch. Update this PR with the exact implementation SHA, test commands/counts, Windows CI links, dependency status and remaining risks. Explain the owner/history/persistence guarantees W6 may rely on. Request final review only after the bounded implementation and relevant checks are complete, and keep the PR draft if acceptance is incomplete.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
