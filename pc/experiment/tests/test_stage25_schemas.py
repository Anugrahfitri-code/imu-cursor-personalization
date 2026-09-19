from pc.experiment.preprocessing.schema import (
    PREPROCESSING_SCHEMA_VERSION,
    COMMON_GRID_COLUMNS,
    PREPROCESSING_CONFIG_REQUIRED_FIELDS,
    PREPROCESSING_QUALITY_REQUIRED_FIELDS,
    PREPROCESSING_MANIFEST_REQUIRED_FIELDS,
    SENSOR_FAMILIES,
    SENSOR_COVERAGE_STATUSES,
    GRID_ROW_STATUSES,
    PREPROCESSING_BUILD_STATUSES,
    DUPLICATE_EVENT_TYPES,
    GAP_EVENT_TYPES,
    REORDER_EVENT_TYPES,
)

from pc.experiment.labels.schema import (
    MAPPED_SENSOR_TIME_COLUMNS,
    NATIVE_LABEL_COLUMNS,
)


EXPECTED_COMMON_GRID_COLUMNS = (
    "grid_record_id",
    "participant_id",
    "session_id",
    "calibration_id",
    "grid_index",
    "grid_pc_time_ns",
    "preprocessing_config_sha256",
    "accel_x",
    "accel_y",
    "accel_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "accel_status",
    "gyro_status",
    "sensor_status",
    "active_motion_flag",
    "grid_label_pc_time_ns",
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


EXPECTED_CONFIG_FIELDS = (
    "schema_version",
    "configuration_id",
    "configuration_role",
    "grid_interval_ns",
    "grid_frequency_hz",
    "grid_origin_rule",
    "grid_domain_rule",
    "sensor_timestamp_field",
    "reorder_policy",
    "duplicate_policy",
    "gap_policy",
    "max_source_gap_ns",
    "accel_resampling_method",
    "gyro_resampling_method",
    "axis_transform",
    "bias_correction",
    "low_pass_filter",
    "filter_reset_policy",
    "active_motion",
    "padding_policy",
    "label_lag_convention",
    "alignment_lag_ns",
    "source_artifact_paths",
    "source_artifact_hashes",
    "derivation_version",
    "functional_commit",
)


EXPECTED_QUALITY_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
    "status",
    "accel_source_count",
    "gyro_source_count",
    "reorder_count",
    "duplicate_count",
    "invalid_timestamp_count",
    "first_mapped_pc_time_ns",
    "last_mapped_pc_time_ns",
    "max_observed_source_gap_ns",
    "gap_event_count",
    "grid_row_count",
    "invalid_accel_row_count",
    "invalid_gyro_row_count",
    "invalid_sensor_row_count",
    "valid_supervision_count",
    "invalid_supervision_count",
    "technical_errors",
    "derivation_version",
)


EXPECTED_MANIFEST_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
    "status",
    "source_artifact_hashes",
    "upstream_stage24_provenance_sha256",
    "preprocessing_config_sha256",
    "common_grid_sha256",
    "preprocessing_quality_sha256",
    "first_grid_pc_time_ns",
    "last_grid_pc_time_ns",
    "grid_row_count",
    "derivation_version",
    "functional_commit",
)


EXPECTED_STAGE24_MAPPED_COLUMNS = (
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


EXPECTED_STAGE24_LABEL_COLUMNS = (
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


def test_preprocessing_schema_version_is_frozen():
    assert PREPROCESSING_SCHEMA_VERSION == "1.0"


def test_common_grid_schema_is_exact_and_ordered():
    assert COMMON_GRID_COLUMNS == (
        EXPECTED_COMMON_GRID_COLUMNS
    )


def test_common_grid_identity_and_time_fields_are_present():
    required = {
        "participant_id",
        "session_id",
        "calibration_id",
        "grid_index",
        "grid_pc_time_ns",
        "preprocessing_config_sha256",
    }

    assert required.issubset(
        set(COMMON_GRID_COLUMNS)
    )


def test_common_grid_contains_six_sensor_channels():
    required = {
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
    }

    assert required.issubset(
        set(COMMON_GRID_COLUMNS)
    )


def test_common_grid_preserves_sensor_validity():
    required = {
        "accel_status",
        "gyro_status",
        "sensor_status",
    }

    assert required.issubset(
        set(COMMON_GRID_COLUMNS)
    )


def test_common_grid_preserves_active_motion():
    assert (
        "active_motion_flag"
        in COMMON_GRID_COLUMNS
    )


def test_common_grid_preserves_stage24_label_semantics():
    required = {
        "grid_label_pc_time_ns",
        "sequence_id",
        "direction_code",
        "phase",
        "ref_x_px",
        "ref_y_px",
        "ref_vx_px_s",
        "ref_vy_px_s",
        "label_status",
    }

    assert required.issubset(
        set(COMMON_GRID_COLUMNS)
    )


def test_preprocessing_config_schema_is_exact():
    assert (
        PREPROCESSING_CONFIG_REQUIRED_FIELDS
        == EXPECTED_CONFIG_FIELDS
    )


def test_config_uses_pc_mapped_sensor_time():
    assert (
        "sensor_timestamp_field"
        in PREPROCESSING_CONFIG_REQUIRED_FIELDS
    )


def test_config_records_candidate_sensitive_components():
    required = {
        "grid_interval_ns",
        "grid_frequency_hz",
        "reorder_policy",
        "duplicate_policy",
        "gap_policy",
        "max_source_gap_ns",
        "accel_resampling_method",
        "gyro_resampling_method",
        "axis_transform",
        "bias_correction",
        "low_pass_filter",
        "active_motion",
        "padding_policy",
        "alignment_lag_ns",
    }

    assert required.issubset(
        set(
            PREPROCESSING_CONFIG_REQUIRED_FIELDS
        )
    )


def test_preprocessing_quality_schema_is_exact():
    assert (
        PREPROCESSING_QUALITY_REQUIRED_FIELDS
        == EXPECTED_QUALITY_FIELDS
    )


def test_quality_schema_records_stream_anomalies():
    required = {
        "reorder_count",
        "duplicate_count",
        "invalid_timestamp_count",
        "max_observed_source_gap_ns",
        "gap_event_count",
    }

    assert required.issubset(
        set(
            PREPROCESSING_QUALITY_REQUIRED_FIELDS
        )
    )


def test_quality_schema_separates_grid_and_supervision():
    required = {
        "grid_row_count",
        "invalid_sensor_row_count",
        "valid_supervision_count",
        "invalid_supervision_count",
    }

    assert required.issubset(
        set(
            PREPROCESSING_QUALITY_REQUIRED_FIELDS
        )
    )


def test_preprocessing_manifest_schema_is_exact():
    assert (
        PREPROCESSING_MANIFEST_REQUIRED_FIELDS
        == EXPECTED_MANIFEST_FIELDS
    )


def test_manifest_binds_stage24_and_stage25_provenance():
    required = {
        "source_artifact_hashes",
        "upstream_stage24_provenance_sha256",
        "preprocessing_config_sha256",
        "common_grid_sha256",
        "preprocessing_quality_sha256",
        "functional_commit",
    }

    assert required.issubset(
        set(
            PREPROCESSING_MANIFEST_REQUIRED_FIELDS
        )
    )


def test_sensor_family_vocabulary_is_exact():
    assert SENSOR_FAMILIES == (
        "ACCEL",
        "GYRO",
    )


def test_sensor_coverage_status_vocabulary_is_exact():
    assert SENSOR_COVERAGE_STATUSES == (
        "VALID",
        "NO_SOURCE",
        "GAP_EXCEEDED",
        "INVALID_SOURCE",
    )


def test_grid_row_status_vocabulary_is_exact():
    assert GRID_ROW_STATUSES == (
        "VALID",
        "INVALID_ACCEL",
        "INVALID_GYRO",
        "INVALID_BOTH",
    )


def test_build_status_vocabulary_is_exact():
    assert PREPROCESSING_BUILD_STATUSES == (
        "VALID",
        "TECHNICAL_INVALID",
    )


def test_duplicate_event_vocabulary_is_exact():
    assert DUPLICATE_EVENT_TYPES == (
        "DUPLICATE_SOURCE_IDENTITY",
        "DUPLICATE_NATIVE_TIMESTAMP",
        "DUPLICATE_MAPPED_TIMESTAMP",
    )


def test_gap_event_vocabulary_is_exact():
    assert GAP_EVENT_TYPES == (
        "BOUNDED_GAP",
        "EXCESSIVE_GAP",
    )


def test_reorder_event_vocabulary_is_exact():
    assert REORDER_EVENT_TYPES == (
        "REORDERED_MAPPED_TIMESTAMP",
    )


def test_stage24_mapped_schema_remains_unchanged():
    assert MAPPED_SENSOR_TIME_COLUMNS == (
        EXPECTED_STAGE24_MAPPED_COLUMNS
    )


def test_stage24_native_label_schema_remains_unchanged():
    assert NATIVE_LABEL_COLUMNS == (
        EXPECTED_STAGE24_LABEL_COLUMNS
    )