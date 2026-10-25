"""Contracts for inherited rainfall, GIS inventory and pandas boundary regressions."""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pytuflow._tmf.cf.tcf import TCF
from pytuflow._tmf.db.bc_dbase import BCDatabase
from pytuflow._tmf.db.rf import RainfallDatabase
from pytuflow._tmf.file_reference import make_file_reference
from pytuflow._tmf.gis import network_attribute_file_sources
from pytuflow._tmf.parsers.command import Command
from pytuflow._tmf.settings import TCFConfig


def test_rainfall_csv_index_is_database(tmp_path: Path) -> None:
    tcf = tmp_path / "model.tcf"
    index = tmp_path / "rainfall_index.csv"
    index.write_text("0,grids/step_000.flt\n1,grids/step_001.flt\n", encoding="utf-8")
    tcf.write_text("Read Grid RF == rainfall_index.csv\n", encoding="utf-8")
    database = TCF(tcf).rainfall_dbase()
    assert isinstance(database, RainfallDatabase)
    assert database.fpath == index
    assert database.df.shape == (2, 1)


def test_netcdf_rainfall_is_direct_grid_not_database(tmp_path: Path) -> None:
    config = TCFConfig(tmp_path / "model.tcf")
    ref = make_file_reference(next(Command("Read Grid RF == rain.nc", config).parts()))
    assert ref.database_kind == "rainfall_netcdf"
    assert not ref.requires_database_scan
    assert ref.requires_raster_metadata_scan
    assert ref.path_pattern == tmp_path / "rain.nc"


@pytest.mark.parametrize(
    ("kind", "value", "ignore", "expected"),
    [
        ("Q", "curve_id", "", ()),
        ("P", "pit_curve_id", "", ()),
        ("PO", "operational_rule", "", ()),
        ("QO", "pump_rule | operational.csv", "", ("operational.csv",)),
        ("M", "flow.csv | area.csv", "", ("flow.csv", "area.csv")),
        ("M", "matrix.csv", "", ("matrix.csv",)),
        ("Q", "q_flow.csv", "", ()),
        ("M", "flow.csv", "Y", ()),
        ("M", "flow.csv", "t", ()),
        ("QO", "pump_rule | tables/operational.csv", "", ("tables/operational.csv",)),
    ],
)
def test_network_file_roles(
    kind: str, value: str, ignore: str, expected: tuple[str, ...],
) -> None:
    attrs = ["id", kind, ignore, "", "", "", "", "", "", "", value]
    assert network_attribute_file_sources(attrs) == expected


def test_qo_without_file_is_rejected() -> None:
    attrs = ["id", "QO", "", "", "", "", "", "", "", "", "pump_rule"]
    with pytest.raises(ValueError, match="Invalid QO"):
        network_attribute_file_sources(attrs)


def test_bc_database_value_avoids_pandas_inplace_deprecation() -> None:
    path = Path(__file__).parent / "test_datasets/models/shp/bc_dbase/bc_dbase_EG00_001.csv"
    database = BCDatabase(path)
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=r"The inplace keyword.*")
        first = database.value("fc01")
        second = database.value("fc01")
    assert first.index.name == "inflow_time_hr"
    assert second.index.equals(first.index)
    assert first.columns.tolist() == ["inflow_FC01"]
    assert first.equals(second)


def test_native_absolute_path_on_windows_and_linux(tmp_path: Path) -> None:
    path = tmp_path.absolute() / "model.tcf"
    path.write_text("Hardware == GPU\n", encoding="utf-8")
    model = TCF(path)
    assert model.fpath == path
    assert model.find_input("Hardware")[0].rhs == "GPU"
