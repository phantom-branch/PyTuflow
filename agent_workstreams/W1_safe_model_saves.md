# W1 — Safe model saves: implementation handoff

## Checkpoint and ownership

- PR: [#17](https://github.com/phantom-branch/PyTuflow/pull/17).
- Branch: `fix/safe-model-saves`; base: `master`.
- Original planning/baseline commit: `e2086fba7796307429887d12f61c2e35542e5cd4`.
- Implemented runtime and regression checkpoint: [`4b929f50e6a017fa785ecd9e572ee6215a903272`](https://github.com/phantom-branch/PyTuflow/commit/4b929f50e6a017fa785ecd9e572ee6215a903272).
- Implementation tree: `1c37b91150e7e52f312aa44676c02c5759439b7c`. The uploaded tree was verified identical to the locally tested tree before the branch was advanced, without a force push.
- Windows acceptance: [W1 run 40074471962](https://github.com/phantom-branch/PyTuflow/actions/runs/40074471962), Python 3.12 and 3.14. Both jobs are running at this handoff checkpoint; no Windows pass is claimed yet. The PR conversation records subsequent exact-head results.

Runtime changes are confined to `cf_build_state.py`, the text read contract in `non_recursive_basic_parser.py`, and progress detection in `scope_writer.py`. Tests use dedicated W1 modules. Five assertions in the two original control-file write tests now expect the source's missing final newline to remain missing. This is the requested preservation contract, not a skipped test or blanket expectation change. The dedicated W1 workflow does not alter common test configuration or existing deferred gates.

No sibling branch was imported. No merge, release, dependent PR, solver run, private model/NAS access or native benchmark was performed. #16, #19 and #23 remain separate workstreams. #18 and #21 were not started.

## Implemented save contract

`ControlFileBuildState.write(inc)` creates a private `_SaveTransaction` and returns the same live control-file object only after publication succeeds.

1. Clone the save-relevant control/input/configuration state. Retain live object identity, UUIDs, child ownership, pending edits and history while planning. Inline FV blocks are detached for serialisation but are not separate file destinations.
2. Plan the root, dirty children, their flattened TRDs and supported database subclasses exactly once. Prepare reference changes and cached loaded paths without invoking the live `rhs` setter or reloading owned children.
3. Reject duplicate lexical/physical destinations, directory-alias collisions, destinations that overwrite another loaded source, read-only/non-regular/symlink destinations, and saved source bytes that changed since loading.
4. Render all control-file outputs in memory. Stage all outputs and recovery copies beside their destinations. Database subclasses render their existing format to a detached staging target, including the materials TMF header. Finish writes, flush, close and synchronise staging files before replacement.
5. Replace child outputs before parents. Each replacement is a filesystem operation; the full model is **not** one atomic transaction.
6. If replacement fails, restore completed replacements in reverse order and inspect the attempted destination as well. A network rename can complete before its acknowledgement is lost. The same verification applies to a rollback whose acknowledgement is lost.
7. Publish precomputed plain state assignments only after every replacement succeeds. Update paths, references, configurations and loaded-path caches together; clear saved dirty flags and begin a new history block while retaining earlier history blocks.

Serialisation, encoding, permission and staging failures propagate their original exceptions. They leave original destination bytes and live object state unchanged, and remove staging files where the filesystem permits cleanup. Cleanup failures are reported in exception notes or logging.

### Replacement failure and manual recovery

`ModelSaveError` is defined in `pytuflow._tmf.cf.cf_build_state` and exposes:

| Attribute | Meaning |
| --- | --- |
| `failed_destination` | Destination whose forward replacement failed. |
| `replaced_paths` | Completed forward replacements, including an attempted replacement found to have changed its destination. |
| `unrestored_paths` | Destinations that could not be restored or removed during rollback. |
| `recovery_paths` | Mapping from an unrestored existing destination to a retained file containing its original bytes. |
| `__cause__` | Original replacement error. |

A new destination has no original recovery copy; an unrestored new file is identified in `unrestored_paths`. Live paths and pending edit/history state remain at the pre-save checkpoint even if rollback is incomplete. The error does not report success or clear those pending edits. Restore the reported recovery files/remove reported new partial outputs before retrying or reloading.

This is recovery from handled exceptions. It does not guarantee consistency after process termination, power loss or concurrent external writes. Sources are checked before rendering/staging; there is no filesystem lock. Direct standalone `DatabaseBuildState.write()` calls remain outside this control-file transaction boundary.

## Control-file text contract

- Read explicitly as UTF-8 with `surrogateescape`, accepting an optional UTF-8 BOM before the first command. This preserves undecodable legacy bytes; it does not guess a legacy character set.
- Unchanged sources reuse their exact original bytes, including scope spelling, comments, BOM, mixed line endings and end-of-file layout.
- Edited sources retain their BOM, newline convention and presence/absence of a final newline. Edited mixed-newline sources use their first newline convention. Newly entered Unicode text encodes as UTF-8; undecodable original bytes remain intact.
- New control files use UTF-8 without a BOM and LF line endings.
- Unencodable new non-byte surrogate characters fail before any replacement.
- Normal RHS edits that reinitialise a flattened TRD input recover that input's recorded source ownership during save. W1 does not redesign the editing or undo API.

### Include boundary for W6 / #21

The inherited flattened representation cannot safely regenerate every empty, missing, repeated or scoped `Read File` directive. Unchanged source bytes remain safe. A changed output requiring one of these unsupported layouts now raises an actionable `ValueError` before writing, rather than silently dropping or regrouping a directive.

This guard is an intentional safety restriction. Ordered include occurrence editing, nested includes and the underlying representation remain owned by #21. Do not remove the guard until that representation has equivalent loss-prevention tests.

## Increment compatibility

For a loaded `model_010.tcf` with a dirty `grid_003.tgc`:

| `inc` | Root output | Child output |
| --- | --- | --- |
| `"auto"` | `model_011.tcf` | `grid_011.tgc` |
| `"025"` | `model_025.tcf` | `grid_025.tgc` |
| `"review"` | `model_review.tcf` | `grid_001.tgc` |
| `"inplace"` | `model_010.tcf` | `grid_010.tgc` |
| `None` | `model_010.tcf` | `grid_003.tgc` |

The arbitrary-suffix child fallback to `001` is inherited naming behaviour and is retained. `None` now implements its documented no-increment semantics instead of reaching the old `inc.lower()` failure. A newly created/unloaded control file retains its specified filename.

All added absolute-path handling uses lexical `Path.absolute()` and normalisation/identity checks. No new `resolve()` or `realpath()` calls were introduced; existing constructor path behaviour was retained to avoid changing the deferred-context API.

## Writer progress contract

The fixed 10,000-iteration ceiling is removed. `ScopeWriter.inputs()` tracks the iterator position and immutable scope/focus state. It raises an actionable error on backwards movement or a repeated unchanged state, and discards prior state tracking whenever the cursor advances. A valid large file is not rejected because of its length.

The focused large-file regression parses and saves a real generated TCF containing 20,000 commands and compares output bytes. Separate tests exercise nested IF/ELSE transitions, a stalled iterator, a rewind and repeated occurrences of the same input object. No solver or performance benchmark is involved.

## Validation evidence

### Baseline failures reproduced before the fixes

Real-package temporary-file regressions at the original runtime demonstrated:

- TCF and TRD comments containing byte `0x81` raised `UnicodeEncodeError` during saving and left their original targets at **zero bytes**.
- Injected parent serialisation failure left a truncated parent and three already-created child/TRD outputs.
- A real 20,000-command TCF failed at the old iteration ceiling. The stalled/backwards-iterator cases also failed their retained assertions.

The initial save reproduction had **3 failed, 0 skipped**. The original scope regression run had **3 failed, 2 passed, 0 skipped**. These red results were recorded before changing the corresponding runtime.

### Linux Python 3.12.14

Dependencies were installed into a task-local target using the normal interpreter; no virtual environment was created. Actual package imports were used throughout.

- Save/ownership/database/FV regression modules: **129 passed, 0 failed, 0 skipped**.
- Full focused suite, including the real 20,000-command save: **134 passed, 0 failed, 0 skipped**, in 175.23 seconds. This is correctness validation, not a performance claim.
- Existing 581-test selection: **549 passed, 32 failed, 0 skipped**, identical to the original runtime. The comparison tool reported **0 new compatibility regressions**.
- Compilation and `git diff --check` passed.

The 32 inherited Linux failures are one rainfall-database load failure, two GIS-referenced dependency inventory failures, and 29 FV tests where pandas 3.1.0's `Pandas4Warning` is promoted to an error by the existing warning policy. They were not skipped, suppressed or changed in this PR.

Focused command:

```text
python -m pytest -q tests/tmf/test_safe_model_saves.py tests/tmf/test_safe_model_save_ownership.py tests/tmf/test_scope_writer_progress.py --junitxml=reports/focused.xml
```

Existing regression selection, run identically against baseline and candidate:

```text
python -m pytest -q tests/tmf/test_control_file.py tests/tmf/test_scope_writer.py tests/tmf/test_altered_inputs.py tests/tmf/test_inputs.py tests/tmf/test_input.py tests/tmf/test_input_context.py tests/tmf/test_cf_context.py tests/tmf/test_context.py tests/tmf/test_fv_cf.py tests/tmf/test_scope.py tests/tmf/test_events.py tests/tmf/test_xs_db_from_cf.py tests/test_deferred_file_references.py tests/test_deferred_database_parity.py tests/test_batch_dependencies.py --junitxml=reports/candidate.xml
python tests/compare_upstream_tmf_junit.py --upstream reports/baseline.xml --fork reports/candidate.xml
```

The Windows workflow uses those commands on Python 3.12 and 3.14, rejects incomplete executions, requires every focused test to pass, rejects added regression failures/skips, and uploads all JUnit reports plus exact interpreter/dependency/source provenance. Unavailable or unfinished Windows validation is not a passing check.

## Checkpoint for W2 / #18

Build on `_SaveTransaction`'s plan → render → stage → replace/recover → publish-state boundary. Preserve input/child identity, the source ownership record, `_source_texts`, reference caches and the prepared-assignment commit discipline. Do not reintroduce live `rhs` setters or direct final-destination writes into planning.

W2 still owns undo/reset and project feature persistence; W6 owns ordered include representation. The current save implementation retains earlier history blocks and only marks successfully saved objects clean. Final review and Windows acceptance status belong in the exact-head PR handoff; neither this document nor the implementation starts a dependent workstream or authorises a merge.
