# [W4] Bound raster result caches and recover NetCDF readers after errors

## Initial status

Draft scaffolding only: this PR currently adds a scoped work plan. Runtime changes and acceptance tests have not been implemented on this branch. Earlier review reproductions were isolated component checks, not full Windows/GIS integration validation.

## Source checkpoints

- Original upstream review: [TUFLOW-Support/PyTuflow `cf908cc922ca8448ed6002834877b0b377329eae`](https://github.com/TUFLOW-Support/PyTuflow/commit/cf908cc922ca8448ed6002834877b0b377329eae).
- Fork source used to create this work package: [`e162c04330d24c37bee3ade94479cc4602651060`](https://github.com/phantom-branch/PyTuflow/commit/e162c04330d24c37bee3ade94479cc4602651060).
- Recheck current source, review comments and applicable repository guidance before implementing.

## Branch and dependencies

- Work branch: `fix/raster-cache-reader-recovery`.
- PR base: `fix/results-time-correctness`.
- Starting state: **Implementation follows W3**.
- Required parent: **W3**, [`fix/results-time-correctness`](https://github.com/phantom-branch/PyTuflow/tree/fix/results-time-correctness). The parent is initially a planning scaffold too. Reproduction tests and source investigation can start now; changes relying on the parent's contract must follow its implemented and validated checkpoint. Integrate that checkpoint before claiming dependent acceptance. Retarget to master only after the parent merges and the remaining diff is checked.
- Common regression/integration coordination: **W5**, `test/original-library-regression-ci`. Existing acceptance workflows must remain intact.

## Purpose

Documentation-only implementation scaffold. Replace all-timestep allocation during one-surface extraction with bounded storage, repair selector bookkeeping and ensure failed reads do not poison subsequent NetCDF operations. No implementation or full integration validation has been completed by this scaffold.

## Scope

- Base: W3 results-time correctness branch, not master while W3 is unmerged. Retarget to master only after W3 is merged and ancestry/diff are verified. W5 supplies common gates without a branch dependency.
- Bound ordinary Grid/NCGrid surface caching by retained slices or bytes instead of allocating the entire temporal cube for one requested surface.
- Preserve explicit load_into_memory behaviour, public numerical results, selector order, repeated indices and supported scalar/slice/array semantics.
- Fix cache bookkeeping that currently records time_index rather than the individual ti, including ndarray selector crashes.
- Repair NCGrid._open exception cleanup so the object cannot retain and reuse a closed Dataset; preserve nested-reader and explicit-owner behaviour.

## Acceptance criteria

- [ ] A single-surface read does not allocate storage proportional to all timesteps. Demonstrate a bounded cache allocation contract with small synthetic fixtures; do not allocate multi-gigabyte test arrays.
- [ ] Repeated reads hit the cache, eviction stays within the documented budget, and selected/repeated/reordered timesteps produce the same values and ordering as direct reads.
- [ ] Explicit load_into_memory remains functional and its memory behaviour is documented separately from ordinary lazy surface reads.
- [ ] An extraction error closes only handles owned by the context, clears stale state, and permits a successful subsequent read; nested and explicitly opened-reader cases are covered.
- [ ] Affected result tests pass on Windows Python 3.12 and 3.14, with numerical parity against the corrected W3 baseline and optional QGIS integration reported separately.

## Exclusions

- Deferred input caching, persistent/cross-invocation result caches, an unrelated whole-reader rewrite or mandatory public API break.
- Private SMB benchmarks, solver runs, changing Windows lexical path identity or using Path.resolve() for normalisation.
- Reworking time semantics owned by W3, numerical FV routines owned by W8, merge, release or production dependency changes.

## Implementation handoff

The PR Conversation contains a copyable agent prompt with the concrete PR links and branch setup commands. The source-specific instructions are retained here as well:

Implement W4 in phantom-branch/PyTuflow on this draft PR's existing branch. This PR is currently a documentation-only scaffold; neither its code changes nor full integration validation exist yet. Complete the bounded implementation and meaningful tests autonomously, update the PR and handoff as work proceeds, and request review only when implementation and relevant available acceptance gates are complete.

Branch relationships: this PR must branch from and target W3's results-time branch while W3 is open. Do not independently base W4 on master or copy W3's changes into a second implementation. Inspect the latest W3 head and refresh the parent relationship without rewriting another contributor's history. If W3 has merged, verify ancestry and the remaining diff before retargeting W4 to master. W5 provides common CI gates but is not a branch dependency; W8 is independent. Preserve unrelated work and record exact start/parent/final SHAs. The inherited result defects were reviewed at upstream cf908cc922ca8448ed6002834877b0b377329eae and fork e162c04330d24c37bee3ade94479cc4602651060; re-read the latest W3 implementation before editing shared files.

Primary source files are pytuflow/_outputs/grid.py and pytuflow/_outputs/nc_grid.py. Grid._surface currently initialises a full float64 cache of shape (all_timesteps, rows, columns), even for one requested 2D surface. At 500 timesteps and 2000 by 2000 cells that design implies 16 GB per variable, although a single surface is 32 MB. This is a calculation from allocation shape, not a measured production benchmark. Replace that behaviour with bounded per-slice storage or another comparably bounded implementation. Choose the smallest design that preserves public results and provides an explicit documented memory bound; do not mandate a broad new API or redesign unrelated mesh/result providers. Retain the existing explicit load_into_memory operation and clearly distinguish its intentional memory use.

Fix selector and cache correctness while touching this code. The loop currently records .add(time_index) instead of .add(ti), causing ndarray selectors to fail as unhashable. Slice expansion currently uses a set and truthiness defaults, which need review for ordering, zero bounds, reverse/stepped selections and repeated indices. Preserve existing supported return shapes and request order. Handle supported scalar, slice and array selections consistently, avoiding implicit copies of the entire temporal cube. Check flux, export and reduction callers; change their internals only as necessary to preserve bounded ordinary operation and numerical parity.

NCGrid._open currently clears self._nc after its Dataset context rather than in finally. An exception closes the Dataset but leaves its reference cached; the next operation receives a closed handle. Repair state and resource ownership so cleanup is exception-safe and idempotent. A nested operation must not close a reader owned by an outer context or a caller using open_reader. Do not silently suppress the original extraction error.

Add focused tests using small arrays and temporary NetCDF files. Demonstrate cache storage/allocated shapes stay bounded as the number of available timesteps grows, rather than constructing huge arrays or using fragile wall-clock thresholds. Cover cache hits and eviction, numerical equality against direct reads, cold/warm requests, static and temporal data, selector ordering/duplicates and explicit load_into_memory. Inject a read failure and then successfully retry on the same reader; cover nested contexts, explicit-reader ownership and repeated close calls. Tests must exercise the imported implementation and observable I/O/memory behaviour, not copy its code.

Run the affected cases from tests/test_map_output.py and tests/test_map_output_pymesh.py, using existing tests/nc_grid public fixtures and small generated fixtures as appropriate. Compare numerical outputs against the corrected W3 baseline, not the earlier incorrect time implementation. Windows Python 3.12 and 3.14 are the common acceptance platforms. Apply W5's common gates when available and report QGIS integration separately; missing optional providers are not evidence of passing integration.

Update the PR with the chosen cache bound, compatibility behaviour, test commands/counts, measured component allocation evidence, exact source revision and any remaining limitations. Keep it draft until acceptance is complete. Preserve lexical Windows/UNC paths and avoid Path.resolve(). Do not touch deferred input work, private SMB data or W8, launch solvers, merge, publish, or repin production dependencies.

## Shared implementation rules

- Implement the original-library work in this PR on its assigned branch. Read current AGENTS.md guidance and the latest PR body/comments first; inspect the latest parent branch before coding.
- Preserve existing public APIs and established model/result semantics unless this scope explicitly identifies a defect. Use modern built-in Python annotations while keeping the declared interpreter support truthful; retain Python 3.12 compatibility needed by QGIS and validate standalone Python 3.14.
- Keep Windows drive-letter, UNC and network paths lexical; use Path.absolute() when an absolute path is needed, not Path.resolve(). Preserve supported GIS/mesh backends and source provenance.
- Use small public or generated fixtures. No TUFLOW solver launches, proprietary SMB models, private data uploads, package releases or merges are part of these work packages.
- Do not expand the deferred/batch/graph optimisation work, alter PRs #4/#14/#15, or weaken their acceptance checks. Coordinate shared files with the linked work-package owner.
- Record baseline failures separately from regressions. Do not make checks green by dropping fixtures, broad skipping, blanket warning suppression or silently changing expected engineering results.
- Complete implementation and relevant validation before requesting final review. Keep this PR draft while work is incomplete; update the body with code checkpoints, commands, results and precise remaining limitations.
- Routine implementation, fixes, tests and pushes to this development branch are authorised. Continue without another confirmation for those steps. Report an actual access or capability blocker with evidence.
