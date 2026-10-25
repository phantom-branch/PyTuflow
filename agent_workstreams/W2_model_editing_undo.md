# W2 — Narrow upstream-compatible nested edit ownership fix

> Revised 25 October 2026. Supersedes the broad W2 planning proposal (preserved in git history at `3fdca609042f72559520bddf75df55230c4d76fd`). This is not an undo redesign or a new editing feature.

## Objective

Preserve **existing** PyTUFLOW editing APIs when called from a root TCF against an input owned by a loaded child control file, and confirm the resulting edit still round-trips using W1's transaction. The original upstream library already implements `remove_input()`, `undo()`, `reset()` and nested control-file traversal. Avoid expanding any API or supported file grammar.

## Only implementation authorised here

- Correct one inherited owner-traversal defect in `ControlFileBuildState.remove_input()`: iterate the encountered child-reference's `inp1.cf` rather than the target setting input's unrelated `inp.cf`.
- Add a generated two-child control-file regression that demonstrates the pre-fix root-to-child deletion returns `None`, then tests ownership, unrelated sibling bytes, and save/reload through the existing W1 API. Test `None` and `auto` increment only as useful.
- No change to the safe-save transaction, source-byte preservation, deferred execution, QGIS, GIS/project generation or arbitrary control-file semantics.
- Preserve public signatures, input UUIDs, parent relationships and dirty tracking. If the focused test shows any wider failure, document it rather than opportunistically expanding scope.

## Explicitly deferred / excluded

- **No change to `undo()`, `reset()` or `AlteredInputs`**. They existed in canonical upstream; known unrelated history bugs are outside the fork's purpose.
- No `insert_input()` redesign, grouped edit history, interactive force/skip policies, project creation, relative-variable path transformations, or new project/editor APIs.
- No new `Read File` representation or parser changes; #21 is a *separate, regression-only* compatibility guard and is not a prerequisite for W2.
- Do not merge automatically, publish or benchmark. Prefer contributing the isolated upstream bug fix to TUFLOW-Support/PyTuflow for upstream ownership.

## Acceptance

- Demonstrate the original `remove_input()` traversal bug with a generated root/child case (no proprietary models).
- With this one-line fix: remove an existing input via its root's public API, save via W1 and reload, preserving sibling files and paths.
- Exact-head Python 3.12/3.14 Windows focused and retained regression evidence, clean Codex review. Leave draft until acceptance completes.
- If upstream or the fork moves meanwhile, preserve newer work and re-evaluate the diff.

## Provenance and status

Original upstream reference: [`TUFLOW-Support/PyTuflow` at `cf908cc9`](https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/_tmf/cf/cf_build_state.py). This defect is inherited, not newly created in our fork. Parent PR #17 and inherited-regression PR #27 are merged in `master` at `9d1ad6664566e4c650f77d2498251f2a0bd6aa40` on initial scope revision. Implementation and exact-head validation outcomes must be recorded separately.

## Review correction — exact object identity

Codex found P1 on the first candidate: two child owners may have commands equal by text even though they are distinct input instances. This required a small, narrow correction. Root removal must restrict traversal to the target's actual owner and remove the **same input object** from both views of `Inputs`, not the first value-equal command. The original public signature and value-equality behaviour elsewhere remain unchanged. Regressions exercise a duplicate command in two separate child files (both increment modes), and duplicate commands within one owner. The prior W2 regression with distinct values is retained. This is a safety correction to the *same* inherited removal bug, not new undo/history functionality. Exact-head CI and re-review are required.
