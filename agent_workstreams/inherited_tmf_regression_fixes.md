# Inherited TMF regression fixes

Independent of #17 and #19, based on `master` at `e162c04330d24c37bee3ade94479cc4602651060`.

## Defects and corrections

- **Rainfall**: A control-file regression incorrectly expected `RainfallDatabase` for `Read Grid RF == rainfall.nc`. CSV rainfall indices are databases; direct NetCDF rainfall grids are primary files, as existing deferred-reference contracts already establish. A temporary two-row CSV index now tests actual database loading.
- **GIS**: Two inherited inventory tests expected the `q_flow.csv` file from an ordinary `Q` network channel where Inlet_Type is a rating-curve database ID, not a path. Matrix (`M`) and complete operational (`QO`) expressions remain explicit file dependencies. The tests still check the remaining discovered paths; dedicated contracts test the difference.
- **FV and pandas**: Replace `DataFrame.reset_index(inplace=True)` with an assigned return value in `BCDatabaseRunState.value()`, retaining index and time/value conversion semantics while avoiding pandas 3.1's `Pandas4Warning`. Warning handling has not been weakened.
- **Windows skip**: Keep the Linux-specific original test skip; add a genuinely cross-platform native absolute-path test.

## Validation expectations

W1's existing 581-test selection produced Linux 549 passed / 32 failed and Windows 548 passed / 32 failed / 1 existing skip. The reported failures were one rainfall expectation, two GIS inventories and 29 FV tests. The new Windows 3.12/3.14 workflow includes the entire selection and generated regressions and fails on any actual pytest failure.

The previous local investigation reported a 596-pass selection after applying equivalent corrections, but acceptance for this committed branch must come from its own exact-head CI. The separate broader TMF suite has another material-parser warning outside these 32 failures; do not suppress or misrepresent it.

## Boundaries

No edits to W1 safe model saving, W5 common CI, #23 numerical reductions or deferred/graph/batch functionality. No private models, network benchmark, solver, release, merge or dependency repin.
## Accepted Windows validation

Runtime/test checkpoint: `1010290286dfcf0b1fe4ecbe0eb1f9752cbe4646`.

- [Exact-head Windows run 40084639614](https://github.com/phantom-branch/PyTuflow/actions/runs/40084639614) **passed both matrix jobs**.
- Python 3.12: **595 passed, 1 skipped, 0 failed**, in 47.20 seconds.
- Python 3.14: **595 passed, 1 skipped, 0 failed**, in 44.34 seconds.
- The single skip is the inherited Linux-only absolute-path test. The newly added cross-platform absolute-path test passes on both Windows interpreters.
- Python dependency/import provenance and JUnit are archived with both jobs; pytest warnings were not globally filtered or suppressed.
- The exact selection comprises the 581 tests previously compared in PR #17 and 15 additional regression cases. Compared with the old Windows 548 passed/32 failed/1 skipped baseline, there are no remaining failures in this selection.

An independent Codex review of this exact runtime was requested in PR #27. Other existing deferred/batch/graph checks are tracked separately and do not affect the inherited-error correction.

## W1 integration fixture compatibility

After PR #17 merged, the complete W5 baseline lane exposed a failing FV-project include-placement test. It used `inp.cf.append(include)` on a newly constructed Include command whose missing target already had an automatically loaded placeholder; thus two distinct control owners targeted `outputs.fvc`. W1 correctly rejects ambiguous duplicate destinations. The test now replaces the placeholder via `inp.cf[:] = [include]`, asserts one owner and continues verifying that the new NetCDF output is written to the include, not to the main FVC. This removes an invalid test arrangement without weakening W1's separate duplicate-owner rejection tests. The dedicated Windows workflow now runs this project test explicitly on both supported versions; full original-library regression remains required.
