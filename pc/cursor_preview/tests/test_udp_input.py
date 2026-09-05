import pytest

from pc.cursor_preview.udp_input import (
    GyroSample,
    LatestGyroState,
    parse_data_packet,
    stream_status,
)


VALID_GYRO = (
    "DATA,1,20260905_120734_878,m2_preview,42,21,GYRO,"
    "55023193819033,55023194819033,55023195000000,"
    "0.1,-0.2,0.3,3"
)

VALID_ACC = (
    "DATA,1,20260905_120734_878,m2_preview,43,22,ACC,"
    "55023193829033,55023194919033,55023195100000,"
    "1.0,2.0,3.0,3"
)


def test_valid_gyro_packet_parses_to_sample():
    sample = parse_data_packet(
        VALID_GYRO,
        pc_receive_monotonic_ns=123456789,
    )

    assert sample == GyroSample(
        seq_global=42,
        sensor_ts_phone_ns=55023193819033,
        pc_receive_monotonic_ns=123456789,
        gx=0.1,
        gy=-0.2,
        gz=0.3,
    )


def test_non_gyro_packet_returns_none():
    result = parse_data_packet(
        VALID_ACC,
        pc_receive_monotonic_ns=123,
    )

    assert result is None


def test_malformed_packet_is_rejected():
    with pytest.raises(
        ValueError,
        match="14 fields",
    ):
        parse_data_packet(
            "DATA,1,too,few,fields",
            pc_receive_monotonic_ns=123,
        )


def test_unsupported_protocol_version_is_rejected():
    message = VALID_GYRO.replace(
        "DATA,1,",
        "DATA,2,",
        1,
    )

    with pytest.raises(
        ValueError,
        match="protocol version",
    ):
        parse_data_packet(
            message,
            pc_receive_monotonic_ns=123,
        )


def test_latest_state_uses_newest_gyro_sample():
    state = LatestGyroState()

    first = GyroSample(
        seq_global=10,
        sensor_ts_phone_ns=1000,
        pc_receive_monotonic_ns=2000,
        gx=0.1,
        gy=0.2,
        gz=0.3,
    )

    second = GyroSample(
        seq_global=11,
        sensor_ts_phone_ns=1100,
        pc_receive_monotonic_ns=2100,
        gx=0.4,
        gy=0.5,
        gz=0.6,
    )

    state.update(first)
    state.update(second)

    snapshot = state.snapshot()

    assert snapshot.sample == second
    assert snapshot.packet_count == 2


def test_stream_status_thresholds():
    assert stream_status(None) == "WAITING"

    assert stream_status(
        0.249
    ) == "STREAMING"

    assert stream_status(
        0.250
    ) == "STALE"

    assert stream_status(
        1.000
    ) == "STALE"

    assert stream_status(
        1.001
    ) == "DISCONNECTED"