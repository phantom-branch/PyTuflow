# Deferred-resolution Linux parity — follow-up after Windows acceptance

**Deferred work only.** This is a tracking-only draft PR, not an implementation
or acceptance prerequisite for [PyTUFLOW #1](https://github.com/phantom-branch/PyTuflow/pull/1)
(which now contains merged supporting [PR #2](https://github.com/phantom-branch/PyTuflow/pull/2)).

## Start condition

Do not implement, enable Linux CI, or request review until supported-input
parity has been established on Windows (including the 174-run example model),
with the downstream [ryan-tools PR #143](https://github.com/Chain-Frost/ryan-tools/pull/143)
fully consuming typed database/GIS dependencies. Run Windows verification first;
Linux must not delay Windows development or merging.

## Historical Linux findings — not Windows acceptance results

Read-only Ubuntu/Python 3.14 diagnostics were run against an earlier PyTUFLOW
supporting branch and pinned ryan-tools commit `aaa475e30eb5397d7b88adeffb970ff0c5155b6f`.
These are diagnostic leads, **not** performance or completeness benchmarks for
Windows.

- [Actions 39652484033](https://github.com/phantom-branch/PyTuflow/actions/runs/39652484033):
  161 TCFs / 174 runs, 21 TCFs accepted, 2 eager-only and 18 deferred-only
  references. The eager Pandas 3 rainfall-index failure was corrected
  subsequently upstream.
- [Actions 39654838025](https://github.com/phantom-branch/PyTuflow/actions/runs/39654838025):
  22/174 run combinations accepted; 41 eager-only rainfall-index grids and
  two deferred-only curve/identifier references. Those differences included
  **unintegrated downstream deferred database kinds**, not solely Linux
  parser defects.
- On case-sensitive Linux filesystems, an input referencing
  `model/materials.csv` did not match the actual archived
  `model/Materials.csv`. This affected a large fraction of Linux
  preflight results and is **not evidence of 145 missing project files**.
  Any proposed fix must have a bounded and deduplicated lookup strategy,
  preserve original path spelling/provenance, and distinguish actual
  case-sensitive engine behaviour from assumed Windows behaviour.

## Future scope (separate PR)

1. Start from the latest *merged Windows-correct* PyTUFLOW and downstream
   materialiser, not the historical reproduction checkouts.
2. Define the Linux/POSIX support target and TUFLOW case sensitivity
   explicitly. Do not silently normalise arbitrary paths, dereference
   junctions/symlinks, or conflate filename aliases.
3. Add Linux-only focused tests for mixed-case literal paths, duplicate
   aliases, GPKG layers and relevant database/GIS providers.
4. Compare complete eager/deferred inventories, preserving run flags,
   command ownership, GIS layer and row/field provenance. Check **both
   missing and extra** files; incomplete secondary scans fail closed.
5. After Windows is green, run the complete 161-TCF / 174-run example suite
   on Linux and report failures by root cause alongside Windows results.
6. Introduce Linux CI **in this future PR only**. No Linux jobs are
   required in the consolidated Windows-focused PR #1 validation workflows.

## Exit criteria

A future Linux PR can be considered when independent Linux regressions and
complete example-model parity pass without weakening Windows behaviour or
introducing repeated per-run filesystem/GIS operations.

**This tracking PR deliberately contains no Linux code or CI changes.**
