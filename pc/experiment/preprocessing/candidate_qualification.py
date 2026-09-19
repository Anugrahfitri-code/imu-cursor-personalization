"""Versioned software qualification, with executed oracles and causal probes.

The caller's records are not asserted to be synthetic or provenance-verified.
Internally generated component fixtures are synthetic. Passing finite probes is
engineering evidence, not proof for every possible input or study suitability.
"""
import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from pc.experiment.preprocessing.builder import build_stage25_preprocessing
from pc.experiment.preprocessing.config import normalize_sha256, validate_preprocessing_config
from pc.experiment.preprocessing.qualification_microfixtures import DIMENSIONS, build_dimension_evidence

QUALIFICATION_VERSION = 'stage2.5-candidate-qualification-v2.0'
SYNTHETIC_FIXTURE_ID = 'stage2.5-executed-component-fixtures-v2'
COMPARED_DIMENSIONS = DIMENSIONS
_BUNDLE_FIELDS = ('qualification_report', 'qualification_report_sha256')
_SENSOR_FIELDS = ('grid_pc_time_ns', 'accel_x', 'accel_y', 'accel_z',
                  'gyro_x', 'gyro_y', 'gyro_z', 'accel_status', 'gyro_status',
                  'sensor_status', 'active_motion_flag')


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest().upper()


def _validate_candidates(candidate_configs):
    if isinstance(candidate_configs, (str, bytes)) or not candidate_configs:
        raise ValueError('candidate configurations must be a nonempty sequence.')
    result, seen = [], set()
    for candidate in candidate_configs:
        if not isinstance(candidate, Mapping):
            raise ValueError('candidate configuration must be a mapping.')
        normalized = validate_preprocessing_config(candidate)
        if normalized['configuration_role'] != 'CANDIDATE':
            raise ValueError('candidate qualification accepts only CANDIDATE configurations.')
        identifier = normalized['configuration_id']
        if identifier in seen:
            raise ValueError(f'duplicate preprocessing configuration_id: {identifier!r}.')
        seen.add(identifier)
        result.append((deepcopy(dict(candidate)), normalized))
    return sorted(result, key=lambda pair: pair[1]['configuration_id'])


def _sensor_rows(rows):
    # Config/provenance hashes and supervision are not online sensor outputs.
    return [{field: row[field] for field in _SENSOR_FIELDS} for row in rows]


def _causality_evidence(*, records, config, base_build, build):
    """Perturb future sensor values without changing timing, support or bias.

    Probe at most three deterministic cut times, in both perturbation directions.
    Include a positive control: at least one later output must respond, otherwise
    a constant/empty result cannot be used as evidence of a functioning pipeline.
    """
    baseline = _sensor_rows(base_build['common_grid_rows'])
    possible = [r['grid_pc_time_ns'] for r in baseline[:-1]
                if r['grid_pc_time_ns'] > config['bias_correction']['window_end_pc_ns']]
    cut_times = sorted({possible[i] for i in (0, len(possible) // 2, len(possible) - 1)}) if possible else []
    violations, probes, changed_future_rows = [], 0, 0
    for cut_time in cut_times:
        for direction in (-1, 1):
            altered = deepcopy(list(records))
            changed_input_count = 0
            for row in altered:
                if row['mapping_status'] != 'MAPPED':
                    continue
                try:
                    timestamp = int(row['pc_mapped_ts_ns'])
                except (TypeError, ValueError, OverflowError):
                    continue
                if timestamp > cut_time:
                    for axis, delta in [('x', 97.0), ('y', -53.0), ('z', 29.0)]:
                        row[axis] = float(row[axis]) + direction * delta
                    changed_input_count += 1
            if not changed_input_count:
                continue
            probes += 1
            try:
                comparison = _sensor_rows(build(altered)['common_grid_rows'])
                prefix_before = [r for r in baseline if r['grid_pc_time_ns'] <= cut_time]
                prefix_after = [r for r in comparison if r['grid_pc_time_ns'] <= cut_time]
                if prefix_before != prefix_after:
                    violations.append({'cut_time_pc_ns': cut_time, 'direction': direction,
                                       'reason': 'FUTURE_VALUES_CHANGED_EARLIER_SENSOR_OUTPUT'})
                changed_future_rows += sum(a != b for a, b in zip(
                    [r for r in baseline if r['grid_pc_time_ns'] > cut_time],
                    [r for r in comparison if r['grid_pc_time_ns'] > cut_time]))
            except Exception as exc:
                violations.append({'cut_time_pc_ns': cut_time, 'direction': direction,
                                   'reason': f'PERTURBED_BUILD_FAILED:{type(exc).__name__}'})
    passed = bool(probes and changed_future_rows and not violations)
    return {'status': 'PASS' if passed else 'FAIL', 'probe_count': probes,
            'cut_times_pc_ns': cut_times, 'changed_future_output_count': changed_future_rows,
            'violations': violations,
            'scope': 'Finite future-value perturbations of integrated sensor outputs; padding checked by component fixture.',
            'failure_reason': None if passed else (
                'EARLIER_OUTPUT_CHANGED' if violations else 'INSUFFICIENT_NONVACUOUS_CAUSALITY_EVIDENCE')}


def _microfixture_status(evidence):
    # Every supported production alternative is a shared software gate. The
    # unimplemented analytical comparator is explicit and cannot claim PASS.
    implemented = [case for dimension in evidence.values() for case in dimension['alternatives']
                   if case['qualification_status'] != 'NOT_IMPLEMENTED']
    return 'PASS' if implemented and all(case['qualification_status'] == 'PASS' for case in implemented) else 'FAIL'


def _candidate_result(supplied, config, first, second, causality, dimensions):
    quality = first['preprocessing_quality']
    gates = {
        'build_valid': 'PASS' if quality['status'] == 'VALID' else 'FAIL',
        'causality': causality['status'],
        'reproducibility': 'PASS' if first == second else 'FAIL',
        'supervision_available': 'PASS' if quality['valid_supervision_count'] > 0 else 'FAIL',
        'microfixtures': _microfixture_status(dimensions),
    }
    failed = [name for name, status in gates.items() if status != 'PASS']
    diagnostics = {key: quality[key] for key in (
        'grid_row_count', 'invalid_accel_row_count', 'invalid_gyro_row_count',
        'invalid_sensor_row_count', 'valid_supervision_count', 'invalid_supervision_count',
        'gap_event_count', 'max_observed_source_gap_ns')}
    diagnostics['active_motion_row_count'] = sum(r['active_motion_flag'] is True for r in first['common_grid_rows'])
    return {
        'configuration_id': config['configuration_id'], 'configuration_role': config['configuration_role'],
        'configuration': deepcopy(supplied), 'preprocessing_config_sha256': first['preprocessing_config_sha256'],
        'build_status': quality['status'], 'qualification_gates': gates,
        'timing_coverage_diagnostics': diagnostics, 'causality_result': causality['status'],
        'causality_evidence': causality, 'reproducibility_result': gates['reproducibility'],
        'acceptance_decision': 'REJECTED' if failed else 'ACCEPTED',
        'acceptance_reason': 'Failed technical qualification gate(s): ' + ', '.join(failed) + '.' if failed
            else 'Executed component oracles, causal perturbations and deterministic rebuild passed; input provenance is caller-supplied.',
        'common_grid_sha256': first['common_grid_sha256'],
        'preprocessing_quality_sha256': first['preprocessing_quality_sha256'],
        'preprocessing_manifest_sha256': first['preprocessing_manifest_sha256'],
    }


def qualify_preprocessing_candidates(
    *, participant_id: str, session_id: str, calibration_id: str,
    records: Sequence[Mapping[str, Any]], reference_trajectory: Sequence[Mapping[str, Any]],
    candidate_configs: Sequence[Mapping[str, Any]], upstream_stage24_provenance_sha256: str,
    upstream_clock_quality_passed: bool, technical_errors: Sequence[Any] = (),
) -> dict[str, Any]:
    if upstream_clock_quality_passed is not True:
        raise ValueError('upstream clock quality gate did not pass.')
    upstream_sha = normalize_sha256(upstream_stage24_provenance_sha256, field_name='upstream Stage 2.4 provenance SHA-256')
    candidates = _validate_candidates(candidate_configs)
    dimensions = build_dimension_evidence()
    results = []
    for supplied, config in candidates:
        def build(source_records):
            return build_stage25_preprocessing(
                participant_id=participant_id, session_id=session_id, calibration_id=calibration_id,
                records=source_records, reference_trajectory=reference_trajectory,
                preprocessing_config=config, upstream_stage24_provenance_sha256=upstream_sha,
                upstream_clock_quality_passed=True, technical_errors=technical_errors)
        first, second = build(records), build(records)
        causality = _causality_evidence(records=records, config=config, base_build=first, build=build)
        results.append(_candidate_result(supplied, config, first, second, causality, dimensions))
    report = {
        'qualification_version': QUALIFICATION_VERSION,
        'participant_id': participant_id, 'session_id': session_id, 'calibration_id': calibration_id,
        'upstream_stage24_provenance_sha256': upstream_sha,
        'evidence_set': {
            'dataset_role': 'caller_input_and_generated_microfixtures',
            'real_participant_data_used': None, 'caller_input_origin': 'UNVERIFIED',
            'microfixture_dataset_role': 'synthetic', 'fixture_id': SYNTHETIC_FIXTURE_ID,
            'compared_dimensions': list(COMPARED_DIMENSIONS),
            'provenance_scope': 'Software qualification does not validate caller artifact hashes or participant-study origin.',
        },
        'dimension_evidence': dimensions, 'candidate_count': len(results), 'candidate_results': results,
    }
    return {'qualification_report': report, 'qualification_report_sha256': _canonical_sha256(report)}


def write_candidate_qualification_evidence(*, qualification_bundle, output_directory):
    if not isinstance(qualification_bundle, Mapping) or tuple(qualification_bundle) != _BUNDLE_FIELDS:
        raise ValueError('qualification bundle has unexpected fields.')
    report = qualification_bundle['qualification_report']
    digest = normalize_sha256(qualification_bundle['qualification_report_sha256'], field_name='qualification report SHA-256')
    if digest != _canonical_sha256(report):
        raise ValueError('qualification report SHA-256 does not match report content.')
    output = Path(output_directory)
    report_path, digest_path = output / 'qualification_report.json', output / 'qualification_report.sha256'
    report_text = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + '\n'
    digest_text = digest + '\n'
    for path, text in [(report_path, report_text), (digest_path, digest_text)]:
        if path.exists() and path.read_text(encoding='utf-8') != text:
            raise ValueError('Refusing to overwrite existing qualification evidence; use a new versioned directory.')
    output.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding='utf-8', newline='\n')
    digest_path.write_text(digest_text, encoding='utf-8', newline='\n')
    return {'qualification_report_path': str(report_path), 'qualification_digest_path': str(digest_path),
            'qualification_report_sha256': digest}
