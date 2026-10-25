# W6 — Read File compatibility guard (deferred)

> Re-scoped 25 October 2026 at user request to minimise divergence from TUFLOW-Support/PyTuflow. This replaces the original broad ordered-include representation design (preserved in this PR's git history at `c1ab6741cfbe86b887bcc24694e7c7ba54a614e1`). It does **not** authorise a new parser or writer.

## Existing capability, no requested new feature

- Canonical upstream already has `Read File` parsing and flattened include processing.
- The merged W1/#17 safe-save transaction already preserves unchanged Read File bytes and **fails closed** before any replacement for edited include layouts it cannot safely represent (empty, missing, repeated or scoped).
- Existing tests in `tests/tmf/test_safe_model_saves.py`: `test_unrepresentable_include_layouts_are_preserved_or_rejected` and `test_repeated_include_edit_is_rejected_even_when_parent_reference_is_unchanged` explicitly protect these cases.
- These behaviours must remain intact for existing eager/deferred consumers. Do not add support for new ordered/nested include grammars just to make old editing limitations disappear.

## New decision gate

**No implementation is authorised by default.** This PR is a parked regression/compatibility follow-up, not a dependency of W2. Before modifying source, demonstrate a failure introduced by the fork (relative to canonical upstream) or a concrete consumer scenario requiring a bounded safety fix, with a minimal public fixture. If there is no such gap, close this PR as not needed and retain this note for historical traceability.

If a regression is demonstrated, restrict work to:
1. Reproduce it in a generated, small, no-solver test that fails on the current fork.
2. Correct only that failure without expanding parser/source representation or accepted grammar.
3. Prove unchanged source fidelity and rejected ambiguous saves still fail before mutation, with Windows Python 3.12/3.14 and existing regression/parity gates.
4. Request final Codex review; seek upstream contribution where appropriate.

## Explicit exclusions

No ordered include occurrence redesign, nested TRD stack/cycle engine, undo/history rewrite, new missing-file recovery semantics, new feature insertion, path canonicalisation, deferred graph/cache work, solver run, SMB benchmark or publication.

## PR relationship and status

This branch remains based on #18 only for historical stack compatibility; **#18 is not blocked by this PR**. At scoping time the branch has only the scope document as its own diff, no runtime changes. Its new status is **deferred**, not merge ready.
