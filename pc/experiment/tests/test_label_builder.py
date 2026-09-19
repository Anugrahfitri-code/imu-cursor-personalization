import pytest

from pc.experiment.labels.schema import (
    NATIVE_LABEL_COLUMNS,
)
from pc.experiment.labels.label_builder import (
    build_native_labels,
)


def _reference_rows():
    """
    Simple synthetic reference trajectory.

    All rows intentionally belong to the same lookup
    domain so exact lookup and interpolation can be tested
    independently from Stage 2.5 preprocessing.
    """
    return [
        {
            "participant_id": "PTEST001",
            "session_id": "STEST001",
            "calibration_id": "CAL2C001",
            "sequence_id": "C01_D01",
            "segment_index": 2,
            "direction_code": "RIGHT",
            "phase": "OUTBOUND",
            "pc_time_ns": 100,
            "ref_x_px": 10.0,
            "ref_y_px": 20.0,
            "ref_vx_px_s": 1.0,
            "ref_vy_px_s": 2.0,
        },
        {
            "participant_id": "PTEST001",
            "session_id": "STEST001",
            "calibration_id": "CAL2C001",
            "sequence_id": "C01_D01",
            "segment_index": 2,
            "direction_code": "RIGHT",
            "phase": "OUTBOUND",
            "pc_time_ns": 200,
            "ref_x_px": 20.0,
            "ref_y_px": 40.0,
            "ref_vx_px_s": 10.0,
            "ref_vy_px_s": 20.0,
        },
        {
            "participant_id": "PTEST001",
            "session_id": "STEST001",
            "calibration_id": "CAL2C001",
            "sequence_id": "C01_D01",
            "segment_index": 2,
            "direction_code": "RIGHT",
            "phase": "OUTBOUND",
            "pc_time_ns": 300,
            "ref_x_px": 30.0,
            "ref_y_px": 60.0,
            "ref_vx_px_s": 100.0,
            "ref_vy_px_s": 200.0,
        },
    ]


def _mapped_row(
    *,
    mapped_record_id="MAP000001",
    source_row_index=10,
    phone_sensor_ts_ns=1_000,
    pc_mapped_ts_ns=300,
    mapping_status="MAPPED",
):
    return {
        "mapped_record_id":
            mapped_record_id,
        "participant_id":
            "PTEST001",
        "session_id":
            "STEST001",
        "calibration_id":
            "CAL2C001",
        "source_file":
            "raw/imu/imu.csv",
        "source_row_index":
            source_row_index,
        "phone_sensor_ts_ns":
            phone_sensor_ts_ns,
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
        "clock_model_sha256":
            "A" * 64,
        "mapping_status":
            mapping_status,
        "derivation_version":
            "mapping-test-v1",
    }


def _build(
    mapped_rows,
    *,
    alignment_lag_ns,
    reference_rows=None,
):
    if reference_rows is None:
        reference_rows = _reference_rows()

    return build_native_labels(
        mapped_sensor_times=mapped_rows,
        reference_trajectory=reference_rows,
        alignment_lag_ns=alignment_lag_ns,
        derivation_version="labels-test-v1",
    )


def test_native_label_rows_follow_exact_schema():
    rows = _build(
        [_mapped_row()],
        alignment_lag_ns=100,
    )

    assert len(rows) == 1

    assert tuple(rows[0].keys()) == (
        NATIVE_LABEL_COLUMNS
    )


def test_positive_lag_uses_t_mapped_minus_tau():
    rows = _build(
        [
            _mapped_row(
                pc_mapped_ts_ns=300
            )
        ],
        alignment_lag_ns=100,
    )

    row = rows[0]

    assert row["label_pc_time_ns"] == 200
    assert row["label_status"] == "VALID"

    # Reference target at t=200.
    assert row["ref_vx_px_s"] == 10.0
    assert row["ref_vy_px_s"] == 20.0


def test_wrong_sign_would_not_recover_expected_target():
    """
    Explicit sign-control fixture.

    Correct:
        300 - 100 = 200

    Incorrect:
        300 + 100 = 400

    t=400 is outside the reference trajectory.
    """
    rows = _build(
        [
            _mapped_row(
                pc_mapped_ts_ns=300
            )
        ],
        alignment_lag_ns=100,
    )

    row = rows[0]

    assert row["label_pc_time_ns"] == 200

    assert (
        row["label_pc_time_ns"]
        != 400
    )

    assert row["ref_vx_px_s"] == 10.0


def test_zero_lag_uses_mapped_time():
    rows = _build(
        [
            _mapped_row(
                pc_mapped_ts_ns=300
            )
        ],
        alignment_lag_ns=0,
    )

    row = rows[0]

    assert row["label_pc_time_ns"] == 300
    assert row["label_status"] == "VALID"
    assert row["ref_vx_px_s"] == 100.0
    assert row["ref_vy_px_s"] == 200.0


def test_pre_start_label_is_outside_reference():
    rows = _build(
        [
            _mapped_row(
                pc_mapped_ts_ns=150
            )
        ],
        alignment_lag_ns=100,
    )

    row = rows[0]

    assert row["label_pc_time_ns"] == 50

    assert (
        row["label_status"]
        == "OUTSIDE_REFERENCE"
    )

    assert row["ref_vx_px_s"] is None
    assert row["ref_vy_px_s"] is None


def test_post_end_label_is_outside_reference():
    rows = _build(
        [
            _mapped_row(
                pc_mapped_ts_ns=450
            )
        ],
        alignment_lag_ns=100,
    )

    row = rows[0]

    assert row["label_pc_time_ns"] == 350

    assert (
        row["label_status"]
        == "OUTSIDE_REFERENCE"
    )


def test_interpolated_reference_velocity_is_target():
    rows = _build(
        [
            _mapped_row(
                pc_mapped_ts_ns=250
            )
        ],
        alignment_lag_ns=100,
    )

    row = rows[0]

    # Query t=150, halfway between t=100 and t=200.
    assert row["label_pc_time_ns"] == 150
    assert row["label_status"] == "VALID"

    assert row["ref_vx_px_s"] == 5.5
    assert row["ref_vy_px_s"] == 11.0


def test_source_identity_is_preserved():
    rows = _build(
        [
            _mapped_row(
                source_row_index=321,
                phone_sensor_ts_ns=999,
                pc_mapped_ts_ns=300,
            )
        ],
        alignment_lag_ns=100,
    )

    row = rows[0]

    assert row["participant_id"] == "PTEST001"
    assert row["session_id"] == "STEST001"
    assert row["calibration_id"] == "CAL2C001"

    assert (
        row["source_file"]
        == "raw/imu/imu.csv"
    )

    assert row["source_row_index"] == 321
    assert row["phone_sensor_ts_ns"] == 999
    assert row["pc_mapped_ts_ns"] == 300

    assert row["alignment_lag_ns"] == 100

    assert (
        row["derivation_version"]
        == "labels-test-v1"
    )


def test_reference_identity_is_preserved():
    rows = _build(
        [_mapped_row()],
        alignment_lag_ns=100,
    )

    row = rows[0]

    assert row["sequence_id"] == "C01_D01"
    assert row["direction_code"] == "RIGHT"
    assert row["phase"] == "OUTBOUND"


def test_label_record_ids_are_unique_and_deterministic():
    mapped = [
        _mapped_row(
            mapped_record_id="MAP000001",
            source_row_index=1,
            pc_mapped_ts_ns=200,
        ),
        _mapped_row(
            mapped_record_id="MAP000002",
            source_row_index=2,
            pc_mapped_ts_ns=300,
        ),
    ]

    first = _build(
        mapped,
        alignment_lag_ns=0,
    )

    second = _build(
        mapped,
        alignment_lag_ns=0,
    )

    first_ids = [
        row["label_record_id"]
        for row in first
    ]

    second_ids = [
        row["label_record_id"]
        for row in second
    ]

    assert len(first_ids) == 2
    assert len(set(first_ids)) == 2
    assert first_ids == second_ids


def test_non_mapped_sensor_row_fails_closed():
    with pytest.raises(
        ValueError,
        match="mapping",
    ):
        _build(
            [
                _mapped_row(
                    mapping_status=(
                        "INVALID_SOURCE_TIMESTAMP"
                    )
                )
            ],
            alignment_lag_ns=0,
        )


def test_calibration_identity_mismatch_fails_closed():
    reference_rows = _reference_rows()

    reference_rows[0][
        "calibration_id"
    ] = "OTHER"

    with pytest.raises(ValueError):
        _build(
            [_mapped_row()],
            alignment_lag_ns=0,
            reference_rows=reference_rows,
        )


def test_label_output_is_deterministic():
    mapped = [
        _mapped_row(
            pc_mapped_ts_ns=250
        )
    ]

    first = _build(
        mapped,
        alignment_lag_ns=100,
    )

    second = _build(
        mapped,
        alignment_lag_ns=100,
    )

    assert first == second