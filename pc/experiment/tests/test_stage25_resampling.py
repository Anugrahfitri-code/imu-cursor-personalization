import pytest

from pc.experiment.preprocessing.resampling import (
    resample_sensor_stream,
    resample_sensor_streams,
)


def _row(
    pc_mapped_ts_ns,
    *,
    x=1.0,
    y=2.0,
    z=3.0,
    source_row_index=1,
    sensor_sequence=1,
    pc_receive_ts_ns=999_999,
):
    return {
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
        "x":
            x,
        "y":
            y,
        "z":
            z,
        "source_row_index":
            source_row_index,
        "sensor_sequence":
            sensor_sequence,
        "pc_receive_ts_ns":
            pc_receive_ts_ns,
    }


def _resample(
    stream,
    grid_times,
    *,
    max_source_gap_ns=20,
):
    return resample_sensor_stream(
        stream=stream,
        grid_pc_times_ns=grid_times,
        method="PREVIOUS_SAMPLE_HOLD",
        max_source_gap_ns=max_source_gap_ns,
    )


def test_exact_source_timestamp_is_valid():
    rows = _resample(
        [
            _row(
                100,
                x=10.0,
                y=20.0,
                z=30.0,
            )
        ],
        [100],
    )

    assert len(rows) == 1

    row = rows[0]

    assert row["grid_pc_time_ns"] == 100
    assert row["source_pc_mapped_ts_ns"] == 100
    assert row["source_age_ns"] == 0
    assert row["status"] == "VALID"

    assert row["x"] == 10.0
    assert row["y"] == 20.0
    assert row["z"] == 30.0


def test_previous_sample_hold_is_causal():
    rows = _resample(
        [
            _row(
                100,
                x=1.0,
            ),
            _row(
                200,
                x=2.0,
            ),
        ],
        [
            100,
            150,
            200,
        ],
        max_source_gap_ns=60,
    )

    assert [
        row["x"]
        for row in rows
    ] == [
        1.0,
        1.0,
        2.0,
    ]

    assert [
        row["source_pc_mapped_ts_ns"]
        for row in rows
    ] == [
        100,
        100,
        200,
    ]


def test_future_sample_never_controls_earlier_grid_time():
    first = _resample(
        [
            _row(
                100,
                x=1.0,
            ),
            _row(
                300,
                x=3.0,
            ),
        ],
        [
            100,
            150,
        ],
        max_source_gap_ns=100,
    )

    second = _resample(
        [
            _row(
                100,
                x=1.0,
            ),
            _row(
                300,
                x=999_999.0,
            ),
        ],
        [
            100,
            150,
        ],
        max_source_gap_ns=100,
    )

    assert first == second


def test_grid_before_first_source_is_no_source():
    rows = _resample(
        [
            _row(100),
            _row(200),
        ],
        [90],
        max_source_gap_ns=50,
    )

    row = rows[0]

    assert row["status"] == "NO_SOURCE"
    assert row["source_pc_mapped_ts_ns"] is None
    assert row["source_age_ns"] is None

    assert row["x"] is None
    assert row["y"] is None
    assert row["z"] is None


def test_grid_after_last_source_is_no_source():
    rows = _resample(
        [
            _row(100),
            _row(200),
        ],
        [201],
        max_source_gap_ns=50,
    )

    row = rows[0]

    assert row["status"] == "NO_SOURCE"
    assert row["source_pc_mapped_ts_ns"] is None
    assert row["x"] is None


def test_gap_within_limit_is_valid():
    rows = _resample(
        [
            _row(
                100,
                x=5.0,
            ),
            _row(
                200,
                x=6.0,
            ),
        ],
        [120],
        max_source_gap_ns=20,
    )

    row = rows[0]

    assert row["status"] == "VALID"
    assert row["source_age_ns"] == 20
    assert row["x"] == 5.0


def test_gap_beyond_limit_is_not_bridged():
    rows = _resample(
        [
            _row(
                100,
                x=5.0,
            ),
            _row(
                200,
                x=6.0,
            ),
        ],
        [121],
        max_source_gap_ns=20,
    )

    row = rows[0]

    assert (
        row["status"]
        == "GAP_EXCEEDED"
    )

    assert (
        row["source_pc_mapped_ts_ns"]
        == 100
    )

    assert row["source_age_ns"] == 21

    assert row["x"] is None
    assert row["y"] is None
    assert row["z"] is None


def test_receive_timestamp_does_not_affect_resampling():
    first_stream = [
        _row(
            100,
            x=1.0,
            pc_receive_ts_ns=9000,
        ),
        _row(
            200,
            x=2.0,
            pc_receive_ts_ns=1000,
        ),
    ]

    second_stream = [
        dict(row)
        for row in first_stream
    ]

    second_stream[0][
        "pc_receive_ts_ns"
    ] = -999

    second_stream[1][
        "pc_receive_ts_ns"
    ] = 999_999_999

    first = _resample(
        first_stream,
        [100, 150, 200],
        max_source_gap_ns=100,
    )

    second = _resample(
        second_stream,
        [100, 150, 200],
        max_source_gap_ns=100,
    )

    assert first == second


def test_accel_and_gyro_are_resampled_independently():
    result = resample_sensor_streams(
        accel_stream=[
            _row(
                100,
                x=10.0,
            ),
            _row(
                200,
                x=20.0,
            ),
        ],
        gyro_stream=[
            _row(
                104,
                x=100.0,
            ),
            _row(
                204,
                x=200.0,
            ),
        ],
        grid_pc_times_ns=[
            110,
            160,
        ],
        accel_method=(
            "PREVIOUS_SAMPLE_HOLD"
        ),
        gyro_method=(
            "PREVIOUS_SAMPLE_HOLD"
        ),
        max_source_gap_ns=60,
    )

    accel = result["ACCEL"]
    gyro = result["GYRO"]

    assert [
        row["source_pc_mapped_ts_ns"]
        for row in accel
    ] == [
        100,
        100,
    ]

    assert [
        row["source_pc_mapped_ts_ns"]
        for row in gyro
    ] == [
        104,
        104,
    ]

    assert [
        row["x"]
        for row in accel
    ] == [
        10.0,
        10.0,
    ]

    assert [
        row["x"]
        for row in gyro
    ] == [
        100.0,
        100.0,
    ]


def test_four_ms_sensor_offset_is_resolved_by_timestamp():
    one_ms = 1_000_000

    result = resample_sensor_streams(
        accel_stream=[
            _row(
                100 * one_ms,
                x=1.0,
            ),
            _row(
                110 * one_ms,
                x=2.0,
            ),
        ],
        gyro_stream=[
            _row(
                104 * one_ms,
                x=10.0,
            ),
            _row(
                114 * one_ms,
                x=20.0,
            ),
        ],
        grid_pc_times_ns=[
            105 * one_ms,
            110 * one_ms,
        ],
        accel_method=(
            "PREVIOUS_SAMPLE_HOLD"
        ),
        gyro_method=(
            "PREVIOUS_SAMPLE_HOLD"
        ),
        max_source_gap_ns=(
            10 * one_ms
        ),
    )

    assert (
        result["ACCEL"][0][
            "source_pc_mapped_ts_ns"
        ]
        == 100 * one_ms
    )

    assert (
        result["GYRO"][0][
            "source_pc_mapped_ts_ns"
        ]
        == 104 * one_ms
    )

    assert (
        result["ACCEL"][1][
            "source_pc_mapped_ts_ns"
        ]
        == 110 * one_ms
    )

    assert (
        result["GYRO"][1][
            "source_pc_mapped_ts_ns"
        ]
        == 104 * one_ms
    )


def test_source_row_and_sequence_do_not_drive_pairing():
    first = _resample(
        [
            _row(
                100,
                x=1.0,
                source_row_index=1,
                sensor_sequence=100,
            ),
            _row(
                200,
                x=2.0,
                source_row_index=2,
                sensor_sequence=101,
            ),
        ],
        [150],
        max_source_gap_ns=100,
    )

    second = _resample(
        [
            _row(
                100,
                x=1.0,
                source_row_index=999,
                sensor_sequence=-999,
            ),
            _row(
                200,
                x=2.0,
                source_row_index=-5,
                sensor_sequence=999999,
            ),
        ],
        [150],
        max_source_gap_ns=100,
    )

    assert first == second


def test_unsorted_stream_fails_closed():
    with pytest.raises(
        ValueError,
        match="sorted",
    ):
        _resample(
            [
                _row(200),
                _row(100),
            ],
            [150],
        )


def test_unknown_resampling_method_fails_closed():
    with pytest.raises(
        ValueError,
        match="method",
    ):
        resample_sensor_stream(
            stream=[
                _row(100),
                _row(200),
            ],
            grid_pc_times_ns=[
                100,
                150,
            ],
            method="MAGIC_SPLINE",
            max_source_gap_ns=50,
        )


def test_negative_gap_limit_fails_closed():
    with pytest.raises(
        ValueError,
        match="gap",
    ):
        _resample(
            [
                _row(100),
                _row(200),
            ],
            [150],
            max_source_gap_ns=-1,
        )


def test_resampling_is_deterministic():
    stream = [
        _row(
            100,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _row(
            200,
            x=4.0,
            y=5.0,
            z=6.0,
        ),
    ]

    first = _resample(
        stream,
        [
            100,
            125,
            150,
            175,
            200,
        ],
        max_source_gap_ns=100,
    )

    second = _resample(
        stream,
        [
            100,
            125,
            150,
            175,
            200,
        ],
        max_source_gap_ns=100,
    )

    assert first == second