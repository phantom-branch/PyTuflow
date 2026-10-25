# Legacy ResData stub contract audit

Reference: original TUFLOW-Support/PyTuflow master at
`cf908cc922ca8448ed6002834877b0b377329eae`. The 41 method signatures,
parameter kinds/names and defaults agree with that source. This PR changes
no inherited implementation. The fork's pre-existing removal of the legacy
`sys.path` mutation and `sys` export is outside this typing pilot.

## Return declaration inventory

The following inventory covers every method in `TUFLOW.pyi`. Types describe
values returned normally, not a guarantee that every legacy format supports
every method or that calls cannot raise.

| Methods | Original implementation contract |
| --- | --- |
| `__init__`, `__del__`, `close`, `setReferenceTime` | No returned value. Date assignment asserts 2016 format; close clears the reader. |
| `format`, `name`, `units` | Strings; unloaded fallback is `''`. |
| `source` | Filename is forwarded unchanged, including a supplied path object for TPC/INFO; unloaded fallback is `''`. |
| `load` | `(bool, str)` from TPC/INFO/GPKG loaders or unrecognised-extension error. TPC `loadTPC` resets the initial message to `''`. |
| `channels`, `nodes`, `channelConnections`, `channelsUpstream`, `channelsDownstream` | Lists of identifier strings; empty fallback. |
| `channelCount`, `nodeCount`, `channelConnectionCount` | Integer counts; zero fallback. |
| `nodeUpstream`, `nodeDownstream` | Identifier strings; `''` fallback. |
| `channelResultTypes`, `nodeResultTypes`, `poNames`, `poResultTypes`, `rlNames`, `rlResultTypes`, `longProfileResultTypes` | Lists of strings, including GPKG delegated type inventories; empty fallback. |
| `rlPointCount`, `rlLineCount`, `rlRegionCount`, `rlCount` | Integer counts; zero fallback for unloaded/2013. |
| `timesteps` | Float lists from array `.tolist()`, which can retain masked entries as `None`; date lists when requested and supported; unloaded `[]`. |
| `getTimeSeriesData` | `(bool, str, (times, values))`. Values are flat lists or a list of column lists. Numeric/string CSV and NetCDF arrays become Python values; masked entries become `None`. Error payload is `([], [])`. |
| `maximum`, `timeOfMaximum`, `maximumTimestepChange`, `timeOfMaximumTimestepChange` | `(bool, str, float)`; unsupported/error paths use numeric zero. GPKG scalar maxima operations report unsupported errors. |
| `getLongProfileData` | `(bool, str, XY-or-polygons)`. TPC culvert/pipe results are lists of polygons made with `list(zip(x, y))`; INFO/GPKG normal results are XY pairs. XY data can retain NumPy float64 scalars or masked constants because these paths do not call `.tolist()`. Errors returned by the façade have empty XY data. |
| `getAdverseGradients` | Two XY pairs, with empty pairs as fallback. |
| `getPipes` | TPC polygon list; unloaded/INFO/GPKG fallback is exactly `[[()]]`. |
| `getLongProfileTimeOfMaximum` | XY pair, or empty lists. |
| `referenceTime` | TPC datetime or `None`, GPKG datetime/default, unloaded `None`. |

No literal overload is used for profiles: result strings are interpreted with
case-insensitive substring tests and supported result types vary by format.
The conservative union retains those behaviours without promising literal
discrimination that the implementation does not enforce.

## Inherited limitations retained

The INFO backend lacks `reference_time` and a domain-aware `timeSteps` method;
the GPKG `timeSteps` method also lacks the façade's `domain` keyword. Those
calls can raise in the original implementation. Some backend error returns
have inconsistent tuple arity. The declarations do not repair those runtime
limitations, invent successful return values for them, or add `None` merely
because a call raises. Focused tests record the INFO/GPKG limitations.

The runtime module exports `ResData`, `ResData_GPKG`, `os` and `warnings` in
the current fork. The stub preserves them and the root `pytuflow.ResData`
identity. New typing helpers are private and create no runtime imports.

## Focused validation

Synthetic tests exercise string CSVs, flat and nested masked arrays, polygons,
XY values, masked timesteps, unloaded sentinels, path forwarding, INFO/GPKG
paths, and all runtime signatures. The strict external wheel consumer checks
heterogeneous types and rejects unchecked numeric arithmetic. The existing
W7 Windows Python 3.12/3.13/3.14 matrix remains unchanged.
