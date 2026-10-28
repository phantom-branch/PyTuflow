# Local agent — native MVP acceptance (phantom-branch only)

Target draft: https://github.com/phantom-branch/PyTuflow/pull/47
Branch: feat/minimal-deferred-batch-validation
Base: PR #46 experiment/trimmed-fragment-dependencies at 3ab0b0bf6d31e5d37394f5f7ca08b49e2c24a084
Previous fast native benchmark: PR #46 exact-master M480 preflight 3.831 s; trimmed fragments 3.782 s. These exclude the newly added PyTUFLOW physical GIS attribute validation.
Existing consumer reference only: Chain-Frost/ryan-tools PR #161 at 04999e77d497173294f43e137dedbd0bde60d88a.

## Objective

Validate the minimum viable library product, not a future roadmap:
- Standalone pytuflow.batch_parser.validate_batch() with no new TCF method.
- Real path/layer existence, TUFLOW file-case rules, nested/conditional scenario/Event/Set Variable substitutions, BC CSV headers, primary/secondary database sources and GIS attribute-linked 1D/BC sources.
- Exact per-run provenance and fail-closed missing/unsupported/corrupt cases.
- Strong performance with the proven fragment cache and deduplicated physical checks.

No ryan-tools source changes, package repin, Chain-Frost roadmap/issues, PR C port, merger, solver run, release or private data publication.

## Method

1. Freeze actual PR #47 head, dependency versions, Python/OS, reference parser SHA and consumer SHA; use a detached worktree/venv without touching existing agent checkout. Run hosted and local tests:
   py -3.14 -m pytest -q tests/test_batch_parser_mvp.py tests/test_input_validation.py tests/test_trimmed_fragment_dependencies.py tests/test_fragment_dependencies.py tests/test_effective_dependency_manifests.py
   py -3.14 -m ruff check pytuflow/batch_parser.py pytuflow/validation.py pytuflow/validation_gis.py pytuflow/validation_links.py tests/test_batch_parser_mvp.py tests/test_input_validation.py
2. Use EXACT saved original run arguments on local M480/M36/M240; do not generate Cartesian combinations from PR #44. For each TCF, parse once, pass the same model into validate_batch(model, flags) and record result.dependencies, result.validation and result.issues.
3. Before timing, recursively compare result.dependencies.runs against the frozen reference PR #46 and cached/uncached same-source controls, including UUIDs, owner lines, ordinal commands, paths/layers/BC source selectors/activations/errors. Cross-process comparisons use deterministic parse UUIDs ONLY outside timing; real timed runs use ordinary UUIDs.
4. Physical parity: compare every required path and selected GeoPackage layer (explicit/implicit/wildcard/all) with ryan-tools' current full inspection. Check feature-attribute-linked 1d_xs, 1d_nwk M/QO, 1d_pit and GIS BC/SA/RF Name references; verify missing/unused/candidate BC rows and associated curve database files. Record every unsupported MIF/MID/file/link schema, every unknown scan and every difference. A missing required reference is a correctness failure; do not waive it for matching aggregate counts.
5. Exercise actual absent files, GPKG missing layers, wildcard filenames, symlink/hardlink/WAL/journal conditions, case policy cs0/cs1/cs2 on Linux, missing CSV columns, missing BC database Name/Source IDs, malformed 1d links, and no-GIS-IO until explicit physical validation. Failed runs yield no partial success.
6. Run balanced fresh-process ABBA/BAAB, >=4 observations per revision per workload, measuring candidate validate_batch total from model parse through completed validation. Separately measure parser-only fragment collection on the same source and original ryan-tools complete preflight as context. Do not compare this NEW physical-check boundary directly with the OLD 3.782-second fragment-only + different-consumer boundary. Capture per-stage timing, files/GPKGs/CSV headers/GIS attribute connections/linked sources, zero issues and per-run counts.
7. If package lacks an ordinary BC CSV selector or a dependency source kind is unsupported, report unresolved rather than claiming success. Keep all proprietary file names, input hashes, flags, profiles and raw sources LOCAL. Post only sanitised exact-SHA counts/timings/failures and an acceptance verdict.

## Deliverable

Comment on PR #47 with PASS / CORRECTNESS FAIL / PERFORMANCE FAIL / INCONCLUSIVE; exact candidate/base/consumer SHAs, tests/CI, M480/M36/M240 full record and physical parity, issues/fallbacks, timings and limitations, with recommendations for the smallest next code correction. Do not merge, change ryan-tools or touch Chain-Frost yet. After PASS, curate only the necessary MVP into a separate Chain-Frost PR C candidate based on accepted upstream A and support Python 3.11.
