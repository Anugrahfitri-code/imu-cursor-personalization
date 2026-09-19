import math

from pc.experiment.calibration.schema import (
    DIRECTION_CODES,
    PAUSE_FLAG_BY_PHASE,
    PHASE_CODES,
    REFERENCE_TRAJECTORY_COLUMNS,
)
from pc.experiment.calibration.trajectory import (
    generate_guided_2c,
)


# Synthetic engineering configuration only.
# These numeric values are NOT final participant-study parameters.
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


DIRECTION_VECTORS = {
    "RIGHT": (1.0, 0.0),
    "UP_RIGHT": (
        1.0 / math.sqrt(2.0),
        -1.0 / math.sqrt(2.0),
    ),
    "UP": (0.0, -1.0),
    "UP_LEFT": (
        -1.0 / math.sqrt(2.0),
        -1.0 / math.sqrt(2.0),
    ),
    "LEFT": (-1.0, 0.0),
    "DOWN_LEFT": (
        -1.0 / math.sqrt(2.0),
        1.0 / math.sqrt(2.0),
    ),
    "DOWN": (0.0, 1.0),
    "DOWN_RIGHT": (
        1.0 / math.sqrt(2.0),
        1.0 / math.sqrt(2.0),
    ),
}


def _generate():
    return generate_guided_2c(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        start_pc_time_ns=START_PC_TIME_NS,
        config=SYNTHETIC_CONFIG,
    )


def _ordered_sequence_groups(rows):
    order = []
    groups = {}

    for row in rows:
        sequence_id = row["sequence_id"]

        if sequence_id not in groups:
            groups[sequence_id] = []
            order.append(sequence_id)

        groups[sequence_id].append(row)

    return [
        (sequence_id, groups[sequence_id])
        for sequence_id in order
    ]


def _collapsed_phases(rows):
    phases = []

    for row in rows:
        phase = row["phase"]

        if not phases or phases[-1] != phase:
            phases.append(phase)

    return phases


def test_generated_rows_follow_reference_schema():
    rows = _generate()

    assert rows

    for row in rows:
        assert tuple(row.keys()) == (
            REFERENCE_TRAJECTORY_COLUMNS
        )


def test_two_cycles_are_generated_exactly():
    rows = _generate()

    assert {
        row["cycle_index"]
        for row in rows
    } == {1, 2}


def test_each_cycle_contains_eight_sequences():
    rows = _generate()
    groups = _ordered_sequence_groups(rows)

    cycle_1 = [
        sequence_id
        for sequence_id, sequence_rows in groups
        if sequence_rows[0]["cycle_index"] == 1
    ]

    cycle_2 = [
        sequence_id
        for sequence_id, sequence_rows in groups
        if sequence_rows[0]["cycle_index"] == 2
    ]

    assert len(cycle_1) == 8
    assert len(cycle_2) == 8
    assert len(groups) == 16


def test_direction_order_is_exact():
    rows = _generate()
    groups = _ordered_sequence_groups(rows)

    actual = [
        sequence_rows[0]["direction_code"]
        for _, sequence_rows in groups
    ]

    assert actual == list(DIRECTION_CODES) * 2


def test_phase_order_is_exact_per_sequence():
    rows = _generate()

    for _, sequence_rows in _ordered_sequence_groups(
        rows
    ):
        assert _collapsed_phases(sequence_rows) == list(
            PHASE_CODES
        )


def test_each_sequence_starts_and_returns_to_center():
    rows = _generate()

    center = (
        SYNTHETIC_CONFIG["center_x_px"],
        SYNTHETIC_CONFIG["center_y_px"],
    )

    for _, sequence_rows in _ordered_sequence_groups(
        rows
    ):
        first = sequence_rows[0]
        last = sequence_rows[-1]

        assert (
            first["ref_x_px"],
            first["ref_y_px"],
        ) == center

        assert (
            last["ref_x_px"],
            last["ref_y_px"],
        ) == center


def test_target_positions_follow_direction_vectors():
    rows = _generate()

    center_x = SYNTHETIC_CONFIG["center_x_px"]
    center_y = SYNTHETIC_CONFIG["center_y_px"]
    radius = SYNTHETIC_CONFIG["radius_px"]

    for _, sequence_rows in _ordered_sequence_groups(
        rows
    ):
        direction = sequence_rows[0][
            "direction_code"
        ]

        target_rows = [
            row
            for row in sequence_rows
            if row["phase"] == "TARGET_HOLD"
        ]

        assert target_rows

        dx, dy = DIRECTION_VECTORS[direction]

        expected_x = center_x + radius * dx
        expected_y = center_y + radius * dy

        for row in target_rows:
            assert math.isclose(
                row["ref_x_px"],
                expected_x,
                rel_tol=0.0,
                abs_tol=1e-9,
            )

            assert math.isclose(
                row["ref_y_px"],
                expected_y,
                rel_tol=0.0,
                abs_tol=1e-9,
            )


def test_relative_trajectory_is_deterministic():
    first = _generate()
    second = _generate()

    assert first == second


def test_reference_timestamps_do_not_decrease():
    rows = _generate()

    pc_times = [
        row["pc_time_ns"]
        for row in rows
    ]

    relative_times = [
        row["relative_time_ns"]
        for row in rows
    ]

    assert pc_times == sorted(pc_times)
    assert relative_times == sorted(relative_times)


def test_reference_sample_ids_are_unique():
    rows = _generate()

    reference_ids = [
        row["reference_sample_id"]
        for row in rows
    ]

    assert len(reference_ids) == len(
        set(reference_ids)
    )


def test_sequence_ids_are_unique_and_deterministic():
    first = _generate()
    second = _generate()

    first_ids = [
        sequence_id
        for sequence_id, _ in
        _ordered_sequence_groups(first)
    ]

    second_ids = [
        sequence_id
        for sequence_id, _ in
        _ordered_sequence_groups(second)
    ]

    assert len(first_ids) == 16
    assert len(set(first_ids)) == 16
    assert first_ids == second_ids


def test_hold_velocity_is_zero():
    rows = _generate()

    for row in rows:
        if row["phase"] in {
            "CENTER_HOLD",
            "TARGET_HOLD",
        }:
            assert row["ref_vx_px_s"] == 0.0
            assert row["ref_vy_px_s"] == 0.0


def test_pause_flag_matches_phase():
    rows = _generate()

    for row in rows:
        assert row["pause_flag"] == (
            PAUSE_FLAG_BY_PHASE[row["phase"]]
        )


def test_direction_codes_are_valid():
    rows = _generate()

    for row in rows:
        assert row["direction_code"] in (
            DIRECTION_CODES
        )


def test_phase_codes_are_valid():
    rows = _generate()

    for row in rows:
        assert row["phase"] in PHASE_CODES