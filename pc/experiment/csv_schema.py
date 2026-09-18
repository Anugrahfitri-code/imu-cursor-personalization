TRIAL_EVENT_COLUMNS = (
    "event_id",
    "participant_id",
    "session_id",
    "condition_code",
    "block_id",
    "sequence_id",
    "trial_id",
    "event_type",
    "pc_time_ns",
    "target_id",
    "target_x_px",
    "target_y_px",
    "target_width_px",
    "target_height_px",
    "pointer_x_px",
    "pointer_y_px",
    "event_note",
)

CURSOR_SAMPLE_COLUMNS = (
    "sample_id",
    "participant_id",
    "session_id",
    "condition_code",
    "block_id",
    "sequence_id",
    "trial_id",
    "pc_time_ns",
    "cursor_x_px",
    "cursor_y_px",
    "active_target_id",
    "source_seq_start",
    "source_seq_end",
)

CALIBRATION_EVENT_COLUMNS = (
    "calibration_event_id",
    "participant_id",
    "session_id",
    "condition_code",
    "calibration_id",
    "step_id",
    "event_type",
    "pc_time_ns",
    "reference_target_id",
    "source_seq_start",
    "source_seq_end",
    "instruction_code",
    "event_note",
)

QUALITY_FLAG_COLUMNS = (
    "scope_type",
    "scope_id",
    "flag_code",
    "flag_value",
    "reason",
    "rule_version",
    "created_utc",
)

CSV_SCHEMAS = {
    "raw/trial_events.csv": TRIAL_EVENT_COLUMNS,
    "raw/cursor_samples.csv": CURSOR_SAMPLE_COLUMNS,
    "raw/calibration_events.csv": CALIBRATION_EVENT_COLUMNS,
    "derived/quality_flags.csv": QUALITY_FLAG_COLUMNS,
}


def validate_header(
    actual: list[str],
    expected: tuple[str, ...],
) -> list[str]:
    if tuple(actual) == expected:
        return []

    return [
        "CSV header mismatch: "
        f"expected={expected!r}, actual={tuple(actual)!r}"
    ]
