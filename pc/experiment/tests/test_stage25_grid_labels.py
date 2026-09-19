import pytest

from pc.experiment.preprocessing.labels import (
    attach_common_grid_reference_labels,
)


def _grid_row(
    grid_pc_time_ns,
    *,
    grid_index=0,
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    sensor_status="VALID",
    accel_status="VALID",
    gyro_status="VALID",
    extra_field="preserve-me",
):
    return {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "grid_index":
            grid_index,
        "grid_pc_time_ns":
            grid_pc_time_ns,
        "sensor_status":
            sensor_status,
        "accel_status":
            accel_status,
        "gyro_status":
            gyro_status,
        "extra_field":
            extra_field,
    }


def _reference_row(
    pc_time_ns,
    *,
    reference_sample_id="REF001",
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    cycle_index=0,
    sequence_id="SEQ001",
    segment_index=0,
    direction_code="RIGHT",
    phase="OUTBOUND",
    relative_time_ns=0,
    ref_x_px=0.0,
    ref_y_px=0.0,
    ref_vx_px_s=0.0,
    ref_vy_px_s=0.0,
    speed_profile_code="SYNTHETIC_TEST",
    pause_flag=0,
    trajectory_version="stage25-test-v1",
):
    return {
        "reference_sample_id":
            reference_sample_id,
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "cycle_index":
            cycle_index,
        "sequence_id":
            sequence_id,
        "segment_index":
            segment_index,
        "direction_code":
            direction_code,
        "phase":
            phase,
        "pc_time_ns":
            pc_time_ns,
        "relative_time_ns":
            relative_time_ns,
        "ref_x_px":
            ref_x_px,
        "ref_y_px":
            ref_y_px,
        "ref_vx_px_s":
            ref_vx_px_s,
        "ref_vy_px_s":
            ref_vy_px_s,
        "speed_profile_code":
            speed_profile_code,
        "pause_flag":
            pause_flag,
        "trajectory_version":
            trajectory_version,
    }


def _reference():
    return [
        _reference_row(
            100,
            reference_sample_id="REF001",
            relative_time_ns=0,
            ref_x_px=0.0,
            ref_y_px=10.0,
            ref_vx_px_s=20.0,
            ref_vy_px_s=30.0,
        ),
        _reference_row(
            200,
            reference_sample_id="REF002",
            relative_time_ns=100,
            ref_x_px=100.0,
            ref_y_px=110.0,
            ref_vx_px_s=120.0,
            ref_vy_px_s=130.0,
        ),
    ]


def _attach(
    grid_rows,
    *,
    reference_trajectory=None,
    alignment_lag_ns=0,
):
    if reference_trajectory is None:
        reference_trajectory = _reference()

    return attach_common_grid_reference_labels(
        common_grid_rows=grid_rows,
        reference_trajectory=reference_trajectory,
        alignment_lag_ns=alignment_lag_ns,
    )


def test_positive_lag_uses_grid_time_minus_tau():
    rows = _attach(
        [
            _grid_row(160)
        ],
        alignment_lag_ns=10,
    )

    row = rows[0]

    assert row["grid_label_pc_time_ns"] == 150
    assert row["label_status"] == "VALID"

    assert row["ref_x_px"] == pytest.approx(
        50.0
    )


def test_zero_lag_uses_grid_timestamp_directly():
    rows = _attach(
        [
            _grid_row(150)
        ],
        alignment_lag_ns=0,
    )

    row = rows[0]

    assert row["grid_label_pc_time_ns"] == 150
    assert row["label_status"] == "VALID"


def test_negative_lag_queries_later_reference_time():
    rows = _attach(
        [
            _grid_row(140)
        ],
        alignment_lag_ns=-10,
    )

    row = rows[0]

    assert row["grid_label_pc_time_ns"] == 150
    assert row["label_status"] == "VALID"


def test_reference_interpolation_preserves_velocity_target():
    rows = _attach(
        [
            _grid_row(150)
        ]
    )

    row = rows[0]

    assert row["ref_x_px"] == pytest.approx(
        50.0
    )

    assert row["ref_y_px"] == pytest.approx(
        60.0
    )

    assert row["ref_vx_px_s"] == pytest.approx(
        70.0
    )

    assert row["ref_vy_px_s"] == pytest.approx(
        80.0
    )

    assert row["sequence_id"] == "SEQ001"
    assert row["direction_code"] == "RIGHT"
    assert row["phase"] == "OUTBOUND"


def test_pre_start_label_is_outside_reference():
    rows = _attach(
        [
            _grid_row(90)
        ]
    )

    row = rows[0]

    assert (
        row["label_status"]
        == "OUTSIDE_REFERENCE"
    )

    assert row["ref_x_px"] is None
    assert row["ref_vx_px_s"] is None


def test_post_end_label_is_outside_reference():
    rows = _attach(
        [
            _grid_row(210)
        ]
    )

    row = rows[0]

    assert (
        row["label_status"]
        == "OUTSIDE_REFERENCE"
    )

    assert row["ref_y_px"] is None
    assert row["ref_vy_px_s"] is None


def test_lookup_does_not_bridge_phase_boundary():
    reference = [
        _reference_row(
            100,
            reference_sample_id="REF001",
            phase="OUTBOUND",
            ref_x_px=0.0,
        ),
        _reference_row(
            200,
            reference_sample_id="REF002",
            phase="TARGET_HOLD",
            ref_x_px=100.0,
        ),
    ]

    rows = _attach(
        [
            _grid_row(150)
        ],
        reference_trajectory=reference,
    )

    row = rows[0]

    assert (
        row["label_status"]
        == "UNRESOLVED_BOUNDARY"
    )

    assert row["ref_x_px"] is None
    assert row["phase"] is None


def test_lookup_does_not_bridge_direction_boundary():
    reference = [
        _reference_row(
            100,
            reference_sample_id="REF001",
            direction_code="RIGHT",
            ref_x_px=0.0,
        ),
        _reference_row(
            200,
            reference_sample_id="REF002",
            direction_code="UP_RIGHT",
            ref_x_px=100.0,
        ),
    ]

    rows = _attach(
        [
            _grid_row(150)
        ],
        reference_trajectory=reference,
    )

    row = rows[0]

    assert (
        row["label_status"]
        == "UNRESOLVED_BOUNDARY"
    )

    assert row["direction_code"] is None


def test_invalid_label_does_not_change_valid_sensor_status():
    rows = _attach(
        [
            _grid_row(
                90,
                sensor_status="VALID",
                accel_status="VALID",
                gyro_status="VALID",
            )
        ]
    )

    row = rows[0]

    assert (
        row["label_status"]
        == "OUTSIDE_REFERENCE"
    )

    assert row["sensor_status"] == "VALID"
    assert row["accel_status"] == "VALID"
    assert row["gyro_status"] == "VALID"


def test_invalid_sensor_row_can_still_have_valid_reference_label():
    rows = _attach(
        [
            _grid_row(
                150,
                sensor_status="INVALID_ACCEL",
                accel_status="GAP_EXCEEDED",
                gyro_status="VALID",
            )
        ]
    )

    row = rows[0]

    assert row["label_status"] == "VALID"

    assert (
        row["sensor_status"]
        == "INVALID_ACCEL"
    )

    assert (
        row["accel_status"]
        == "GAP_EXCEEDED"
    )

    assert row["gyro_status"] == "VALID"


def test_existing_grid_provenance_is_preserved():
    rows = _attach(
        [
            _grid_row(
                150,
                grid_index=123,
                extra_field="audit-value",
            )
        ]
    )

    row = rows[0]

    assert row["grid_index"] == 123
    assert row["grid_pc_time_ns"] == 150

    assert (
        row["extra_field"]
        == "audit-value"
    )


def test_input_common_grid_is_not_mutated():
    grid_rows = [
        _grid_row(
            150,
            grid_index=7,
        )
    ]

    original = [
        dict(row)
        for row in grid_rows
    ]

    _attach(
        grid_rows
    )

    assert grid_rows == original


def test_mixed_common_grid_identity_fails_closed():
    with pytest.raises(
        ValueError,
        match="participant",
    ):
        _attach(
            [
                _grid_row(
                    140,
                    participant_id="PTEST001",
                ),
                _grid_row(
                    150,
                    participant_id="OTHER",
                ),
            ]
        )


def test_reference_identity_mismatch_fails_closed():
    reference = [
        _reference_row(
            100,
            reference_sample_id="REF001",
            calibration_id="OTHER",
        ),
        _reference_row(
            200,
            reference_sample_id="REF002",
            calibration_id="OTHER",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="calibration",
    ):
        _attach(
            [
                _grid_row(150)
            ],
            reference_trajectory=reference,
        )


def test_common_grid_label_output_is_deterministic():
    grid_rows = [
        _grid_row(
            125,
            grid_index=1,
        ),
        _grid_row(
            150,
            grid_index=2,
        ),
        _grid_row(
            175,
            grid_index=3,
        ),
    ]

    first = _attach(
        grid_rows,
        alignment_lag_ns=5,
    )

    second = _attach(
        grid_rows,
        alignment_lag_ns=5,
    )

    assert first == second