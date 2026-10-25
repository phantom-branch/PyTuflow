"""Saved-time contracts using the public readers and small on-disk NetCDF files."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from netCDF4 import Dataset

from pytuflow import Grid, NCGrid
from pytuflow._outputs.map_output import MapOutput
from pytuflow._outputs.output import DEFAULT_REFERENCE_TIME, Output


REFERENCE = datetime(2000, 1, 1, tzinfo=timezone.utc)


def write_grid(tmp_path, times=(0., 1., 2.), units='hours since 2000-01-01 00:00:00',
               calendar=None, static_only=False):
    """Each temporal surface has a distinct constant value: 10, 20, 30, ... ."""
    path = tmp_path / 'times.nc'
    with Dataset(path, 'w') as nc:
        for axis in ('x', 'y'):
            nc.createDimension(axis, 2)
            coordinate = nc.createVariable(axis, 'f8', (axis,))
            coordinate.axis = axis.upper()
            coordinate[:] = [0.5, 1.5]
        if not static_only:
            nc.createDimension('time', len(times))
            time = nc.createVariable('time', 'f8', ('time',))
            if units is not None:
                time.units = units
            if calendar is not None:
                time.calendar = calendar
            time[:] = times
            level = nc.createVariable('water_level', 'f8', ('time', 'y', 'x'))
            level[:] = np.broadcast_to(
                np.arange(1, len(times) + 1)[:, None, None] * 10., (len(times), 2, 2)
            )
        nc.createDimension('static_time', 1)
        maximum = nc.createVariable('maximum_water_level', 'f8', ('static_time', 'y', 'x'))
        maximum[:] = 100.
        bed = nc.createVariable('bed_level', 'f8', ('y', 'x'))
        bed[:] = -5.
    return path


def memory_grid(times):
    return Grid({
        'dx': 1., 'ncol': 2, 'nrow': 2, 'data_type': 'water level',
        'timesteps': times,
        'data': np.broadcast_to(np.arange(1, len(times) + 1)[:, None, None] * 10.,
                                (len(times), 2, 2)).copy(),
    })


@pytest.mark.parametrize(('requested', 'expected'), [
    (-1., 10.), (0., 10.), (0.6, 10.), (1., 20.), (1.6, 20.), (2., 30.), (3., 30.),
])
@pytest.mark.parametrize('absolute', [False, True])
def test_public_point_selects_previous_saved_sample(tmp_path, requested, expected, absolute):
    reader = NCGrid(write_grid(tmp_path))
    time = REFERENCE + timedelta(hours=requested) if absolute else requested
    assert reader.data_point((0.5, 0.5), 'water level', time) == expected


@pytest.mark.parametrize(('method', 'expected'), [('previous', 0), ('next', 1), ('closest', 1)])
def test_selection_methods_use_real_reader_times(tmp_path, method, expected):
    reader = NCGrid(write_grid(tmp_path))
    assert reader._closest_time_index(reader.times(), 0.6, method) == expected


@pytest.mark.parametrize('method', ['previous', 'next', 'closest'])
@pytest.mark.parametrize(('requested', 'expected'), [(-1., 0), (0., 0), (1., 1), (2., 2), (3., 2)])
def test_selection_exact_hits_and_endpoints(method, requested, expected):
    assert Output._closest_time_index([0., 1., 2.], requested, method) == expected


@pytest.mark.parametrize('method', ['previous', 'next', 'closest'])
def test_empty_selection_raises_explicit_error(method):
    with pytest.raises(ValueError, match='(?i)empty|no.*time'):
        Output._closest_time_index([], 0., method)


def test_closest_tie_and_first_tolerance_match_are_stable():
    assert Output._closest_time_index([0., 1., 2.], 0.5, 'closest') == 0
    assert Output._closest_time_index([0., 0.0005, 1.], 0.0004, 'next') == 0


@pytest.mark.parametrize(('requested', 'expected'), [
    (0.999, 20.), (0.9995, 20.), (0.998, 10.), (1.0005, 20.), (1.001, 20.),
])
def test_numeric_and_datetime_tolerance_select_same_sample(tmp_path, requested, expected):
    reader = NCGrid(write_grid(tmp_path))
    assert reader.data_point((0.5, 0.5), 'water level', requested) == expected
    absolute = REFERENCE + timedelta(hours=requested)
    assert reader.data_point((0.5, 0.5), 'water level', absolute) == expected
    assert reader.data_point((0.5, 0.5), 'water level', absolute.replace(tzinfo=None)) == expected


@pytest.mark.parametrize(('unit', 'per_hour', 'label'), [
    ('seconds', 3600., 's'), ('minutes', 60., 'm'), ('hours', 1., 'h'),
    ('days', 1. / 24., 'd'), ('milliseconds', 3_600_000., 'ms'),
    ('microseconds', 3_600_000_000., 'us'),
    ('s', 3600., 's'), ('min', 60., 'm'), ('h', 1., 'h'), ('HOURS', 1., 'h'),
])
def test_equivalent_units_preserve_times_and_extracted_data(tmp_path, unit, per_hour, label):
    source_units = f'{unit} since 2000-01-01 00:00:00'
    reader = NCGrid(write_grid(tmp_path, np.array([0., 1., 2.]) * per_hour, source_units))
    assert reader.times() == pytest.approx([0., 1., 2.])
    assert reader.times(fmt='absolute') == [REFERENCE + timedelta(hours=i) for i in range(3)]
    assert reader.reference_time == REFERENCE
    assert reader.has_reference_time
    assert reader.time_units == label
    assert reader.source_time_units == source_units
    assert reader.data_point((0.5, 0.5), 'water level', 1.) == 20.
    frame = reader.time_series((0.5, 0.5), 'water level')
    np.testing.assert_allclose(frame.index, [0., 1., 2.])
    np.testing.assert_allclose(frame.iloc[:, 0], [10., 20., 30.])
    absolute = reader.time_series((0.5, 0.5), 'water level', time_fmt='absolute')
    assert absolute.index.tolist() == reader.times(fmt='absolute')


@pytest.mark.parametrize('times', [(0., 1., 3.), (0., 1., 1.5), (0.25, 0.5, 2., 4.), (1.5,)])
@pytest.mark.parametrize('from_file', [True, False])
def test_saved_axis_is_preserved_including_irregular_final_gap_and_singleton(tmp_path, times, from_file):
    reader = NCGrid(write_grid(tmp_path, times)) if from_file else memory_grid(times)
    assert reader.times('temporal') == list(times)
    assert reader.data_types('temporal') == ['water level']
    for i, time in enumerate(times):
        surface = reader.surface('water level', time)
        np.testing.assert_allclose(surface['value'], (i + 1) * 10.)
    if from_file:
        frame = reader.time_series((0.5, 0.5), 'water level')
        np.testing.assert_allclose(frame.index, times)
        np.testing.assert_allclose(frame.iloc[:, 0], np.arange(1, len(times) + 1) * 10.)


def test_short_temporal_axis_does_not_become_static(tmp_path):
    reader = NCGrid(write_grid(tmp_path, (0., 1., 2.), 'seconds since 2000-01-01 00:00:00'))
    assert reader.times() == [0., 1. / 3600., 2. / 3600.]
    assert len(reader.time_series((0.5, 0.5), 'water level')) == 3


@pytest.mark.parametrize('times', [(0., 0.001, 0.002), (0., 0.333, 0.666, 0.999)])
def test_subsecond_saved_times_do_not_round_to_zero_or_add_samples(tmp_path, times):
    reader = NCGrid(write_grid(tmp_path, times, 'seconds since 2000-01-01 00:00:00'))
    np.testing.assert_allclose(reader.times(), np.array(times) / 3600., rtol=0., atol=1e-15)
    assert len(reader.time_series((0.5, 0.5), 'water level')) == len(times)


@pytest.mark.parametrize('static_only', [True, False])
def test_static_dimensions_remain_separate_from_temporal_singleton(tmp_path, static_only):
    reader = NCGrid(write_grid(tmp_path, (1.5,), static_only=static_only))
    assert reader.times('static') == []
    assert reader.times('temporal') == ([] if static_only else [1.5])
    assert set(reader.data_types('static')) == {'max water level', 'bed level'}
    assert reader.data_point((0.5, 0.5), 'max water level', 123.) == 100.
    assert reader.data_point((0.5, 0.5), 'bed level', 123.) == -5.


def test_empty_temporal_coordinate_has_no_saved_samples(tmp_path):
    reader = NCGrid(write_grid(tmp_path, ()))
    assert reader.times() == []
    assert reader.time_series((0.5, 0.5), 'water level').empty
    with pytest.raises(ValueError, match='(?i)empty|no.*time'):
        reader.data_point((0.5, 0.5), 'water level', 0.)


@pytest.mark.parametrize('columns', [[], ['start'], ['end', 'dt'], ['start', 'end']])
def test_incomplete_time_metadata_returns_empty_list(columns):
    reader = memory_grid([0., 1.])
    reader._info = pd.DataFrame([{name: 0. for name in columns}])
    assert reader.times() == []


@pytest.mark.parametrize('times', [[], [5400.]])
def test_step_derivation_preserves_empty_and_singleton_axes(times):
    assert MapOutput._calculate_time_step(np.array(times)) == tuple(times)


@pytest.mark.parametrize(('units', 'reference'), [
    ('seconds since 2000-01-01T08:00:00.250+08:00', REFERENCE + timedelta(microseconds=250000)),
    ('hours since 1999-12-31 19:00:00-05:00', REFERENCE),
    ('hours since 2000-01-01 00:00:00Z', REFERENCE),
    ('hours since 2000-01-01 00:00 UTC', REFERENCE),
    ('hours since 2000-01-01', REFERENCE),
    ('hours since 2000-01-31', REFERENCE + timedelta(days=30)),
    ('hours since 2000-01-01T08:00:00+0800', REFERENCE),
    ('hours since 2000-01-01T08:00:00+08', REFERENCE),
])
def test_reference_timezone_and_fractional_seconds_are_respected(tmp_path, units, reference):
    reader = NCGrid(write_grid(tmp_path, (0.,), units))
    assert reader.reference_time == reference
    assert reader.reference_time.tzinfo is not None
    assert reader.times(fmt='absolute') == [reference]
    assert reader.source_time_units == units
    assert reader.data_point((0.5, 0.5), 'water level', reference) == 10.


@pytest.mark.parametrize('units', ['seconds', 'minutes', 'hours'])
def test_unit_only_axis_keeps_default_reference(tmp_path, units):
    reader = NCGrid(write_grid(tmp_path, (0.,), units))
    assert not reader.has_reference_time
    assert reader.reference_time == DEFAULT_REFERENCE_TIME
    assert reader.times(fmt='absolute') == [DEFAULT_REFERENCE_TIME]


@pytest.mark.parametrize('units', [
    None, '', 'fortnights since 2000-01-01 00:00:00', 'months since 2000-01-01',
    'hours since not-a-date', 'hours since 2000-02-30 00:00:00', 'hours since',
    'hours since 2000-01-01 00:00:00 unexpected',
    'hours since 2000-01-01T08:00:00+08:99', 'hours since 2000-01-01T00:00:00+01:60',
    'hours since 0001-01-01T00:00:00+01:00',
])
def test_invalid_units_or_reference_are_diagnosed(tmp_path, units):
    with pytest.raises(ValueError, match='(?i)time|unit|reference'):
        NCGrid(write_grid(tmp_path, units=units))


@pytest.mark.parametrize('calendar', ['standard', 'gregorian', 'proleptic_gregorian'])
def test_supported_calendars_use_real_datetime_contract(tmp_path, calendar):
    reader = NCGrid(write_grid(tmp_path, calendar=calendar))
    assert reader.times(fmt='absolute') == [REFERENCE + timedelta(hours=i) for i in range(3)]
    assert reader.source_calendar == calendar


@pytest.mark.parametrize('calendar', ['360_day', 'noleap', 'julian', 'unknown'])
def test_unsupported_calendars_are_diagnosed(tmp_path, calendar):
    with pytest.raises(ValueError, match='(?i)calendar'):
        NCGrid(write_grid(tmp_path, calendar=calendar))


@pytest.mark.parametrize('times', [(0., 1., 1.), (0., 2., 1.), (0., np.nan), (0., np.inf)])
def test_invalid_saved_coordinates_are_diagnosed(tmp_path, times):
    with pytest.raises(ValueError, match='(?i)time coordinate'):
        NCGrid(write_grid(tmp_path, times))


def test_standard_calendar_does_not_silently_cross_gregorian_transition(tmp_path):
    with pytest.raises(ValueError, match='1582-10-15'):
        NCGrid(write_grid(tmp_path, (-24., 0.), 'hours since 1582-10-15 00:00:00'))


def test_proleptic_gregorian_reference_before_transition_is_supported(tmp_path):
    reader = NCGrid(write_grid(tmp_path, (0.,), 'hours since 1500-01-01', 'proleptic_gregorian'))
    assert reader.times(fmt='absolute') == [datetime(1500, 1, 1, tzinfo=timezone.utc)]


def test_surface_uses_previous_but_section_preserves_closest_policy(tmp_path):
    reader = NCGrid(write_grid(tmp_path))
    np.testing.assert_allclose(reader.surface('water level', 0.6)['value'], 10.)
    section = reader.section([(0.25, 0.5), (1.75, 0.5)], 'water level', 0.6)
    np.testing.assert_allclose(section.iloc[:, -1], 20.)


def test_nominal_float32_axis_keeps_existing_regular_metadata_convention(tmp_path):
    times = np.arange(7, dtype=np.float32) / np.float32(60.)
    reader = NCGrid(write_grid(tmp_path, times))
    assert len(reader.times()) == 7
    np.testing.assert_allclose(reader.times(), np.arange(7) / 60., rtol=1e-6)
    assert reader._info.loc[reader._info['data_type'] == 'water level', 'dt'].iloc[0] == 60.
