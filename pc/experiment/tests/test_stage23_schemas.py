from pc.experiment.calibration.schema import (
    CALIBRATION_MANIFEST_REQUIRED_FIELDS,
    DIRECTION_CODES,
    PAUSE_FLAG_BY_PHASE,
    PHASE_CODES,
    REFERENCE_TRAJECTORY_COLUMNS,
)
from pc.experiment.labels.schema import (
    LABEL_BUILD_STATUSES,
    LABEL_CONFIG_REQUIRED_FIELDS,
    LABEL_MANIFEST_REQUIRED_FIELDS,
    LABEL_STATUSES,
    MAPPED_SENSOR_TIME_COLUMNS,
    MAPPING_STATUSES,
    NATIVE_LABEL_COLUMNS,
)


def test_reference_trajectory_columns_are_exact():
    assert REFERENCE_TRAJECTORY_COLUMNS == (
        "reference_sample_id",
        "participant_id",
        "session_id",
        "calibration_id",
        "cycle_index",
        "sequence_id",
        "segment_index",
        "direction_code",
        "phase",
        "pc_time_ns",
        "relative_time_ns",
        "ref_x_px",
        "ref_y_px",
        "ref_vx_px_s",
        "ref_vy_px_s",
        "speed_profile_code",
        "pause_flag",
        "trajectory_version",
    )


def test_direction_codes_are_exact():
    assert DIRECTION_CODES == (
        "RIGHT",
        "UP_RIGHT",
        "UP",
        "UP_LEFT",
        "LEFT",
        "DOWN_LEFT",
        "DOWN",
        "DOWN_RIGHT",
    )


def test_phase_codes_are_exact():
    assert PHASE_CODES == (
        "CENTER_HOLD",
        "OUTBOUND",
        "TARGET_HOLD",
        "RETURN",
    )


def test_pause_flag_semantics_are_exact():
    assert PAUSE_FLAG_BY_PHASE == {
        "CENTER_HOLD": 1,
        "TARGET_HOLD": 1,
        "OUTBOUND": 0,
        "RETURN": 0,
    }


def test_calibration_manifest_fields_are_exact():
    assert CALIBRATION_MANIFEST_REQUIRED_FIELDS == (
        "participant_id",
        "session_id",
        "calibration_id",
        "calibration_start_pc_ns",
        "calibration_end_pc_ns",
        "cycle_count",
        "reference_trajectory_file",
        "trajectory_version",
        "trajectory_config_sha256",
        "raw_imu_sha256",
        "clock_model_sha256",
    )


def test_mapped_sensor_time_columns_are_exact():
    assert MAPPED_SENSOR_TIME_COLUMNS == (
        "mapped_record_id",
        "participant_id",
        "session_id",
        "calibration_id",
        "source_file",
        "source_row_index",
        "phone_sensor_ts_ns",
        "pc_mapped_ts_ns",
        "clock_model_sha256",
        "mapping_status",
        "derivation_version",
    )


def test_mapping_status_vocabulary_is_exact():
    assert MAPPING_STATUSES == frozenset(
        {
            "MAPPED",
            "INVALID_SOURCE_TIMESTAMP",
        }
    )


def test_native_label_columns_are_exact():
    assert NATIVE_LABEL_COLUMNS == (
        "label_record_id",
        "participant_id",
        "session_id",
        "calibration_id",
        "source_file",
        "source_row_index",
        "phone_sensor_ts_ns",
        "pc_mapped_ts_ns",
        "alignment_lag_ns",
        "label_pc_time_ns",
        "sequence_id",
        "direction_code",
        "phase",
        "ref_x_px",
        "ref_y_px",
        "ref_vx_px_s",
        "ref_vy_px_s",
        "label_status",
        "derivation_version",
    )


def test_label_status_vocabulary_is_exact():
    assert LABEL_STATUSES == frozenset(
        {
            "VALID",
            "OUTSIDE_REFERENCE",
            "UNRESOLVED_BOUNDARY",
        }
    )


def test_label_config_required_fields_are_exact():
    assert LABEL_CONFIG_REQUIRED_FIELDS == (
        "schema_version",
        "trajectory_version",
        "lag_sign_convention",
        "alignment_lag_ns",
        "clock_mapping_method",
        "reference_lookup_method",
        "reference_interpolation_rule",
        "out_of_range_policy",
        "source_artifact_paths",
        "source_artifact_hashes",
        "derivation_version",
        "functional_commit",
        "configuration_role",
    )


def test_label_manifest_required_fields_are_exact():
    assert LABEL_MANIFEST_REQUIRED_FIELDS == (
        "participant_id",
        "session_id",
        "calibration_id",
        "status",
        "raw_imu_sha256",
        "reference_trajectory_sha256",
        "clock_model_sha256",
        "label_config_sha256",
        "mapped_record_count",
        "valid_label_count",
        "invalid_label_count",
        "first_mapped_pc_time_ns",
        "last_mapped_pc_time_ns",
        "derivation_version",
        "functional_commit",
    )


def test_label_build_status_vocabulary_is_exact():
    assert LABEL_BUILD_STATUSES == frozenset(
        {
            "VALID",
            "TECHNICAL_INVALID",
        }
    )