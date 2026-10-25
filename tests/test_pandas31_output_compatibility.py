"""Pandas 3.1 compatibility checks for unchanged 2DM and line-output semantics.

Strict warning handling is intentional: pandas deprecations are errors under
the repository's existing pytest policy. No warning filters are added.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from pytuflow._outputs.map_output import MapOutput
from pytuflow._outputs.pymesh.mesh_geom.py2dm import Py2dm


def test_2dm_node_coordinates_for_one_based_indices() -> None:
    nodes = pd.DataFrame(
        {
            "A": ["ND", "ND", "ND"],
            "B": [1, 2, 3],
            "C": [100.0, 105.0, 100.0],
            "D": [200.0, 200.0, 205.0],
            "E": [2.0, 3.0, 4.0],
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        actual = Py2dm.load_nodes(nodes)

    assert actual.dtype == np.dtype("float64")
    np.testing.assert_array_equal(actual, [[100.0, 200.0, 2.0], [105.0, 200.0, 3.0], [100.0, 205.0, 4.0]])
    # The source dataframe is reused elsewhere to load cell connectivity.
    assert list(nodes["B"]) == [1, 2, 3]


def test_2dm_node_coordinates_for_zero_based_indices() -> None:
    nodes = pd.DataFrame(
        {
            "A": ["ND", "ND"],
            "B": [0, 1],
            "C": [10.0, 20.0],
            "D": [30.0, 40.0],
            "E": [50.0, 60.0],
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        actual = Py2dm.load_nodes(nodes)
    np.testing.assert_array_equal(actual, [[10.0, 30.0, 50.0], [20.0, 40.0, 60.0]])


def test_2dm_reader_file_round_trip(tmp_path) -> None:
    path = tmp_path / "small.2dm"
    path.write_text(
        "MESH2D\n"
        "E3T 1 1 2 3 1\n"
        "ND 1 100 200 2\n"
        "ND 2 105 200 3\n"
        "ND 3 100 205 4\n",
        encoding="utf-8",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parsed = Py2dm.read_2dm_file(path)
        actual = Py2dm.load_nodes(parsed)
    np.testing.assert_array_equal(actual, [[100.0, 200.0, 2.0], [105.0, 200.0, 3.0], [100.0, 205.0, 4.0]])


def test_line_output_reset_index_preserves_offset_and_values() -> None:
    samples = pd.DataFrame({"water level": [1.5, 1.75]}, index=pd.Index([0.0, 4.0], name="offset"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        actual = MapOutput._merge_line_dataframe(pd.DataFrame(), samples, "Section A", reset_index=True)

    assert isinstance(actual.columns, pd.MultiIndex)
    assert list(actual.columns.to_flat_index()) == [
        ("Section A", "offset"),
        ("Section A", "water level"),
    ]
    np.testing.assert_array_equal(actual.to_numpy(dtype=float), [[0.0, 1.5], [4.0, 1.75]])
    assert isinstance(actual.index, pd.RangeIndex)


def test_line_output_merges_multiple_sections() -> None:
    first = pd.DataFrame({"a": [1.0, 2.0]}, index=pd.Index([0.0, 10.0], name="offset"))
    second = pd.DataFrame({"b": [3.0, 4.0]}, index=pd.Index([0.0, 10.0], name="offset"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        a = MapOutput._merge_line_dataframe(pd.DataFrame(), first, "First", reset_index=True)
        b = MapOutput._merge_line_dataframe(a, second, "Second", reset_index=True)
    assert list(b.columns.to_flat_index()) == [
        ("First", "offset"), ("First", "a"), ("Second", "offset"), ("Second", "b")
    ]
    np.testing.assert_array_equal(b.iloc[:, [1, 3]].to_numpy(dtype=float), [[1.0, 3.0], [2.0, 4.0]])
