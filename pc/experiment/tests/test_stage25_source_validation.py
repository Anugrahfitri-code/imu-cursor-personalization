import pytest

from pc.experiment.preprocessing.source_validation import (
    normalize_sensor_streams,
)


def _row(
    *,
    sensor_family="ACCEL",
    source_row_index=1,
    sensor_sequence=100,
    phone_sensor_ts_ns=1_000,
    pc_mapped_ts_ns=10_000,
    pc_receive_ts_ns=99_000,
    mapping_status="MAPPED",
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    source_file="raw/imu/imu.csv",
    x=1.0,
    y=2.0,
    z=3.0,
):
    return {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "sensor_family":
            sensor_family,
        "source_file":
            source_file,
        "source_row_index":
            source_row_index,
        "sensor_sequence":
            sensor_sequence,
        "phone_sensor_ts_ns":
            phone_sensor_ts_ns,
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
        "pc_receive_ts_ns":
            pc_receive_ts_ns,
        "mapping_status":
            mapping_status,
        "x":
            x,
        "y":
            y,
        "z":
            z,
    }


def _normalize(records):
    return normalize_sensor_streams(
        records=records,
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
    )


def test_accel_and_gyro_are_independent_streams():
    result = _normalize(
        [
            _row(
                sensor_family="ACCEL",
                source_row_index=1,
                pc_mapped_ts_ns=100,
            ),
            _row(
                sensor_family="GYRO",
                source_row_index=2,
                pc_mapped_ts_ns=101,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=3,
                pc_mapped_ts_ns=200,
            ),
            _row(
                sensor_family="GYRO",
                source_row_index=4,
                pc_mapped_ts_ns=201,
            ),
        ]
    )

    assert tuple(
        result["streams"].keys()
    ) == (
        "ACCEL",
        "GYRO",
    )

    assert [
        row["source_row_index"]
        for row in result["streams"]["ACCEL"]
    ] == [1, 3]

    assert [
        row["source_row_index"]
        for row in result["streams"]["GYRO"]
    ] == [2, 4]


def test_each_stream_is_sorted_by_pc_mapped_timestamp():
    result = _normalize(
        [
            _row(
                sensor_family="ACCEL",
                source_row_index=1,
                pc_mapped_ts_ns=300,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=2,
                pc_mapped_ts_ns=100,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=3,
                pc_mapped_ts_ns=200,
            ),
        ]
    )

    assert [
        row["pc_mapped_ts_ns"]
        for row in result["streams"]["ACCEL"]
    ] == [
        100,
        200,
        300,
    ]


def test_receive_timestamp_does_not_control_ordering():
    result = _normalize(
        [
            _row(
                sensor_family="GYRO",
                source_row_index=1,
                pc_mapped_ts_ns=100,
                pc_receive_ts_ns=900,
            ),
            _row(
                sensor_family="GYRO",
                source_row_index=2,
                pc_mapped_ts_ns=200,
                pc_receive_ts_ns=100,
            ),
        ]
    )

    rows = result["streams"]["GYRO"]

    assert [
        row["source_row_index"]
        for row in rows
    ] == [1, 2]

    assert [
        row["pc_mapped_ts_ns"]
        for row in rows
    ] == [100, 200]

    assert [
        row["pc_receive_ts_ns"]
        for row in rows
    ] == [900, 100]


def test_source_provenance_is_preserved():
    source = _row(
        sensor_family="ACCEL",
        source_row_index=321,
        sensor_sequence=777,
        phone_sensor_ts_ns=123_456,
        pc_mapped_ts_ns=223_456,
        pc_receive_ts_ns=999_999,
        source_file="raw/imu/source_A.csv",
        x=1.25,
        y=-2.5,
        z=3.75,
    )

    result = _normalize([source])

    row = result["streams"]["ACCEL"][0]

    for field in (
        "participant_id",
        "session_id",
        "calibration_id",
        "sensor_family",
        "source_file",
        "source_row_index",
        "sensor_sequence",
        "phone_sensor_ts_ns",
        "pc_mapped_ts_ns",
        "pc_receive_ts_ns",
        "mapping_status",
        "x",
        "y",
        "z",
    ):
        assert row[field] == source[field]


def test_mixed_participant_identity_fails_closed():
    records = [
        _row(),
        _row(
            source_row_index=2,
            participant_id="OTHER",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="participant",
    ):
        _normalize(records)


def test_mixed_session_identity_fails_closed():
    records = [
        _row(),
        _row(
            source_row_index=2,
            session_id="OTHER",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="session",
    ):
        _normalize(records)


def test_mixed_calibration_identity_fails_closed():
    records = [
        _row(),
        _row(
            source_row_index=2,
            calibration_id="OTHER",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="calibration",
    ):
        _normalize(records)


def test_unknown_sensor_family_fails_closed():
    with pytest.raises(
        ValueError,
        match="sensor",
    ):
        _normalize(
            [
                _row(
                    sensor_family="MAGNETOMETER"
                )
            ]
        )


def test_invalid_mapped_timestamp_is_flagged_and_not_used():
    result = _normalize(
        [
            _row(
                sensor_family="ACCEL",
                source_row_index=10,
                pc_mapped_ts_ns=100,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=11,
                pc_mapped_ts_ns=None,
                mapping_status=(
                    "INVALID_SOURCE_TIMESTAMP"
                ),
            ),
        ]
    )

    assert [
        row["source_row_index"]
        for row in result["streams"]["ACCEL"]
    ] == [10]

    diagnostics = result["diagnostics"]

    assert (
        diagnostics["invalid_timestamp_count"]
        == 1
    )

    assert (
        diagnostics["invalid_timestamp_rows"]
        == [11]
    )


def test_temporal_reorder_event_is_detected():
    result = _normalize(
        [
            _row(
                sensor_family="ACCEL",
                source_row_index=1,
                pc_mapped_ts_ns=300,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=2,
                pc_mapped_ts_ns=100,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=3,
                pc_mapped_ts_ns=200,
            ),
        ]
    )

    diagnostics = result["diagnostics"]

    assert diagnostics["reorder_count"] == 1

    assert diagnostics["reorder_events"] == [
        {
            "event_type":
                "REORDERED_MAPPED_TIMESTAMP",
            "sensor_family":
                "ACCEL",
            "source_row_index":
                2,
            "previous_pc_mapped_ts_ns":
                300,
            "pc_mapped_ts_ns":
                100,
        }
    ]


def test_duplicate_source_identity_is_detected_without_dropping_rows():
    result = _normalize(
        [
            _row(
                sensor_family="ACCEL",
                source_row_index=10,
                phone_sensor_ts_ns=100,
                pc_mapped_ts_ns=200,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=10,
                phone_sensor_ts_ns=101,
                pc_mapped_ts_ns=201,
            ),
        ]
    )

    diagnostics = result["diagnostics"]

    assert diagnostics["duplicate_count"] == 1

    assert (
        diagnostics["duplicate_events"][0][
            "event_type"
        ]
        == "DUPLICATE_SOURCE_IDENTITY"
    )

    assert len(
        result["streams"]["ACCEL"]
    ) == 2


def test_duplicate_native_timestamp_is_detected_without_dropping_rows():
    result = _normalize(
        [
            _row(
                sensor_family="GYRO",
                source_row_index=1,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1000,
            ),
            _row(
                sensor_family="GYRO",
                source_row_index=2,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1001,
            ),
        ]
    )

    event_types = [
        event["event_type"]
        for event in (
            result["diagnostics"][
                "duplicate_events"
            ]
        )
    ]

    assert (
        "DUPLICATE_NATIVE_TIMESTAMP"
        in event_types
    )

    assert len(
        result["streams"]["GYRO"]
    ) == 2


def test_duplicate_mapped_timestamp_is_detected_without_dropping_rows():
    result = _normalize(
        [
            _row(
                sensor_family="ACCEL",
                source_row_index=1,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1000,
            ),
            _row(
                sensor_family="ACCEL",
                source_row_index=2,
                phone_sensor_ts_ns=501,
                pc_mapped_ts_ns=1000,
            ),
        ]
    )

    event_types = [
        event["event_type"]
        for event in (
            result["diagnostics"][
                "duplicate_events"
            ]
        )
    ]

    assert (
        "DUPLICATE_MAPPED_TIMESTAMP"
        in event_types
    )

    assert len(
        result["streams"]["ACCEL"]
    ) == 2


def test_normalization_is_deterministic():
    records = [
        _row(
            sensor_family="GYRO",
            source_row_index=4,
            phone_sensor_ts_ns=400,
            pc_mapped_ts_ns=600,
        ),
        _row(
            sensor_family="ACCEL",
            source_row_index=3,
            phone_sensor_ts_ns=300,
            pc_mapped_ts_ns=500,
        ),
        _row(
            sensor_family="GYRO",
            source_row_index=2,
            phone_sensor_ts_ns=200,
            pc_mapped_ts_ns=400,
        ),
        _row(
            sensor_family="ACCEL",
            source_row_index=1,
            phone_sensor_ts_ns=100,
            pc_mapped_ts_ns=300,
        ),
    ]

    first = _normalize(records)
    second = _normalize(records)

    assert first == second