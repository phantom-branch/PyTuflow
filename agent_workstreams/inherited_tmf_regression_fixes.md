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