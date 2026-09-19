import pytest

from pc.experiment.preprocessing.source_validation import (
    apply_stream_anomaly_policy,
    normalize_sensor_streams,
)

from pc.experiment.preprocessing.resampling import (
    detect_source_gap_events,
)


def _row(
    *,
    sensor_family="ACCEL",
    source_row_index=1,
    sensor_sequence=1,
    phone_sensor_ts_ns=100,
    pc_mapped_ts_ns=1000,
    pc_receive_ts_ns=9999,
    source_file="raw/imu/source.csv",
    mapping_status="MAPPED",
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
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


def _apply(
    records,
    *,
    reorder_policy="SORT_AND_REPORT",
    duplicate_policy="KEEP_ALL_REPORT",
):
    normalized = _normalize(records)

    return apply_stream_anomaly_policy(
        normalized_result=normalized,
        reorder_policy=reorder_policy,
        duplicate_policy=duplicate_policy,
    )


def _gap_stream(times):
    return [
        {
            "pc_mapped_ts_ns":
                timestamp,
        }
        for timestamp in times
    ]


def test_sort_and_report_preserves_normalized_temporal_order():
    result = _apply(
        [
            _row(
                source_row_index=1,
                pc_mapped_ts_ns=300,
            ),
            _row(
                source_row_index=2,
                pc_mapped_ts_ns=100,
            ),
            _row(
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

    diagnostics = result["diagnostics"]

    assert (
        diagnostics["reorder_policy"]
        == "SORT_AND_REPORT"
    )

    assert diagnostics["reorder_count"] == 1


def test_unknown_reorder_policy_fails_closed():
    normalized = _normalize(
        [
            _row(),
        ]
    )

    with pytest.raises(
        ValueError,
        match="reorder",
    ):
        apply_stream_anomaly_policy(
            normalized_result=normalized,
            reorder_policy="IGNORE_REORDER",
            duplicate_policy="KEEP_ALL_REPORT",
        )


def test_keep_all_report_retains_duplicate_rows():
    result = _apply(
        [
            _row(
                source_row_index=10,
                phone_sensor_ts_ns=100,
                pc_mapped_ts_ns=1000,
            ),
            _row(
                source_row_index=10,
                phone_sensor_ts_ns=101,
                pc_mapped_ts_ns=1001,
            ),
        ],
        duplicate_policy="KEEP_ALL_REPORT",
    )

    assert (
        len(result["streams"]["ACCEL"])
        == 2
    )

    diagnostics = result["diagnostics"]

    assert (
        diagnostics["duplicate_policy"]
        == "KEEP_ALL_REPORT"
    )

    assert (
        diagnostics[
            "policy_duplicate_dropped_count"
        ]
        == 0
    )


def test_keep_first_drops_later_duplicate_source_identity():
    result = _apply(
        [
            _row(
                source_row_index=10,
                phone_sensor_ts_ns=100,
                pc_mapped_ts_ns=1000,
                x=1.0,
            ),
            _row(
                source_row_index=10,
                phone_sensor_ts_ns=101,
                pc_mapped_ts_ns=1001,
                x=999.0,
            ),
        ],
        duplicate_policy="KEEP_FIRST",
    )

    rows = result["streams"]["ACCEL"]

    assert len(rows) == 1
    assert rows[0]["x"] == 1.0

    assert (
        result["diagnostics"][
            "policy_duplicate_dropped_count"
        ]
        == 1
    )


def test_keep_first_drops_later_duplicate_native_timestamp():
    result = _apply(
        [
            _row(
                source_row_index=1,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1000,
                x=1.0,
            ),
            _row(
                source_row_index=2,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1001,
                x=2.0,
            ),
        ],
        duplicate_policy="KEEP_FIRST",
    )

    rows = result["streams"]["ACCEL"]

    assert len(rows) == 1
    assert rows[0]["x"] == 1.0


def test_keep_first_drops_later_duplicate_mapped_timestamp():
    result = _apply(
        [
            _row(
                source_row_index=1,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1000,
                x=1.0,
            ),
            _row(
                source_row_index=2,
                phone_sensor_ts_ns=501,
                pc_mapped_ts_ns=1000,
                x=2.0,
            ),
        ],
        duplicate_policy="KEEP_FIRST",
    )

    rows = result["streams"]["ACCEL"]

    assert len(rows) == 1
    assert rows[0]["x"] == 1.0


def test_duplicate_identity_is_scoped_per_sensor_family():
    result = _apply(
        [
            _row(
                sensor_family="ACCEL",
                source_row_index=1,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1000,
                x=1.0,
            ),
            _row(
                sensor_family="GYRO",
                source_row_index=1,
                phone_sensor_ts_ns=500,
                pc_mapped_ts_ns=1000,
                x=10.0,
            ),
        ],
        duplicate_policy="KEEP_FIRST",
    )

    assert (
        len(result["streams"]["ACCEL"])
        == 1
    )

    assert (
        len(result["streams"]["GYRO"])
        == 1
    )

    assert (
        result["diagnostics"][
            "policy_duplicate_dropped_count"
        ]
        == 0
    )


def test_unknown_duplicate_policy_fails_closed():
    normalized = _normalize(
        [
            _row(),
        ]
    )

    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        apply_stream_anomaly_policy(
            normalized_result=normalized,
            reorder_policy="SORT_AND_REPORT",
            duplicate_policy="DROP_RANDOM",
        )


def test_one_missing_sample_is_bounded_gap():
    events = detect_source_gap_events(
        stream=_gap_stream(
            [
                100,
                110,
                130,
            ]
        ),
        expected_interval_ns=10,
        max_source_gap_ns=25,
    )

    assert events == [
        {
            "event_type":
                "BOUNDED_GAP",
            "previous_pc_mapped_ts_ns":
                110,
            "pc_mapped_ts_ns":
                130,
            "observed_gap_ns":
                20,
            "expected_interval_ns":
                10,
            "estimated_missing_count":
                1,
        }
    ]


def test_bounded_missing_burst_is_reported():
    events = detect_source_gap_events(
        stream=_gap_stream(
            [
                100,
                110,
                140,
            ]
        ),
        expected_interval_ns=10,
        max_source_gap_ns=35,
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event["event_type"]
        == "BOUNDED_GAP"
    )

    assert (
        event["observed_gap_ns"]
        == 30
    )

    assert (
        event["estimated_missing_count"]
        == 2
    )


def test_excessive_gap_is_reported_explicitly():
    events = detect_source_gap_events(
        stream=_gap_stream(
            [
                100,
                110,
                150,
            ]
        ),
        expected_interval_ns=10,
        max_source_gap_ns=30,
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event["event_type"]
        == "EXCESSIVE_GAP"
    )

    assert (
        event["observed_gap_ns"]
        == 40
    )

    assert (
        event["estimated_missing_count"]
        == 3
    )


def test_regular_stream_has_no_gap_events():
    events = detect_source_gap_events(
        stream=_gap_stream(
            [
                100,
                110,
                120,
                130,
            ]
        ),
        expected_interval_ns=10,
        max_source_gap_ns=30,
    )

    assert events == []


def test_gap_detection_requires_sorted_stream():
    with pytest.raises(
        ValueError,
        match="sorted",
    ):
        detect_source_gap_events(
            stream=_gap_stream(
                [
                    100,
                    130,
                    120,
                ]
            ),
            expected_interval_ns=10,
            max_source_gap_ns=30,
        )


def test_gap_detection_is_deterministic():
    stream = _gap_stream(
        [
            100,
            110,
            140,
            150,
            200,
        ]
    )

    first = detect_source_gap_events(
        stream=stream,
        expected_interval_ns=10,
        max_source_gap_ns=35,
    )

    second = detect_source_gap_events(
        stream=stream,
        expected_interval_ns=10,
        max_source_gap_ns=35,
    )

    assert first == second