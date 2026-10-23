# [W6] Preserve ordered Read File directives when editing models

## Initial status

Draft scaffolding only: this PR currently adds a scoped work plan. Runtime changes and acceptance tests have not been implemented on this branch. Earlier review reproductions were isolated component checks, not full Windows/GIS integration validation.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `fix/include-roundtrip-fidelity`.
- PR base: `fix/model-editing-undo`.
- Starting state: **Implementation follows W2**.
- Required parent: **W2**, [`fix/model-editing-undo`](https://github.com/phantom-branch/PyTuflow/tree/fix/model-editing-undo). The parent is initially a planning scaffold too. Reproduction tests and source investigation can start now; changes relying on the parent's contract must follow its implemented and validated checkpoint. Integrate that checkpoint before claiming dependent acceptance. Retarget to master only after the parent merges and the remaining diff is checked.
- Common regression/integration coordination: **W5**, `test/original-library-regression-ci`. Existing acceptance workflows must remain intact.

## Purpose

Scope-only draft; no implementation or acceptance pass is claimed. Preserve include occurrence identity and source order during read/edit/write, including empty or unavailable includes. Base: W2 branch, inheriting W1's safe writer.

## Scope

- Own Read File/include source representation and reconstruction in pytuflow/_tmf/cf/cf_build_state.py, with supporting changes in pytuflow/_tmf/inp/trd.py, pytuflow/_tmf/inp/inputs.py and parser/source metadata only where required.
- Retain each include directive as its own source occurrence with original text, path expression, inline comment, source location, scope, owner and include-chain identity. Preserve ordered flattened-input access for existing consumers.
- Eliminate _get_trd_inputs() grouping semantics that collapse repeated occurrences of one path into a single Read File directive. One physical target and multiple ordered include occurrences must remain distinct concepts.
- Preserve empty and missing include directives during save/reload. Missing targets need explicit diagnostics; loading and saving must not silently delete the source command or fabricate a missing file.
- Preserve scope/variable context at each include occurrence and the order of intervening commands. For edits that imply incompatible content for one shared physical target, reject the ambiguous write before replacement rather than silently choosing one occurrence.
- Milestone 1 is same-model include fidelity. A later milestone may support nested TRDs only after consulting authoritative TUFLOW semantics and completing a bounded include-stack/cycle design and tests. Until then preserve the current explicit nested-TRD limitation; do not introduce guessed semantics.
- Use W1's staged writer and W2's owner/history contracts. W6 does not own a second save engine, independent undo rewrite, or deferred dependency/compiler/cache implementation.
- Extend tests/tmf/test_control_file.py, tests/tmf/test_input.py, tests/tmf/test_scope_writer.py and documentation in docs/examples/working_with_read_files.rst; add a focused include-roundtrip test module if useful.

## Acceptance criteria

- [ ] Real-package round-trip of two occurrences of the same TRD separated by a setting/variable command preserves both directives, original order and each occurrence's scope/comment/source ownership.
- [ ] Empty, comment-only, missing and repeated includes remain present after unchanged and edited saves; missing files are not invented, and diagnostics identify the originating command.
- [ ] Save/reload with changes before, inside and after an include preserves active settings and ordering for representative scenario/event contexts. Existing eager and deferred consumers must observe the same existing supported semantics.
- [ ] Modify a shared physical include consistently and write it once; deliberately conflicting occurrence-specific modifications fail before replacing originals and leave history/object state consistent with W1/W2.
- [ ] Cover lexical drive/UNC-style paths, relative path expressions, variable-bearing include text, mixed line endings and non-ASCII comments without introducing Path.resolve().
- [ ] If nested includes are implemented in this work package, explicitly test multi-level origin chains, direct/indirect cycles, repeated non-cyclic references, relative path ownership and failure recovery; otherwise retain and test the explicit unsupported diagnostic.
- [ ] Pass affected Windows Python 3.12/3.14 TMF editing/context tests and all existing relevant dependency parity gates affected by changed source representation. Report exact SHA, commands/counts/skips and CI links; no solver or private-model validation.

## Exclusions

- No deferred execution, graph/compiler/cache or SMB performance work; maintain compatibility with those existing consumers.
- No writer staging/encoding redesign (W1) or broad undo/project persistence redesign (W2).
- No automatic model flattening, include deduplication, path rewriting or silent creation of missing targets.
- No guessed or unbounded TUFLOW grammar expansion; nested include support is a later explicit milestone following fidelity and authoritative semantic confirmation.
- No publication, merge, solver launch or private dataset access.

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Implement W6 in phantom-branch/PyTuflow on its assigned branch and existing draft PR. The starting PR is deliberately scope-only. Its base is the linked W2 branch, which inherits W1's save contract. Read the exact branch/PR/SHA linkage recorded by the coordinator and retain it. Implement the authorised scope without repeatedly requesting permission.

Fetch and inspect current refs, applicable repository guidance, this PR's plan/comment and the latest W1/W2 contracts. Work only on the assigned W6 branch; preserve concurrent changes and integrate parent commits without rewriting shared history. Do not commit to a parent/sibling branch or master, replace the PR, merge or release. Independent include regression design can proceed while parent fixes finish; record any actual integration dependency clearly.

The original representation loses source fidelity. In pytuflow/_tmf/cf/cf_build_state.py, _append_input() consumes a Read File directive and flattens the target's inputs into the caller. _get_trd_inputs() later groups these inputs by TRD path and emits only one directive per path. Actual-method component execution of two includes of common.trd separated by another command reconstructed a single Read File plus that intervening command; both included input sets were grouped together. Empty or missing targets contribute no inputs from which the original directive could be reconstructed. This code was unchanged from canonical upstream cf908cc922ca8448ed6002834877b0b377329eae through fork e162c04330d24c37bee3ade94479cc4602651060. Component reproduction is not full-package acceptance.

Retain each source include occurrence explicitly. Store original command text/path expression, comment, source line, owner, scope and include-chain identity. Preserve the existing useful flattened-input view and ordered public behaviour so downstream consumers need not inspect new internals. Distinguish a shared physical file from its multiple ordered invocations. Repeated occurrences must not be collapsed, moved or replaced by concatenating their target inputs.

Keep empty/comment-only/missing directives when saving. Expose an actionable missing-target diagnostic with source context; do not silently remove the directive or fabricate the missing file. Preserve variable-bearing path expressions and each occurrence's scenario/event context. Define editing of shared targets carefully: consistent edits should produce one physical write, while incompatible occurrence-specific content must fail before replacing destinations. Do not silently choose the first occurrence or duplicate the target file without a requested operation.

Use W1's staging/encoding/recovery mechanism and W2's owner/history guarantees. Your primary ownership is include representation and reconstruction, not a second writer, undo framework or project generator. Candidate files are pytuflow/_tmf/cf/cf_build_state.py, pytuflow/_tmf/inp/trd.py, pytuflow/_tmf/inp/inputs.py and narrowly needed parser/source metadata. Preserve lexical Windows paths using Path.absolute() where necessary; never add resolve()/realpath canonicalisation.

Deliver reliable fidelity for currently supported inputs first. Nested TRD currently has an explicit unsupported error. Treat nesting as a later milestone after fidelity is accepted and authoritative TUFLOW documentation or verified fixtures establish the intended semantics. Only then implement a bounded include stack with separate cycle/ownership tests. Until those prerequisites are met, retain the explicit unsupported diagnostic and document the later milestone. Do not guess grammar semantics or claim nested support is complete.

Build real temporary fixtures and installed-package regressions in tests/tmf/test_control_file.py, tests/tmf/test_input.py and tests/tmf/test_scope_writer.py, or a dedicated include-roundtrip module. Cover repeated includes separated by settings/variables; per-occurrence scopes and comments; empty/comment-only/missing targets; changes before/inside/after an include; consistent and conflicting shared-target edits; variable-bearing and lexical network paths; and save failures. Reopen saved files and compare both ordered source directives and representative resolved settings. If supporting nesting, also test direct/indirect cycles, repeated non-cyclic references, source chains and relative owner paths. Update docs/examples/working_with_read_files.rst to describe the actual retained/changed public behaviour.

Run affected tests on Windows Python 3.12 and 3.14 and the existing relevant context/dependency parity gates because source representation can affect existing consumers. Do not change their contracts or weaken comparisons. Report skips, missing fixtures and pre-existing baseline failures honestly; isolated component methods are not substitutes for integration acceptance. No TUFLOW solver, private model access, SMB benchmarks, deferred/graph/cache optimisation, publication or merge.

Commit and push only to this branch, update the PR with actual source SHA and test/CI evidence, and explain include identity, shared-target editing semantics, retained limitations and parent integration status. Complete the bounded implementation before requesting final review; leave the PR draft when acceptance remains incomplete.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
