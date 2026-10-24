# [W7] Harden package compatibility, imports and public API

## Current implementation status (24 October 2026)

Milestone A and portions of B/D are implemented on this existing branch. The first focused Windows Python 3.12/3.13/3.14 package-API run passed in all three jobs; its tested checkpoint preceded the later import-path changes. W5 full regression/wheel and the latest focused jobs remain the acceptance requirements. This PR stays draft until the outstanding B/C import/typing scope and exact-head checks have been completed.

### Implemented

- Corrected library-owned stdout INFO/DEBUG logging without changing application-owned handlers, added idempotent rotating file logging (51,200 bytes, two backups), and unified legacy TMF/public logging entry points with resolvable Literal level annotations.
- Added isolated subprocess regressions for level changes, duplicate prevention, app-owned handlers, file rotation, invalid paths, public annotations and legacy/public import compatibility.
- Set metadata to Python >=3.12,<3.15 without modifying production dependency pins; this preserves Python 3.12 QGIS and 3.14 standalone support. Python 3.13 has focused test coverage.
- Removed redundant global sys.path additions from package and legacy result-module initialisation, retaining relative imports; pending final-head regression evidence.
- Fixed README dependency/backend claims and replaced retired TMF/FM test paths. Added a dedicated W7 Windows 3.12/3.13/3.14 CI workflow.
- Merged validated W5 into this branch as merge commit `04d293ca132296cdf1f1f18dd0c92c82b77b25c9`, then retargeted PR #22 to master. The resulting W7 diff excludes W5-owned infrastructure.

### Evidence and retained limitations

- [First focused W7 run — all three jobs passed](https://github.com/phantom-branch/PyTuflow/actions/runs/40085496170).
- [Merged W5 parent and its final successful CI](https://github.com/phantom-branch/PyTuflow/actions/runs/40084325928).
- Import/lazy backend boundaries, explicit public exports/typing marker, dependency support matrix, real QGIS validation after W7 changes and final source-head W5 equivalence remain pending. Current-dependency pandas warning failures are recorded as inherited rather than suppressed. Do not mark this PR ready or merge until retained acceptance is met.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `refactor/package-api-quality`.
- PR base: `master` (post-merge).
- Current state: **W7 implementation follows merged W5; draft until final acceptance.**
- Required parent **W5 / #19** merged to master at `a6ee90bd0886f7b544adbe8865c4cc73e977a6b2`. W7 has integrated its final code, and PR #22 now targets `master`.
- Common regression/integration coordination: **W5**, `test/original-library-regression-ci`. Existing acceptance workflows must remain intact.

## Purpose

Documentation-only draft scaffold for staged package/API improvements, based on W5 so it can use the broader regression and installed-wheel checks. Preserve public entry points and the capabilities supplied by the default installation. Address concrete metadata/logging defects first, then import boundaries, supported typing and accurate documentation.

## Scope

- Milestone A — Define and verify actual Python/dependency support. pyproject currently advertises Python >=3.9 while imported modules evaluate PEP 604 unions without postponed annotations. Decide the supported minimum from the code and dependency matrix; retain the relevant Python 3.12 QGIS use case and Python 3.14 standalone use case. Do not impose the ryan-tools Python policy blindly.
- Milestone A — Repair logging: the default handler remains at WARNING after set_logging_level changes the logger; plain FileHandler is given ineffective rotation fields; Union of string values is an invalid Literal contract. Preserve application-owned handlers, make repeated configuration idempotent, and verify INFO/DEBUG emission, duplicate prevention and any promised rotation.
- Milestone B — Classify core, GIS, mesh and export dependency boundaries and implement safe lazy imports where useful. Preserve existing public imports and default-install capabilities. Replace sys.path mutation and wildcard export ambiguity with explicit supported import/export paths, with compatibility aliases where required.
- Milestone B — Design dependency extras honestly. Extras add dependencies and cannot subtract the currently mandatory stack: pytuflow[core] is not a valid mechanism for a lighter install while base requirements remain unchanged. Do not silently remove mandatory dependencies from the default install. Ship compatible optional groups where valid and document any separately reviewed future distribution/migration required for a lightweight core; do not claim installation savings that are not delivered.
- Milestone C — Correct public annotations and explicit exports for a bounded initial surface: core model/context entry points, major result readers, project creation and binary discovery. Add a tested installed-package typing contract and py.typed only when the supported public surface is coherent. Expand checking incrementally; do not require cleaning every internal module before shipping the concrete fixes.
- Milestone D — Correct README installation/backend support, actual test commands and development setup. It currently mislabels netCDF4/shapely as optional, says XMDF/NCMesh require QGIS despite Python drivers, and points to removed test paths. Keep requirements for tests, docs and profiling distinct and reproducible.
- Own README, pyproject metadata/dependencies, runtime imports/exports, logging and public annotations. W5 owns shared CI/configuration/fixture infrastructure. Add focused tests through the agreed W5 structure and coordinate any shared-file changes; do not rewrite existing deferred gates.

## Acceptance criteria

- [ ] Advertised Python and dependency compatibility matches clean installed-wheel checks on the chosen support matrix, including Windows Python 3.12 and 3.14 where applicable. Unsupported Python versions are rejected by metadata rather than failing unpredictably during import.
- [ ] Existing documented public imports and representative results/project/model operations continue to work after installing the default package. No supported capability silently disappears because a dependency was moved.
- [ ] Importing the supported core does not import unused optional mesh/export backends merely through package initialisation, to the extent claimed by the implemented boundaries. Public module/class identity, pickle/import paths where applicable, and compatibility aliases remain stable. Record measured import differences before claiming speed or memory savings.
- [ ] Optional-backend use raises a clear capability/install error when the backend is absent; collection/import must not fail via empty runtime stubs or obscure attribute errors. Tests cover both available and unavailable backend cases.
- [ ] set_logging_level(INFO/DEBUG) makes library-owned console handlers emit those levels, repeated calls do not duplicate handlers/messages, application-owned handlers are respected, and any documented file rotation actually works.
- [ ] Public annotation tests/type-checking examples resolve without NameError and exercise the installed wheel. py.typed is present if typing is advertised. Type-checking scope is explicit and does not hide errors through blanket Any or ignores.
- [ ] README commands point to existing paths and backend/extra documentation matches package metadata and observed behaviour. W5 regression and wheel checks pass without weakening their baseline comparison.
- [ ] Each milestone has a separate reviewable commit or bounded follow-up decision. Report what is implemented versus deferred; the draft remains incomplete until its retained acceptance scope is satisfied.

## Exclusions

- No deferred execution, graph cache, batch runner or private SMB benchmark changes.
- No breaking default-install dependency removal, wholesale public API rewrite, blanket strict typing migration or cosmetic reformat of all 460 source modules.
- No automatic Python 3.14-only requirement: evaluate actual support and preserve the relevant QGIS Python runtime.
- No numerical result algorithm changes, solver execution, merge, release, tag, publication or production consumer repin.

## Source pointers

- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pyproject.toml#L8-L40
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/__init__.py#L1-L24
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/TUFLOW.py#L1-L6
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/_outputs/tabular_output.py#L50-L61
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/_outputs/gpkg_base.py#L30-L59
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/util/_util/logging.py#L44-L84
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/_pytuflow_types.py
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/pytuflow/_outputs/nc_mesh.py#L33-L60
- https://github.com/TUFLOW-Support/PyTuflow/blob/cf908cc922ca8448ed6002834877b0b377329eae/README.md#L21-L117

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Implement this draft W7 package/API PR in staged, reviewable milestones. Start by reading the current PR body/comments/reviews, repository guidance, and exact head/base SHAs. This PR is based on W5, not directly on master. W5 owns shared regression workflows, test configuration and fixtures; coordinate before touching those files. Initial content is documentation-only scaffolding, not an implemented fix.

Historical review references: original upstream cf908cc922ca8448ed6002834877b0b377329eae, reviewed fork e162c04330d24c37bee3ade94479cc4602651060. Fetch current W5/W7 heads and use this PR's actual branch; do not reset newer work or recreate it on a guessed base. Work in an isolated checkout/worktree when other agents are active.

A. Concrete correctness first. Reproduce the Python metadata mismatch and logging issues from unchanged original code. pyproject.toml advertises >=3.9, but _outputs/tabular_output.py:50-51 and _outputs/gpkg_base.py:34 evaluate PEP 604 unions. Establish a truthful supported minimum using actual dependency/interpreter checks; Python 3.12 is needed for the relevant QGIS environment and 3.14 for standalone use. Do not assume every dependency supports an advertised interpreter. In __init__.py:11-16 the handler is WARNING; util/_util/logging.py:82-84 only changes the logger level. Fix the resulting missing INFO/DEBUG output, preserve application handlers, prevent duplicate configuration, and use actual rotating handlers if rotation is intended. Replace Union['DEBUG', ...] with an appropriate Literal contract and make get_type_hints succeed. Keep these fixes as small independently tested commits.

B. Imports and dependencies. Inspect the full public import surface before refactoring __init__.py and TUFLOW.py. Remove global sys.path additions and make supported exports explicit. Use lazy imports only with regression tests preserving public class identity and existing from-pytuflow imports. Classify core/GIS/mesh/export backends and give missing capabilities clear errors. Preserve the default installation's currently supported capabilities. Python extras only add dependencies: do not claim pytuflow[core] removes mandatory dependencies, and do not silently strip the default dependency list. If a genuinely lighter distribution requires a breaking/versioned migration or separate core distribution, document that decision as a separate follow-up and keep the current default compatible. Measure import startup/module loading before making performance claims.

C. Public typing. Prioritise the supported model/context, result-reader, project and binary-discovery APIs. Correct public annotations, explicit exports and a small installed-wheel consumer example checked with the agreed type checker. Introduce py.typed only with a coherent tested public contract. Avoid broad Any, ignore comments or a package-wide mass reformat merely to make the tool green. Match syntax to the supported interpreter range while using built-in collection annotations.

D. Documentation/development setup. Correct README backend claims and removed test paths. The existing test locations are tests/tmf and tests/fm_lib; Python mesh tests are tests/test_map_output_pymesh.py, while tests/test_map_output.py requires QGIS. Split necessary test/build tooling from optional docs/notebook/profiling setup without discarding reproducibility. Verify metadata/resource paths using the actual installed wheel, not source-tree availability.

Use the W5 test harness. Initial Windows checks, after reading its current documented commands:
  py -3.12 -m pip install -e . pytest build
  py -3.12 -m pytest -q <focused-new-package-tests-and-affected-original-groups>
  py -3.14 -m pip install -e . pytest build
  py -3.14 -m pytest -q <same-focused-selection>
  py -3.14 -m build
Then install the wheel into clean environments and run the public import/API/CLI/typing/resource smoke checks from outside the checkout. Select actual test paths after creating meaningful regressions; do not leave placeholder commands in the final handoff. Run QGIS capability checks with the actual QGIS interpreter, not an assumed standalone Python. Preserve all existing deferred acceptance workflows and source pins. Check subprocess tests before execution; no TUFLOW or other proprietary solver may launch.

After each milestone, report exact changes, tests and remaining work. Before completion, update this PR with precise scope, current parent/head SHAs, installed-wheel evidence, compatibility matrix, missing-backend behaviour, measured import results if any and W5 CI URLs. Record any rejected or deferred dependency migration explicitly rather than pretending a lightweight package was delivered. Leave draft status if retained implementation or validation is incomplete. No merge, release, publication, tag, solver launch, private SMB access or production dependency repin.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
