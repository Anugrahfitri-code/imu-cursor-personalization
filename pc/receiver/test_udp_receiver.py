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
        12
    )

    assert stats.missing_packets == 1

    update_session_stats(
        stats,
        11
    )

    assert stats.packet_count == 3
    assert stats.missing_packets == 0
    assert stats.out_of_order == 1
    assert stats.duplicate_packets == 0
    
def test_duplicate_detection():

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

    assert stats.packet_count == 3
    assert stats.missing_packets == 0
    assert stats.duplicate_packets == 1

    assert stats.out_of_order == 0
    
def test_late_out_of_order_packet_resolves_missing_gap():
    stats = SessionStats()

    update_session_stats(stats, 232837)
    update_session_stats(stats, 232839)

    # Pada titik ini 232838 memang belum tiba.
    assert stats.missing_packets == 1

    # Paket yang dianggap hilang ternyata datang terlambat.
    update_session_stats(stats, 232838)
    update_session_stats(stats, 232840)

    # Final accounting harus mengoreksi missing menjadi nol.
    assert stats.packet_count == 4
    assert stats.missing_packets == 0
    assert stats.duplicate_packets == 0
    assert stats.out_of_order == 1
    assert stats.first_seq == 232837
    assert stats.last_seq == 232840
    
def test_longest_missing_burst_exact():

    stats = SessionStats()

    # Received:
    # 1, 2, [3 missing], 4, 5,
    # [6,7,8 missing], 9, 10
    for seq in [
        1,
        2,
        4,
        5,
        9,
        10,
    ]:
        update_session_stats(
            stats,
            seq
        )

    # Missing sequence:
    # 3, 6, 7, 8
    assert stats.missing_packets == 4

    # Burst terpanjang:
    # 6,7,8 = 3 packet
    assert getattr(
        stats,
        "longest_missing_burst",
        None
    ) == 3    