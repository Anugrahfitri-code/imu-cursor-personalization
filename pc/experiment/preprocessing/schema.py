PREPROCESSING_SCHEMA_VERSION = "1.0"


COMMON_GRID_COLUMNS = (
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


PREPROCESSING_CONFIG_REQUIRED_FIELDS = (
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


PREPROCESSING_QUALITY_REQUIRED_FIELDS = (
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


PREPROCESSING_MANIFEST_REQUIRED_FIELDS = (
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


SENSOR_FAMILIES = (
    "ACCEL",
    "GYRO",
)


SENSOR_COVERAGE_STATUSES = (
    "VALID",
    "NO_SOURCE",
    "GAP_EXCEEDED",
    "INVALID_SOURCE",
)


GRID_ROW_STATUSES = (
    "VALID",
    "INVALID_ACCEL",
    "INVALID_GYRO",
    "INVALID_BOTH",
)


PREPROCESSING_BUILD_STATUSES = (
    "VALID",
    "TECHNICAL_INVALID",
)


DUPLICATE_EVENT_TYPES = (
    "DUPLICATE_SOURCE_IDENTITY",
    "DUPLICATE_NATIVE_TIMESTAMP",
    "DUPLICATE_MAPPED_TIMESTAMP",
)


GAP_EVENT_TYPES = (
    "BOUNDED_GAP",
    "EXCESSIVE_GAP",
)


REORDER_EVENT_TYPES = (
    "REORDERED_MAPPED_TIMESTAMP",
)