"""Verify file evidence before invoking the trusted in-memory Stage 2.5 kernel.

This boundary verifies byte hashes, calibration source selection, the Android /
mapped-time join, reference identity and reconstructed clock-only quality. It
does not qualify transport, prove stationary bias eligibility, or enforce a
native-label manifest/configuration chain. No caller clock-pass flag is accepted.
"""
import csv
import hashlib
import io
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from pc.clock_sync.session_quality import verify_clock_artifacts
from pc.experiment.calibration.provenance import (
    build_calibration_manifest, calibration_provenance_sha256,
)
from pc.experiment.calibration.schema import REFERENCE_TRAJECTORY_COLUMNS
from pc.experiment.labels.schema import MAPPED_SENSOR_TIME_COLUMNS
from pc.experiment.preprocessing.builder import build_stage25_preprocessing
from pc.experiment.preprocessing.config import normalize_sha256, validate_preprocessing_config


_REQUIRED_ARTIFACTS = frozenset({
    'raw_imu', 'mapped_sensor_times', 'reference_trajectory', 'clock_model',
    'sync_probes', 'calibration_manifest',
})
_ANDROID_COLUMNS = (
    'session_id', 'record_name', 'seq_global', 'seq_sensor', 'sensor_type',
    'sensor_ts_phone_ns', 'callback_elapsed_ns', 'x', 'y', 'z', 'accuracy',
)
_IDENTITY_FIELDS = ('participant_id', 'session_id', 'calibration_id')
_SELECTION_INTEGERS = (
    'source_first_row', 'source_last_row', 'source_first_sequence',
    'source_last_sequence', 'calibration_start_pc_ns', 'calibration_end_pc_ns',
)


def _integer(value, field):
    if isinstance(value, bool) or not re.fullmatch(r'[+-]?\d+', str(value)):
        raise ValueError(f'{field} must be an integer.')
    return int(value)


def _relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('artifact path must be a nonempty relative POSIX path.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) == '.':
        raise ValueError('artifact path must remain within the session root.')
    return path.as_posix()


def _read_verified_bytes(root, config):
    required = _REQUIRED_ARTIFACTS - config['source_artifact_paths'].keys()
    if required:
        raise ValueError(f'missing required artifact paths: {sorted(required)}')
    content, hashes, paths = {}, {}, {}
    for role, declared in config['source_artifact_paths'].items():
        relative = _relative_path(declared)
        try:
            path = (root / relative).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('artifact path must be a file within the session root.')
            payload = path.read_bytes()
        except (OSError, RuntimeError) as exc:
            raise ValueError(f'artifact file unavailable for {role}.') from exc
        digest = hashlib.sha256(payload).hexdigest().upper()
        if digest != config['source_artifact_hashes'][role]:
            raise ValueError(f'artifact SHA-256 hash mismatch for {role}.')
        content[role], hashes[role], paths[role] = payload, digest, relative
    return content, hashes, paths


def _json_object(payload, role):
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f'{role} contains duplicate JSON keys.')
            value[key] = item
        return value

    def reject_constant(value):
        raise ValueError(f'{role} contains nonfinite JSON number {value}.')

    try:
        result = json.loads(payload.decode('utf-8-sig'), object_pairs_hook=object_pairs,
                            parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid JSON artifact {role}.') from exc
    if not isinstance(result, dict):
        raise ValueError(f'{role} must be a JSON object.')
    return result


def _csv_rows(payload, columns, role):
    try:
        reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig'), newline=''), strict=True)
        if tuple(reader.fieldnames or ()) != columns:
            raise ValueError(f'{role} CSV header does not match its source schema.')
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError(f'invalid CSV artifact {role}.') from exc
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f'{role} CSV must contain complete data rows.')
    return rows


def _validate_identity(row, identity, context):
    if any(row.get(field) != identity[field] for field in _IDENTITY_FIELDS):
        raise ValueError(f'{context} participant/session/calibration identity mismatch.')


def _manifest_selection(manifest, identity, paths, hashes, raw_count):
    _validate_identity(manifest, identity, 'calibration manifest')
    selection = manifest.get('source_selection')
    if not isinstance(selection, Mapping):
        raise ValueError('calibration manifest missing source selection.')
    for field in ('calibration_start_pc_ns', 'calibration_end_pc_ns', 'cycle_count'):
        _integer(manifest.get(field), f'calibration manifest {field}')
    for field in _SELECTION_INTEGERS:
        _integer(selection.get(field), f'source selection {field}')
    # Reuse the Stage 2.3 provenance contract, including cycle count, hashes,
    # calibration identity and equality of manifest/selection time windows.
    fields = (
        *_IDENTITY_FIELDS, 'calibration_start_pc_ns', 'calibration_end_pc_ns',
        'cycle_count', 'reference_trajectory_file', 'trajectory_version',
        'trajectory_config_sha256', 'raw_imu_sha256', 'clock_model_sha256',
        'source_selection',
    )
    if any(field not in manifest for field in fields):
        raise ValueError('calibration manifest missing required source fields.')
    validated = build_calibration_manifest(**{field: manifest[field] for field in fields})
    selected = validated['source_selection']
    for role in ('raw_imu', 'clock_model'):
        if validated[f'{role}_sha256'] != hashes[role]:
            raise ValueError(f'calibration manifest {role} hash mismatch.')
    if _relative_path(selected['source_file']) != paths['raw_imu']:
        raise ValueError('source selection file does not match the declared raw source.')
    if _relative_path(validated['reference_trajectory_file']) != paths['reference_trajectory']:
        raise ValueError('manifest reference path does not match the declared reference artifact.')
    first, last = selected['source_first_row'], selected['source_last_row']
    if not 1 <= first <= last <= raw_count:
        raise ValueError('source selection row boundaries are outside the raw file.')
    return selected


def _recording_identity(selected_raw):
    result = {}
    for field in ('session_id', 'record_name'):
        values = {row[field] for row in selected_raw}
        if len(values) != 1 or not next(iter(values)).strip():
            raise ValueError(f'raw selected evidence has mixed/empty Android {field}.')
        result[field] = next(iter(values))
    return result


def _verify_clock_snapshot(content, recording):
    # The helper accepts paths. Its private snapshots contain precisely the bytes
    # already hashed, so replacing an original file cannot alter what is parsed.
    with TemporaryDirectory(prefix='stage25-clock-verification-') as temporary:
        directory = Path(temporary)
        model_path, probes_path = directory / 'clock_model.json', directory / 'sync_probes.csv'
        model_path.write_bytes(content['clock_model'])
        probes_path.write_bytes(content['sync_probes'])
        verification = verify_clock_artifacts(
            clock_model_path=model_path, sync_probes_path=probes_path,
            expected_session_id=recording['record_name'])
    if not verification['passed']:
        raise ValueError('clock artifact verification failed: ' + ', '.join(verification['failed_gates']))
    return verification


def _join_source_rows(raw, mapped, selection, identity, raw_path, clock_sha, clock):
    first, last = selection['source_first_row'], selection['source_last_row']
    selected_raw = raw[first - 1:last]
    first_seq, last_seq = selection['source_first_sequence'], selection['source_last_sequence']
    sequences = [_integer(row['seq_global'], 'raw global sequence') for row in selected_raw]
    if sequences[0] != first_seq or sequences[-1] != last_seq or any(
        not first_seq <= seq <= last_seq for seq in sequences
    ):
        raise ValueError('source selection sequence boundaries do not match raw evidence.')
    by_source_row = {}
    for row in mapped:
        _validate_identity(row, identity, 'mapped source')
        if _relative_path(row['source_file']) != raw_path:
            raise ValueError('mapped source_file does not match raw source.')
        index = _integer(row['source_row_index'], 'mapped source row index')
        if index in by_source_row:
            raise ValueError('mapped source coverage contains a duplicate row.')
        by_source_row[index] = row
    if set(by_source_row) != set(range(first, last + 1)):
        raise ValueError('mapped source coverage must equal the exact selected raw slice.')
    records = []
    for index in range(first, last + 1):
        native, row = raw[index - 1], by_source_row[index]
        if row['mapping_status'] != 'MAPPED':
            raise ValueError('mapped source row must have MAPPED status.')
        if normalize_sha256(row['clock_model_sha256'], field_name='mapped clock SHA-256') != clock_sha:
            raise ValueError('mapped clock hash differs from the verified clock artifact.')
        phone = _integer(native['sensor_ts_phone_ns'], 'raw phone sensor timestamp')
        if phone < 0 or _integer(row['phone_sensor_ts_ns'], 'mapped phone timestamp') != phone:
            raise ValueError('mapped phone timestamp differs from raw source.')
        expected_pc = int(clock['alpha'] * phone + clock['beta_ns'])
        mapped_pc = _integer(row['pc_mapped_ts_ns'], 'mapped PC timestamp')
        if mapped_pc != expected_pc:
            raise ValueError('mapped timestamp differs from reconstructed affine clock mapping.')
        if not selection['calibration_start_pc_ns'] <= mapped_pc <= selection['calibration_end_pc_ns']:
            raise ValueError('mapped source timestamp is outside the selected calibration window.')
        family = {'ACC': 'ACCEL', 'GYRO': 'GYRO'}.get(native['sensor_type'])
        if family is None:
            raise ValueError('raw source contains an unsupported sensor family.')
        try:
            values = {axis: float(native[axis]) for axis in ('x', 'y', 'z')}
        except (TypeError, ValueError) as exc:
            raise ValueError('raw sensor channels must be finite numeric values.') from exc
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError('raw sensor channels must be finite numeric values.')
        records.append({
            **identity, **values, 'sensor_family': family, 'source_file': raw_path,
            'source_row_index': index, 'sensor_sequence': _integer(native['seq_sensor'], 'raw sensor sequence'),
            'phone_sensor_ts_ns': phone, 'pc_mapped_ts_ns': mapped_pc,
            'pc_receive_ts_ns': None, 'mapping_status': 'MAPPED',
        })
    return records


def build_stage25_from_artifacts(
    *, session_root, preprocessing_config, participant_id, session_id, calibration_id,
):
    """Build from verified local artifacts; does not modify source files.

    Source row numbers are 1-based CSV data-row positions. Android session_id
    and record_name are recording identities, distinct from study session_id.
    The upstream provenance hash is the canonical actual calibration manifest,
    using Stage 2.3's calibration_provenance_sha256 contract. No assertion about
    a native-label manifest chain or full transport/session quality is made.
    """
    root = Path(session_root).resolve()
    if not root.is_dir():
        raise ValueError('session root must be an existing directory.')
    identity = dict(participant_id=participant_id, session_id=session_id, calibration_id=calibration_id)
    if any(not isinstance(value, str) or not value.strip() for value in identity.values()):
        raise ValueError('experiment identity must contain nonempty strings.')
    config = validate_preprocessing_config(preprocessing_config)
    content, hashes, paths = _read_verified_bytes(root, config)
    raw = _csv_rows(content['raw_imu'], _ANDROID_COLUMNS, 'raw_imu')
    mapped = _csv_rows(content['mapped_sensor_times'], MAPPED_SENSOR_TIME_COLUMNS, 'mapped_sensor_times')
    reference = _csv_rows(content['reference_trajectory'], REFERENCE_TRAJECTORY_COLUMNS, 'reference_trajectory')
    manifest = _json_object(content['calibration_manifest'], 'calibration_manifest')
    selection = _manifest_selection(manifest, identity, paths, hashes, len(raw))
    recording = _recording_identity(raw[selection['source_first_row'] - 1:selection['source_last_row']])
    clock = _verify_clock_snapshot(content, recording)
    records = _join_source_rows(raw, mapped, selection, identity, paths['raw_imu'], hashes['clock_model'], clock['clock'])
    for row in reference:
        _validate_identity(row, identity, 'reference trajectory')
        if row['trajectory_version'] != manifest['trajectory_version']:
            raise ValueError('reference trajectory version differs from calibration manifest.')
    provenance = calibration_provenance_sha256(manifest)
    result = build_stage25_preprocessing(
        **identity, records=records, reference_trajectory=reference,
        preprocessing_config=config, upstream_stage24_provenance_sha256=provenance,
        upstream_clock_quality_passed=True,
    )
    result['source_verification'] = {
        'verification_version': 'stage2.5-artifacts-v1',
        'source_artifact_hashes': hashes, 'source_artifact_paths': paths,
        'calibration_provenance_sha256': provenance, 'source_selection': selection,
        'mapped_source_row_count': len(records),
        'android_session_id': recording['session_id'], 'record_name': recording['record_name'],
        'clock_verification': clock,
        'scope': {
            'artifact_bytes_and_source_slice_verified': True,
            'clock_only_quality_verified': True,
            'transport_session_quality_verified': False,
            'native_label_manifest_chain_verified': False,
            'bias_stationarity_verified': False,
            'guided_trajectory_geometry_verified': False,
            'pc_receive_timestamps_available': False,
        },
    }
    return result
