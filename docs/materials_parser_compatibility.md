# Free-form material parsing and pandas 3.1

Follow-up to [the materials-parser contract on PR #30](https://github.com/phantom-branch/PyTuflow/pull/30#issuecomment-6394835240), independent of that PR's result-reader changes.

Current master `520a292806be97b431c511d157a9c0b5422b4bda` includes #27 and #22. On Windows CPython 3.12.14, the unchanged `tests/tmf/test_database.py::test_mat_tmf_final_boss` passed with pandas 3.0.3 and failed with pandas 3.1.0. The matched environments differed only in pandas. They used `ci/requirements-regression.txt`, with GeoPandas 1.2.0 in both environments: the pinned GeoPandas 1.1.3 (and 1.1.4) reads a deprecated pandas option during import and cannot reach this test under pandas 3.1 with warnings treated as errors. The unmodified pinned environment separately passed the original test. No warning filter was changed.

The fixture is a supported free-form TMF file containing comments and records of different widths. `CsvDatabaseDriver` correctly falls back from `read_csv` to `text_to_db_parser`. Pandas 3.1 warns about the fallback's implicit padding of ragged sequences; the driver's exception wrapper exposes that warning as `ParserError`. Explicit NaN padding before constructing the DataFrame preserves the previous output and removes the deprecated operation. The fixture is unchanged (SHA256 `436487c2384a5a19afb259849fc99c150ea06ac21d462d04df9157096e15583b`).

The complete database suite plus new parser regressions pass 32 tests in each local Windows environment: Python 3.12.14 and 3.14.6, each with pandas 3.0.3 and 3.1.0. Checks preserve 22 rows and seven columns, ordered Material IDs, all field labels, `value(6) == 0.03`, missing optional fields, and the exact two-row depth/Manning values for material 22. Synthetic parser checks cover short records before and after the longest record. No solver or private files are involved.

Reproduce with the dependency list above, changing only pandas between lanes:

```text
python -m pytest -q tests/tmf/test_database.py tests/tmf/test_materials_parser.py --junitxml=reports/materials.xml
```

`.github/workflows/materials-parser.yml` runs the same four Windows lanes and retains source/dependency provenance and JUnit evidence. Hosted status must be checked separately from these local results. The public dependency contract, original W5 pins, fixtures and warning policy remain unchanged.
