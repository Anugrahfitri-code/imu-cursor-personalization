from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass


EXPECTED_PROTOCOL_VERSION = 1
BUFFER_SIZE = 4096
SOCKET_TIMEOUT_S = 0.25


@dataclass(frozen=True)
class GyroSample:
    seq_global: int
    sensor_ts_phone_ns: int
    pc_receive_monotonic_ns: int
    gx: float
    gy: float
    gz: float


@dataclass(frozen=True)
class GyroSnapshot:
    sample: GyroSample | None
    packet_count: int
    invalid_count: int


def parse_data_packet(
    message: str,
    pc_receive_monotonic_ns: int,
) -> GyroSample | None:

    parts = message.strip().split(",")

    if len(parts) != 14:
        raise ValueError(
            f"expected 14 fields, got {len(parts)}"
        )

    if parts[0] != "DATA":
        raise ValueError(
            f"invalid packet type: {parts[0]}"
        )

    version = int(parts[1])

    if version != EXPECTED_PROTOCOL_VERSION:
        raise ValueError(
            f"unsupported protocol version: {version}"
        )

    sensor_type = parts[6]

    # Preview tahap ini hanya memakai GYRO.
    # ACC tetap valid tetapi tidak masuk latest gyro state.
    if sensor_type != "GYRO":
        return None

    return GyroSample(
        seq_global=int(parts[4]),
        sensor_ts_phone_ns=int(parts[7]),
        pc_receive_monotonic_ns=(
            pc_receive_monotonic_ns
        ),
        gx=float(parts[10]),
        gy=float(parts[11]),
        gz=float(parts[12]),
    )


def stream_status(
    age_s: float | None,
) -> str:

    if age_s is None:
        return "WAITING"

    if age_s < 0.250:
        return "STREAMING"

    if age_s <= 1.000:
        return "STALE"

    return "DISCONNECTED"


class LatestGyroState:

    def __init__(self) -> None:

        self._lock = threading.Lock()

        self._sample: GyroSample | None = None

        self._packet_count = 0
        self._invalid_count = 0


    def update(
        self,
        sample: GyroSample,
    ) -> None:

        with self._lock:

            self._sample = sample
            self._packet_count += 1


    def note_invalid(self) -> None:

        with self._lock:

            self._invalid_count += 1


    def snapshot(
        self,
    ) -> GyroSnapshot:

        with self._lock:

            return GyroSnapshot(
                sample=self._sample,
                packet_count=self._packet_count,
                invalid_count=self._invalid_count,
            )


class UdpGyroReceiver:

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5005,
    ) -> None:

        self.host = host
        self.port = port

        self.state = LatestGyroState()

        self._stop_event = threading.Event()

        self._thread: (
            threading.Thread | None
        ) = None

        self._socket: (
            socket.socket | None
        ) = None

        self.bind_error: (
            OSError | None
        ) = None


    def start(self) -> None:

        if self._thread is not None:
            raise RuntimeError(
                "receiver already started"
            )

        self._thread = threading.Thread(
            target=self._run,
            name="CursorPreviewUdpReceiver",
            daemon=True,
        )

        self._thread.start()


    def stop(self) -> None:

        self._stop_event.set()

        sock = self._socket

        if sock is not None:

            try:
                sock.close()

            except OSError:
                pass

        thread = self._thread

        if thread is not None:

            thread.join(
                timeout=2.0
            )


    def _run(self) -> None:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        self._socket = sock

        sock.settimeout(
            SOCKET_TIMEOUT_S
        )

        try:

            sock.bind(
                (
                    self.host,
                    self.port,
                )
            )

        except OSError as exc:

            self.bind_error = exc

            try:
                sock.close()

            finally:
                return


        try:

            while not self._stop_event.is_set():

                try:

                    payload, _addr = (
                        sock.recvfrom(
                            BUFFER_SIZE
                        )
                    )

                except socket.timeout:
                    continue

                except OSError:

                    if self._stop_event.is_set():
                        break

                    raise


                receive_ns = (
                    time.monotonic_ns()
                )


                try:

                    sample = parse_data_packet(
                        payload.decode(
                            "utf-8"
                        ),
                        pc_receive_monotonic_ns=(
                            receive_ns
                        ),
                    )

                except (
                    UnicodeDecodeError,
                    ValueError,
                ):

                    self.state.note_invalid()
                    continue


                if sample is not None:

                    self.state.update(
                        sample
                    )

        finally:

            try:
                sock.close()

            except OSError:
                pass