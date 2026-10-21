"""Tests for opt-in batch dependency discovery and safe per-run memoisation."""

from pathlib import Path
from unittest.mock import patch

from pytuflow import TCF
from pytuflow._tmf.batch_dependencies import BatchContext, collect_batch_dependencies
from pytuflow._tmf.context import Context
from pytuflow._tmf.tfpathlib import TuflowPath


def _make_model(tmp_path: Path) -> TCF:
    source = tmp_path / 'shared.tcf'
    source.write_text(
        'IF Scenario == DEV\n'
        '    Read GIS Code == gis/2d_code_DEV.shp\n'
        'ELSE\n'
        '    Read GIS Code == gis/2d_code_EXG.shp\n'
        'END IF\n'
        'Read Grid Zpts == grids/terrain_*.tif\n',
        encoding='utf-8',
    )
    return TCF(source)


def test_batch_matches_individual_deferred_contexts(tmp_path):
    model = _make_model(tmp_path)
    flags = ('-s1 EXG', '-s1 DEV', '-s1 EXG')
    batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    assert len(batch.runs) == len(flags)
    for case, options in zip(batch.runs, flags, strict=True):
        old = model.context(options, file_resolution='deferred')
        expected = tuple(ref for inp in old.find_input() for ref in inp.file_references)
        assert case.file_references == expected
        assert case.database_sources == old.deferred_database_sources()
        assert case.database_activations == old.deferred_database_activations()


def test_batch_cached_and_uncached_have_identical_references(tmp_path):
    model = _make_model(tmp_path)
    flags = ('-s1 EXG', '-s1 DEV') * 5
    cached = collect_batch_dependencies(model, flags)
    plain = collect_batch_dependencies(model, flags, cache_scopes=False)
    assert cached.passed and plain.passed
    assert tuple((x.file_references, x.database_sources, x.database_activations, x.error)
                 for x in cached.runs) == tuple(
        (x.file_references, x.database_sources, x.database_activations, x.error)
        for x in plain.runs
    )
    assert cached.scope_hits > 0
    assert cached.translation_hits > 0


def test_batch_invalidates_cache_when_loading_new_variables(tmp_path):
    model = _make_model(tmp_path)
    ctx = BatchContext('-s1 DEV', config=model.config)
    first = ctx.translate('gis/<<TEST>>.shp')
    assert first == 'gis/<<TEST>>.shp'
    assert ctx.translate('gis/<<TEST>>.shp') == first
    assert ctx.translation_hits > 0
    ctx.load_variables({'TEST': 'one'})
    assert ctx.translate('gis/<<TEST>>.shp') == 'gis/one.shp'
    ctx.load_variables({'TEST': 'two'})
    assert ctx.translate('gis/<<TEST>>.shp') == 'gis/two.shp'


def test_batch_after_parse_makes_no_input_probes(tmp_path):
    model = _make_model(tmp_path)
    with (
        patch.object(TuflowPath, 'glob', side_effect=AssertionError('glob')),
        patch.object(Path, 'stat', side_effect=AssertionError('stat')),
        patch.object(Path, 'open', side_effect=AssertionError('open')),
    ):
        batch = model.collect_batch_dependencies(('-s1 EXG', '-s1 DEV'))
    assert batch.passed
    assert all(run.file_references for run in batch.runs)


def test_batch_500_contexts_keep_correct_per_run_dependencies(tmp_path):
    model = _make_model(tmp_path)
    flags = tuple('-s1 DEV' if n % 2 else '-s1 EXG' for n in range(500))
    batch = model.collect_batch_dependencies(flags)
    assert batch.passed
    assert len(batch.runs) == 500
    assert batch.scope_hits > 0
    # Literal duplicate contexts can share the exact same immutable projection.
    assert batch.contexts_constructed == 2
    assert batch.contexts_reused == 498
    for case, flag in zip(batch.runs, flags, strict=True):
        scenario = flag.split()[-1]
        paths = {ref.path_pattern.name for ref in case.file_references}
        assert f'2d_code_{scenario}.shp' in paths
        assert 'terrain_*.tif' in paths


def test_single_context_default_stays_eager(tmp_path):
    model = _make_model(tmp_path)
    default = model.context('-s1 DEV')
    assert default.ctx.file_resolution == 'eager'
    assert not isinstance(default.ctx, BatchContext)


def test_batch_context_rejects_invalid_parse_without_making_partial_pass(tmp_path):
    model = _make_model(tmp_path)
    result = model.collect_batch_dependencies(('-s1 DEV', '-s1 DEV -s1 EXG'))
    assert result.runs[0].error is None
    assert result.runs[1].error is not None
    assert not result.passed
    assert result.runs[1].file_references == ()


def test_duplicate_runs_keep_separate_provenance(tmp_path):
    model = _make_model(tmp_path)
    batch = model.collect_batch_dependencies(('-s1 DEV', '-s1 DEV', '-s1 EXG'))
    assert batch.passed
    assert (batch.contexts_constructed, batch.contexts_reused) == (2, 1)
    assert [case.index for case in batch.runs] == [0, 1, 2]
    assert batch.runs[0].file_references == batch.runs[1].file_references
    plain = model.collect_batch_dependencies(('-s1 DEV', '-s1 DEV', '-s1 EXG'), cache_scopes=False)
    assert plain.contexts_constructed == 3
    assert plain.contexts_reused == 0


def test_empty_batch_is_rejected(tmp_path):
    import pytest

    model = _make_model(tmp_path)
    with pytest.raises(ValueError, match='At least one'):
        model.collect_batch_dependencies(())
