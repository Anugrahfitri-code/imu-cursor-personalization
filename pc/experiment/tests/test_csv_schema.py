from pc.experiment.csv_schema import (
    CALIBRATION_EVENT_COLUMNS,
    CURSOR_SAMPLE_COLUMNS,
    QUALITY_FLAG_COLUMNS,
    TRIAL_EVENT_COLUMNS,
    validate_header,
)


def test_trial_event_columns_are_exact():
    assert TRIAL_EVENT_COLUMNS == (
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


def test_cursor_sample_columns_are_exact():
    assert CURSOR_SAMPLE_COLUMNS == (
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


def test_calibration_event_columns_are_exact():
    assert CALIBRATION_EVENT_COLUMNS == (
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


def test_quality_flag_columns_are_exact():
    assert QUALITY_FLAG_COLUMNS == (
        "scope_type",
        "scope_id",
        "flag_code",
        "flag_value",
        "reason",
        "rule_version",
        "created_utc",
    )


def test_header_validation_accepts_exact_header():
    assert validate_header(
        list(TRIAL_EVENT_COLUMNS),
        TRIAL_EVENT_COLUMNS,
    ) == []


def test_header_validation_rejects_missing_column():
    actual = list(TRIAL_EVENT_COLUMNS[:-1])

    errors = validate_header(
        actual,
        TRIAL_EVENT_COLUMNS,
    )

    assert errors
