MAPPED_SENSOR_TIME_COLUMNS = (
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


MAPPING_STATUSES = frozenset(
    {
        "MAPPED",
        "INVALID_SOURCE_TIMESTAMP",
    }
)


NATIVE_LABEL_COLUMNS = (
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


LABEL_STATUSES = frozenset(
    {
        "VALID",
        "OUTSIDE_REFERENCE",
        "UNRESOLVED_BOUNDARY",
    }
)


LABEL_CONFIG_REQUIRED_FIELDS = (
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


LABEL_MANIFEST_REQUIRED_FIELDS = (
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


LABEL_BUILD_STATUSES = frozenset(
    {
        "VALID",
        "TECHNICAL_INVALID",
    }
)