REFERENCE_TRAJECTORY_COLUMNS = (
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


DIRECTION_CODES = (
    "RIGHT",
    "UP_RIGHT",
    "UP",
    "UP_LEFT",
    "LEFT",
    "DOWN_LEFT",
    "DOWN",
    "DOWN_RIGHT",
)


PHASE_CODES = (
    "CENTER_HOLD",
    "OUTBOUND",
    "TARGET_HOLD",
    "RETURN",
)


PAUSE_FLAG_BY_PHASE = {
    "CENTER_HOLD": 1,
    "TARGET_HOLD": 1,
    "OUTBOUND": 0,
    "RETURN": 0,
}


CALIBRATION_MANIFEST_REQUIRED_FIELDS = (
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