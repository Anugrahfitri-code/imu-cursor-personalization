from copy import deepcopy
import json
import pytest

from pc.experiment.preprocessing import axis_transform, builder
from pc.experiment.preprocessing import (
    active_motion, bias, filtering, grid, padding, resampling, source_validation,
)
from pc.experiment.preprocessing.qualification_microfixtures import build_dimension_evidence
from pc.experiment.preprocessing.candidate_qualification import qualify_preprocessing_candidates
from pc.experiment.preprocessing.candidate_qualification import write_candidate_qualification_evidence
from pc.experiment.tests.test_stage25_qualification import (
    UPSTREAM_SHA, _candidates, _records, _reference,
)


def qualify():
    records = _records()
    records[5]['x'] = 14.0
    return qualify_preprocessing_candidates(
        participant_id='PTEST001', session_id='STEST001',
        calibration_id='CAL2C001', records=records,
        reference_trajectory=_reference(), candidate_configs=_candidates(),
        upstream_stage24_provenance_sha256=UPSTREAM_SHA,
        upstream_clock_quality_passed=True,
    )['qualification_report']


def test_future_reading_filter_fails_behavioral_causality(monkeypatch):
    # A deterministic lookahead must fail even with supported config names.
    def lookahead(*, stream, **kwargs):
        result = deepcopy(stream)
        for i, row in enumerate(result):
            for channel in ('x', 'y', 'z'):
                row[channel] = stream[min(i + 1, len(stream) - 1)][channel]
        return result

    monkeypatch.setattr(builder, 'filter_sensor_stream', lookahead)
    report = qualify()
    assert all(r['causality_result'] == 'FAIL' for r in report['candidate_results'])
    assert all(r['acceptance_decision'] == 'REJECTED' for r in report['candidate_results'])


def test_production_transform_error_changes_evidence_and_rejects_candidates(monkeypatch):
    # Production returns an incorrect basis vector, rather than merely a spy call.
    original = axis_transform.transform_sensor_sample

    def wrong_transform(**kwargs):
        result = original(**kwargs)
        result['x'] += 1.0
        return result

    monkeypatch.setattr(axis_transform, 'transform_sensor_sample', wrong_transform)
    report = qualify()
    alternatives = report['dimension_evidence']['axis_transform']['alternatives']
    assert any(a['qualification_status'] == 'FAIL' for a in alternatives)
    assert all(r['qualification_gates']['microfixtures'] == 'FAIL' for r in report['candidate_results'])
    assert all(r['acceptance_decision'] == 'REJECTED' for r in report['candidate_results'])


def test_input_origin_is_not_inferred_from_qualification_entrypoint():
    report = qualify()
    assert report['qualification_version'] != 'stage2.5-candidate-qualification-v1.0'
    assert report['evidence_set']['caller_input_origin'] == 'UNVERIFIED'
    assert report['evidence_set']['real_participant_data_used'] is None
    assert report['evidence_set']['microfixture_dataset_role'] == 'synthetic'


def test_writer_preserves_existing_historical_evidence(tmp_path):
    # A new report must not silently replace evidence already cited by a decision.
    from pc.experiment.tests.test_stage25_candidate_qualification import _qualify
    historical = tmp_path / 'qualification_report.json'
    historical.write_text(json.dumps({'qualification_version': 'historical-v1'}))
    with pytest.raises(ValueError, match='existing|overwrite|historical'):
        write_candidate_qualification_evidence(qualification_bundle=_qualify(), output_directory=tmp_path)
    assert json.loads(historical.read_text())['qualification_version'] == 'historical-v1'


@pytest.mark.parametrize('dimension,module,function', [
    ('grid_interval_frequency', grid, 'build_common_grid'),
    ('causal_resampling', resampling, 'resample_sensor_stream'),
    ('maximum_source_gap', resampling, 'resample_sensor_stream'),
    ('duplicate_policy', source_validation, 'apply_stream_anomaly_policy'),
    ('causal_filter_configuration', filtering, 'filter_sensor_stream'),
    ('bias_correction', bias, 'estimate_sensor_bias'),
    ('active_motion_rule', active_motion, 'classify_active_motion_sample'),
    ('padding_policy', padding, 'build_causal_sequence_windows'),
])
def test_each_component_oracle_detects_incorrect_production_output(monkeypatch, dimension, module, function):
    # A plausible wrong value from each production component must invalidate
    # its executed evidence, independent of the candidate's constant fixture.
    original = getattr(module, function)

    def incorrect(**kwargs):
        result = deepcopy(original(**kwargs))
        if function == 'build_common_grid':
            result['grid_pc_times_ns'][0] += 1
        elif function in ('resample_sensor_stream', 'filter_sensor_stream'):
            result[0]['x'] = 999.0
        elif function == 'apply_stream_anomaly_policy':
            result['streams']['ACCEL'][0]['x'] = 999.0
        elif function == 'estimate_sensor_bias':
            result['bias']['x'] = 999.0
        elif function == 'classify_active_motion_sample':
            result = not result
        elif function == 'build_causal_sequence_windows':
            result[0]['window'] = ((999.0,),) * 3
        return result

    monkeypatch.setattr(module, function, incorrect)
    evidence = build_dimension_evidence()[dimension]['alternatives']
    assert any(case['qualification_status'] == 'FAIL' for case in evidence)


def test_normal_pipeline_has_nonvacuous_future_perturbation_evidence():
    report = qualify()
    for result in report['candidate_results']:
        evidence = result['causality_evidence']
        assert result['acceptance_decision'] == 'ACCEPTED'
        assert evidence['probe_count'] > 0
        assert evidence['changed_future_output_count'] > 0
        assert evidence['violations'] == []
