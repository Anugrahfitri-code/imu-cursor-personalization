import pytest

from pc.experiment.preprocessing.bias import (
    apply_sensor_bias_correction,
    estimate_sensor_bias,
)


def _row(
    pc_mapped_ts_ns,
    *,
    x=0.0,
    y=0.0,
    z=0.0,
    source_row_index=1,
    reference_value=None,
    evaluation_score=None,
):
    return {
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
        "source_row_index":
            source_row_index,
        "x":
            x,
        "y":
            y,
        "z":
            z,
        "reference_value":
            reference_value,
        "evaluation_score":
            evaluation_score,
    }


def _estimate(
    stream,
    *,
    sensor_family="GYRO",
    method="MEAN_PC_WINDOW",
    window_start_pc_ns=100,
    window_end_pc_ns=200,
    channels=("x", "y", "z"),
    minimum_samples=3,
):
    return estimate_sensor_bias(
        stream=stream,
        sensor_family=sensor_family,
        method=method,
        window_start_pc_ns=window_start_pc_ns,
        window_end_pc_ns=window_end_pc_ns,
        channels=channels,
        minimum_samples=minimum_samples,
    )


def test_known_additive_bias_is_recovered():
    result = _estimate(
        [
            _row(
                100,
                x=1.5,
                y=-2.0,
                z=0.25,
            ),
            _row(
                150,
                x=1.5,
                y=-2.0,
                z=0.25,
            ),
            _row(
                200,
                x=1.5,
                y=-2.0,
                z=0.25,
            ),
        ]
    )

    assert result["bias"]["x"] == pytest.approx(
        1.5
    )

    assert result["bias"]["y"] == pytest.approx(
        -2.0
    )

    assert result["bias"]["z"] == pytest.approx(
        0.25
    )


def test_estimation_window_excludes_outside_samples():
    result = _estimate(
        [
            _row(
                50,
                x=999.0,
                y=999.0,
                z=999.0,
            ),
            _row(
                100,
                x=1.0,
                y=2.0,
                z=3.0,
            ),
            _row(
                150,
                x=1.0,
                y=2.0,
                z=3.0,
            ),
            _row(
                200,
                x=1.0,
                y=2.0,
                z=3.0,
            ),
            _row(
                250,
                x=-999.0,
                y=-999.0,
                z=-999.0,
            ),
        ]
    )

    assert result["bias"] == {
        "x": 1.0,
        "y": 2.0,
        "z": 3.0,
    }

    assert result["sample_count"] == 3


def test_window_boundaries_are_inclusive():
    result = _estimate(
        [
            _row(
                100,
                x=1.0,
                y=2.0,
                z=3.0,
            ),
            _row(
                150,
                x=2.0,
                y=3.0,
                z=4.0,
            ),
            _row(
                200,
                x=3.0,
                y=4.0,
                z=5.0,
            ),
        ],
        minimum_samples=3,
    )

    assert result["sample_count"] == 3

    assert result["bias"] == {
        "x": 2.0,
        "y": 3.0,
        "z": 4.0,
    }


def test_insufficient_eligible_samples_fails_closed():
    with pytest.raises(
        ValueError,
        match="sample",
    ):
        _estimate(
            [
                _row(
                    100,
                    x=1.0,
                    y=2.0,
                    z=3.0,
                ),
                _row(
                    150,
                    x=1.0,
                    y=2.0,
                    z=3.0,
                ),
            ],
            minimum_samples=3,
        )


def test_unsupported_method_fails_closed():
    with pytest.raises(
        ValueError,
        match="method",
    ):
        _estimate(
            [
                _row(100),
                _row(150),
                _row(200),
            ],
            method="MAGIC_BIAS",
        )


def test_unknown_sensor_family_fails_closed():
    with pytest.raises(
        ValueError,
        match="sensor",
    ):
        _estimate(
            [
                _row(100),
                _row(150),
                _row(200),
            ],
            sensor_family="MAGNETOMETER",
        )


def test_invalid_window_fails_closed():
    with pytest.raises(
        ValueError,
        match="window",
    ):
        _estimate(
            [
                _row(100),
                _row(150),
                _row(200),
            ],
            window_start_pc_ns=300,
            window_end_pc_ns=100,
        )


def test_unsupported_channel_fails_closed():
    with pytest.raises(
        ValueError,
        match="channel",
    ):
        _estimate(
            [
                _row(100),
                _row(150),
                _row(200),
            ],
            channels=(
                "x",
                "y",
                "w",
            ),
        )


def test_duplicate_channel_fails_closed():
    with pytest.raises(
        ValueError,
        match="channel",
    ):
        _estimate(
            [
                _row(100),
                _row(150),
                _row(200),
            ],
            channels=(
                "x",
                "x",
            ),
        )


def test_non_finite_eligible_value_fails_closed():
    with pytest.raises(
        ValueError,
        match="finite",
    ):
        _estimate(
            [
                _row(
                    100,
                    x=1.0,
                ),
                _row(
                    150,
                    x=float("nan"),
                ),
                _row(
                    200,
                    x=1.0,
                ),
            ]
        )


def test_reference_and_evaluation_fields_do_not_influence_estimate():
    first = [
        _row(
            100,
            x=1.0,
            y=2.0,
            z=3.0,
            reference_value=1000.0,
            evaluation_score=0.1,
        ),
        _row(
            150,
            x=1.0,
            y=2.0,
            z=3.0,
            reference_value=2000.0,
            evaluation_score=0.2,
        ),
        _row(
            200,
            x=1.0,
            y=2.0,
            z=3.0,
            reference_value=3000.0,
            evaluation_score=0.3,
        ),
    ]

    second = [
        dict(row)
        for row in first
    ]

    second[0]["reference_value"] = -999999.0
    second[1]["reference_value"] = 999999.0
    second[2]["reference_value"] = 0.0

    second[0]["evaluation_score"] = 999.0
    second[1]["evaluation_score"] = -999.0
    second[2]["evaluation_score"] = 42.0

    first_result = _estimate(
        first
    )

    second_result = _estimate(
        second
    )

    assert (
        first_result
        == second_result
    )


def test_bias_estimate_contains_explicit_provenance():
    result = _estimate(
        [
            _row(100),
            _row(150),
            _row(200),
        ],
        sensor_family="GYRO",
        channels=(
            "x",
            "y",
            "z",
        ),
        minimum_samples=3,
    )

    assert result["sensor_family"] == "GYRO"

    assert result["method"] == "MEAN_PC_WINDOW"

    assert (
        result["window_start_pc_ns"]
        == 100
    )

    assert (
        result["window_end_pc_ns"]
        == 200
    )

    assert result["channels"] == (
        "x",
        "y",
        "z",
    )

    assert result["minimum_samples"] == 3
    assert result["sample_count"] == 3

    assert (
        result["first_eligible_pc_time_ns"]
        == 100
    )

    assert (
        result["last_eligible_pc_time_ns"]
        == 200
    )


def test_bias_estimation_is_deterministic():
    stream = [
        _row(
            100,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _row(
            150,
            x=2.0,
            y=3.0,
            z=4.0,
        ),
        _row(
            200,
            x=3.0,
            y=4.0,
            z=5.0,
        ),
    ]

    first = _estimate(stream)
    second = _estimate(stream)

    assert first == second


def test_apply_bias_correction_removes_known_bias():
    stream = [
        _row(
            100,
            x=1.5,
            y=-2.0,
            z=0.25,
        ),
        _row(
            150,
            x=1.5,
            y=-2.0,
            z=0.25,
        ),
        _row(
            200,
            x=1.5,
            y=-2.0,
            z=0.25,
        ),
    ]

    estimate = _estimate(
        stream
    )

    corrected = (
        apply_sensor_bias_correction(
            stream=stream,
            bias_estimate=estimate,
        )
    )

    for row in corrected:
        assert row["x"] == pytest.approx(0.0)
        assert row["y"] == pytest.approx(0.0)
        assert row["z"] == pytest.approx(0.0)


def test_correction_only_changes_selected_channels():
    stream = [
        _row(
            100,
            x=2.0,
            y=20.0,
            z=200.0,
        ),
        _row(
            150,
            x=2.0,
            y=20.0,
            z=200.0,
        ),
        _row(
            200,
            x=2.0,
            y=20.0,
            z=200.0,
        ),
    ]

    estimate = _estimate(
        stream,
        channels=(
            "x",
        ),
    )

    corrected = (
        apply_sensor_bias_correction(
            stream=stream,
            bias_estimate=estimate,
        )
    )

    for row in corrected:
        assert row["x"] == pytest.approx(0.0)
        assert row["y"] == 20.0
        assert row["z"] == 200.0


def test_correction_preserves_non_axis_fields():
    stream = [
        _row(
            100,
            x=1.0,
            y=2.0,
            z=3.0,
            source_row_index=123,
        ),
        _row(
            150,
            x=1.0,
            y=2.0,
            z=3.0,
            source_row_index=456,
        ),
        _row(
            200,
            x=1.0,
            y=2.0,
            z=3.0,
            source_row_index=789,
        ),
    ]

    estimate = _estimate(
        stream
    )

    corrected = (
        apply_sensor_bias_correction(
            stream=stream,
            bias_estimate=estimate,
        )
    )

    assert [
        row["source_row_index"]
        for row in corrected
    ] == [
        123,
        456,
        789,
    ]

    assert [
        row["pc_mapped_ts_ns"]
        for row in corrected
    ] == [
        100,
        150,
        200,
    ]


def test_correction_does_not_mutate_input():
    stream = [
        _row(
            100,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _row(
            150,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _row(
            200,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
    ]

    original = [
        dict(row)
        for row in stream
    ]

    estimate = _estimate(
        stream
    )

    apply_sensor_bias_correction(
        stream=stream,
        bias_estimate=estimate,
    )

    assert stream == original


def test_correction_rejects_missing_bias_channel():
    stream = [
        _row(
            100,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
    ]

    invalid_estimate = {
        "sensor_family":
            "GYRO",
        "method":
            "MEAN_PC_WINDOW",
        "window_start_pc_ns":
            100,
        "window_end_pc_ns":
            200,
        "channels":
            (
                "x",
                "y",
            ),
        "minimum_samples":
            3,
        "sample_count":
            3,
        "first_eligible_pc_time_ns":
            100,
        "last_eligible_pc_time_ns":
            200,
        "bias":
            {
                "x": 1.0,
            },
    }

    with pytest.raises(
        ValueError,
        match="bias",
    ):
        apply_sensor_bias_correction(
            stream=stream,
            bias_estimate=invalid_estimate,
        )