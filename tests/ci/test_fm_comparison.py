"""Regression checks for FM output inventories and reference text comparison."""

from pathlib import Path

import pytest

from tests.fm_lib.common.compare_txt import compare_txt
from tests.fm_lib.integration_tests import test_conversion as conversion


def make_result(folder: Path, filenames: list[str], *, converted: bool = False) -> conversion.Result:
    folder.mkdir()
    for name in filenames:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('same contents\n', encoding='utf-8')
    return conversion.Result.converted(folder) if converted else conversion.Result(folder)


@pytest.mark.parametrize(
    ('first_names', 'second_names', 'kind'),
    [
        ([], ['model.ecf'], 'ECF'),
        (['model.ecf'], [], 'ECF'),
        (['wrong.ecf'], ['model.ecf'], 'ECF'),
        (['wrong.csv'], ['section.csv'], 'CSV'),
        (['a/section.csv'], ['b/section.csv'], 'CSV'),
    ],
)
def test_rejects_missing_or_misnamed_outputs(
    tmp_path, monkeypatch, first_names, second_names, kind,
):
    first = make_result(tmp_path / 'actual', first_names)
    second = make_result(tmp_path / 'reference', second_names)

    def unexpected_comparison(*args):
        pytest.fail('Content comparison ran before all output identities were checked')

    monkeypatch.setattr(conversion, 'compare_csv', unexpected_comparison)
    monkeypatch.setattr(conversion, 'compare_txt', unexpected_comparison)
    with pytest.raises(AssertionError, match=f'{kind} identities do not match'):
        conversion.compare(first, second)


def test_pairs_relative_names_independently_of_enumeration_order(tmp_path, monkeypatch):
    first = make_result(tmp_path / 'actual', ['z.csv', 'a.csv', 'z.ecf', 'a.ecf'])
    second = make_result(tmp_path / 'reference', ['a.ecf', 'z.ecf', 'a.csv', 'z.csv'])
    first.csvs.reverse()
    first.ecfs.reverse()
    seen = []

    def record_pair(path1, path2):
        assert path1.relative_to(first.pre_conv_folder) == path2.relative_to(second.pre_conv_folder)
        seen.append(path1.name)

    monkeypatch.setattr(conversion, 'compare_csv', record_pair)
    monkeypatch.setattr(conversion, 'compare_txt', record_pair)
    conversion.compare(first, second)
    assert seen == ['a.csv', 'z.csv', 'a.ecf', 'z.ecf']


def test_result_sorts_file_and_layer_inventory(tmp_path, monkeypatch):
    class FakeVectorLayer:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def layers(self):
            return iter(['z_layer', 'a_layer'])

    monkeypatch.setattr(conversion, 'VectorLayer', FakeVectorLayer)
    result = make_result(tmp_path / 'actual', ['z.gpkg', 'a.gpkg', 'z.csv', 'a.csv'])
    assert [path.name for path in result.csvs] == ['a.csv', 'z.csv']
    assert [path.name for path in result.gis_files] == ['a.gpkg', 'z.gpkg']
    assert result.gis_layers == [
        f'{tmp_path / "actual" / path} >> {layer}'
        for path in ['a.gpkg', 'z.gpkg']
        for layer in ['a_layer', 'z_layer']
    ]


@pytest.mark.parametrize('changed_identity', ['file', 'layer'])
def test_rejects_equal_count_wrong_gpkg_identity(tmp_path, monkeypatch, changed_identity):
    first = make_result(tmp_path / 'actual', [])
    second = make_result(tmp_path / 'reference', [])
    first_file = first.pre_conv_folder / ('wrong.gpkg' if changed_identity == 'file' else 'model.gpkg')
    second_file = second.pre_conv_folder / 'model.gpkg'
    first.gis_files = [first_file]
    second.gis_files = [second_file]
    first.gis_layers = [f'{first_file} >> wrong_layer']
    second.gis_layers = [f'{second_file} >> reference_layer']

    def unexpected_comparison(*args):
        pytest.fail('Mismatched GPKG identities were passed to the content comparator')

    monkeypatch.setattr(conversion, 'compare_vector_layer', unexpected_comparison)
    with pytest.raises(AssertionError, match='GPKG.*identities do not match'):
        conversion.compare(first, second)


def test_pairs_gpkg_layers_by_relative_file_and_name(tmp_path, monkeypatch):
    first = make_result(tmp_path / 'actual', [])
    second = make_result(tmp_path / 'reference', [])
    first_file, second_file = first.pre_conv_folder / 'model.gpkg', second.pre_conv_folder / 'model.gpkg'
    first.gis_files, second.gis_files = [first_file], [second_file]
    first.gis_layers = [f'{first_file} >> z_layer', f'{first_file} >> a_layer']
    second.gis_layers = [f'{second_file} >> a_layer', f'{second_file} >> z_layer']
    seen = []

    def record_pair(layer1, layer2):
        assert layer1.split(' >> ')[1] == layer2.split(' >> ')[1]
        seen.append(layer1.split(' >> ')[1])

    monkeypatch.setattr(conversion, 'compare_vector_layer', record_pair)
    conversion.compare(first, second)
    assert seen == ['a_layer', 'z_layer']


def test_declared_category_roots_preserve_nested_relative_names(tmp_path, monkeypatch):
    class FakeVectorLayer:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def layers(self):
            return iter(['network'])

    monkeypatch.setattr(conversion, 'VectorLayer', FakeVectorLayer)
    first = make_result(
        tmp_path / 'actual', ['csv/nested/section.csv', 'gis/nested/model.gpkg', 'model.ecf'],
        converted=True,
    )
    second = make_result(
        tmp_path / 'reference', ['nested/section.csv', 'nested/model.gpkg', 'model.ecf'],
    )
    seen = []

    def check_csv(path1, path2):
        assert path1.relative_to(first.csv_root) == path2.relative_to(second.csv_root)
        seen.append('csv')

    def check_layer(layer1, layer2):
        path1, name1 = layer1.split(' >> ')
        path2, name2 = layer2.split(' >> ')
        assert Path(path1).relative_to(first.gis_root) == Path(path2).relative_to(second.gis_root)
        assert name1 == name2 == 'network'
        seen.append('gpkg')

    monkeypatch.setattr(conversion, 'compare_csv', check_csv)
    monkeypatch.setattr(conversion, 'compare_vector_layer', check_layer)
    conversion.compare(first, second)
    assert seen == ['csv', 'gpkg']


def test_declared_category_root_does_not_flatten_wrong_subdirectory(tmp_path):
    first = make_result(tmp_path / 'actual', ['csv/wrong/section.csv'], converted=True)
    second = make_result(tmp_path / 'reference', ['expected/section.csv'])
    with pytest.raises(AssertionError, match='CSV identities do not match'):
        conversion.compare(first, second)


def test_declared_category_root_rejects_output_in_wrong_category(tmp_path):
    first = make_result(tmp_path / 'actual', ['wrong/section.csv'], converted=True)
    second = make_result(tmp_path / 'reference', ['section.csv'])
    with pytest.raises(ValueError, match='not in the subpath'):
        conversion.compare(first, second)


def test_rejects_extra_empty_geopackage(tmp_path):
    first = make_result(tmp_path / 'actual', [])
    second = make_result(tmp_path / 'reference', [])
    first.gis_files = [first.pre_conv_folder / 'extra.gpkg']
    with pytest.raises(AssertionError, match='GPKG identities do not match'):
        conversion.compare(first, second)


@pytest.mark.parametrize(
    ('actual', 'reference'),
    [
        ('Read File == actual.csv\n', 'Read File == reference.csv\n'),
        ('first\nsecond\n', 'first\nchanged\n'),
        ('first\nsecond\n', 'first\n'),
        ('value \n', 'value\n'),
        ('value\n', 'value'),
    ],
)
def test_text_comparison_rejects_different_contents(tmp_path, actual, reference):
    first, second = tmp_path / 'actual.ecf', tmp_path / 'reference.ecf'
    first.write_text(actual, encoding='utf-8')
    second.write_text(reference, encoding='utf-8')
    with pytest.raises(AssertionError):
        compare_txt(first, second)


def test_text_comparison_accepts_identical_contents(tmp_path):
    first, second = tmp_path / 'actual.ecf', tmp_path / 'reference.ecf'
    first.write_text('line 1\n  line 2\n', encoding='utf-8')
    second.write_text('line 1\n  line 2\n', encoding='utf-8')
    compare_txt(first, second)
