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
    (tmp_path / "ad_global.csv").write_text(
        "Name,Initial Condition,Minimum Dispersion\nTracer,0,0\n",
        encoding="utf-8",
    )
    tcf.write_text(
        tcf.read_text(encoding="utf-8") + "AD Global Database == ad_global.csv\n",
        encoding="utf-8",
    )

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
    tcf.write_text(
        "AD Global Database == global.csv\nAD BC Database == missing.csv\n",
        encoding="utf-8",
    )
    (tmp_path / "global.csv").write_text(
        "Name,Initial Condition,Minimum Dispersion\nTracer,0,0\n",
        encoding="utf-8",
    )
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
    assert all(x.requires_raster_metadata_scan for x in sources)
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
    assert ref.requires_raster_metadata_scan
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
        "Set Variable ABC == suffix\nAD Global Database == global.csv\n"
        "AD BC Database == ad.csv\n",
        encoding="utf-8",
    )
    (tmp_path / "global.csv").write_text(
        "Name,Initial Condition,Minimum Dispersion\nTracer,0,0\n",
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



def test_nested_adcf_materialises_global_layers_and_bc_source_root(tmp_path):
    tcf = tmp_path / "model.tcf"
    adcf = tmp_path / "adcf" / "ad.adcf"
    adcf.parent.mkdir()
    tables = tmp_path / "tables"
    tables.mkdir()
    tcf.write_text("AD Control File == adcf/ad.adcf\n", encoding="utf-8")
    adcf.write_text(
        "AD Global Database == ../tables/constituents.csv\n"
        "AD BC Database == ../adbc/conditions.csv\n",
        encoding="utf-8",
    )
    (tmp_path / "adbc").mkdir()
    _bc_csv(tmp_path / "adbc" / "conditions.csv", "source_series.csv")
    (tables / "constituents.csv").write_text(
        "Name,Initial Condition,Minimum Dispersion\n"
        "Salinity,../gis/2d_ad_ic.gpkg >> 2d_ad_ic_Salinity,../gis/2d_ad_md.shp\n"
        "Heat,12.5,0\n",
        encoding="utf-8",
    )
    model = TCF(tcf)
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
        patch("sqlite3.connect", side_effect=AssertionError("sqlite")),
    ):
        run = model.context(file_resolution="deferred")
        refs = run.deferred_database_sources()
    kinds = {(ref.database_kind, ref.path_pattern.name) for ref in refs}
    assert ("ad_bc", "source_series.csv") in kinds
    assert ("ad_global", "2d_ad_ic.gpkg") in kinds
    assert ("ad_global", "2d_ad_md.shp") in kinds
    bc = next(ref for ref in refs if ref.database_kind == "ad_bc")
    assert bc.path_pattern == adcf.parent / "../tables/source_series.csv"
    global_gpkg = next(ref for ref in refs if ref.path_pattern.name == "2d_ad_ic.gpkg")
    assert global_gpkg.layer_pattern == "2d_ad_ic_Salinity"
    assert global_gpkg.requires_layer_scan
    assert global_gpkg.source_field == "initial condition"
    assert global_gpkg.entry_name == "Salinity"
    assert global_gpkg.owner_control_file == adcf


def test_ad_global_blank_minimum_dispersion_is_invalid(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("AD Global Database == ad_global.csv\n", encoding="utf-8")
    (tmp_path / "ad_global.csv").write_text(
        "Name,Initial Condition,Minimum Dispersion\nTracer,3,\n",
        encoding="utf-8",
    )
    with pytest.raises(DeferredDatabaseResolutionError, match="Minimum Dispersion"):
        TCF(tcf).context(file_resolution="deferred").deferred_database_sources()


def test_ad_global_numeric_only_has_no_secondary_files(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("AD Global Database == ad_global.csv\n", encoding="utf-8")
    (tmp_path / "ad_global.csv").write_text(
        "Name,Initial Condition,Minimum Dispersion\nTracer,,0\n",
        encoding="utf-8",
    )
    assert TCF(tcf).context(file_resolution="deferred").deferred_database_sources() == ()


def test_ad_bc_fails_closed_if_global_database_is_ambiguous(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "AD Global Database == one.csv\n"
        "AD Global Database == two.csv\n"
        "AD BC Database == ad_bc.csv\n",
        encoding="utf-8",
    )
    for name in ("one.csv", "two.csv"):
        (tmp_path / name).write_text(
            "Name,Initial Condition,Minimum Dispersion\nTracer,0,0\n",
            encoding="utf-8",
        )
    _bc_csv(tmp_path / "ad_bc.csv", "source.csv")
    with pytest.raises(ValueError, match="Multiple active ad global|requires one active"):
        TCF(tcf).context(file_resolution="deferred").deferred_database_sources()



def test_cross_section_csv_database_source_files(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("XS Database == xs.csv\n", encoding="utf-8")
    (tmp_path / "xs.csv").write_text(
        "Name,Source,Type,Flags\n"
        "section1,sections/one.csv,XZ,\n"
        "section2,sections/two.csv,CS,\n",
        encoding="utf-8",
    )
    model = TCF(tcf)
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
    ):
        sources = model.context(file_resolution="deferred").deferred_database_sources()
    assert {r.database_kind for r in sources} == {"cross_section"}
    assert {r.path_pattern for r in sources} == {
        tmp_path / "sections" / "one.csv",
        tmp_path / "sections" / "two.csv",
    }


def test_cross_section_without_source_column_fails_closed(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text("XS Database == xs.csv\n", encoding="utf-8")
    (tmp_path / "xs.csv").write_text(
        "Name,Other\nsection1,not-a-file\n", encoding="utf-8",
    )
    with pytest.raises(DeferredDatabaseResolutionError, match="no Source column"):
        TCF(tcf).context(file_resolution="deferred").deferred_database_sources()



def test_multiple_rainfall_indexes_and_netcdf_are_independently_projected(tmp_path):
    """Multiple RF commands represent additive inputs, not ambiguous DB roles."""
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "Read Grid RF == east.csv\n"
        "Read Grid RF == satellite.nc\n"
        "Read Grid RF == west.csv\n",
        encoding="utf-8",
    )
    (tmp_path / "east.csv").write_text("0,grids/east_000.tif\n", encoding="utf-8")
    (tmp_path / "west.csv").write_text("0,grids/west_000.tif\n", encoding="utf-8")
    model = TCF(tcf)
    with (
        patch.object(Path, "open", side_effect=AssertionError("file opened")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
        patch("sqlite3.connect", side_effect=AssertionError("SQLite")),
    ):
        run = model.context(file_resolution="deferred")
        secondary = run.deferred_database_sources()
    assert {(ref.database_path.name, ref.path_pattern.name) for ref in secondary} == {
        ("east.csv", "east_000.tif"),
        ("west.csv", "west_000.tif"),
    }
    assert all(ref.requires_raster_metadata_scan for ref in secondary)
    primaries = [
        ref for inp in run.find_input(lhs="Read Grid RF")
        for ref in inp.file_references
    ]
    assert {ref.path_pattern.name for ref in primaries} == {
        "east.csv", "satellite.nc", "west.csv",
    }
    assert {ref.database_kind for ref in primaries} == {
        "rainfall", "rainfall_netcdf",
    }



def test_multiple_material_files_contribute_independent_sources(tmp_path):
    """TUFLOW permits more than one Read Materials File command."""
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "Read Materials File == rock.csv | 0.85\n"
        "Read Material File == soil_roughness.csv\n",
        encoding="utf-8",
    )
    (tmp_path / "rock.csv").write_text(
        "Material ID,Manning's n\n1,rock_roughness.csv\n",
        encoding="utf-8",
    )
    (tmp_path / "soil_roughness.csv").write_text(
        "Material ID,Manning's n\n2,0.04\n",
        encoding="utf-8",
    )
    model = TCF(tcf)
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
    ):
        run = model.context(file_resolution="deferred")
        sources = run.deferred_database_sources()
    assert len(sources) == 1
    assert sources[0].path_pattern == tmp_path / "rock_roughness.csv"
    assert sources[0].database_path == tmp_path / "rock.csv"
    assert {
        ref.path_pattern.name for inp in run.find_input()
        for ref in inp.file_references if ref.database_kind == "materials"
    } == {"rock.csv", "soil_roughness.csv"}



def test_bc_database_reassignments_retain_order_and_do_not_merge(tmp_path):
    """A later BC Database changes the active table for subsequent BC inputs."""
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "BC Database == before.csv\n"
        "Read GIS BC == gis/2d_bc_before.shp\n"
        "BC Database == after.csv\n"
        "Read GIS BC == gis/2d_bc_after.shp\n",
        encoding="utf-8",
    )
    _bc_csv(tmp_path / "before.csv", "first.csv")
    _bc_csv(tmp_path / "after.csv", "second.csv")
    model = TCF(tcf)
    with (
        patch.object(Path, "open", side_effect=AssertionError("open")),
        patch.object(Path, "stat", side_effect=AssertionError("stat")),
        patch.object(TuflowPath, "glob", side_effect=AssertionError("glob")),
        patch("sqlite3.connect", side_effect=AssertionError("sqlite")),
    ):
        run = model.context(file_resolution="deferred")
        activations = run.deferred_database_activations()
    bc = [entry for entry in activations if entry.database_kind == "bc"]
    assert [entry.database_path.name for entry in bc] == ["before.csv", "after.csv"]
    assert bc[0].sequence < bc[1].sequence
    assert bc[0].input_uuid != bc[1].input_uuid
    assert all(entry.owning_command.casefold() == "bc database" for entry in bc)
    assert all(entry.owner_control_file == tcf for entry in bc)
    with pytest.raises(ValueError, match="Multiple active bc"):
        run.deferred_database_sources()


def test_scenario_scoping_of_database_activations(tmp_path):
    tcf = tmp_path / "model.tcf"
    tcf.write_text(
        "If Scenario == EXG\n"
        "    BC Database == exg.csv\n"
        "Else\n"
        "    BC Database == dev.csv\n"
        "End If\n",
        encoding="utf-8",
    )
    _bc_csv(tmp_path / "exg.csv", "existing.csv")
    _bc_csv(tmp_path / "dev.csv", "developed.csv")
    model = TCF(tcf)
    exg = model.context("-s1 EXG", file_resolution="deferred")
    dev = model.context("-s1 DEV", file_resolution="deferred")
    assert [x.database_path.name for x in exg.deferred_database_activations()
            if x.database_kind == "bc"] == ["exg.csv"]
    assert [x.database_path.name for x in dev.deferred_database_activations()
            if x.database_kind == "bc"] == ["dev.csv"]
