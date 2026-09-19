import pytest

from pc.experiment.preprocessing.grid import (
    build_common_grid,
)


def _row(
    pc_mapped_ts_ns,
    *,
    source_row_index=1,
    sensor_sequence=1,
    pc_receive_ts_ns=999_999,
):
    return {
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
        "source_row_index":
            source_row_index,
        "sensor_sequence":
            sensor_sequence,
        "pc_receive_ts_ns":
            pc_receive_ts_ns,
    }


def _build(
    accel_times,
    gyro_times,
    *,
    grid_interval_ns=50,
    grid_origin_pc_ns=0,
):
    accel_stream = [
        _row(
            timestamp,
            source_row_index=index,
            sensor_sequence=1000 + index,
        )
        for index, timestamp in enumerate(
            accel_times,
            start=1,
        )
    ]

    gyro_stream = [
        _row(
            timestamp,
            source_row_index=index,
            sensor_sequence=2000 + index,
        )
        for index, timestamp in enumerate(
            gyro_times,
            start=1,
        )
    ]

    return build_common_grid(
        accel_stream=accel_stream,
        gyro_stream=gyro_stream,
        grid_interval_ns=grid_interval_ns,
        grid_origin_pc_ns=grid_origin_pc_ns,
        grid_domain_rule="INTERSECTION",
    )


def test_common_grid_uses_intersection_of_sensor_coverage():
    result = _build(
        accel_times=[
            100,
            160,
            220,
            280,
        ],
        gyro_times=[
            120,
            180,
            240,
            300,
        ],
        grid_interval_ns=50,
        grid_origin_pc_ns=0,
    )

    assert (
        result["coverage_start_pc_ns"]
        == 120
    )

    assert (
        result["coverage_end_pc_ns"]
        == 280
    )

    assert (
        result["grid_pc_times_ns"]
        == [
            150,
            200,
            250,
        ]
    )


def test_explicit_origin_controls_grid_phase():
    result = _build(
        accel_times=[
            100,
            200,
            300,
        ],
        gyro_times=[
            100,
            200,
            300,
        ],
        grid_interval_ns=50,
        grid_origin_pc_ns=25,
    )

    assert (
        result["grid_pc_times_ns"]
        == [
            125,
            175,
            225,
            275,
        ]
    )


def test_large_nanosecond_grid_uses_exact_integer_arithmetic():
    base = 9_000_000_000_000_000

    result = _build(
        accel_times=[
            base + 1,
            base + 40_000_001,
        ],
        gyro_times=[
            base + 3,
            base + 40_000_003,
        ],
        grid_interval_ns=10_000_000,
        grid_origin_pc_ns=base,
    )

    assert (
        result["grid_pc_times_ns"]
        == [
            base + 10_000_000,
            base + 20_000_000,
            base + 30_000_000,
            base + 40_000_000,
        ]
    )


def test_grid_timestamps_are_strictly_increasing():
    result = _build(
        accel_times=[
            100,
            500,
        ],
        gyro_times=[
            100,
            500,
        ],
        grid_interval_ns=25,
    )

    times = result[
        "grid_pc_times_ns"
    ]

    assert all(
        right > left
        for left, right in zip(
            times,
            times[1:],
            strict=False,
        )
    )


def test_grid_never_extrapolates_outside_intersection():
    result = _build(
        accel_times=[
            103,
            297,
        ],
        gyro_times=[
            111,
            289,
        ],
        grid_interval_ns=25,
        grid_origin_pc_ns=0,
    )

    times = result[
        "grid_pc_times_ns"
    ]

    assert times

    assert min(times) >= 111
    assert max(times) <= 289


def test_receive_timestamp_does_not_change_grid():
    accel_first = [
        _row(
            100,
            source_row_index=1,
            pc_receive_ts_ns=9_000,
        ),
        _row(
            300,
            source_row_index=2,
            pc_receive_ts_ns=1_000,
        ),
    ]

    gyro_first = [
        _row(
            100,
            source_row_index=1,
            pc_receive_ts_ns=8_000,
        ),
        _row(
            300,
            source_row_index=2,
            pc_receive_ts_ns=2_000,
        ),
    ]

    accel_second = [
        dict(row)
        for row in accel_first
    ]

    gyro_second = [
        dict(row)
        for row in gyro_first
    ]

    accel_second[0][
        "pc_receive_ts_ns"
    ] = -999

    accel_second[1][
        "pc_receive_ts_ns"
    ] = 999_999_999

    gyro_second[0][
        "pc_receive_ts_ns"
    ] = 123

    gyro_second[1][
        "pc_receive_ts_ns"
    ] = 456

    first = build_common_grid(
        accel_stream=accel_first,
        gyro_stream=gyro_first,
        grid_interval_ns=50,
        grid_origin_pc_ns=0,
        grid_domain_rule="INTERSECTION",
    )

    second = build_common_grid(
        accel_stream=accel_second,
        gyro_stream=gyro_second,
        grid_interval_ns=50,
        grid_origin_pc_ns=0,
        grid_domain_rule="INTERSECTION",
    )

    assert first == second


def test_sequence_and_row_identity_do_not_change_grid():
    accel = [
        _row(
            100,
            source_row_index=1,
            sensor_sequence=10,
        ),
        _row(
            300,
            source_row_index=2,
            sensor_sequence=11,
        ),
    ]

    gyro = [
        _row(
            100,
            source_row_index=1,
            sensor_sequence=5000,
        ),
        _row(
            300,
            source_row_index=2,
            sensor_sequence=9000,
        ),
    ]

    first = build_common_grid(
        accel_stream=accel,
        gyro_stream=gyro,
        grid_interval_ns=50,
        grid_origin_pc_ns=0,
        grid_domain_rule="INTERSECTION",
    )

    accel_changed = [
        dict(row)
        for row in accel
    ]

    gyro_changed = [
        dict(row)
        for row in gyro
    ]

    accel_changed[0][
        "source_row_index"
    ] = 999

    accel_changed[0][
        "sensor_sequence"
    ] = -50

    gyro_changed[1][
        "source_row_index"
    ] = 777

    gyro_changed[1][
        "sensor_sequence"
    ] = -999

    second = build_common_grid(
        accel_stream=accel_changed,
        gyro_stream=gyro_changed,
        grid_interval_ns=50,
        grid_origin_pc_ns=0,
        grid_domain_rule="INTERSECTION",
    )

    assert first == second


def test_grid_build_is_deterministic():
    first = _build(
        accel_times=[
            101,
            201,
            301,
            401,
        ],
        gyro_times=[
            109,
            209,
            309,
            409,
        ],
        grid_interval_ns=20,
        grid_origin_pc_ns=5,
    )

    second = _build(
        accel_times=[
            101,
            201,
            301,
            401,
        ],
        gyro_times=[
            109,
            209,
            309,
            409,
        ],
        grid_interval_ns=20,
        grid_origin_pc_ns=5,
    )

    assert first == second


def test_empty_accel_stream_fails_closed():
    with pytest.raises(
        ValueError,
        match="accel",
    ):
        build_common_grid(
            accel_stream=[],
            gyro_stream=[
                _row(100),
                _row(200),
            ],
            grid_interval_ns=10,
            grid_origin_pc_ns=0,
            grid_domain_rule=(
                "INTERSECTION"
            ),
        )


def test_empty_gyro_stream_fails_closed():
    with pytest.raises(
        ValueError,
        match="gyro",
    ):
        build_common_grid(
            accel_stream=[
                _row(100),
                _row(200),
            ],
            gyro_stream=[],
            grid_interval_ns=10,
            grid_origin_pc_ns=0,
            grid_domain_rule=(
                "INTERSECTION"
            ),
        )


def test_non_overlapping_sensor_coverage_fails_closed():
    with pytest.raises(
        ValueError,
        match="overlap",
    ):
        _build(
            accel_times=[
                100,
                200,
            ],
            gyro_times=[
                300,
                400,
            ],
            grid_interval_ns=10,
        )


def test_non_positive_grid_interval_fails_closed():
    with pytest.raises(
        ValueError,
        match="interval",
    ):
        _build(
            accel_times=[
                100,
                200,
            ],
            gyro_times=[
                100,
                200,
            ],
            grid_interval_ns=0,
        )


def test_unsorted_native_stream_fails_closed():
    accel = [
        _row(300),
        _row(100),
        _row(200),
    ]

    gyro = [
        _row(100),
        _row(200),
        _row(300),
    ]

    with pytest.raises(
        ValueError,
        match="sorted",
    ):
        build_common_grid(
            accel_stream=accel,
            gyro_stream=gyro,
            grid_interval_ns=50,
            grid_origin_pc_ns=0,
            grid_domain_rule=(
                "INTERSECTION"
            ),
        )