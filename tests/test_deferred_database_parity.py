"""Upstream deferred database-kind and secondary-source regression cases."""
from pathlib import Path
from unittest.mock import patch

import pytest

from pytuflow import TCF
from pytuflow._tmf.deferred_database import DeferredDatabaseResolutionError
from pytuflow._tmf.file_reference import make_file_reference
from pytuflow._tmf.parsers.command import Command
from pytuflow._tmf.settings import TCFConfig
from pytuflow._tmf.tfpathlib import TuflowPath


def _cfg(tmp_path: Path) -> TCFConfig:
    return TCFConfig(
        control_file=tmp_path / "model.tcf",
        init_from_tcf=False,
        file_resolution="deferred",
    )


def _bc_csv(path: Path, source: str) -> None:
    path.write_text(
        "Name,Source,Column 1,Column 2,Add Col 1,Mult Col 2,Add Col 2,Column 3,Column 4\n"
        + "FC01," + source + ",time,flow,,,,,\n",
        encoding="utf-8",
    )


def test_hydraulic_and_ad_bc_databases_are_independent(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "BC Database == hydraulic.csv\n"
        "AD BC Database == ad_sources.csv\n",
        encoding="utf-8",
    )
    _bc_csv(tmp_path / "hydraulic.csv", "hydro.csv")
    _bc_csv(tmp_path / "ad_sources.csv", "ad.csv")

    model = TCF(tcf)
    eager = model.context()
    assert eager.bc_dbase().fpath == tmp_path / "hydraulic.csv"
    assert eager.ad_bc_dbase().fpath == tmp_path / "ad_sources.csv"

    with (
        patch.object(Path, "open", side_effect=AssertionError("file opened")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
        patch("sqlite3.connect", side_effect=AssertionError("SQLite")),
    ):
        run = model.context(file_resolution="deferred")
        result = run.deferred_database_sources()

    assert {(x.database_kind, x.database_path.name, x.path_pattern.name)
            for x in result} == {
        ("bc", "hydraulic.csv", "hydro.csv"),
        ("ad_bc", "ad_sources.csv", "ad.csv"),
    }
    assert {x.owning_command.casefold() for x in result} == {
        "bc database", "ad bc database",
    }
    assert all(x.owner_control_file == tcf for x in result)


def test_multiple_hydraulic_databases_fail_closed(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "BC Database == first.csv\nBC Database == second.csv\n",
        encoding="utf-8",
    )
    _bc_csv(tmp_path / "first.csv", "first.dat")
    _bc_csv(tmp_path / "second.csv", "second.dat")
    with pytest.raises(ValueError, match="Multiple active"):
        TCF(tcf).context(file_resolution="deferred").deferred_database_sources()


def test_missing_cached_ad_bc_database_fails_closed(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("AD BC Database == missing.csv\n", encoding="utf-8")
    with pytest.raises(DeferredDatabaseResolutionError, match="has not been loaded"):
        TCF(tcf).context(file_resolution="deferred").deferred_database_sources()


def test_rainfall_index_secondary_paths_without_raster_reads(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("Read Grid RF == rainfall_index.csv\n", encoding="utf-8")
    (tmp_path / "rainfall_index.csv").write_text(
        "0,grids/step_000.tif\n1,grids/step_001.asc\n", encoding="utf-8",
    )
    model = TCF(tcf)

    with (
        patch.object(Path, "open", side_effect=AssertionError("file opened")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
    ):
        run = model.context(file_resolution="deferred")
        sources = run.deferred_database_sources()

    assert {x.path_pattern for x in sources} == {
        tmp_path / "grids" / "step_000.tif",
        tmp_path / "grids" / "step_001.asc",
    }
    assert all(x.database_kind == "rainfall" for x in sources)
    assert all(x.database_path == tmp_path / "rainfall_index.csv" for x in sources)


def test_invalid_rainfall_index_missing_grid_fails_closed(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("Read Grid RF == rainfall_index.csv\n", encoding="utf-8")
    (tmp_path / "rainfall_index.csv").write_text(
        "0,step_000.tif\n1,\n", encoding="utf-8",
    )
    with pytest.raises(DeferredDatabaseResolutionError, match="Empty rainfall"):
        TCF(tcf).context(file_resolution="deferred").deferred_database_sources()


def test_netcdf_rainfall_is_terminal_primary_not_database(tmp_path):
    cfg = _cfg(tmp_path)
    command = Command("Read Grid RF == rain.nc", cfg)
    ref = make_file_reference(next(command.parts()))
    assert ref.database_kind == "rainfall_netcdf"
    assert not ref.requires_database_scan
    assert ref.path_pattern == tmp_path / "rain.nc"

    tcf = tmp_path / "model.tcf"
    tcf.write_text("Read Grid RF == rain.nc\n", encoding="utf-8")
    model = TCF(tcf)
    run = model.context(file_resolution="deferred")
    assert run.deferred_database_sources() == ()
    assert [x.path_pattern for inp in run.find_input() for x in inp.file_references] == [
        tmp_path / "rain.nc",
    ]


def test_table_link_is_a_gis_attribute_scan_not_csv_database(tmp_path):
    command = Command(
        "Read GIS Table Links == gis/1d_xs_001.shp", _cfg(tmp_path),
    )
    ref = make_file_reference(next(command.parts()))
    assert ref.database_kind == "gis_table_links"
    assert ref.requires_table_link_scan
    assert ref.requires_attribute_scan
    assert not ref.requires_database_scan

    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "Read GIS Table Links == gis/1d_xs_001.shp\n", encoding="utf-8",
    )
    run = TCF(tcf).context(file_resolution="deferred")
    inp = run.find_input(lhs="Read GIS Table Links")[0]
    assert inp.file_references[0].requires_table_link_scan


def test_bc_database_paths_include_context_expansion(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "Set Variable ABC == suffix\nAD BC Database == ad.csv\n",
        encoding="utf-8",
    )
    _bc_csv(tmp_path / "ad.csv", "ad_<<ABC>>.csv")
    run = TCF(tcf).context(file_resolution="deferred")
    sources = run.deferred_database_sources()
    assert len(sources) == 1
    assert sources[0].database_kind == "ad_bc"
    assert sources[0].path_pattern == tmp_path / "ad_suffix.csv"


def test_pit_inlet_and_depth_discharge_sources_are_typed(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "Pit Inlet Database == pit.csv\n"
        "Depth Discharge Database == curves.csv\n",
        encoding="utf-8",
    )
    for filename, source in [
        ("pit.csv", "pit_curve.csv"),
        ("curves.csv", "network_curve.csv"),
    ]:
        (tmp_path / filename).write_text(
            "Name,Source,Depth_Col,Flow_Col,Area,Width\n"
            + "aa," + source + ",Depth,Flow,0,0\n",
            encoding="utf-8",
        )

    model = TCF(tcf)
    with (
        patch.object(Path, "open", side_effect=AssertionError("file opened")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
    ):
        refs = model.context(file_resolution="deferred").deferred_database_sources()
    assert {(ref.database_kind, ref.path_pattern.name) for ref in refs} == {
        ("pit_inlet", "pit_curve.csv"),
        ("depth_discharge", "network_curve.csv"),
    }
    assert all(ref.entry_name == "aa" for ref in refs)


@pytest.mark.parametrize("row", ["aa,,Depth,Flow,0,0", "aa,<<UNKNOWN>>,Depth,Flow,0,0"])
def test_invalid_pit_sources_fail_closed(tmp_path, row):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("Pit Inlet Database == pit.csv\n", encoding="utf-8")
    (tmp_path / "pit.csv").write_text(
        "Name,Source,Depth_Col,Flow_Col,Area,Width\n" + row + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DeferredDatabaseResolutionError):
        TCF(tcf).context(file_resolution="deferred").deferred_database_sources()


def test_network_file_roles_do_not_treat_curve_ids_as_paths():
    from pytuflow._tmf.gis import network_attribute_file_sources

    attrs = ["id", "Q", "", "", "", "", "", "", "", "", "aa"]
    assert network_attribute_file_sources(attrs) == ()
    attrs[1] = "P"
    assert network_attribute_file_sources(attrs) == ()
    attrs[1] = "PO"
    assert network_attribute_file_sources(attrs) == ()
    attrs[1] = "QO"
    attrs[10] = "pump_rule | operational.csv"
    assert network_attribute_file_sources(attrs) == ("operational.csv",)
    attrs[1] = "M"
    attrs[10] = "flow.csv | area.csv"
    assert network_attribute_file_sources(attrs) == ("flow.csv", "area.csv")
    attrs[2] = "Y"
    assert network_attribute_file_sources(attrs) == ()
    attrs[2] = "t"
    assert network_attribute_file_sources(attrs) == ()


def test_incomplete_network_qo_expression_rejected():
    from pytuflow._tmf.gis import network_attribute_file_sources

    attrs = ["id", "QO", "", "", "", "", "", "", "", "", "control_only"]
    with pytest.raises(ValueError, match="QO operational"):
        network_attribute_file_sources(attrs)
