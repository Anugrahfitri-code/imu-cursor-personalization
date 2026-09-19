"""Task 17: qualification must detect real pipeline defects and preserve evidence."""
import hashlib
import importlib
import importlib.util
import json
from copy import deepcopy

import pytest


MODULE = 'pc.experiment.preprocessing.synthetic_qualification'
REVISION = 'synthetic-test-revision'
REQUIRED = {
    'regular_streams', 'offset_4ms', 'timestamp_jitter', 'reorder', 'duplicate',
    'missing_sample', 'bounded_burst', 'excessive_gap', 'basis_vectors', 'known_bias',
    'filter_impulse', 'filter_step', 'future_perturbation', 'active_motion_boundaries',
    'sequence_start_padding', 'reference_label_boundaries', 'deterministic_rebuild',
    'invalid_timestamp', 'invalid_clock', 'identity_mismatch', 'source_boundaries',
    'reference_sensor_independence', 'receive_time_independence',
}


def _module():
    assert importlib.util.find_spec(MODULE) is not None, 'Task 17 qualification runner is missing'
    return importlib.import_module(MODULE)


@pytest.fixture(scope='module')
def qualified(tmp_path_factory):
    root = tmp_path_factory.mktemp('task17') / 'evidence'
    report = _module().run_synthetic_qualification(output_root=root, functional_commit=REVISION)
    return root, report


def test_all_required_scenarios_execute_and_pass(qualified):
    _, report = qualified
    assert report['status'] == 'VALID'
    assert report['dataset_role'] == 'synthetic'
    assert report['real_participant_data_used'] is False
    assert REQUIRED <= report['scenarios'].keys()
    assert all(case['status'] == 'PASS' for case in report['scenarios'].values())
    assert report['functional_commit'] == REVISION
    for case in report['scenarios'].values():
        assert case['checks']
        assert all('actual' in check and 'expected' in check for check in case['checks'])


def test_selected_policies_and_full_two_cycle_reference_are_bound(qualified):
    root, report = qualified
    config = json.loads((root / 'baseline/artifacts/preprocessing/preprocessing_config.json').read_text())
    assert config['configuration_id'] == 'stage2.5-preprocessing-final-v1.1'
    assert config['configuration_role'] == 'FINAL'
    assert config['grid_interval_ns'] == 10_000_000
    assert config['grid_frequency_hz'] == 100.0
    assert config['low_pass_filter']['cutoff_hz'] == 10.0
    assert config['max_source_gap_ns'] == 20_000_000
    assert config['duplicate_policy'] == 'KEEP_FIRST'
    assert config['padding_policy']['method'] == 'REPEAT_FIRST'
    assert report['baseline']['reference_cycle_count'] == 2
    assert report['baseline']['reference_sequence_count'] == 16
    assert report['baseline']['source_verification']['clock_only_quality_verified'] is True
    assert report['fixture_parameters']['window_length_is_model_choice'] is False


def test_every_recorded_file_hash_matches_actual_bytes(qualified):
    root, report = qualified
    for relative, expected in report['artifact_file_sha256'].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest().upper() == expected
    recorded = json.loads((root / 'qualification_report.json').read_text())
    assert recorded == report
    canonical = json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    assert (root / 'qualification_report.sha256').read_text().strip() == hashlib.sha256(canonical.encode()).hexdigest().upper()
    assert len(report['baseline']['preprocessing_config_sha256']) == 64
    assert len(report['baseline']['common_grid_sha256']) == 64
    assert len(report['baseline']['preprocessing_quality_sha256']) == 64
    assert len(report['baseline']['preprocessing_manifest_sha256']) == 64
    assert len(report['reproducibility_digest']) == 64


def test_fresh_output_directories_reproduce_identical_evidence(qualified, tmp_path):
    _, first = qualified
    second = _module().run_synthetic_qualification(output_root=tmp_path / 'second', functional_commit=REVISION)
    assert second == first


def test_existing_evidence_is_never_overwritten(tmp_path):
    marker = tmp_path / 'qualification_report.json'
    marker.write_text('historical evidence')
    with pytest.raises(ValueError, match='empty|exist|overwrite'):
        _module().run_synthetic_qualification(output_root=tmp_path, functional_commit=REVISION)
    assert marker.read_text() == 'historical evidence'


def test_future_reading_production_filter_invalidates_qualification(tmp_path, monkeypatch):
    from pc.experiment.preprocessing import builder
    def lookahead(*, stream, channels, **kwargs):
        result = deepcopy(stream)
        for i, row in enumerate(result):
            for channel in channels:
                row[channel] = stream[min(i + 1, len(stream) - 1)][channel]
        return result
    monkeypatch.setattr(builder, 'filter_sensor_stream', lookahead)
    report = _module().run_synthetic_qualification(output_root=tmp_path / 'future', functional_commit=REVISION)
    assert report['status'] == 'TECHNICAL_INVALID'
    assert report['scenarios']['future_perturbation']['status'] == 'FAIL'
    assert report['scenarios']['filter_step']['status'] == 'FAIL'


def test_broken_grid_cannot_get_a_valid_report(tmp_path, monkeypatch):
    from pc.experiment.preprocessing import builder
    original = builder.build_common_grid
    def wrong_grid(**kwargs):
        result = original(**kwargs)
        result['grid_pc_times_ns'] = [t + 1 for t in result['grid_pc_times_ns']]
        return result
    monkeypatch.setattr(builder, 'build_common_grid', wrong_grid)
    report = _module().run_synthetic_qualification(output_root=tmp_path / 'badgrid', functional_commit=REVISION)
    assert report['status'] == 'TECHNICAL_INVALID'
    assert report['scenarios']['offset_4ms']['status'] == 'FAIL'


def test_gap_and_boundary_failures_remain_visible(qualified):
    _, report = qualified
    gap = report['scenarios']['excessive_gap']
    assert gap['observed']['invalid_sensor_row_count'] > 0
    assert gap['observed']['gap_event_count'] > 0
    assert gap['observed']['build_status'] == 'VALID'  # Explicit row invalidity.
    assert report['scenarios']['reference_label_boundaries']['observed']['unresolved_boundary_count'] > 0
    assert report['scenarios']['reference_label_boundaries']['observed']['outside_reference_count'] > 0
    assert report['scenarios']['invalid_clock']['observed']['rejected'] is True
    assert report['scenarios']['invalid_timestamp']['observed']['rejected'] is True


def test_cli_refuses_to_claim_uncommitted_code_as_functional_revision(tmp_path, monkeypatch):
    module = _module()
    def uncommitted():
        raise ValueError('qualification implementation is not committed')
    monkeypatch.setattr(module, '_verified_git_revision', uncommitted)
    root = tmp_path / 'cli'
    assert module.main(['--output-dir', str(root)]) == 2
    assert not root.exists()
