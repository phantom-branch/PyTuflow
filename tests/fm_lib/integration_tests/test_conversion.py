import unittest
from pathlib import Path
import pyproj

from pytuflow._fm.parsers.dat import DAT
from pytuflow._fm.parsers.gxy import GXY
from pytuflow._fm.utils.output_writer import OutputWriter
from pytuflow._fm.helpers.settings import get_fm2estry_settings
from ..common.compare_csv import compare_csv
from ..common.compare_txt import compare_txt
from ..common.compare_vector_layer import compare_vector_layer
from ..common.gis import VectorLayer


class Setup:

    def __init__(self, dat_path: Path) -> None:
        self.dat_path = dat_path
        self.gxy_path = dat_path.with_suffix('.gxy')
        self.name = dat_path.stem
        self.settings = get_fm2estry_settings()
        self.settings.__init__()  # reset settings to default values
        self.settings.crs = pyproj.CRS('EPSG:32760')
        self.settings.dat_fpath_ = self.dat_path
        self.settings.output_dir = Path('./tests/fm_lib/integration_tests/outputs_tmp') / self.name
        self.pre_conv_folder = Path('./tests/fm_lib/integration_tests/pre_converted') / self.name
        [x.unlink() for x in self.settings.output_dir.glob('**/*') if x.is_file()]


class Result:

    def __init__(self, folder: Path, *, csv_subdir: str = '.', gis_subdir: str = '.') -> None:
        self.pre_conv_folder = folder
        self.csv_root = folder / csv_subdir
        self.gis_root = folder / gis_subdir

        def relative_name(path: Path) -> str:
            return path.relative_to(folder).as_posix()

        self.csvs = sorted(folder.glob('**/*.csv'), key=relative_name)
        self.ecfs = sorted(folder.glob('**/*.ecf'), key=relative_name)
        self.gis_files = sorted(folder.glob('**/*.gpkg'), key=relative_name)
        self.gis_layers = []
        for gis_file in self.gis_files:
            with VectorLayer(gis_file) as v:
                self.gis_layers.extend(f'{gis_file} >> {name}' for name in sorted(v.layers()))

    @classmethod
    def converted(cls, folder: Path) -> 'Result':
        # The committed reference archive is flat. The converter's declared
        # output layout places CSV and GIS files in separate category folders.
        # Compare relative identities within these explicit roots; never discard
        # arbitrary directory components or flatten nested output names.
        return cls(folder, csv_subdir='csv', gis_subdir='gis')


def run_conversion(setup):
    dat = DAT(setup.dat_path)
    gxy = GXY(setup.gxy_path)
    dat.add_gxy(gxy)
    output_writer = OutputWriter()
    for unit in dat.units:
        output = unit.convert()
        output_writer.write(output)
    output_writer.finalize()


def _relative_files(root: Path, paths: list[Path]) -> dict[str, Path]:
    return {path.relative_to(root).as_posix(): path for path in paths}


def _relative_layers(result: Result) -> dict[tuple[str, str], str]:
    layers = {}
    for layer in result.gis_layers:
        path, name = layer.split(' >> ', 1)
        key = (Path(path).relative_to(result.gis_root).as_posix(), name)
        assert key not in layers, f'Duplicate GPKG layer identity: {key}'
        layers[key] = layer
    return layers


def _assert_matching_identities[Key: str | tuple[str, str], Value](
    kind: str, first: dict[Key, Value], second: dict[Key, Value],
) -> None:
    assert first.keys() == second.keys(), (
        f'{kind} identities do not match: '
        f'only in result1={sorted(first.keys() - second.keys())}; '
        f'only in result2={sorted(second.keys() - first.keys())}'
    )


def compare(result1: Result, result2: Result) -> None:
    csv1, csv2 = _relative_files(result1.csv_root, result1.csvs), _relative_files(result2.csv_root, result2.csvs)
    ecf1 = _relative_files(result1.pre_conv_folder, result1.ecfs)
    ecf2 = _relative_files(result2.pre_conv_folder, result2.ecfs)
    gpkg1 = _relative_files(result1.gis_root, result1.gis_files)
    gpkg2 = _relative_files(result2.gis_root, result2.gis_files)
    layers1, layers2 = _relative_layers(result1), _relative_layers(result2)

    # Validate the complete output inventory before comparing any contents. Pairing
    # glob results with zip() can hide missing files or pair unrelated names.
    for kind, first, second in (
        ('CSV', csv1, csv2), ('ECF', ecf1, ecf2),
        ('GPKG', gpkg1, gpkg2), ('GPKG layer', layers1, layers2),
    ):
        _assert_matching_identities(kind, first, second)
    for name in sorted(csv1):
        compare_csv(csv1[name], csv2[name])
    for name in sorted(ecf1):
        compare_txt(ecf1[name], ecf2[name])
    for name in sorted(layers1):
        compare_vector_layer(layers1[name], layers2[name])


class TestConversion(unittest.TestCase):

    def test_convert_river_only(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Only.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_replicates(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_replicates.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_interpolates(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_interpolates.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_junctions(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Junctions.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_symmetrical_conduit(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Symmetrical_Conduit.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_asymmetrical_conduit(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Asymmetrical_Conduit.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_circular_conduit(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Circular_Conduit.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_rectangular_conduit(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Rectangular_Conduit.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_full_arch_conduit(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Full_Arch_Conduit.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_sprung_arch_conduit(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Sprung_Arch_Conduit.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_orifice(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Orifice.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_inverted_syphon(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Inverted_Syphon.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_outfall(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Outfall.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_flood_relief_arch(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Flood_Relief_Arch.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_broad_crested_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Broad_Crested_Weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_crump_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Crump_Weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_flat_v_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Flat_V_Weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_flow_head_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Flow_Head_Weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_gated_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Gated_weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_notional_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Notional_weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_labyrinth_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Labyrinth_weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_sharp_crested_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Sharp_Crested_weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_syphon(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Syphon.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_general_weir(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_General_weir.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_InLine_Spill(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_InLine_Spill.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_vertical_sluice(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Vertical.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_radial_sluice(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Radial.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_arch_bridge_irreg_basic(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Arch_Bridge.dat')
        setup = Setup(dat_path)
        setup.settings.arch_bridge_approach = 'I-CULV'
        setup.settings.output_dir = setup.settings.output_dir.parent / 'River_Sections_w_Arch_Bridge_Irregular_Basic'
        [x.unlink() for x in setup.settings.output_dir.glob('**/*') if x.is_file()]
        setup.pre_conv_folder = setup.pre_conv_folder.parent / 'River_Sections_w_Arch_Bridge_Irregular_Basic'
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_arch_bridge_barch_basic(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Arch_Bridge.dat')
        setup = Setup(dat_path)
        setup.settings.arch_bridge_approach = 'BARCH'
        setup.settings.output_dir = setup.settings.output_dir.parent / 'River_Sections_w_Arch_Bridge_BArch_Basic'
        [x.unlink() for x in setup.settings.output_dir.glob('**/*') if x.is_file()]
        setup.pre_conv_folder = setup.pre_conv_folder.parent / 'River_Sections_w_Arch_Bridge_BArch_Basic'
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_arch_bridge_irreg_2arches_as_one(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Arch_Bridge_2.dat')
        setup = Setup(dat_path)
        setup.settings.arch_bridge_approach = 'I-CULV'
        setup.settings.arch_bridge_culv_approach = 'SINGLE'
        setup.settings.output_dir = setup.settings.output_dir.parent / 'River_Sections_w_Arch_Bridge_Irregular_2Arches_as_one'
        [x.unlink() for x in setup.settings.output_dir.glob('**/*') if x.is_file()]
        setup.pre_conv_folder = setup.pre_conv_folder.parent / 'River_Sections_w_Arch_Bridge_Irregular_2Arches_as_one'
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_arch_bridge_irreg_2arches_as_multi(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Arch_Bridge_2.dat')
        setup = Setup(dat_path)
        setup.settings.arch_bridge_approach = 'I-CULV'
        setup.settings.arch_bridge_culv_approach = 'MULTI'
        setup.settings.output_dir = setup.settings.output_dir.parent / 'River_Sections_w_Arch_Bridge_Irregular_2Arches_as_multi'
        [x.unlink() for x in setup.settings.output_dir.glob('**/*') if x.is_file()]
        setup.pre_conv_folder = setup.pre_conv_folder.parent / 'River_Sections_w_Arch_Bridge_Irregular_2Arches_as_multi'
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_arch_bridge_wspill(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Arch_Bridge_wSpill.dat')
        setup = Setup(dat_path)
        setup.settings.arch_bridge_approach = 'BARCH'
        setup.settings.arch_bridge_culv_approach = 'MULTI'
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_pier_loss_bridge(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_Pier_Loss_Bridge.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_w_usbpr_bridge(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_w_USBPR_Bridge.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)

    def test_convert_river_culvert_inlet_outlet(self):
        dat_path = Path('./tests/fm_lib/data/River_Sections_Culvert_inlet_outlet.dat')
        setup = Setup(dat_path)
        pre_cooked_result = Result(setup.pre_conv_folder)
        run_conversion(setup)
        result = Result.converted(setup.settings.output_dir)
        compare(result, pre_cooked_result)
