import csv
import socket
import time

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


HOST = "0.0.0.0"
PORT = 5005

BUFFER_SIZE = 4096

EXPECTED_PROTOCOL_VERSION = 1

# Agar Ctrl+C responsif
SOCKET_TIMEOUT_SECONDS = 0.5


# ============================================================
# DATA STRUCTURE
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
    duplicate_packets: int = 0

    received_sequences: set[int] = field(default_factory=set)
    
    @property
    def longest_missing_burst(self) -> int:
        """
        Menghitung burst missing terpanjang secara exact
        berdasarkan sequence unik yang benar-benar diterima.

        Contoh:
        received = {1, 2, 4, 5, 9, 10}

        missing:
        3
        6, 7, 8

        longest burst = 3
        """

        if len(self.received_sequences) < 2:
            return 0

        ordered = sorted(
            self.received_sequences
        )

        longest = 0

        for previous_seq, current_seq in zip(
            ordered,
            ordered[1:]
        ):

            gap = (
                current_seq
                - previous_seq
                - 1
            )

            if gap > longest:
                longest = gap

        return longest    


# ============================================================
# PARSER
# ============================================================

def parse_data_packet(message: str) -> DataPacket:


    parts = message.strip().split(",")


    if len(parts) != 14:

        raise ValueError(
            f"Expected 14 fields, got {len(parts)}"
        )


    if parts[0] != "DATA":

        raise ValueError(
            f"Invalid packet type: {parts[0]}"
        )


    version = int(parts[1])


    if version != EXPECTED_PROTOCOL_VERSION:

        raise ValueError(
            f"Unsupported protocol version {version}"
        )


    return DataPacket(

        protocol_version=version,

        session_id=parts[2],
        record_name=parts[3],

        seq_global=int(parts[4]),
        seq_sensor=int(parts[5]),

        sensor_type=parts[6],

        sensor_ts_phone_ns=int(parts[7]),
        callback_elapsed_ns=int(parts[8]),
        send_elapsed_ns=int(parts[9]),

        x=float(parts[10]),
        y=float(parts[11]),
        z=float(parts[12]),

        accuracy=int(parts[13])
    )



# ============================================================
# LOSS ACCOUNTING
# ============================================================

def update_session_stats(
        stats: SessionStats,
        seq: int
):
    stats.packet_count += 1

    # --------------------------------------------------------
    # DUPLICATE
    # --------------------------------------------------------
    # Jika sequence sudah pernah diterima, paket ini duplicate.
    # Jangan masukkan lagi ke unique sequence accounting.
    if seq in stats.received_sequences:
        stats.duplicate_packets += 1
        return

    # --------------------------------------------------------
    # FIRST PACKET
    # --------------------------------------------------------
    if not stats.received_sequences:
        stats.received_sequences.add(seq)

        stats.first_seq = seq
        stats.last_seq = seq
        stats.missing_packets = 0

        return

    assert stats.first_seq is not None
    assert stats.last_seq is not None

    # --------------------------------------------------------
    # OUT-OF-ORDER
    # --------------------------------------------------------
    # Paket unik tetapi sequence-nya lebih kecil daripada
    # sequence tertinggi yang sebelumnya sudah diterima.
    if seq < stats.last_seq:
        stats.out_of_order += 1

    # Simpan sequence unik.
    stats.received_sequences.add(seq)

    # Update range sequence aktual.
    if seq < stats.first_seq:
        stats.first_seq = seq

    if seq > stats.last_seq:
        stats.last_seq = seq

    expected = (
        stats.last_seq
        - stats.first_seq
        + 1
    )

    unique_received = len(
        stats.received_sequences
    )

    stats.missing_packets = (
        expected
        - unique_received
    )



# ============================================================
# MAIN RECEIVER
# ============================================================

def main():


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
        /
        f"udp_stream_{timestamp}.csv"
    )


    sessions = {}


    total_packets = 0
    invalid_packets = 0


    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )


    sock.bind(
        (HOST, PORT)
    )


    # ========================================================
    # FIX UTAMA
    # ========================================================

    sock.settimeout(
        SOCKET_TIMEOUT_SECONDS
    )


    print("=" * 70)

    print(
        "IMU UDP Receiver"
    )

    print(
        f"Listening on UDP {HOST}:{PORT}"
    )

    print(
        f"Protocol version: {EXPECTED_PROTOCOL_VERSION}"
    )

    print(
        f"Socket timeout: {SOCKET_TIMEOUT_SECONDS}s"
    )

    print(
        f"Output: {output_file}"
    )

    print(
        "Press CTRL+C to stop"
    )

    print("=" * 70)



    try:

        with open(
            output_file,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:


            writer = csv.writer(f)


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

                "accuracy"

            ])



            while True:


                try:

                    data, addr = sock.recvfrom(
                        BUFFER_SIZE
                    )


                except socket.timeout:

                    # hanya timeout normal
                    continue



                pc_receive_monotonic_ns = (
                    time.monotonic_ns()
                )


                pc_receive_wall_ns = (
                    time.time_ns()
                )



                try:

                    packet = parse_data_packet(
                        data.decode("utf-8")
                    )


                except Exception as e:

                    invalid_packets += 1

                    print(
                        "[INVALID]",
                        e
                    )

                    continue



                total_packets += 1



                if packet.session_id not in sessions:

                    sessions[
                        packet.session_id
                    ] = SessionStats()



                stats = sessions[
                    packet.session_id
                ]


                update_session_stats(
                    stats,
                    packet.seq_global
                )



                writer.writerow([


                    pc_receive_monotonic_ns,

                    pc_receive_wall_ns,

                    addr[0],

                    addr[1],

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

                    packet.accuracy

                ])



                if total_packets % 200 == 0:


                    f.flush()


                    expected = (

                        stats.last_seq
                        -
                        stats.first_seq
                        +
                        1
                    )


                    loss = (

                        100
                        *
                        stats.missing_packets
                        /
                        expected

                    )


                    print(

                        f"session={packet.record_name} "

                        f"packets={stats.packet_count} "

                        f"last_seq={stats.last_seq} "

                        f"missing={stats.missing_packets} "

                        f"loss={loss:.4f}% "

                        f"duplicate={stats.duplicate_packets} "

                        f"out_of_order={stats.out_of_order}"

                    )



    except KeyboardInterrupt:


        print("\nCTRL+C received. Stopping receiver...")



    finally:


        try:

            sock.close()

        except:

            pass



        print()

        print("=" * 70)

        print(
            "Receiver stopped"
        )

        print(
            f"Total valid packets : {total_packets}"
        )

        print(
            f"Invalid packets     : {invalid_packets}"
        )



        for sid, stats in sessions.items():


            expected = (

                stats.last_seq
                -
                stats.first_seq
                +
                1

            )


            loss = (

                100
                *
                stats.missing_packets
                /
                expected

            )



            print()

            print(
                f"Session {sid}"
            )

            print(
                f" received     : {stats.packet_count}"
            )

            print(
                f" missing      : {stats.missing_packets}"
            )

            print(
                f" duplicate    : {stats.duplicate_packets}"
            )

            print(
                f" loss         : {loss:.6f}%"
            )
            
            print(
                f" max burst    : {stats.longest_missing_burst}"
            )

            print(
                f" out-of-order : {stats.out_of_order}"
            )


        print()

        print(
            f"Saved to: {output_file}"
        )

        print("=" * 70)




if __name__ == "__main__":

    main()