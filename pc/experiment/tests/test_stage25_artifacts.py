"""Artifact-bound Stage 2.5 entrypoint regressions (real fitted clock fixture)."""
import csv
import hashlib
import json
from copy import deepcopy

import pytest

from pc.clock_sync.tests.test_session_quality import _write_fixture, LOCAL_FIELDS
from pc.experiment.calibration.provenance import (
    build_calibration_manifest, calibration_provenance_sha256,
)
from pc.experiment.labels.schema import MAPPED_SENSOR_TIME_COLUMNS
from pc.experiment.tests.test_stage25_builder import _builder_config, _reference

IDENTITY = dict(participant_id='PTEST001', session_id='STEST001', calibration_id='CAL2C001')


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _csv(path, rows, fields=None):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')


def _fixture(root):
    _, raw, _, model, probes = _write_fixture(root, total_samples=20)
    rows = _read_csv(raw)
    # Put the sensor samples inside the clock-exchange time domain.
    for row in rows:
        row['sensor_ts_phone_ns'] = str(int(row['sensor_ts_phone_ns']) + 1_129_000_000_000)
        row['callback_elapsed_ns'] = str(int(row['callback_elapsed_ns']) + 1_129_000_000_000)
    _csv(raw, rows, LOCAL_FIELDS)
    clock = json.loads(model.read_text())
    mapped = []
    for row_index in range(3, 19):
        phone = int(rows[row_index - 1]['sensor_ts_phone_ns'])
        mapped.append({
            'mapped_record_id': f'MAP{row_index:06d}', **IDENTITY,
            'source_file': raw.name, 'source_row_index': row_index,
            'phone_sensor_ts_ns': phone,
            'pc_mapped_ts_ns': int(clock['alpha'] * phone + clock['beta_ns']),
            'clock_model_sha256': _sha(model), 'mapping_status': 'MAPPED',
            'derivation_version': 'stage2.4-real-clock-fixture-v1',
        })
    mapped_path = root / 'mapped.csv'
    _csv(mapped_path, mapped, MAPPED_SENSOR_TIME_COLUMNS)
    start, end = mapped[0]['pc_mapped_ts_ns'], mapped[-1]['pc_mapped_ts_ns']
    reference = _reference()
    for index, row in enumerate(reference):
        row['pc_time_ns'] = start if index == 0 else end
        row['relative_time_ns'] = row['pc_time_ns'] - start
        row['trajectory_version'] = 'stage2.5-artifacts-fixture-v1'
    reference_path = root / 'reference.csv'
    _csv(reference_path, reference)
    manifest = build_calibration_manifest(
        **IDENTITY, calibration_start_pc_ns=start, calibration_end_pc_ns=end,
        cycle_count=2, reference_trajectory_file=reference_path.name,
        trajectory_version='stage2.5-artifacts-fixture-v1', trajectory_config_sha256='C' * 64,
        raw_imu_sha256=_sha(raw), clock_model_sha256=_sha(model), source_selection={
            'source_file': raw.name, 'source_file_sha256': _sha(raw),
            'source_first_row': 3, 'source_last_row': 18,
            'source_first_sequence': 3, 'source_last_sequence': 18,
            'calibration_start_pc_ns': start, 'calibration_end_pc_ns': end,
            'calibration_id': IDENTITY['calibration_id'],
        })
    manifest_path = root / 'calibration_manifest.json'
    _json(manifest_path, manifest)
    config = _builder_config()
    config['source_artifact_paths'] = {
        'raw_imu': raw.name, 'mapped_sensor_times': mapped_path.name,
        'reference_trajectory': reference_path.name, 'clock_model': model.name,
        'sync_probes': probes.name, 'calibration_manifest': manifest_path.name,
    }
    config['source_artifact_hashes'] = {
        role: _sha(root / path) for role, path in config['source_artifact_paths'].items()}
    config['bias_correction']['window_start_pc_ns'] = start
    config['bias_correction']['window_end_pc_ns'] = mapped[3]['pc_mapped_ts_ns']
    return config


def _build(root, config):
    from pc.experiment.preprocessing.artifacts import build_stage25_from_artifacts
    return build_stage25_from_artifacts(session_root=root, preprocessing_config=config, **IDENTITY)


def _rehash(root, config, role):
    config['source_artifact_hashes'][role] = _sha(root / config['source_artifact_paths'][role])


def test_real_clock_artifacts_build_and_record_verified_provenance(tmp_path):
    config = _fixture(tmp_path)
    before = deepcopy(config)
    result = _build(tmp_path, config)
    assert result['preprocessing_quality']['status'] == 'VALID'
    verification = result['source_verification']
    assert verification['source_artifact_hashes'] == config['source_artifact_hashes']
    assert verification['mapped_source_row_count'] == 16
    assert verification['android_session_id'] == 'test-session'
    assert verification['record_name'] == 'test-run'
    assert verification['clock_verification']['passed'] is True
    manifest = json.loads((tmp_path / 'calibration_manifest.json').read_text())
    assert result['preprocessing_manifest']['upstream_stage24_provenance_sha256'] == calibration_provenance_sha256(manifest)
    assert verification['scope']['transport_session_quality_verified'] is False
    assert verification['scope']['native_label_manifest_chain_verified'] is False
    assert config == before
    assert _build(tmp_path, config) == result


def test_hash_tamper_is_rejected_before_parsing(tmp_path):
    config = _fixture(tmp_path)
    (tmp_path / 'android.csv').write_bytes(b'not even a CSV')
    with pytest.raises(ValueError, match='hash|SHA-256'):
        _build(tmp_path, config)


@pytest.mark.parametrize('bad_path', ['missing.csv', '../outside.csv', '/outside.csv'])
def test_missing_and_escaping_paths_fail_closed(tmp_path, bad_path):
    config = _fixture(tmp_path)
    config['source_artifact_paths']['raw_imu'] = bad_path
    with pytest.raises(ValueError, match='path|file|root'):
        _build(tmp_path, config)


def test_symlink_escape_fails_closed(tmp_path):
    root = tmp_path / 'session'
    root.mkdir()
    config = _fixture(root)
    outside = tmp_path / 'outside.csv'
    outside.write_bytes((root / 'android.csv').read_bytes())
    (root / 'escape.csv').symlink_to(outside)
    config['source_artifact_paths']['raw_imu'] = 'escape.csv'
    with pytest.raises(ValueError, match='path|root'):
        _build(root, config)


@pytest.mark.parametrize('field,value', [('source_last_sequence', 17), ('source_last_row', 21), ('calibration_start_pc_ns', 0)])
def test_rehashed_source_selection_mismatch_is_rejected(tmp_path, field, value):
    config = _fixture(tmp_path)
    path = tmp_path / 'calibration_manifest.json'
    manifest = json.loads(path.read_text())
    manifest['source_selection'][field] = value
    _json(path, manifest)
    _rehash(tmp_path, config, 'calibration_manifest')
    with pytest.raises(ValueError, match='selection|sequence|window|row'):
        _build(tmp_path, config)


@pytest.mark.parametrize('mutation', ['drop', 'duplicate', 'source_file', 'mapped_time', 'phone_time'])
def test_rehashed_mapped_rows_must_match_exact_raw_slice_and_clock(tmp_path, mutation):
    config = _fixture(tmp_path)
    path = tmp_path / 'mapped.csv'
    rows = _read_csv(path)
    if mutation == 'drop':
        rows.pop(4)
    elif mutation == 'duplicate':
        rows.append(dict(rows[0]))
    elif mutation == 'source_file':
        rows[0]['source_file'] = 'other.csv'
    elif mutation == 'mapped_time':
        rows[0]['pc_mapped_ts_ns'] = str(int(rows[0]['pc_mapped_ts_ns']) + 1)
    else:
        rows[0]['phone_sensor_ts_ns'] = str(int(rows[0]['phone_sensor_ts_ns']) + 1)
    _csv(path, rows)
    _rehash(tmp_path, config, 'mapped_sensor_times')
    with pytest.raises(ValueError, match='mapped|mapping|coverage|source|phone'):
        _build(tmp_path, config)


def test_rehashed_foreign_reference_is_rejected(tmp_path):
    config = _fixture(tmp_path)
    path = tmp_path / 'reference.csv'
    rows = _read_csv(path)
    for row in rows:
        row['participant_id'] = 'OTHER'
    _csv(path, rows)
    _rehash(tmp_path, config, 'reference_trajectory')
    with pytest.raises(ValueError, match='reference.*identity|participant'):
        _build(tmp_path, config)


def test_rehashed_foreign_clock_probes_are_rejected(tmp_path):
    config = _fixture(tmp_path)
    path = tmp_path / 'sync_probes.csv'
    rows = _read_csv(path)
    for row in rows:
        row['session_id'] = 'foreign-record'
    _csv(path, rows)
    _rehash(tmp_path, config, 'sync_probes')
    with pytest.raises(ValueError, match='clock'):
        _build(tmp_path, config)
