"""Executed synthetic component checks; expected values are independent oracles.

These cases test software mechanics, not participant-study suitability. Sensor
values are explicitly synthetic channel units, and all timestamps are ns.
"""
import math
import json

from pc.experiment.preprocessing import (
    active_motion, axis_transform, bias, filtering, grid, padding,
    resampling, source_validation,
)

DIMENSIONS = (
    'grid_interval_frequency', 'causal_resampling', 'maximum_source_gap',
    'duplicate_policy', 'causal_filter_configuration', 'axis_transform',
    'bias_correction', 'active_motion_rule', 'padding_policy',
)
MS = 1_000_000
IDENTITY = dict(participant_id='SYNTHETIC', session_id='FIXTURE', calibration_id='CAL')


def _equal(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            _equal(actual[k], v) for k, v in expected.items())
    if isinstance(expected, (tuple, list)):
        return isinstance(actual, (tuple, list)) and len(actual) == len(expected) and all(
            _equal(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isfinite(actual) and math.isclose(
            actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    return actual == expected


def _case(name, config, execute, expected, units):
    try:
        actual = json.loads(json.dumps(execute()))
        passed = _equal(actual, expected)
    except Exception as exc:
        actual = {'error_type': type(exc).__name__, 'error': str(exc)}
        passed = False
    return {
        'alternative_id': name,
        'configuration_delta': config,
        'metrics': {'actual': actual, 'expected': expected, 'units': units,
                    'numeric_absolute_tolerance': 1e-12, 'numeric_relative_tolerance': 1e-12},
        'qualification_status': 'PASS' if passed else 'FAIL',
        'qualification_reason': 'Production output matches independent oracle.' if passed
            else 'Production output or execution disagrees with independent oracle.',
    }


def _sample(ms, value=1.0):
    return {'pc_mapped_ts_ns': ms * MS, 'x': value, 'y': 2.0, 'z': 3.0}


def _axis_config(invert_x=False):
    return {family: {axis: {'source_axis': axis, 'sign': -1 if invert_x and axis == 'x' else 1}
                     for axis in ('x', 'y', 'z')} for family in ('ACCEL', 'GYRO')}


def _duplicate_result(policy):
    records = []
    for index, (family, ms, value) in enumerate(
        [('ACCEL', 100, 1.0), ('ACCEL', 100, 2.0), ('ACCEL', 110, 3.0), ('GYRO', 100, 4.0)], 1
    ):
        records.append({**IDENTITY, **_sample(ms, value), 'sensor_family': family,
                        'source_file': 'synthetic.csv', 'source_row_index': index,
                        'sensor_sequence': index, 'phone_sensor_ts_ns': ms * MS + index,
                        'pc_receive_ts_ns': ms * MS + 999, 'mapping_status': 'MAPPED'})
    normalized = source_validation.normalize_sensor_streams(records=records, **IDENTITY)
    result = source_validation.apply_stream_anomaly_policy(
        normalized_result=normalized, reorder_policy='SORT_AND_REPORT', duplicate_policy=policy)
    return {'retained_values': [r['x'] for r in result['streams']['ACCEL']],
            'duplicate_event_count': result['diagnostics']['duplicate_count']}


def _filter_result(cutoff):
    config = dict(family='ONE_POLE_IIR', order=1, cutoff_hz=cutoff,
                  grid_frequency_hz=100.0, initialization='FIRST_SAMPLE',
                  reset_policy='EXPLICIT_BOUNDARIES')
    rows = filtering.filter_sensor_stream(
        stream=[{'x': v} for v in [0.0, 1.0, 1.0, 0.0]], filter_config=config,
        channels=['x'], reset_before_indices=[3])
    return [r['x'] for r in rows]


def _axis_result(invert):
    return {family: [[axis_transform.transform_sensor_sample(
        sample=dict(zip(('x', 'y', 'z'), vector)), sensor_family=family,
        axis_transform=_axis_config(invert))[axis] for axis in ('x', 'y', 'z')]
        for vector in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]]
        for family in ('ACCEL', 'GYRO')}


def _bias_result(count):
    rows = [_sample(i) for i in range(count)]
    estimates = {}
    for family in ('ACCEL', 'GYRO'):
        estimate = bias.estimate_sensor_bias(
            stream=rows, sensor_family=family, method='MEAN_PC_WINDOW',
            window_start_pc_ns=0, window_end_pc_ns=(count - 1) * MS,
            channels=['x', 'y', 'z'], minimum_samples=2)
        corrected = bias.apply_sensor_bias_correction(stream=rows, bias_estimate=estimate)
        estimates[family] = {'estimated_bias': estimate['bias'],
                            'sample_count': estimate['sample_count'],
                            'residuals': [[r[a] for a in ('x', 'y', 'z')] for r in corrected]}
    return estimates


def _padding_result(method):
    rows = [{**IDENTITY, 'sequence_id': seq, 'x': value}
            for seq, value in [('A', 1.0), ('A', 2.0), ('B', 9.0)]]
    result = padding.build_causal_sequence_windows(
        rows=rows, feature_fields=['x'], window_length=3,
        padding_policy=method, padding_value=0.0)
    # Full-stream and prefix builds must agree on the earlier windows as well.
    prefix = padding.build_causal_sequence_windows(
        rows=rows[:1], feature_fields=['x'], window_length=3,
        padding_policy=method, padding_value=0.0)
    return {'windows': [r['window'] for r in result],
            'padding_masks': [r['padding_mask'] for r in result],
            'prefix_unchanged': prefix[0]['window'] == result[0]['window']}


def build_dimension_evidence():
    cases = {dimension: [] for dimension in DIMENSIONS}
    for interval, expected in [(10, [110 * MS, 120 * MS, 130 * MS]), (20, [120 * MS])]:
        cases['grid_interval_frequency'].append(_case(
            f'grid-{1000 // interval}hz', {'grid_interval_ns': interval * MS, 'grid_frequency_hz': 1000 / interval},
            lambda interval=interval: grid.build_common_grid(
                accel_stream=[_sample(100), _sample(130)], gyro_stream=[_sample(104), _sample(134)],
                grid_interval_ns=interval * MS, grid_origin_pc_ns=0,
                grid_domain_rule='INTERSECTION')['grid_pc_times_ns'], expected, 'ns'))
    for offset in (0, 4):
        cases['causal_resampling'].append(_case(
            'previous-sample-hold' if offset == 4 else 'previous-sample-hold-exact',
            {'resampling_method': 'PREVIOUS_SAMPLE_HOLD', 'fixture_offset_ns': offset * MS},
            lambda offset=offset: {k: v for k, v in resampling.resample_sensor_stream(
                stream=[_sample(100, 2.0), _sample(110, 99.0)], grid_pc_times_ns=[(100 + offset) * MS],
                method='PREVIOUS_SAMPLE_HOLD', max_source_gap_ns=20 * MS)[0].items()
                if k in ('x', 'source_age_ns', 'source_pc_mapped_ts_ns', 'status')},
            {'x': 2.0, 'source_age_ns': offset * MS, 'source_pc_mapped_ts_ns': 100 * MS, 'status': 'VALID'},
            {'x': 'synthetic channel units', 'source_age_ns': 'ns', 'source_pc_mapped_ts_ns': 'ns'}))
    cases['causal_resampling'].append({
        'alternative_id': 'exact-only-comparison',
        'configuration_delta': {'resampling_method': 'EXACT_ONLY_COMPARISON'},
        'metrics': {'comparison_only': True, 'production_implementation_available': False},
        'qualification_status': 'NOT_IMPLEMENTED',
        'qualification_reason': 'Analytical comparison only; no production method is qualified.'})
    for gap, expected in [(5, {'status': 'GAP_EXCEEDED', 'x': None}), (20, {'status': 'VALID', 'x': 1.0})]:
        cases['maximum_source_gap'].append(_case(
            f'max-gap-{gap}ms', {'max_source_gap_ns': gap * MS},
            lambda gap=gap: {k: v for k, v in resampling.resample_sensor_stream(
                stream=[_sample(0), _sample(20)], grid_pc_times_ns=[6 * MS],
                method='PREVIOUS_SAMPLE_HOLD', max_source_gap_ns=gap * MS)[0].items()
                if k in ('status', 'x')}, expected, {'time': 'ns', 'x': 'synthetic channel units'}))
    for policy, expected in [('KEEP_FIRST', [1.0, 3.0]), ('KEEP_ALL_REPORT', [1.0, 2.0, 3.0])]:
        cases['duplicate_policy'].append(_case(
            policy.lower().replace('_', '-'), {'duplicate_policy': policy},
            lambda policy=policy: _duplicate_result(policy),
            {'retained_values': expected, 'duplicate_event_count': 1}, 'synthetic channel units; event count'))
    # Independently tabulated backward-Euler one-pole step response at 100 Hz.
    for cutoff, expected in [(5.0, [0.0, 0.23905722361068824, 0.42096609106092586, 0.0]),
                             (10.0, [0.0, 0.38586954509503757, 0.622843784358224, 0.0])]:
        cases['causal_filter_configuration'].append(_case(
            f'one-pole-{cutoff:g}hz', {'cutoff_hz': cutoff, 'grid_frequency_hz': 100.0},
            lambda cutoff=cutoff: _filter_result(cutoff), expected, 'unit step amplitude; Hz'))
    for invert in (False, True):
        expected = [[-1.0 if invert else 1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        cases['axis_transform'].append(_case(
            'invert-x' if invert else 'identity-xyz', {'axis_transform': _axis_config(invert)},
            lambda invert=invert: _axis_result(invert),
            {family: expected for family in ('ACCEL', 'GYRO')}, 'unit basis vectors'))
    for count in (3, 4):
        expected = {'estimated_bias': {'x': 1.0, 'y': 2.0, 'z': 3.0},
                    'sample_count': count, 'residuals': [[0.0, 0.0, 0.0]] * count}
        cases['bias_correction'].append(_case(
            f'mean-window-{count}-samples', {'method': 'MEAN_PC_WINDOW', 'fixture_sample_count': count},
            lambda count=count: _bias_result(count),
            {family: expected for family in ('ACCEL', 'GYRO')}, 'synthetic additive channel units; sample count'))
    for threshold, expected in [(0.1, [False, True, True, True, True]), (0.5, [False, False, False, True, True])]:
        cases['active_motion_rule'].append(_case(
            f'l2-threshold-{threshold}', {'threshold': threshold, 'comparison': 'GREATER_EQUAL'},
            lambda threshold=threshold: [active_motion.classify_active_motion_sample(
                sample={'x': value, 'y': 0.0}, active_motion_config={
                    'method': 'L2_NORM_THRESHOLD', 'channels': ['x', 'y'],
                    'threshold': threshold, 'comparison': 'GREATER_EQUAL'})
                for value in [0.0, 0.1, 0.2, 0.5, 1.0]], expected, 'synthetic gyroscope rad/s; boolean'))
    for method, windows in [
        ('REPEAT_FIRST', [[[1.0], [1.0], [1.0]], [[1.0], [1.0], [2.0]], [[9.0], [9.0], [9.0]]]),
        ('CONSTANT', [[[0.0], [0.0], [1.0]], [[0.0], [1.0], [2.0]], [[0.0], [0.0], [9.0]]]),
    ]:
        cases['padding_policy'].append(_case(
            method.lower().replace('_', '-'), {'method': method, 'window_length': 3},
            lambda method=method: _padding_result(method),
            {'windows': windows, 'padding_masks': [[True, True, False], [True, False, False], [True, True, False]],
             'prefix_unchanged': True}, 'synthetic feature units; boolean masks'))
    return {dimension: {'fixture_id': f'stage2.5-{dimension}-executed-v2',
                        'dataset_role': 'synthetic', 'alternatives': alternatives}
            for dimension, alternatives in cases.items()}
