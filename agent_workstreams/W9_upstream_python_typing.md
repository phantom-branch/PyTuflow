# W9 — Upstream parity and Python 3.10 typing baseline

## Approved policy — 25 October 2026

- Original implementation reference is **TUFLOW-Support/PyTuflow `master` at `cf908cc922ca8448ed6002834877b0b377329eae`**, not the fork's changed master.
- **Python 3.10 is the typing analysis baseline and syntax/style floor, not a new supported runtime or a runtime CI target.** Modern built-in generics (`list[T]`, `dict[K, V]`) and PEP 604 unions (`A | B`) are permitted. Do not introduce Python 3.12 PEP 695 type parameter/type-alias statements or 3.14-specific typing constructs.
- **Python 3.12 remains the supported runtime minimum and QGIS deployment baseline.** No repository Pyright configuration sets a Python target; the collector explicitly selects 3.10 by default. Preserve the fork's already tested `>=3.12,<3.15` runtime metadata and pre-existing tests for 3.12/3.13/3.14. Do not add Python 3.10/3.11 CI, interpreters, installation tests, or runtime support claims.
- No Python 3.9 restoration. Original upstream metadata advertised `>=3.9`, but source-evaluated union aliases and mandatory `pyvista>=0.48.2` are incompatible with a normal Python 3.9 install. Retain the historical audit evidence without adding new checks for this version.
- We do **not** maintain the original PyTUFLOW library. Contribute only small, demonstrable correctness improvements and public typing that directly represents behaviour already supported upstream. Preserve imports, exported symbols, signatures, defaults, QGIS compatibility, solver/numerical behaviour, and runtime dependencies. Do not undertake package-wide typing cleanup solely to increase scores.

## Completed, source-bounded audit

[Local-agent audit, PR #29 comment 6395043014](https://github.com/phantom-branch/PyTuflow/pull/29#issuecomment-6395043014) was carried out on independent clones:

- Original upstream: `cf908cc922ca8448ed6002834877b0b377329eae`.
- Fork candidate: `b4d817d10635379ffb74eff05e9516b10e70e8f6`.
- Pyright 1.1.411. Historical one-off static six-version comparison was completed; **do not add these old-version checks to continuing CI**.
- At 3.12: upstream 4,966 default-profile errors; fork 5,046, of which **4,937 match upstream** using repository-relative path/rule/message matching. These are static reports, not 5,046 proved defects.
- Strict 3.12 profile: upstream 27,152 reports; fork 28,447. Many report unknown/missing types; some are environmental QGIS/optional-backend issues or contract mismatches needing inspection.
- Correctly source-bound fork `--verifytypes pytuflow --ignoreexternal` completeness: **27.09%** at 3.12 (217 known / 70 ambiguous / 514 unknown public symbols). This is *not* an installed-wheel completeness score or a mandate to annotate all internal code.
- At QGIS 4.2.3 / Python 3.12.15 with real MDAL, 13 package/API tests passed. The audit did not run QGIS 3 LTR.
- All 17 common public classes inspected had matching constructor parameter/default/module signatures in the bounded comparison.
- The local agent fixed collector validation and source identity issues; **12 diagnostic tests passed locally**, but corrected `ci/typing_baseline.py` and `tests/ci/test_typing_baseline.py` remained **unstaged and unpushed** in a separate local checkout when the audit was posted.

## PR #29 disposition

This PR only owns a diagnostic collector, regression tests and this workstream document. Keep it separate from any production code changes.

1. Bring the **already validated local collector corrections** onto PR #29's branch safely, without resetting or overwriting newer remote work. Changes must fail closed for invalid JSON, verify the selected package identity for `--verifytypes`, and suppress host executable paths in aggregate summaries. Never publish raw paths or diagnostic JSON containing private information.
2. Preserve the updated supported-version policy: **default Pyright target 3.10 only**. Optional existing 3.12/3.13/3.14 targets can remain in the diagnostic CLI; do not restore 3.9 or add older-interpreter runtime CI. One-off historical evidence remains valid.
3. Verify the corrected collector with local tests and one source-bound 3.10 `--verifytypes` run. Raw evidence stays local; publish only aggregates and exact git SHAs.
4. Do not raise the library-wide strictness, fail CI for inherited diagnostic debt, change `pyproject.toml`, modify production code, add blanket `.pyi`, or weaken diagnostic checks to conceal errors.
5. Obtain review and existing required CI before marking this diagnostic PR ready. Do not merge it automatically.

## Later work (independent, small PRs only where justified)

- Correct **proven wrong** public typing signatures, not arbitrary Pyright counts. Start with one maintained public API component where input/output contracts can be confirmed from original upstream and existing tests. Inline typing is preferred when implementation is already stable.
- A `.pyi` file is only justified where annotating stable legacy interfaces inline is difficult. A stub must faithfully cover the full supported public surface of its selected module so it does not mask real attributes/methods.
- Check parameter names/kinds/defaults, class/import identity, existing public exports and dynamic behaviour against original upstream; run current W5, installed-wheel consumer and relevant real QGIS 3.12 checks. Only changes with demonstrable parity and maintained, concrete value should be proposed upstream.
- Any future type-completeness improvement should have a measured Python 3.10 typing baseline and must not require the original maintainer to adopt an entirely new strict-typing regime.

## Diagnostic command

Use a verified, updated PR #29 checkout and an existing Python launcher/Pyright installation. All reports belong outside the source checkout. There is no default multi-interpreter matrix.

```powershell
py -3.14 "<fork>\ci\typing_baseline.py" --source-root "<fork>" --output-dir "<private-fresh-dir>" --targets 3.10 --verifytypes
```

The Python 3.14 interpreter here runs the **collector script**, while Pyright analyses the package as Python 3.10. This command does not prove Python 3.12 wheel/runtime compatibility; retain the separate established QGIS/installed-wheel tests.

## Integrated collector acceptance ? 25 October 2026

- Reconciled the preserved local collector fixes with the updated PR branch. Python 3.10 is now the explicit default static target; runtime metadata and runtime CI remain unchanged.
- Invalid/incomplete JSON summaries and invalid completeness scores fail collection. Source identity and nonzero exported-symbol counts are checked for `--verifytypes`; aggregate tool names omit executable directories.
- Local quick workflow selection: **160 passed, 10 subtests passed**, including **24 collector tests**. This is local Python 3.14 evidence, not the hosted interpreter matrix.
- Pyright 1.1.411, Python 3.10 target: **4,965 source errors / 29 warnings**, 461 files; source identity verified, **217 known / 70 ambiguous / 514 unknown** exported symbols, **27.09%** completeness. Collection succeeded; diagnostics remain and are not a clean typing pass.
- Raw reports remain outside the repository. Existing hosted regression/wheel checks must pass on the pushed commit before merge.
