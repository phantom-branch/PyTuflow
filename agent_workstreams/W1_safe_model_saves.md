# [W1] Make model saves recoverable and preserve text encoding

## Initial status

Draft scaffolding only: this PR currently adds a scoped work plan. Runtime changes and acceptance tests have not been implemented on this branch. Earlier review reproductions were isolated component checks, not full Windows/GIS integration validation.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `fix/safe-model-saves`.
- PR base: `master`.
- Starting state: **Can start now**.
- This is an independent branch from master; it does not depend on the deferred optimisation PRs.
- Dependent work: W2 on `fix/model-editing-undo`.
- Common regression/integration coordination: **W5**, `test/original-library-regression-ci`. Existing acceptance workflows must remain intact.

## Purpose

Scope-only draft; no implementation or acceptance pass is claimed. Repair original control-file/TRD write safety and the valid-large-file writer failure. Base: master. W2 will build on this write contract; W6 will later change include representation.

## Scope

- Own pytuflow/_tmf/cf/cf_build_state.py write planning/serialisation/commit behaviour, the text read policy in pytuflow/_tmf/parsers/non_recursive_basic_parser.py as needed for lossless encoding, and the non-progress guard in pytuflow/_tmf/scope_writer.py.
- Render every affected parent/child/TRD output to staging before replacing existing destinations or committing in-memory path/reference/history changes. Preserve existing inc='auto', explicit suffix, inc='inplace' and inc=None semantics.
- Preserve source encoding/error handling, newline style, BOM policy and undecodable legacy comment bytes; define UTF-8 behaviour for newly created files. A read accepted with surrogateescape must not lose the original during a failed write.
- Use temporary files on the destination filesystem and explicit replacement/recovery handling. Document that multiple filesystem replacements are not a single atomic transaction. Preserve originals on staging failure; define rollback and accurate partial-failure reporting for commit failures.
- Replace ScopeWriter's fixed >10,000 iteration ceiling with bounded detection of actual non-progress. Valid 10,001+ line input must write successfully.
- Keep output ownership, child ordering and dirty/history transitions explicit; change persistent object state only when the corresponding save contract succeeds.
- Use lexical Path.absolute() when an absolute path is required; do not introduce Path.resolve(), realpath calls or network path canonicalisation.
- Regression additions belong in tests/tmf/test_control_file.py and tests/tmf/test_scope_writer.py, with a new dedicated temporary-fixture test module if separation improves clarity. Update relevant write API documentation/examples only for the contract implemented.

## Acceptance criteria

- [ ] Reproduce the legacy read/write mismatch with a real TCF/TRD and the installed package: earlier isolated-method evidence reduced a 30-byte file to zero after UnicodeEncodeError, but that evidence is not integration validation.
- [ ] Test unchanged and edited UTF-8, UTF-8 BOM, CRLF/LF, no-final-newline and undecodable legacy comment bytes using temporary files; preserve bytes where the contract promises no changes.
- [ ] Inject serialisation, encoding, temporary-write, permission and replacement failures before and during parent/child/TRD saves. Assert original bytes, destination inventory, in-memory paths, references and dirty/history states match the documented failure contract.
- [ ] Cover all existing increment modes and a model with more than one dirty child. Prevent duplicate writes to one destination and unintended overwrites introduced by the new staging layer.
- [ ] Verify at least 20,000 valid flat commands and a representative nested-scope file. A deliberately stalled writer must still terminate with an actionable diagnostic.
- [ ] Pass affected tests on Windows Python 3.12 and 3.14, followed by existing relevant TMF editing/context regression selections. Report exact commands, counts, skips, source SHA and CI links; do not represent component tests or Linux execution as Windows acceptance.
- [ ] Confirm no deferred/batch/graph API or behaviour change, no solver invocation, and a clean git diff --check.

## Exclusions

- No deferred execution, compiled graph, cache or benchmark optimisation.
- No include-tree redesign or nested TRD feature; W6 owns include representation and occurrence identity.
- No undo/reset redesign or project feature-persistence fix; W2 owns these.
- No broad project template overwrite-policy redesign unless the coordinator explicitly assigns that scope.
- No publication, merge, solver execution, private model access or native SMB benchmark.

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Implement W1 in phantom-branch/PyTuflow on the existing assigned W1 branch and draft PR. The starting PR is intentionally scope-only: its planning document is not an implementation, and earlier component reproductions are not acceptance results. W1 targets master; use the exact branch, PR URL and initial source SHA recorded in the PR. W2 depends on this contract and W6 later depends on W2. Work autonomously within this scope; do not ask for another implementation confirmation.

First fetch the latest refs, inspect repository guidance, the PR scope/comment and current CI, then check out the assigned branch. Preserve other agents' work. Do not switch to or commit on master or a sibling branch. If the parent changes, integrate its actual current head into your assigned branch without force-pushing or rewriting shared history; keep this PR's documented base.

The review identified two original-source faults. ControlFileBuildState.write() in pytuflow/_tmf/cf/cf_build_state.py opens destinations with mode 'w' before serialisation succeeds, writes children before their parent, and mutates paths/references during the operation. get_commands() in pytuflow/_tmf/parsers/non_recursive_basic_parser.py reads with errors='surrogateescape', whereas writes use strict defaults. An isolated reproduction accepted a legacy byte on read, raised UnicodeEncodeError during the actual write method and left a 30-byte target empty. Separately, ScopeWriter.inputs() in pytuflow/_tmf/scope_writer.py rejects a valid 10,001-command flat file because it mistakes an absolute loop count for non-progress. These areas are unchanged from canonical upstream cf908cc922ca8448ed6002834877b0b377329eae through fork e162c04330d24c37bee3ade94479cc4602651060.

Implement a concrete save contract. Build and validate a complete write plan, render affected parent/child/TRD files to temporary output, then replace destinations with explicit recovery handling. Use staging beside the destination. Do not advertise multiple replacements as globally atomic. Existing originals must survive staging or serialization failure. Define rollback and accurate reporting if replacement fails midway, and leave in-memory filenames, references and dirty/history state consistent with the actual result. Preserve existing increment modes rather than changing naming policy. Avoid repeated writes to the same physical destination.

Preserve the source text's encoding/error policy, newline convention and BOM where applicable; define an explicit policy for new files. Do not silently discard or replace undecodable bytes. Keep this implementation compatible with current flattened include representation: W6 owns its redesign. W2 owns undo/reset mechanics and project secondary-file persistence. Coordinate a small stable internal writer interface rather than duplicating these changes downstream. Preserve lexical Windows drive and UNC paths; use Path.absolute() when needed, never introduce resolve()/realpath canonicalisation.

Replace the writer's fixed loop ceiling with detection of genuinely unchanged input/scope state. It must support normal large files while still bounding a malformed non-progressing stream.

Add meaningful regressions around tests/tmf/test_control_file.py and tests/tmf/test_scope_writer.py, preferably temporary generated fixtures rather than production data. First demonstrate the old fault, then cover UTF-8/BOM, legacy bytes, CRLF/LF, no final newline, all increment modes, multiple dirty children and at least 20,000 flat commands. Inject failures at serialisation, staging and replacement boundaries; verify both disk contents and object state. A failed save must not be reported as success.

Run the affected installed-package tests on Windows Python 3.12 and 3.14 plus the relevant existing TMF editing/context selections. Use hosted CI when local Windows is unavailable. Distinguish an unavailable integration environment, a pre-existing failure, a skipped test and a new regression; do not use isolated AST methods as a substitute for acceptance. Broaden testing only to resolve a remaining risk or satisfy an existing gate. Do not execute TUFLOW, request private data, run SMB benchmarks, change deferred/batch/graph behaviour, publish or merge.

Commit and push the implementation to the assigned branch, update this PR's scope/status with actual validation evidence, and record the writer interface and any remaining limitation for W2/W6. Report commit SHA, exact tests/CI links, failure-recovery contract and review findings. Complete the bounded implementation before requesting final review; keep the PR draft if acceptance remains incomplete.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
