import csv
import socket
import time

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


HOST = "0.0.0.0"
PORT = 5005
BUFFER_SIZE = 4096

EXPECTED_PROTOCOL_VERSION = 1


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class DataPacket:
    protocol_version: int

    session_id: str
    record_name: str

    seq_global: int
    seq_sensor: int

    sensor_type: str

    sensor_ts_phone_ns: int
    callback_elapsed_ns: int
    send_elapsed_ns: int

    x: float
    y: float
    z: float

    accuracy: int


@dataclass
class SessionStats:
    packet_count: int = 0

    first_seq: int | None = None
    last_seq: int | None = None

    missing_packets: int = 0
    out_of_order: int = 0


# ============================================================
# PACKET PARSER
# ============================================================

def parse_data_packet(message: str) -> DataPacket:

    parts = message.strip().split(",")

    if len(parts) != 14:
        raise ValueError(
            f"Expected 14 fields, received {len(parts)}"
        )

    packet_type = parts[0]

    if packet_type != "DATA":
        raise ValueError(
            f"Unsupported packet type: {packet_type}"
        )

    protocol_version = int(parts[1])

    if protocol_version != EXPECTED_PROTOCOL_VERSION:
        raise ValueError(
            f"Unsupported protocol version: {protocol_version}"
        )

    sensor_type = parts[6]

    if sensor_type not in {"ACC", "GYRO"}:
        raise ValueError(
            f"Invalid sensor type: {sensor_type}"
        )

    return DataPacket(
        protocol_version=protocol_version,

        session_id=parts[2],
        record_name=parts[3],

        seq_global=int(parts[4]),
        seq_sensor=int(parts[5]),

        sensor_type=sensor_type,

        sensor_ts_phone_ns=int(parts[7]),
        callback_elapsed_ns=int(parts[8]),
        send_elapsed_ns=int(parts[9]),

        x=float(parts[10]),
        y=float(parts[11]),
        z=float(parts[12]),

        accuracy=int(parts[13]),
    )


# ============================================================
# SESSION LOSS ACCOUNTING
# ============================================================

def update_session_stats(
    stats: SessionStats,
    seq_global: int,
) -> None:

    stats.packet_count += 1

    if stats.first_seq is None:
        stats.first_seq = seq_global
        stats.last_seq = seq_global
        return

    assert stats.last_seq is not None

    if seq_global > stats.last_seq + 1:

        stats.missing_packets += (
            seq_global
            - stats.last_seq
            - 1
        )

    elif seq_global <= stats.last_seq:

        stats.out_of_order += 1

    if seq_global > stats.last_seq:
        stats.last_seq = seq_global


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    output_dir = (
        Path(__file__)
        .resolve()
        .parent
        / "logs"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_file = (
        output_dir
        / f"udp_stream_{timestamp}.csv"
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    sock.bind(
        (HOST, PORT)
    )


    print("=" * 70)
    print("IMU UDP Receiver")
    print(f"Listening on UDP {HOST}:{PORT}")
    print(f"Protocol version: {EXPECTED_PROTOCOL_VERSION}")
    print(f"Output: {output_file}")
    print("Press CTRL+C to stop")
    print("=" * 70)


    sessions: dict[str, SessionStats] = {}

    total_packets = 0
    invalid_packets = 0


    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file_handle:

        writer = csv.writer(
            file_handle
        )


        writer.writerow([
            "pc_receive_monotonic_ns",
            "pc_receive_wall_ns",

            "source_ip",
            "source_port",

            "protocol_version",

            "session_id",
            "record_name",

            "seq_global",
            "seq_sensor",

            "sensor_type",

            "sensor_ts_phone_ns",
            "callback_elapsed_ns",
            "send_elapsed_ns",

            "x",
            "y",
            "z",

            "accuracy",
        ])


        try:

            while True:

                data, address = sock.recvfrom(
                    BUFFER_SIZE
                )


                
                # PC receive timestamps are captured
                # immediately after recvfrom returns.


                pc_receive_monotonic_ns = (
                    time.monotonic_ns()
                )

                pc_receive_wall_ns = (
                    time.time_ns()
                )


                try:

                    message = data.decode(
                        "utf-8"
                    )


                    packet = parse_data_packet(
                        message
                    )


                except Exception as error:

                    invalid_packets += 1

                    print(
                        f"[INVALID PACKET] {error}"
                    )

                    continue


                total_packets += 1


                if packet.session_id not in sessions:

                    sessions[
                        packet.session_id
                    ] = SessionStats()


                session_stats = sessions[
                    packet.session_id
                ]


                update_session_stats(
                    session_stats,
                    packet.seq_global
                )


                writer.writerow([
                    pc_receive_monotonic_ns,
                    pc_receive_wall_ns,

                    address[0],
                    address[1],

                    packet.protocol_version,

                    packet.session_id,
                    packet.record_name,

                    packet.seq_global,
                    packet.seq_sensor,

                    packet.sensor_type,

                    packet.sensor_ts_phone_ns,
                    packet.callback_elapsed_ns,
                    packet.send_elapsed_ns,

                    packet.x,
                    packet.y,
                    packet.z,

                    packet.accuracy,
                ])


                if total_packets % 200 == 0:

                    file_handle.flush()


                    expected = (

                        (
                            session_stats.last_seq
                            - session_stats.first_seq
                            + 1
                        )

                        if (
                            session_stats.first_seq
                            is not None

                            and session_stats.last_seq
                            is not None
                        )

                        else 0
                    )


                    loss_pct = (

                        (
                            100.0
                            * session_stats.missing_packets
                            / expected
                        )

                        if expected > 0

                        else 0.0
                    )


                    print(
                        f"session={packet.record_name} "
                        f"packets={session_stats.packet_count} "
                        f"last_seq={session_stats.last_seq} "
                        f"missing={session_stats.missing_packets} "
                        f"loss={loss_pct:.4f}% "
                        f"out_of_order={session_stats.out_of_order}"
                    )


        except KeyboardInterrupt:

            pass


    sock.close()


    print()
    print("=" * 70)
    print("Receiver stopped")
    print(f"Total valid packets : {total_packets}")
    print(f"Invalid packets     : {invalid_packets}")
    print()


    for session_id, stats in sessions.items():

        expected = (

            (
                stats.last_seq
                - stats.first_seq
                + 1
            )

            if (
                stats.first_seq is not None
                and stats.last_seq is not None
            )

            else 0
        )


        loss_pct = (

            (
                100.0
                * stats.missing_packets
                / expected
            )

            if expected > 0

            else 0.0
        )


        print(
            f"Session {session_id}"
        )

        print(
            f"  received     : {stats.packet_count}"
        )

        print(
            f"  missing      : {stats.missing_packets}"
        )

        print(
            f"  loss         : {loss_pct:.6f}%"
        )

        print(
            f"  out-of-order : {stats.out_of_order}"
        )

        print()


    print(
        f"Saved to: {output_file}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()