"""Task 17: deterministic, artifact-bound qualification of selected preprocessing.

Run the CLI only after committing the implementation. The Python API accepts a
caller-declared revision for tests; this is explicitly not a verified Git claim.
Synthetic timing/trajectory/window parameters are engineering fixtures, not
participant-study choices. Expected sensor outputs use known injected bias and
a closed-form convolution, independently of the production filter recurrence.
"""
import argparse
from bisect import bisect_right
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

from pc.clock_sync.analyze_sync import analyze_session
from pc.clock_sync.session_quality import verify_clock_artifacts
from pc.experiment.calibration.provenance import (
    build_calibration_manifest, calibration_provenance_sha256,
)
from pc.experiment.calibration.schema import REFERENCE_TRAJECTORY_COLUMNS
from pc.experiment.calibration.trajectory import generate_guided_2c
from pc.experiment.calibration.validator import validate_reference_trajectory
from pc.experiment.labels.clock_mapping import map_sensor_records
from pc.experiment.labels.schema import MAPPED_SENSOR_TIME_COLUMNS
from pc.experiment.preprocessing import builder
from pc.experiment.preprocessing.artifacts import build_stage25_from_artifacts
from pc.experiment.preprocessing.padding import build_causal_sequence_windows
from pc.experiment.preprocessing.schema import COMMON_GRID_COLUMNS


MS = 1_000_000
START = 1_130_050_000_000
CLOCK_OFFSET = 50 * MS
STEP = 10 * MS
BIAS_END = START - 8 * MS
CUT = START + 320 * MS
IDENTITY = dict(participant_id='PSYNTH001', session_id='SSYNTH001', calibration_id='CALSYNTH2C')
AXES = ('x', 'y', 'z')
BIAS = {'ACCEL': (0.25, -0.5, 9.5), 'GYRO': (0.02, -0.03, 0.04)}
CHANNELS = tuple(f'{family}_{axis}' for family in ('accel', 'gyro') for axis in AXES)
SENSOR_FIELDS = ('grid_pc_time_ns', *CHANNELS, 'accel_status', 'gyro_status',
                 'sensor_status', 'active_motion_flag')
ANDROID_COLUMNS = ('session_id', 'record_name', 'seq_global', 'seq_sensor', 'sensor_type',
                   'sensor_ts_phone_ns', 'callback_elapsed_ns', 'x', 'y', 'z', 'accuracy')
TRAJECTORY = dict(center_x_px=960.0, center_y_px=540.0, radius_px=120.0,
                  center_hold_ns=20*MS, outbound_ns=40*MS, target_hold_ns=20*MS,
                  return_ns=40*MS, sample_interval_ns=STEP,
                  speed_profile_code='SYNTHETIC_LINEAR', trajectory_version='task17-synthetic-v1')
VERSION = 'stage2.5-synthetic-qualification-v1.0'


def _digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest().upper()


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def _csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _config(revision):
    return dict(
        schema_version='1.0', configuration_id='stage2.5-preprocessing-final-v1.1',
        configuration_role='FINAL', grid_interval_ns=STEP, grid_frequency_hz=100.0,
        grid_origin_rule='ALIGN_TO_ORIGIN', grid_domain_rule='INTERSECTION',
        sensor_timestamp_field='pc_mapped_ts_ns', reorder_policy='SORT_AND_REPORT',
        duplicate_policy='KEEP_FIRST', gap_policy='EXPLICIT_STATUS', max_source_gap_ns=20*MS,
        accel_resampling_method='PREVIOUS_SAMPLE_HOLD', gyro_resampling_method='PREVIOUS_SAMPLE_HOLD',
        axis_transform={family: {axis: dict(source_axis=axis, sign=1) for axis in AXES} for family in BIAS},
        bias_correction=dict(method='MEAN_PC_WINDOW', channels=list(AXES), minimum_samples=2,
                             window_start_pc_ns=START-80*MS, window_end_pc_ns=BIAS_END),
        low_pass_filter=dict(family='ONE_POLE_IIR', order=1, cutoff_hz=10.0, grid_frequency_hz=100.0,
                             initialization='FIRST_SAMPLE', reset_policy='EXPLICIT_BOUNDARIES'),
        filter_reset_policy='EXPLICIT_BOUNDARIES',
        active_motion=dict(sensor_family='GYRO', method='L2_NORM_THRESHOLD', channels=['x', 'y'],
                           threshold=0.1, comparison='GREATER_EQUAL'),
        padding_policy=dict(method='REPEAT_FIRST', padding_value=0.0),
        label_lag_convention='grid_label_pc_time_ns = grid_pc_time_ns - alignment_lag_ns',
        alignment_lag_ns=5*MS, source_artifact_paths={}, source_artifact_hashes={},
        derivation_version=VERSION, functional_commit=revision,
    )


def _truth(family, time, scenario):
    elapsed = time - START
    if elapsed < 0 or scenario == 'known_bias':
        return (0.0, 0.0, 0.0)
    if scenario == 'basis_vectors':
        axis = (elapsed // (320*MS)) % 3
        sign = 1.0 if family == 'ACCEL' else -1.0
        return tuple(sign if i == axis else 0.0 for i in range(3))
    if scenario in ('filter_impulse', 'filter_step'):
        active = elapsed >= 80*MS and (scenario == 'filter_step' or elapsed < 88*MS)
        return (float(active), 0.0, 0.0)
    phase = elapsed / (160*MS)
    scale = 1.0 if family == 'ACCEL' else 0.25
    return (scale * (1 + math.sin(phase)), scale * math.cos(phase), scale * math.sin(phase/2))


def _clock(root):
    probes = []
    for seq in range(1, 121):
        phone = 1_000_000_000_000 + seq*2_000_000_000
        pc = phone + CLOCK_OFFSET
        probes.append(dict(session_id='synthetic-task17', probe_phase='startup' if seq <= 60 else 'background',
                           probe_seq=seq, response_valid='True', invalid_reason='',
                           t1_pc_ns=pc-20_100_000, t2_phone_ns=phone-100_000,
                           t3_phone_ns=phone+100_000, t4_pc_ns=pc+20_100_000))
    _csv(root / 'sync_probes.csv', probes)
    model = analyze_session(root)
    # Normalize text newlines on Windows as well as POSIX before hashing.
    _csv(root / 'sync_probes.csv', _read_csv(root / 'sync_probes.csv'))
    _json(root / 'clock_model.json', json.loads((root / 'clock_model.json').read_text(encoding='utf-8')))
    summary = root / 'summary.txt'
    text = summary.read_text(encoding='utf-8')
    with summary.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
    verification = verify_clock_artifacts(clock_model_path=root / 'clock_model.json',
                                          sync_probes_path=root / 'sync_probes.csv',
                                          expected_session_id='synthetic-task17')
    if not verification['passed']:
        raise ValueError('synthetic clock fixture failed reconstructed quality gates')
    return model


def _fixture(root, scenario, revision, *, future_delta=0.0, change_reference=False):
    root.mkdir(parents=True)
    reference = generate_guided_2c(**IDENTITY, start_pc_time_ns=START, config=TRAJECTORY)
    errors = validate_reference_trajectory(reference)
    if errors:
        raise ValueError(f'synthetic guided reference is invalid: {errors}')
    end = reference[-1]['pc_time_ns'] + 24*MS
    raw = []
    for family in BIAS:
        offset = 0 if scenario == 'regular_streams' or family == 'ACCEL' else 4*MS
        for index, time in enumerate(range(START-80*MS+offset, end+1, 8*MS)):
            elapsed = time-START
            if scenario == 'missing_sample' and family == 'ACCEL' and elapsed == 248*MS:
                continue
            if scenario == 'bounded_burst' and family == 'GYRO' and elapsed in (244*MS, 252*MS):
                continue
            if scenario == 'excessive_gap' and family == 'GYRO' and 240*MS <= elapsed <= 320*MS:
                continue
            if scenario == 'timestamp_jitter' and elapsed >= 0:
                time += (-1, 0, 1, 0)[index % 4] * MS
            values = [a+b for a, b in zip(_truth(family, time, scenario), BIAS[family])]
            if future_delta and time > CUT:
                values = [v+future_delta*(i+1) for i, v in enumerate(values)]
            phone = time-CLOCK_OFFSET
            raw.append(dict(session_id='synthetic-android', record_name='synthetic-task17',
                            seq_global=0, seq_sensor=index+1, sensor_type='ACC' if family == 'ACCEL' else 'GYRO',
                            sensor_ts_phone_ns=phone, callback_elapsed_ns=phone+2*MS,
                            **dict(zip(AXES, values)), accuracy=3))
    raw.sort(key=lambda row: (row['sensor_ts_phone_ns'], row['sensor_type']))
    if scenario == 'reorder':
        raw[80], raw[84] = raw[84], raw[80]
    if scenario == 'duplicate':
        extra = dict(raw[80])
        extra['x'] += 90.0  # Distinguishes KEEP_FIRST from KEEP_LAST/averaging.
        raw.insert(81, extra)
    for seq, row in enumerate(raw, 1):
        row['seq_global'] = seq
    _csv(root / 'android.csv', raw, ANDROID_COLUMNS)
    model = _clock(root)
    if scenario == 'invalid_clock':
        path = root / 'clock_model.json'
        saved = json.loads(path.read_text(encoding='utf-8'))
        saved['beta_ns'] += 1*MS
        _json(path, saved)
    if scenario == 'invalid_timestamp':
        raw[80]['sensor_ts_phone_ns'] = -1
        _csv(root / 'android.csv', raw, ANDROID_COLUMNS)
    clock_sha = _file_sha(root / 'clock_model.json')
    mapped = map_sensor_records(
        **IDENTITY, records=[dict(source_row_index=i, phone_sensor_ts_ns=r['sensor_ts_phone_ns'])
                             for i, r in enumerate(raw, 1)],
        source_file='android.csv', clock_model=model, clock_model_sha256=clock_sha,
        clock_quality_passed=True, derivation_version=VERSION)
    _csv(root / 'mapped.csv', mapped, MAPPED_SENSOR_TIME_COLUMNS)
    if scenario == 'identity_mismatch':
        for row in reference:
            row['participant_id'] = 'FOREIGN'
    if change_reference:
        for row in reference:
            for field in ('ref_x_px', 'ref_y_px', 'ref_vx_px_s', 'ref_vy_px_s'):
                row[field] = -3*row[field]+17.0
    _csv(root / 'reference.csv', reference, REFERENCE_TRAJECTORY_COLUMNS)
    _json(root / 'trajectory_config.json', TRAJECTORY)
    mapped_times = [row['pc_mapped_ts_ns'] for row in mapped if row['mapping_status'] == 'MAPPED']
    first, last = min(mapped_times), max(mapped_times)
    manifest = build_calibration_manifest(
        **IDENTITY, calibration_start_pc_ns=first, calibration_end_pc_ns=last,
        cycle_count=2, reference_trajectory_file='reference.csv', trajectory_version=TRAJECTORY['trajectory_version'],
        trajectory_config_sha256=_digest(TRAJECTORY), raw_imu_sha256=_file_sha(root / 'android.csv'),
        clock_model_sha256=clock_sha, source_selection=dict(
            source_file='android.csv', source_file_sha256=_file_sha(root / 'android.csv'),
            source_first_row=1, source_last_row=len(raw), source_first_sequence=1, source_last_sequence=len(raw),
            calibration_start_pc_ns=first, calibration_end_pc_ns=last, calibration_id=IDENTITY['calibration_id']))
    _json(root / 'calibration_manifest.json', manifest)
    config = _config(revision)
    config['source_artifact_paths'] = dict(raw_imu='android.csv', mapped_sensor_times='mapped.csv',
                                         reference_trajectory='reference.csv', clock_model='clock_model.json',
                                         sync_probes='sync_probes.csv', calibration_manifest='calibration_manifest.json')
    config['source_artifact_hashes'] = {role: _file_sha(root / path) for role, path in config['source_artifact_paths'].items()}
    _json(root / 'input_preprocessing_config.json', config)
    records = []
    for index, (native, mapped_row) in enumerate(zip(raw, mapped), 1):
        records.append(dict(**IDENTITY, **{axis: native[axis] for axis in AXES},
                            sensor_family='ACCEL' if native['sensor_type'] == 'ACC' else 'GYRO',
                            source_file='android.csv', source_row_index=index, sensor_sequence=native['seq_sensor'],
                            phone_sensor_ts_ns=native['sensor_ts_phone_ns'], pc_mapped_ts_ns=mapped_row['pc_mapped_ts_ns'],
                            mapping_status=mapped_row['mapping_status']))
    return dict(root=root, config=config, records=records, reference=reference, manifest=manifest)


def _build(fixture):
    result = build_stage25_from_artifacts(session_root=fixture['root'], preprocessing_config=fixture['config'], **IDENTITY)
    folder = fixture['root'] / 'artifacts/preprocessing'
    for key in ('preprocessing_config', 'preprocessing_quality', 'preprocessing_manifest', 'source_verification',
                'source_diagnostics', 'gap_events'):
        _json(folder / f'{key}.json', result[key])
    _csv(folder / 'common_grid.csv', result['common_grid_rows'], COMMON_GRID_COLUMNS)
    _json(folder / 'common_grid.json', result['common_grid_rows'])
    return result


def _oracle(records):
    """Independent fixed-policy oracle: no production preprocessing helpers."""
    streams = {}
    for family in BIAS:
        candidates = sorted((r for r in records if r['sensor_family'] == family),
                            key=lambda r: (r['pc_mapped_ts_ns'], r['source_file'],
                                           str(r['source_row_index']), str(r['sensor_sequence'])))
        unique = {}
        for row in candidates:
            unique.setdefault(row['pc_mapped_ts_ns'], row)
        streams[family] = list(unique.values())
    lower = max(rows[0]['pc_mapped_ts_ns'] for rows in streams.values())
    upper = min(rows[-1]['pc_mapped_ts_ns'] for rows in streams.values())
    times = [t for t in range(((lower+STEP-1)//STEP)*STEP, upper+1, STEP) if t > BIAS_END]
    expected = [dict(grid_pc_time_ns=t) for t in times]
    alpha = (2*math.pi*10/100)/(1+2*math.pi*10/100)
    q = 1-alpha
    for family, rows in streams.items():
        native_times = [r['pc_mapped_ts_ns'] for r in rows]
        history = []
        for time, out in zip(times, expected):
            source = rows[bisect_right(native_times, time)-1]
            valid = time-source['pc_mapped_ts_ns'] <= 20*MS
            out[f'{family.lower()}_status'] = 'VALID' if valid else 'GAP_EXCEEDED'
            if valid:
                history.append([source[axis]-BIAS[family][i] for i, axis in enumerate(AXES)])
                n = len(history)-1
                values = [q**n*history[0][i] + alpha*math.fsum(q**(n-k)*history[k][i] for k in range(1, n+1))
                          for i in range(3)]
            else:
                history = []
                values = [None]*3
            out.update({f'{family.lower()}_{axis}': value for axis, value in zip(AXES, values)})
    for row in expected:
        a, g = row['accel_status'] == 'VALID', row['gyro_status'] == 'VALID'
        row['sensor_status'] = 'VALID' if a and g else 'INVALID_GYRO' if a else 'INVALID_ACCEL' if g else 'INVALID_BOTH'
        row['active_motion_flag'] = g and math.hypot(row['gyro_x'], row['gyro_y']) >= 0.1
    return expected


def _check(name, actual, expected, *, tolerance=None):
    passed = (abs(actual-expected) <= tolerance) if tolerance is not None else actual == expected
    result = dict(name=name, actual=actual, expected=expected, passed=bool(passed))
    if tolerance is not None:
        result['absolute_tolerance'] = tolerance
    return result


def _case(checks, **observed):
    return dict(status='PASS' if checks and all(c['passed'] for c in checks) else 'FAIL',
                checks=checks, observed=observed)


def _compare(actual, expected, fields):
    mismatches, max_error = [], 0.0
    if len(actual) != len(expected):
        mismatches.append(dict(field='row_count', actual=len(actual), expected=len(expected)))
    for index, (got, want) in enumerate(zip(actual, expected)):
        for field in fields:
            a, e = got[field], want[field]
            if isinstance(e, float) and isinstance(a, (int, float)) and not isinstance(a, bool):
                error = abs(a-e)
                max_error = max(max_error, error)
                equal = math.isfinite(a) and error <= 1e-10
            else:
                equal = a == e
            if not equal:
                mismatches.append(dict(row=index, field=field, actual=a, expected=e))
    return [_check('mismatched_fields', len(mismatches), 0)], dict(
        row_count=len(actual), max_absolute_numeric_error=max_error, first_mismatches=mismatches[:8])


def _label_oracle(reference, time):
    domain = ('participant_id', 'session_id', 'calibration_id', 'sequence_id', 'segment_index', 'direction_code', 'phase')
    fields = ('sequence_id', 'direction_code', 'phase', 'ref_x_px', 'ref_y_px', 'ref_vx_px_s', 'ref_vy_px_s')
    result = dict.fromkeys(fields)
    result['grid_label_pc_time_ns'] = time
    if time < reference[0]['pc_time_ns'] or time > reference[-1]['pc_time_ns']:
        return dict(result, label_status='OUTSIDE_REFERENCE')
    left = bisect_right([r['pc_time_ns'] for r in reference], time)-1
    a = reference[left]
    if a['pc_time_ns'] == time:
        return dict(result, **{f: a[f] for f in fields}, label_status='VALID')
    b = reference[left+1]
    if any(a[f] != b[f] for f in domain):
        return dict(result, label_status='UNRESOLVED_BOUNDARY')
    weight = (time-a['pc_time_ns'])/(b['pc_time_ns']-a['pc_time_ns'])
    result.update({f: a[f] if not f.startswith('ref_') else a[f]+weight*(b[f]-a[f]) for f in fields})
    return dict(result, label_status='VALID')


def _windows(rows):
    return build_causal_sequence_windows(rows=rows, feature_fields=CHANNELS, window_length=3,
                                         padding_policy='REPEAT_FIRST', padding_value=0.0)


def _negative(root, scenario, revision, expected_fragment):
    fixture = _fixture(root, scenario, revision)
    message, rejected = '', False
    try:
        _build(fixture)
    except ValueError as exc:
        message, rejected = str(exc), True
    checks = [_check('rejected', rejected, True),
              _check('expected_rejection_reason', expected_fragment in message, True)]
    _json(root / 'rejection.json', dict(rejected=rejected, reason=message))
    return _case(checks, rejected=rejected, reason=message)


def run_synthetic_qualification(*, output_root, functional_commit):
    """Generate new evidence, refusing all nonempty directories. Never reads participant data."""
    if not isinstance(functional_commit, str) or not functional_commit.strip():
        raise ValueError('functional_commit must be a nonempty caller-declared revision')
    root = Path(output_root)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError('output directory must be new or empty; evidence overwrite is forbidden')
    root.mkdir(parents=True, exist_ok=True)
    scenarios, fixtures, results = {}, {}, {}
    names = ('regular_streams', 'offset_4ms', 'timestamp_jitter', 'reorder', 'duplicate',
             'missing_sample', 'bounded_burst', 'excessive_gap', 'basis_vectors', 'known_bias',
             'filter_impulse', 'filter_step')
    for name in names:
        folder = root / ('baseline' if name == 'offset_4ms' else name)
        fixture = _fixture(folder, name, functional_commit)
        result = _build(fixture)
        expected = _oracle(fixture['records'])
        _json(folder / 'expected_sensor_rows.json', expected)
        checks, observed = _compare(result['common_grid_rows'], expected, SENSOR_FIELDS)
        quality = result['preprocessing_quality']
        checks.append(_check('build_status', quality['status'], 'VALID'))
        if name in ('reorder', 'duplicate'):
            checks.append(_check('injected_anomaly_reported', quality[f'{name}_count'] > 0, True))
        if name == 'excessive_gap':
            checks.extend([_check('gap_reported', quality['gap_event_count'] > 0, True),
                           _check('invalid_rows_visible', quality['invalid_sensor_row_count'] > 0, True)])
        observed.update(build_status=quality['status'], invalid_sensor_row_count=quality['invalid_sensor_row_count'],
                        gap_event_count=quality['gap_event_count'])
        scenarios[name] = _case(checks, **observed)
        fixtures[name], results[name] = fixture, result
    baseline, base_fixture = results['offset_4ms'], fixtures['offset_4ms']
    rows = baseline['common_grid_rows']

    expected_labels = [_label_oracle(base_fixture['reference'], row['grid_pc_time_ns']-5*MS) for row in rows]
    label_fields = tuple(expected_labels[0])
    checks, observed = _compare(rows, expected_labels, label_fields)
    unresolved = sum(r['label_status'] == 'UNRESOLVED_BOUNDARY' for r in rows)
    outside = sum(r['label_status'] == 'OUTSIDE_REFERENCE' for r in rows)
    checks.extend([_check('boundary_exercised', unresolved > 0, True), _check('outside_exercised', outside > 0, True)])
    scenarios['reference_label_boundaries'] = _case(checks, **observed,
                                                   unresolved_boundary_count=unresolved, outside_reference_count=outside)
    _json(root / 'baseline/expected_labels.json', expected_labels)

    windows, expected_windows, history, previous = _windows(rows), [], [], object()
    for row in rows:
        if row['sequence_id'] != previous:
            history = []
        previous = row['sequence_id']
        history.append(tuple(row[c] for c in CHANNELS))
        count = max(0, 3-len(history))
        expected_windows.append(dict(window=tuple([history[0]]*count + history[-3:]),
                                     padding_mask=tuple([True]*count + [False]*(3-count))))
    checks, observed = _compare(windows, expected_windows, ('window', 'padding_mask'))
    scenarios['sequence_start_padding'] = _case(checks, **observed, diagnostic_window_length=3)
    _json(root / 'baseline/sequence_windows.json', windows)
    _json(root / 'baseline/expected_windows.json', expected_windows)

    future_checks = []
    base_prefix = [r for r in rows if r['grid_pc_time_ns'] <= CUT]
    for label, delta in (('positive', 37.0), ('negative', -37.0)):
        fixture = _fixture(root / f'future_{label}', 'offset_4ms', functional_commit, future_delta=delta)
        future = _build(fixture)['common_grid_rows']
        prefix = [r for r in future if r['grid_pc_time_ns'] <= CUT]
        checks, _ = _compare(prefix, base_prefix, SENSOR_FIELDS)
        checks[0]['name'] = f'{label}_unchanged_past_sensor_fields'
        future_checks.extend(checks)
        a, b = _windows(prefix), _windows(base_prefix)
        future_checks.append(_check(f'{label}_unchanged_past_windows',
                                    [(r['window'], r['padding_mask']) for r in a],
                                    [(r['window'], r['padding_mask']) for r in b]))
        changed = sum(any(a[c] != b[c] for c in CHANNELS) for a, b in zip(future, rows) if a['grid_pc_time_ns'] > CUT)
        future_checks.append(_check(f'{label}_future_positive_control', changed > 0, True))
    scenarios['future_perturbation'] = _case(future_checks, cutoff_pc_ns=CUT, directions_tested=2,
                                           scope='mapped sensor event-time causality; not PC arrival availability')

    motion_checks = []
    for value, expected in ((0.1-1e-12, False), (0.1, True), (0.1+1e-12, True)):
        got = builder.classify_active_motion_sample(sample=dict(x=value, y=0.0, z=900.0),
                                                    active_motion_config=base_fixture['config']['active_motion'])
        motion_checks.append(_check(f'norm_{value:.12f}', got, expected))
    scenarios['active_motion_boundaries'] = _case(motion_checks, diagnostic_inputs='x around 0.1; y=0; excluded z=900')

    rebuilt = build_stage25_from_artifacts(session_root=base_fixture['root'],
                                          preprocessing_config=base_fixture['config'], **IDENTITY)
    scenarios['deterministic_rebuild'] = _case([_check('complete_bundle_equal', rebuilt == baseline, True)],
                                              first_digest=_digest(baseline), rebuilt_digest=_digest(rebuilt))
    _json(root / 'baseline/rebuilt_bundle.json', rebuilt)
    for name, fragment in (('invalid_timestamp', 'phone timestamp differs from raw source'), ('invalid_clock', 'clock artifact verification failed'),
                           ('identity_mismatch', 'identity mismatch')):
        scenarios[name] = _negative(root / name, name, functional_commit, fragment)

    oracle_rows = _oracle(base_fixture['records'])
    scenarios['source_boundaries'] = _case([
        _check('first_grid', rows[0]['grid_pc_time_ns'], oracle_rows[0]['grid_pc_time_ns']),
        _check('last_grid', rows[-1]['grid_pc_time_ns'], oracle_rows[-1]['grid_pc_time_ns']),
        _check('all_grid_rows_after_bias', all(r['grid_pc_time_ns'] > BIAS_END for r in rows), True),
    ], bias_window_end_pc_ns=BIAS_END)
    ref_fixture = _fixture(root / 'changed_reference', 'offset_4ms', functional_commit, change_reference=True)
    ref_rows = _build(ref_fixture)['common_grid_rows']
    checks, observed = _compare(ref_rows, rows, SENSOR_FIELDS)
    checks.append(_check('reference_positive_control', any(a['ref_x_px'] != b['ref_x_px'] for a, b in zip(ref_rows, rows)), True))
    scenarios['reference_sensor_independence'] = _case(checks, **observed)

    modified = deepcopy(base_fixture['records'])
    for index, row in enumerate(modified):
        row.update(pc_receive_ts_ns=START-index*100*MS, evaluation_score=999-index, condition_id='ARBITRARY')
    _json(root / 'receive_time_probe_records.json', modified)
    memory_result = builder.build_stage25_preprocessing(
        **IDENTITY, records=modified, reference_trajectory=base_fixture['reference'],
        preprocessing_config=base_fixture['config'], upstream_clock_quality_passed=True,
        upstream_stage24_provenance_sha256=calibration_provenance_sha256(base_fixture['manifest']))
    checks, observed = _compare(memory_result['common_grid_rows'], rows, SENSOR_FIELDS)
    scenarios['receive_time_independence'] = _case(checks, **observed,
                                                  scope='trusted in-memory kernel; no physical arrival-time guarantee')

    reference = base_fixture['reference']
    summary = {key: baseline[key] for key in ('preprocessing_config_sha256', 'common_grid_sha256',
                                              'preprocessing_quality_sha256', 'preprocessing_manifest_sha256')}
    summary.update(reference_cycle_count=len({r['cycle_index'] for r in reference}),
                   reference_sequence_count=len({r['sequence_id'] for r in reference}),
                   source_verification=baseline['source_verification']['scope'])
    config = baseline['preprocessing_config']
    report = dict(
        report_version=VERSION, status='VALID' if all(s['status'] == 'PASS' for s in scenarios.values()) else 'TECHNICAL_INVALID',
        dataset_role='synthetic', real_participant_data_used=False, functional_commit=functional_commit,
        functional_commit_provenance='CALLER_DECLARED_API_ARGUMENT', baseline=summary, scenarios=scenarios,
        selected_policies={k: v for k, v in config.items() if k not in ('source_artifact_paths', 'source_artifact_hashes')},
        fixture_parameters=dict(native_interval_ns=8*MS, sensor_offset_ns=4*MS, label_lag_ns=5*MS,
                                known_bias=BIAS, trajectory=TRAJECTORY, window_length=3,
                                window_length_is_model_choice=False, absolute_numeric_tolerance=1e-10),
        limitations=['Synthetic software qualification only; no real participant or model-performance evidence.',
                     'Clock-fit residuals do not prove absolute synchronization accuracy.',
                     'Mapped-time causality does not prove PC arrival-time availability.',
                     'Native-label manifest chain and Android lifecycle/transport are not qualified.',
                     'Bias stationarity is constructed in this fixture, not inferred from participant recordings.'],
    )
    report['artifact_file_sha256'] = {p.relative_to(root).as_posix(): _file_sha(p)
                                      for p in sorted(root.rglob('*')) if p.is_file()}
    # Exclude only self-referential report/digest files. All raw inputs, oracle
    # values, configuration and production artifact bytes are covered above.
    report = json.loads(json.dumps(report))
    report['reproducibility_digest'] = _digest(report)
    _write_report(root, report)
    return report


def _write_report(root, report):
    _json(root / 'qualification_report.json', report)
    (root / 'qualification_report.sha256').write_bytes((_digest(report)+'\n').encode('ascii'))


def _verified_git_revision():
    root = Path(__file__).resolve().parents[3]
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=False)
    tracked = git('ls-files', '--error-unmatch', 'pc/experiment/preprocessing/synthetic_qualification.py')
    clean = git('diff', '--quiet', 'HEAD', '--', 'pc/clock_sync', 'pc/experiment')
    revision = git('rev-parse', 'HEAD')
    if tracked.returncode or clean.returncode or revision.returncode:
        raise ValueError('qualification implementation must be committed, with no changes under pc/clock_sync or pc/experiment')
    return revision.stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='new or empty evidence directory')
    args = parser.parse_args(argv)
    try:
        revision = _verified_git_revision()
        report = run_synthetic_qualification(output_root=args.output_dir, functional_commit=revision)
        report['functional_commit_provenance'] = 'VERIFIED_CLEAN_GIT_HEAD_AT_CLI_START'
        report.pop('reproducibility_digest')
        report['reproducibility_digest'] = _digest(report)
        _write_report(args.output_dir, report)
    except (ValueError, OSError) as exc:
        print(f'Qualification refused: {exc}')
        return 2
    print(f"{report['status']}: {args.output_dir / 'qualification_report.json'}")
    print(f'functional_commit={revision}')
    return 0 if report['status'] == 'VALID' else 1


if __name__ == '__main__':
    raise SystemExit(main())
