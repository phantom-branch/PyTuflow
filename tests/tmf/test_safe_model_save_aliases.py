"""Renamed saves retain lexical reference caches across directory aliases."""

import os
from pathlib import Path
import subprocess

import pytest

from pytuflow._tmf.cf.tcf import TCF


def _directory_alias(directory: Path) -> tuple[Path, Path]:
    real = directory / 'real'
    alias = directory / 'alias'
    real.mkdir()
    if os.name == 'nt':
        # Directory junctions exercise lexical aliases without requiring the
        # Windows symbolic-link privilege or Developer Mode.
        subprocess.run(
            ['cmd', '/c', 'mklink', '/J', str(alias), str(real)],
            check=True, capture_output=True, text=True,
        )
    else:
        alias.symlink_to(real, target_is_directory=True)
    return real, alias


def _assert_reference_cache(reference, destination: Path, attribute: str) -> None:
    assert reference.files == [destination]
    assert reference._rhs_files == [destination]
    assert getattr(reference, attribute) == [destination]
    assert list(reference._file_to_original) == [destination]
    assert list(reference._file_to_scope) == [str(destination)]
    assert Path(reference._file_to_original[destination]) == destination


@pytest.mark.parametrize('mode', ['eager', 'deferred'])
@pytest.mark.parametrize('nested', [False, True], ids=['child', 'grandchild'])
def test_renamed_child_alias_keeps_context_and_reference_caches(
    tmp_path: Path, mode: str, nested: bool,
) -> None:
    real, alias = _directory_alias(tmp_path)
    text = b'Cell Size == 5\n'
    if nested:
        (real / 'nested').mkdir()
        (real / 'nested' / 'boundary_004.tbc').write_bytes(b'Timestep == 1\n')
        text += b'BC Control File == nested/boundary_004.tbc\n'
    original_geometry = real / 'grid_003.tgc'
    original_geometry.write_bytes(text)
    root = tmp_path / 'model_010.tcf'
    root.write_bytes(b'Geometry Control File == alias/grid_003.tgc\n')
    model = TCF(root)
    reference = model.find_input('Geometry Control File')[0]
    geometry = reference.cf[0]
    lexical_geometry = reference._cf_loaded_paths[0]
    assert lexical_geometry == alias / 'grid_003.tgc'
    assert geometry.fpath == real / 'grid_003.tgc'
    _assert_reference_cache(reference, lexical_geometry, '_cf_loaded_paths')
    if nested:
        nested_reference = geometry.find_input('BC Control File')[0]
        boundary = nested_reference.cf[0]
        lexical_boundary = nested_reference._cf_loaded_paths[0]
        assert lexical_boundary == alias / 'nested' / 'boundary_004.tbc'
        assert boundary.fpath == real / 'nested' / 'boundary_004.tbc'
        _assert_reference_cache(nested_reference, lexical_boundary, '_cf_loaded_paths')

    for increment, size in ((11, 10), (12, 15)):
        geometry.find_input('Cell Size')[0].rhs = str(size)
        if nested:
            boundary.find_input('Timestep')[0].rhs = str(increment)
        model.write('auto')

        # Deferred contexts must select the same owned child through its
        # lexical cache after a save, without reopening the original file.
        context = model.context(file_resolution=mode)
        assert context.find_input('Cell Size')[0].value == float(size)
        destination = alias / f'grid_{increment:03d}.tgc'
        _assert_reference_cache(reference, destination, '_cf_loaded_paths')
        assert reference.cf[0] is geometry
        assert geometry.fpath == real / destination.name
        assert reference.rhs.replace('\\', '/') == f'alias/{destination.name}'
        contextual_ref = context.find_input('Geometry Control File')[0]
        assert contextual_ref.file_references[0].path_pattern == destination
        if nested:
            nested_destination = lexical_boundary.with_name(f'boundary_{increment:03d}.tbc')
            _assert_reference_cache(nested_reference, nested_destination, '_cf_loaded_paths')
            assert nested_reference.cf[0] is boundary
            assert boundary.fpath == real / 'nested' / nested_destination.name
            assert context.find_input('Timestep')[0].value == float(increment)
            contextual_nested_ref = context.find_input('BC Control File')[0]
            assert contextual_nested_ref.file_references[0].path_pattern == nested_destination

    assert original_geometry.read_bytes() == text
    assert root.read_bytes() == b'Geometry Control File == alias/grid_003.tgc\n'


@pytest.mark.parametrize('extension', ['csv', 'tmf'])
def test_renamed_database_alias_retains_cached_secondary_source_selection(
    tmp_path: Path, extension: str,
) -> None:
    real, alias = _directory_alias(tmp_path)
    filename = f'materials_003.{extension}'
    header = "! Material ID,Manning's n" if extension == 'tmf' else "Material ID,Manning's n"
    original_data = f'{header}\n1,0.03\n'.encode('ascii')
    (real / filename).write_bytes(original_data)
    root = tmp_path / 'model_010.tcf'
    root.write_text(f'Read Materials File == alias/{filename}\n', encoding='utf-8')
    model = TCF(root)
    reference = model.find_input('Read Materials File')[0]
    database = reference.cf[0]
    assert database.fpath == real / filename
    assert reference._database_loaded_paths == [alias / filename]
    _assert_reference_cache(reference, alias / filename, '_database_loaded_paths')

    for increment, value in ((11, 0.04), (12, 0.05)):
        database.df.loc[1, "Manning's n"] = value
        model.write('auto')
        destination = alias / f'materials_{increment:03d}.{extension}'
        for mode in ('eager', 'deferred'):
            context = model.context(file_resolution=mode)
            contextual_ref = context.find_input('Read Materials File')[0]
            assert contextual_ref.file_references[0].path_pattern == destination
            # Numeric materials have no secondary file dependencies, but
            # selecting the correct cached database is still mandatory.
            assert contextual_ref.database_source_references == ()
        _assert_reference_cache(reference, destination, '_database_loaded_paths')
        assert reference.cf[0] is database
        assert database.fpath == real / destination.name
        assert database.value(1) == pytest.approx(value)

    assert (real / filename).read_bytes() == original_data
