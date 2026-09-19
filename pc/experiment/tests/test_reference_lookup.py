from copy import deepcopy

import math

from pc.experiment.calibration.trajectory import (
    generate_guided_2c,
)
from pc.experiment.labels.reference_lookup import (
    lookup_reference_state,
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


def _trajectory():
    return generate_guided_2c(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        start_pc_time_ns=START_PC_TIME_NS,
        config=SYNTHETIC_CONFIG,
    )


def _rows_for_sequence(
    rows,
    sequence_id,
):
    return [
        row
        for row in rows
        if row["sequence_id"] == sequence_id
    ]


def _first_sequence(rows):
    sequence_id = rows[0]["sequence_id"]

    return _rows_for_sequence(
        rows,
        sequence_id,
    )


def test_exact_timestamp_match_is_preferred():
    rows = _trajectory()

    source = next(
        row
        for row in rows
        if row["phase"] == "OUTBOUND"
    )

    result = lookup_reference_state(
        rows,
        source["pc_time_ns"],
    )

    assert result["label_status"] == "VALID"

    assert result["ref_x_px"] == (
        source["ref_x_px"]
    )

    assert result["ref_y_px"] == (
        source["ref_y_px"]
    )

    assert result["ref_vx_px_s"] == (
        source["ref_vx_px_s"]
    )

    assert result["ref_vy_px_s"] == (
        source["ref_vy_px_s"]
    )

    assert result["direction_code"] == (
        source["direction_code"]
    )

    assert result["phase"] == source["phase"]

    assert result["sequence_id"] == (
        source["sequence_id"]
    )


def test_valid_same_segment_interpolation_succeeds():
    rows = _trajectory()

    outbound = [
        row
        for row in _first_sequence(rows)
        if row["phase"] == "OUTBOUND"
    ]

    left = outbound[0]
    right = outbound[1]

    query_time = (
        left["pc_time_ns"]
        +
        (
            right["pc_time_ns"]
            - left["pc_time_ns"]
        ) // 2
    )

    result = lookup_reference_state(
        rows,
        query_time,
    )

    assert result["label_status"] == "VALID"

    expected_x = (
        left["ref_x_px"]
        + right["ref_x_px"]
    ) / 2.0

    expected_y = (
        left["ref_y_px"]
        + right["ref_y_px"]
    ) / 2.0

    assert math.isclose(
        result["ref_x_px"],
        expected_x,
        rel_tol=0.0,
        abs_tol=1e-9,
    )

    assert math.isclose(
        result["ref_y_px"],
        expected_y,
        rel_tol=0.0,
        abs_tol=1e-9,
    )

    assert result["sequence_id"] == (
        left["sequence_id"]
    )

    assert result["direction_code"] == (
        left["direction_code"]
    )

    assert result["phase"] == "OUTBOUND"


def test_interpolated_velocity_is_linear():
    rows = _trajectory()

    outbound = [
        row
        for row in _first_sequence(rows)
        if row["phase"] == "OUTBOUND"
    ]

    left = outbound[0]
    right = outbound[1]

    query_time = (
        left["pc_time_ns"]
        +
        (
            right["pc_time_ns"]
            - left["pc_time_ns"]
        ) // 2
    )

    result = lookup_reference_state(
        rows,
        query_time,
    )

    expected_vx = (
        left["ref_vx_px_s"]
        + right["ref_vx_px_s"]
    ) / 2.0

    expected_vy = (
        left["ref_vy_px_s"]
        + right["ref_vy_px_s"]
    ) / 2.0

    assert math.isclose(
        result["ref_vx_px_s"],
        expected_vx,
        rel_tol=0.0,
        abs_tol=1e-9,
    )

    assert math.isclose(
        result["ref_vy_px_s"],
        expected_vy,
        rel_tol=0.0,
        abs_tol=1e-9,
    )


def test_lookup_does_not_cross_phase_boundary():
    rows = _trajectory()

    sequence_rows = _first_sequence(rows)

    center_last = [
        row
        for row in sequence_rows
        if row["phase"] == "CENTER_HOLD"
    ][-1]

    outbound_first = [
        row
        for row in sequence_rows
        if row["phase"] == "OUTBOUND"
    ][0]

    query_time = (
        center_last["pc_time_ns"]
        +
        (
            outbound_first["pc_time_ns"]
            - center_last["pc_time_ns"]
        ) // 2
    )

    result = lookup_reference_state(
        rows,
        query_time,
    )

    assert (
        result["label_status"]
        == "UNRESOLVED_BOUNDARY"
    )


def test_lookup_does_not_cross_sequence_boundary():
    rows = _trajectory()

    first_sequence_id = rows[0][
        "sequence_id"
    ]

    first_sequence = _rows_for_sequence(
        rows,
        first_sequence_id,
    )

    first_end_index = rows.index(
        first_sequence[-1]
    )

    left = rows[first_end_index]
    right = rows[first_end_index + 1]

    assert (
        left["sequence_id"]
        != right["sequence_id"]
    )

    query_time = (
        left["pc_time_ns"]
        +
        (
            right["pc_time_ns"]
            - left["pc_time_ns"]
        ) // 2
    )

    result = lookup_reference_state(
        rows,
        query_time,
    )

    assert (
        result["label_status"]
        == "UNRESOLVED_BOUNDARY"
    )


def test_lookup_does_not_cross_direction_boundary():
    rows = _trajectory()

    first_sequence = _first_sequence(rows)
    left = first_sequence[0]
    right = first_sequence[1]

    mutated = deepcopy(rows)

    left_index = rows.index(left)
    right_index = rows.index(right)

    mutated[left_index][
        "direction_code"
    ] = "RIGHT"

    mutated[right_index][
        "direction_code"
    ] = "UP"

    query_time = (
        mutated[left_index]["pc_time_ns"]
        +
        (
            mutated[right_index]["pc_time_ns"]
            - mutated[left_index]["pc_time_ns"]
        ) // 2
    )

    result = lookup_reference_state(
        mutated,
        query_time,
    )

    assert (
        result["label_status"]
        == "UNRESOLVED_BOUNDARY"
    )


def test_lookup_does_not_cross_segment_boundary():
    rows = _trajectory()

    first_sequence = _first_sequence(rows)

    left = first_sequence[0]
    right = first_sequence[1]

    mutated = deepcopy(rows)

    left_index = rows.index(left)
    right_index = rows.index(right)

    mutated[left_index][
        "segment_index"
    ] = 100

    mutated[right_index][
        "segment_index"
    ] = 101

    query_time = (
        mutated[left_index]["pc_time_ns"]
        +
        (
            mutated[right_index]["pc_time_ns"]
            - mutated[left_index]["pc_time_ns"]
        ) // 2
    )

    result = lookup_reference_state(
        mutated,
        query_time,
    )

    assert (
        result["label_status"]
        == "UNRESOLVED_BOUNDARY"
    )


def test_pre_start_query_is_outside_reference():
    rows = _trajectory()

    result = lookup_reference_state(
        rows,
        rows[0]["pc_time_ns"] - 1,
    )

    assert (
        result["label_status"]
        == "OUTSIDE_REFERENCE"
    )


def test_post_end_query_is_outside_reference():
    rows = _trajectory()

    result = lookup_reference_state(
        rows,
        rows[-1]["pc_time_ns"] + 1,
    )

    assert (
        result["label_status"]
        == "OUTSIDE_REFERENCE"
    )


def test_outside_reference_has_no_reference_state():
    rows = _trajectory()

    result = lookup_reference_state(
        rows,
        rows[0]["pc_time_ns"] - 1,
    )

    assert result["ref_x_px"] is None
    assert result["ref_y_px"] is None
    assert result["ref_vx_px_s"] is None
    assert result["ref_vy_px_s"] is None
    assert result["direction_code"] is None
    assert result["phase"] is None
    assert result["sequence_id"] is None


def test_mixed_participant_identity_fails_closed():
    rows = _trajectory()

    mutated = deepcopy(rows)

    mutated[-1]["participant_id"] = "OTHER"

    try:
        lookup_reference_state(
            mutated,
            mutated[10]["pc_time_ns"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Mixed participant identity "
            "must raise ValueError."
        )


def test_mixed_session_identity_fails_closed():
    rows = _trajectory()

    mutated = deepcopy(rows)

    mutated[-1]["session_id"] = "OTHER"

    try:
        lookup_reference_state(
            mutated,
            mutated[10]["pc_time_ns"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Mixed session identity "
            "must raise ValueError."
        )


def test_mixed_calibration_identity_fails_closed():
    rows = _trajectory()

    mutated = deepcopy(rows)

    mutated[-1]["calibration_id"] = "OTHER"

    try:
        lookup_reference_state(
            mutated,
            mutated[10]["pc_time_ns"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Mixed calibration identity "
            "must raise ValueError."
        )


def test_lookup_is_deterministic():
    rows = _trajectory()

    outbound = [
        row
        for row in _first_sequence(rows)
        if row["phase"] == "OUTBOUND"
    ]

    query_time = (
        outbound[0]["pc_time_ns"]
        +
        (
            outbound[1]["pc_time_ns"]
            - outbound[0]["pc_time_ns"]
        ) // 2
    )

    first = lookup_reference_state(
        rows,
        query_time,
    )

    second = lookup_reference_state(
        rows,
        query_time,
    )

    assert first == second