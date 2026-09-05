from __future__ import annotations

import argparse
import csv
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from pc.clock_sync.protocol import (
    build_sync_request,
    parse_sync_response,
)


SYNC_PORT = 5006
PROBE_TIMEOUT_S = 0.25

BURST_COUNT = 30
BURST_INTERVAL_S = 0.05

BACKGROUND_BURST_SIZE = 5
BACKGROUND_PROBE_INTERVAL_S = 0.05
BACKGROUND_BURST_INTERVAL_S = 10.0

def _classify_response_error(
    error: Exception,
) -> str:
    message = str(error).lower()

    if "sequence mismatch" in message:
        return "seq_mismatch"

    if "t1 echo mismatch" in message:
        return "t1_echo_mismatch"

    if "protocol version" in message:
        return "protocol_mismatch"

    if "t3 before t2" in message:
        return "t3_before_t2"

    return "malformed_response"


@dataclass(frozen=True)
class ScheduledProbe:
    phase: str
    target_offset_s: float


@dataclass
class ProbeResult:
    session_id: str
    probe_phase: str
    probe_seq: int

    t1_pc_ns: int
    t2_phone_ns: int | None
    t3_phone_ns: int | None
    t4_pc_ns: int

    response_valid: bool
    invalid_reason: str

    selected_low_delay: bool = False
    robust_inlier: bool = False
    model_residual_ns: float | None = None

    @classmethod
    def timeout(
        cls,
        *,
        session_id: str,
        probe_phase: str,
        probe_seq: int,
        t1_pc_ns: int,
        t4_pc_ns: int,
    ) -> "ProbeResult":
        return cls(
            session_id=session_id,
            probe_phase=probe_phase,
            probe_seq=probe_seq,
            t1_pc_ns=t1_pc_ns,
            t2_phone_ns=None,
            t3_phone_ns=None,
            t4_pc_ns=t4_pc_ns,
            response_valid=False,
            invalid_reason="timeout",
        )

    @property
    def pc_rtt_ns(self) -> int | None:
        if not self.response_valid:
            return None

        return (
            self.t4_pc_ns
            - self.t1_pc_ns
        )

    @property
    def phone_processing_ns(
        self,
    ) -> int | None:

        if (
            not self.response_valid
            or self.t2_phone_ns is None
            or self.t3_phone_ns is None
        ):
            return None

        return (
            self.t3_phone_ns
            - self.t2_phone_ns
        )

    @property
    def delay_like_ns(self) -> int | None:

        pc_rtt = self.pc_rtt_ns
        phone_processing = (
            self.phone_processing_ns
        )

        if (
            pc_rtt is None
            or phone_processing is None
        ):
            return None

        return (
            pc_rtt
            - phone_processing
        )

    @property
    def phone_mid_ns(self) -> int | None:

        if (
            self.t2_phone_ns is None
            or self.t3_phone_ns is None
        ):
            return None

        return (
            self.t2_phone_ns
            + self.t3_phone_ns
        ) // 2

    @property
    def pc_mid_ns(self) -> int:
        return (
            self.t1_pc_ns
            + self.t4_pc_ns
        ) // 2

def execute_probe(
    sock: socket.socket,
    *,
    phone_ip: str,
    session_id: str,
    phase: str,
    seq: int,
    port: int = SYNC_PORT,
    timeout_s: float = PROBE_TIMEOUT_S,
) -> ProbeResult:

    if seq < 0:
        raise ValueError(
            "seq must be >= 0"
        )

    if not 0 < port <= 65535:
        raise ValueError(
            "port must be in 1..65535"
        )

    if timeout_s <= 0:
        raise ValueError(
            "timeout_s must be > 0"
        )

    # t1 belongs to the PC monotonic clock.
    # Keep request construction/send immediately
    # after this timestamp.
    t1_pc_ns = time.monotonic_ns()

    request = build_sync_request(
        seq=seq,
        t1_pc_ns=t1_pc_ns,
    ).encode("utf-8")

    sock.sendto(
        request,
        (
            phone_ip,
            port,
        ),
    )

    deadline = (
        time.monotonic()
        + timeout_s
    )

    last_invalid_reason: str | None = None

    while True:

        remaining_s = (
            deadline
            - time.monotonic()
        )

        if remaining_s <= 0:
            return ProbeResult(
                session_id=session_id,
                probe_phase=phase,
                probe_seq=seq,
                t1_pc_ns=t1_pc_ns,
                t2_phone_ns=None,
                t3_phone_ns=None,
                t4_pc_ns=time.monotonic_ns(),
                response_valid=False,
                invalid_reason=(
                    last_invalid_reason
                    or "timeout"
                ),
            )

        sock.settimeout(
            remaining_s
        )

        try:
            payload, _address = (
                sock.recvfrom(4096)
            )

        except socket.timeout:
            return ProbeResult(
                session_id=session_id,
                probe_phase=phase,
                probe_seq=seq,
                t1_pc_ns=t1_pc_ns,
                t2_phone_ns=None,
                t3_phone_ns=None,
                t4_pc_ns=time.monotonic_ns(),
                response_valid=False,
                invalid_reason=(
                    last_invalid_reason
                    or "timeout"
                ),
            )

        except ConnectionResetError:
            # On Windows, sending UDP to an
            # unused localhost port can surface
            # ICMP Port Unreachable as WinError
            # 10054 instead of socket.timeout.
            return ProbeResult(
                session_id=session_id,
                probe_phase=phase,
                probe_seq=seq,
                t1_pc_ns=t1_pc_ns,
                t2_phone_ns=None,
                t3_phone_ns=None,
                t4_pc_ns=time.monotonic_ns(),
                response_valid=False,
                invalid_reason=(
                    last_invalid_reason
                    or "timeout"
                ),
            )

        # Stamp t4 immediately after receiving
        # the datagram, before parsing it.
        t4_pc_ns = time.monotonic_ns()

        try:
            message = payload.decode(
                "utf-8"
            )

        except UnicodeDecodeError:
            last_invalid_reason = (
                "malformed_response"
            )
            continue

        try:
            response = (
                parse_sync_response(
                    message,
                    expected_seq=seq,
                    expected_t1_pc_ns=(
                        t1_pc_ns
                    ),
                )
            )

        except ValueError as error:
            last_invalid_reason = (
                _classify_response_error(
                    error
                )
            )
            continue

        result = ProbeResult(
            session_id=session_id,
            probe_phase=phase,
            probe_seq=seq,

            t1_pc_ns=t1_pc_ns,
            t2_phone_ns=(
                response.t2_phone_ns
            ),
            t3_phone_ns=(
                response.t3_phone_ns
            ),
            t4_pc_ns=t4_pc_ns,

            response_valid=True,
            invalid_reason="",
        )

        delay_like_ns = (
            result.delay_like_ns
        )

        if (
            delay_like_ns is None
            or delay_like_ns < 0
        ):
            result.response_valid = False
            result.invalid_reason = (
                "negative_delay"
            )

        return result
    
def build_probe_schedule(
    *,
    background_duration_s: float,
) -> list[ScheduledProbe]:

    if background_duration_s < 0:
        raise ValueError(
            "background_duration_s must be >= 0"
        )

    schedule: list[ScheduledProbe] = []

    for index in range(BURST_COUNT):

        schedule.append(
            ScheduledProbe(
                phase="startup",
                target_offset_s=(
                    index
                    * BURST_INTERVAL_S
                ),
            )
        )

    background_start = (
        BURST_COUNT
        * BURST_INTERVAL_S
    )

    background_burst_count = int(
        background_duration_s
        // BACKGROUND_BURST_INTERVAL_S
    )

    for burst_index in range(
        background_burst_count
    ):

        burst_start = (
            background_start
            + (
                burst_index
                * BACKGROUND_BURST_INTERVAL_S
            )
        )

        for probe_index in range(
            BACKGROUND_BURST_SIZE
        ):

            schedule.append(
                ScheduledProbe(
                    phase="background",
                    target_offset_s=(
                        burst_start
                        + (
                            probe_index
                            * BACKGROUND_PROBE_INTERVAL_S
                        )
                    ),
                )
            )

    shutdown_start = (
        background_start
        + background_duration_s
    )

    for index in range(BURST_COUNT):

        schedule.append(
            ScheduledProbe(
                phase="shutdown",
                target_offset_s=(
                    shutdown_start
                    + (
                        index
                        * BURST_INTERVAL_S
                    )
                ),
            )
        )

    return schedule


CSV_FIELDS = [
    "session_id",
    "probe_phase",
    "probe_seq",

    "t1_pc_ns",
    "t2_phone_ns",
    "t3_phone_ns",
    "t4_pc_ns",

    "pc_rtt_ns",
    "phone_processing_ns",
    "delay_like_ns",

    "phone_mid_ns",
    "pc_mid_ns",

    "response_valid",
    "invalid_reason",

    "selected_low_delay",
    "robust_inlier",
    "model_residual_ns",
]


def write_probe_csv(
    path: Path,
    rows: list[ProbeResult],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
        )

        writer.writeheader()

        for row in rows:

            writer.writerow(
                {
                    "session_id":
                        row.session_id,

                    "probe_phase":
                        row.probe_phase,

                    "probe_seq":
                        row.probe_seq,

                    "t1_pc_ns":
                        row.t1_pc_ns,

                    "t2_phone_ns":
                        row.t2_phone_ns,

                    "t3_phone_ns":
                        row.t3_phone_ns,

                    "t4_pc_ns":
                        row.t4_pc_ns,

                    "pc_rtt_ns":
                        row.pc_rtt_ns,

                    "phone_processing_ns":
                        row.phone_processing_ns,

                    "delay_like_ns":
                        row.delay_like_ns,

                    "phone_mid_ns":
                        row.phone_mid_ns,

                    "pc_mid_ns":
                        row.pc_mid_ns,

                    "response_valid":
                        row.response_valid,

                    "invalid_reason":
                        row.invalid_reason,

                    "selected_low_delay":
                        row.selected_low_delay,

                    "robust_inlier":
                        row.robust_inlier,

                    "model_residual_ns":
                        row.model_residual_ns,
                }
            )
            
def run_sync_session(
    *,
    phone_ip: str,
    session_id: str,
    background_duration_s: float,
    output_root: Path,
) -> Path:

    schedule = build_probe_schedule(
        background_duration_s=(
            background_duration_s
        )
    )

    session_dir = (
        output_root
        / session_id
    )

    csv_path = (
        session_dir
        / "sync_probes.csv"
    )

    rows: list[ProbeResult] = []

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    session_start = (
        time.monotonic()
    )

    try:
        for seq, item in enumerate(
            schedule,
            start=1,
        ):
            target_time = (
                session_start
                + item.target_offset_s
            )

            sleep_s = (
                target_time
                - time.monotonic()
            )

            if sleep_s > 0:
                time.sleep(
                    sleep_s
                )

            result = execute_probe(
                sock,
                phone_ip=phone_ip,
                session_id=session_id,
                phase=item.phase,
                seq=seq,
            )

            rows.append(
                result
            )

    finally:
        sock.close()

        write_probe_csv(
            csv_path,
            rows,
        )

    return csv_path            
def build_arg_parser(
) -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "M2.3 monotonic clock "
            "synchronization client"
        )
    )

    parser.add_argument(
        "--phone-ip",
        required=True,
        help=(
            "Current Samsung Wi-Fi "
            "IPv4 address"
        ),
    )

    parser.add_argument(
        "--session-id",
        required=True,
        help=(
            "Unique M2.3 bench "
            "session identifier"
        ),
    )

    parser.add_argument(
        "--duration-s",
        required=True,
        type=float,
        help=(
            "Background probe duration "
            "in seconds"
        ),
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            "bench_data/M2_clock_sync"
        ),
        help=(
            "Root directory for "
            "runtime clock-sync data"
        ),
    )

    return parser

def main(
    argv: list[str] | None = None,
) -> int:

    parser = build_arg_parser()

    args = parser.parse_args(
        argv
    )

    if args.duration_s < 0:
        parser.error(
            "--duration-s must be >= 0"
        )

    csv_path = run_sync_session(
        phone_ip=args.phone_ip,
        session_id=args.session_id,
        background_duration_s=(
            args.duration_s
        ),
        output_root=args.output_root,
    )

    print(
        f"Saved: {csv_path}"
    )

    return 0

if __name__ == "__main__":
    raise SystemExit(
        main()
    )