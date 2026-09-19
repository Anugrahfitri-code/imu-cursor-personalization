from copy import deepcopy

from pc.experiment.calibration.trajectory import (
    generate_guided_2c,
)
from pc.experiment.calibration.validator import (
    validate_reference_trajectory,
)


SYNTHETIC_CONFIG = {
    "center_x_px": 960.0,
    "center_y_px": 540.0,
    "radius_px": 120.0,
    "center_hold_ns": 20_000_000,
    "outbound_ns": 40_000_000,
    "target_hold_ns": 20_000_000,
    "return_ns": 40_000_000,
    "sample_interval_ns": 10_000_000,
    "speed_profile_code": "SYNTHETIC_LINEAR_V1",
    "trajectory_version": "stage2.3-test-v1",
}

START_PC_TIME_NS = 1_000_000_000_000


def _valid_rows():
    return generate_guided_2c(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        start_pc_time_ns=START_PC_TIME_NS,
        config=SYNTHETIC_CONFIG,
    )


def _has_error(errors, code):
    return any(
        error == code
        or error.startswith(f"{code}:")
        for error in errors
    )


def _first_sequence_id(rows):
    return rows[0]["sequence_id"]


def _sequence_rows(rows, sequence_id):
    return [
        row
        for row in rows
        if row["sequence_id"] == sequence_id
    ]


def test_valid_reference_trajectory_passes():
    errors = validate_reference_trajectory(
        _valid_rows()
    )

    assert errors == []


def test_missing_required_column_fails():
    rows = deepcopy(_valid_rows())

    del rows[0]["phase"]

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "MISSING_REQUIRED_COLUMN",
    )


def test_duplicate_reference_sample_id_fails():
    rows = deepcopy(_valid_rows())

    rows[1]["reference_sample_id"] = (
        rows[0]["reference_sample_id"]
    )

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "DUPLICATE_REFERENCE_SAMPLE_ID",
    )


def test_invalid_cycle_index_fails():
    rows = deepcopy(_valid_rows())

    rows[0]["cycle_index"] = 3

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "INVALID_CYCLE_INDEX",
    )


def test_wrong_cycle_count_fails():
    rows = [
        row
        for row in deepcopy(_valid_rows())
        if row["cycle_index"] == 1
    ]

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "INVALID_CYCLE_COUNT",
    )


def test_invalid_direction_code_fails():
    rows = deepcopy(_valid_rows())

    rows[0]["direction_code"] = "INVALID"

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "INVALID_DIRECTION_CODE",
    )


def test_wrong_direction_order_fails():
    rows = deepcopy(_valid_rows())

    sequence_id = _first_sequence_id(rows)

    for row in _sequence_rows(
        rows,
        sequence_id,
    ):
        row["direction_code"] = "UP_RIGHT"

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "DIRECTION_ORDER_MISMATCH",
    )


def test_invalid_phase_fails():
    rows = deepcopy(_valid_rows())

    rows[0]["phase"] = "INVALID"

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "INVALID_PHASE",
    )


def test_wrong_phase_order_fails():
    rows = deepcopy(_valid_rows())

    sequence_id = _first_sequence_id(rows)

    for row in _sequence_rows(
        rows,
        sequence_id,
    ):
        if row["phase"] == "OUTBOUND":
            row["phase"] = "RETURN"

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "PHASE_ORDER_MISMATCH",
    )


def test_invalid_pause_flag_fails():
    rows = deepcopy(_valid_rows())

    center_hold = next(
        row
        for row in rows
        if row["phase"] == "CENTER_HOLD"
    )

    center_hold["pause_flag"] = 0

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "INVALID_PAUSE_FLAG",
    )


def test_invalid_hold_velocity_fails():
    rows = deepcopy(_valid_rows())

    center_hold = next(
        row
        for row in rows
        if row["phase"] == "CENTER_HOLD"
    )

    center_hold["ref_vx_px_s"] = 1.0

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "INVALID_HOLD_VELOCITY",
    )


def test_decreasing_pc_time_fails():
    rows = deepcopy(_valid_rows())

    rows[1]["pc_time_ns"] = (
        rows[0]["pc_time_ns"] - 1
    )

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "DECREASING_PC_TIME",
    )


def test_decreasing_relative_time_fails():
    rows = deepcopy(_valid_rows())

    rows[1]["relative_time_ns"] = (
        rows[0]["relative_time_ns"] - 1
    )

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "DECREASING_RELATIVE_TIME",
    )


def test_missing_return_to_center_fails():
    rows = deepcopy(_valid_rows())

    sequence_id = _first_sequence_id(rows)

    sequence_rows = _sequence_rows(
        rows,
        sequence_id,
    )

    last = sequence_rows[-1]

    last["ref_x_px"] += 1.0

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "MISSING_RETURN_TO_CENTER",
    )


def test_mixed_participant_identity_fails():
    rows = deepcopy(_valid_rows())

    rows[-1]["participant_id"] = "OTHER"

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "PARTICIPANT_ID_MISMATCH",
    )


def test_mixed_session_identity_fails():
    rows = deepcopy(_valid_rows())

    rows[-1]["session_id"] = "OTHER"

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "SESSION_ID_MISMATCH",
    )


def test_mixed_calibration_identity_fails():
    rows = deepcopy(_valid_rows())

    rows[-1]["calibration_id"] = "OTHER"

    errors = validate_reference_trajectory(rows)

    assert _has_error(
        errors,
        "CALIBRATION_ID_MISMATCH",
    )