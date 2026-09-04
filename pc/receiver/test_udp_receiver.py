from udp_receiver import (
    parse_data_packet,
    SessionStats,
    update_session_stats,
)


def test_parse_valid_data_packet():

    message = (
        "DATA,1,"
        "20260905_001500_123,"
        "m2_udp_test_01,"
        "100,50,"
        "GYRO,"
        "123456789000,"
        "123456790000,"
        "123456791000,"
        "0.1,-0.2,0.3,"
        "3"
    )

    packet = parse_data_packet(message)

    assert packet.protocol_version == 1

    assert (
        packet.session_id
        == "20260905_001500_123"
    )

    assert (
        packet.record_name
        == "m2_udp_test_01"
    )

    assert packet.seq_global == 100
    assert packet.seq_sensor == 50

    assert packet.sensor_type == "GYRO"

    assert (
        packet.sensor_ts_phone_ns
        == 123456789000
    )

    assert (
        packet.callback_elapsed_ns
        == 123456790000
    )

    assert (
        packet.send_elapsed_ns
        == 123456791000
    )

    assert packet.x == 0.1
    assert packet.y == -0.2
    assert packet.z == 0.3

    assert packet.accuracy == 3


def test_missing_packet_detection():

    stats = SessionStats()

    update_session_stats(
        stats,
        1
    )

    update_session_stats(
        stats,
        2
    )

    update_session_stats(
        stats,
        5
    )

    assert stats.packet_count == 3

    assert stats.missing_packets == 2

    assert stats.out_of_order == 0


def test_out_of_order_detection():

    stats = SessionStats()

    update_session_stats(
        stats,
        10
    )

    update_session_stats(
        stats,
        11
    )

    update_session_stats(
        stats,
        10
    )

    assert stats.out_of_order == 1