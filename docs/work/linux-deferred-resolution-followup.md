# Deferred-resolution Linux parity: follow-up after Windows acceptance

**Deferred work only.** This draft tracks Linux/POSIX path investigation. It
targets current fork master and deliberately adds no implementation, tests or
workflow changes. It does not gate Windows acceptance or authorize Linux work.

The original tracking branch inherited historical Windows development from
PRs #1/#2. It has now been refreshed from current master, retaining only this
tracking document so obsolete parser and workflow copies cannot be reintroduced.
The future consolidated upstream contribution remains separate.

## Start condition

Do not implement, enable Linux CI or request implementation review until Windows
supported-input parity and downstream typed database/GIS materialisation are
accepted, including the complete 161-TCF / 174-run example sweep. Use the latest
accepted PyTUFLOW and downstream consumer code, not the historical PR branches.
Linux must not delay Windows development or merging.

## Historical Linux findings: not current acceptance evidence

Read-only Ubuntu/Python 3.14 diagnostics used an earlier PyTUFLOW supporting
branch and pinned ryan-tools commit `aaa475e30eb5397d7b88adeffb970ff0c5155b6f`.
These remain diagnostic leads, not current Windows or Linux acceptance, and not
performance/completeness benchmarks.

- [Actions 39652484033](https://github.com/phantom-branch/PyTuflow/actions/runs/39652484033):
  161 TCFs / 174 runs, 21 TCFs accepted, two eager-only and 18 deferred-only
  references. The eager Pandas 3 rainfall-index failure was corrected later.
- [Actions 39654838025](https://github.com/phantom-branch/PyTuflow/actions/runs/39654838025):
  22/174 run combinations accepted; 41 eager-only rainfall-index grids and two
  deferred-only curve/identifier references. These included unintegrated
  downstream deferred database kinds, not solely Linux parser defects.
- Case-sensitive Linux lookup did not match `model/materials.csv` to the
  archived `model/Materials.csv`. This affected many preflight results and is
  **not evidence of 145 missing project files**. Any proposed fix needs bounded,
  deduplicated lookup, original path spelling/provenance, and an explicit
  distinction between actual engine case sensitivity and Windows assumptions.

## Future scope: separate implementation PR

1. Establish the Linux/POSIX support and TUFLOW case-sensitivity contract. Do
   not silently normalize arbitrary paths, dereference symlinks/junctions or
   conflate filename aliases.
2. Add Linux-only focused tests for mixed-case literal paths, duplicate aliases,
   GeoPackage layers and relevant database/GIS providers.
3. Compare complete eager/deferred inventories, preserving run flags, command
   ownership, GIS layer and row/field provenance. Check both missing and extra
   references; incomplete secondary scans must fail closed.
4. After Windows acceptance, run the full 161-TCF / 174-run public example suite
   on Linux and classify root causes alongside current Windows results.
5. Add Linux CI only in that future implementation PR. No Linux jobs are required
   by this tracking document or the consolidated Windows contribution.

## Exit criteria

Independent Linux regressions and complete example-model parity must pass
without weakening Windows behavior or introducing repeated per-run filesystem
or GIS operations. This refresh runs no Linux validation or solver and makes
no claim that the historical Linux defects are reproduced or fixed today.
