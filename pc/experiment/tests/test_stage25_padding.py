import pytest

from pc.experiment.preprocessing.padding import (
    build_causal_sequence_windows,
)


def _row(
    grid_index,
    *,
    sequence_id="SEQ001",
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    accel_x=0.0,
    gyro_x=0.0,
    evaluation_score=None,
    extra_field="preserve-me",
):
    return {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "sequence_id":
            sequence_id,
        "grid_index":
            grid_index,
        "accel_x":
            accel_x,
        "gyro_x":
            gyro_x,
        "evaluation_score":
            evaluation_score,
        "extra_field":
            extra_field,
    }


def _build(
    rows,
    *,
    window_length=3,
    padding_policy="REPEAT_FIRST",
    padding_value=0.0,
):
    return build_causal_sequence_windows(
        rows=rows,
        feature_fields=(
            "accel_x",
            "gyro_x",
        ),
        window_length=window_length,
        padding_policy=padding_policy,
        padding_value=padding_value,
    )


def test_repeat_first_pads_first_sequence_row():
    result = _build(
        [
            _row(
                0,
                accel_x=1.0,
                gyro_x=10.0,
            )
        ],
        window_length=3,
        padding_policy="REPEAT_FIRST",
    )

    assert result[0]["window"] == (
        (1.0, 10.0),
        (1.0, 10.0),
        (1.0, 10.0),
    )

    assert result[0]["padding_mask"] == (
        True,
        True,
        False,
    )


def test_second_row_uses_only_available_past_and_current():
    result = _build(
        [
            _row(
                0,
                accel_x=1.0,
                gyro_x=10.0,
            ),
            _row(
                1,
                accel_x=2.0,
                gyro_x=20.0,
            ),
        ],
        window_length=3,
        padding_policy="REPEAT_FIRST",
    )

    assert result[1]["window"] == (
        (1.0, 10.0),
        (1.0, 10.0),
        (2.0, 20.0),
    )

    assert result[1]["padding_mask"] == (
        True,
        False,
        False,
    )


def test_full_history_requires_no_padding():
    result = _build(
        [
            _row(
                0,
                accel_x=1.0,
                gyro_x=10.0,
            ),
            _row(
                1,
                accel_x=2.0,
                gyro_x=20.0,
            ),
            _row(
                2,
                accel_x=3.0,
                gyro_x=30.0,
            ),
        ],
        window_length=3,
    )

    assert result[2]["window"] == (
        (1.0, 10.0),
        (2.0, 20.0),
        (3.0, 30.0),
    )

    assert result[2]["padding_mask"] == (
        False,
        False,
        False,
    )


def test_constant_padding_uses_explicit_padding_value():
    result = _build(
        [
            _row(
                0,
                accel_x=7.0,
                gyro_x=70.0,
            )
        ],
        window_length=3,
        padding_policy="CONSTANT",
        padding_value=-9.0,
    )

    assert result[0]["window"] == (
        (-9.0, -9.0),
        (-9.0, -9.0),
        (7.0, 70.0),
    )

    assert result[0]["padding_mask"] == (
        True,
        True,
        False,
    )


def test_new_sequence_resets_history():
    result = _build(
        [
            _row(
                0,
                sequence_id="SEQ001",
                accel_x=1.0,
                gyro_x=10.0,
            ),
            _row(
                1,
                sequence_id="SEQ001",
                accel_x=2.0,
                gyro_x=20.0,
            ),
            _row(
                2,
                sequence_id="SEQ002",
                accel_x=100.0,
                gyro_x=1000.0,
            ),
        ],
        window_length=3,
        padding_policy="REPEAT_FIRST",
    )

    assert result[2]["window"] == (
        (100.0, 1000.0),
        (100.0, 1000.0),
        (100.0, 1000.0),
    )

    assert result[2]["padding_mask"] == (
        True,
        True,
        False,
    )


def test_return_to_previous_sequence_starts_new_run():
    result = _build(
        [
            _row(
                0,
                sequence_id="SEQ001",
                accel_x=1.0,
                gyro_x=10.0,
            ),
            _row(
                1,
                sequence_id="SEQ002",
                accel_x=2.0,
                gyro_x=20.0,
            ),
            _row(
                2,
                sequence_id="SEQ001",
                accel_x=3.0,
                gyro_x=30.0,
            ),
        ],
        window_length=2,
        padding_policy="REPEAT_FIRST",
    )

    assert result[2]["window"] == (
        (3.0, 30.0),
        (3.0, 30.0),
    )

    assert result[2]["padding_mask"] == (
        True,
        False,
    )


def test_future_sample_cannot_change_earlier_window():
    first_rows = [
        _row(
            0,
            accel_x=1.0,
            gyro_x=10.0,
        ),
        _row(
            1,
            accel_x=2.0,
            gyro_x=20.0,
        ),
        _row(
            2,
            accel_x=3.0,
            gyro_x=30.0,
        ),
    ]

    second_rows = [
        dict(row)
        for row in first_rows
    ]

    second_rows[2]["accel_x"] = 999999.0
    second_rows[2]["gyro_x"] = 999999.0

    first = _build(
        first_rows,
        window_length=3,
    )

    second = _build(
        second_rows,
        window_length=3,
    )

    assert first[:2] == second[:2]


def test_window_ends_at_current_row():
    result = _build(
        [
            _row(
                0,
                accel_x=10.0,
                gyro_x=100.0,
            ),
            _row(
                1,
                accel_x=20.0,
                gyro_x=200.0,
            ),
            _row(
                2,
                accel_x=30.0,
                gyro_x=300.0,
            ),
            _row(
                3,
                accel_x=40.0,
                gyro_x=400.0,
            ),
        ],
        window_length=3,
    )

    assert result[3]["window"] == (
        (20.0, 200.0),
        (30.0, 300.0),
        (40.0, 400.0),
    )


def test_output_preserves_current_row_provenance():
    result = _build(
        [
            _row(
                123,
                accel_x=1.0,
                gyro_x=10.0,
                extra_field="audit-value",
            )
        ]
    )

    assert result[0]["grid_index"] == 123
    assert result[0]["sequence_id"] == "SEQ001"

    assert (
        result[0]["extra_field"]
        == "audit-value"
    )


def test_input_rows_are_not_mutated():
    rows = [
        _row(
            0,
            accel_x=1.0,
            gyro_x=10.0,
        ),
        _row(
            1,
            accel_x=2.0,
            gyro_x=20.0,
        ),
    ]

    original = [
        dict(row)
        for row in rows
    ]

    _build(
        rows
    )

    assert rows == original


def test_evaluation_outcome_does_not_influence_padding():
    first_rows = [
        _row(
            0,
            accel_x=1.0,
            gyro_x=10.0,
            evaluation_score=0.1,
        ),
        _row(
            1,
            accel_x=2.0,
            gyro_x=20.0,
            evaluation_score=0.2,
        ),
    ]

    second_rows = [
        dict(row)
        for row in first_rows
    ]

    second_rows[0]["evaluation_score"] = 999999.0
    second_rows[1]["evaluation_score"] = -999999.0

    first = _build(
        first_rows
    )

    second = _build(
        second_rows
    )

    assert [
        row["window"]
        for row in first
    ] == [
        row["window"]
        for row in second
    ]

    assert [
        row["padding_mask"]
        for row in first
    ] == [
        row["padding_mask"]
        for row in second
    ]


def test_mixed_participant_identity_fails_closed():
    with pytest.raises(
        ValueError,
        match="participant",
    ):
        _build(
            [
                _row(
                    0,
                    participant_id="PTEST001",
                ),
                _row(
                    1,
                    participant_id="OTHER",
                ),
            ]
        )


def test_mixed_session_identity_fails_closed():
    with pytest.raises(
        ValueError,
        match="session",
    ):
        _build(
            [
                _row(
                    0,
                    session_id="STEST001",
                ),
                _row(
                    1,
                    session_id="OTHER",
                ),
            ]
        )


def test_mixed_calibration_identity_fails_closed():
    with pytest.raises(
        ValueError,
        match="calibration",
    ):
        _build(
            [
                _row(
                    0,
                    calibration_id="CAL2C001",
                ),
                _row(
                    1,
                    calibration_id="OTHER",
                ),
            ]
        )


def test_missing_sequence_id_fails_closed():
    row = _row(
        0
    )

    del row["sequence_id"]

    with pytest.raises(
        ValueError,
        match="sequence",
    ):
        _build(
            [
                row
            ]
        )


def test_missing_feature_fails_closed():
    row = _row(
        0
    )

    del row["gyro_x"]

    with pytest.raises(
        ValueError,
        match="feature",
    ):
        _build(
            [
                row
            ]
        )


def test_non_positive_window_length_fails_closed():
    with pytest.raises(
        ValueError,
        match="window",
    ):
        _build(
            [
                _row(0)
            ],
            window_length=0,
        )


def test_unknown_padding_policy_fails_closed():
    with pytest.raises(
        ValueError,
        match="padding",
    ):
        _build(
            [
                _row(0)
            ],
            padding_policy="MAGIC_PADDING",
        )


def test_empty_feature_list_fails_closed():
    with pytest.raises(
        ValueError,
        match="feature",
    ):
        build_causal_sequence_windows(
            rows=[
                _row(0)
            ],
            feature_fields=(),
            window_length=3,
            padding_policy="REPEAT_FIRST",
            padding_value=0.0,
        )


def test_padding_is_deterministic():
    rows = [
        _row(
            0,
            accel_x=1.0,
            gyro_x=10.0,
        ),
        _row(
            1,
            accel_x=2.0,
            gyro_x=20.0,
        ),
        _row(
            2,
            accel_x=3.0,
            gyro_x=30.0,
        ),
    ]

    first = _build(
        rows,
        window_length=4,
        padding_policy="CONSTANT",
        padding_value=0.0,
    )

    second = _build(
        rows,
        window_length=4,
        padding_policy="CONSTANT",
        padding_value=0.0,
    )

    assert first == second