from __future__ import annotations

from dataclasses import dataclass


SYNC_PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class SyncResponse:
    seq: int
    t1_pc_ns: int
    t2_phone_ns: int
    t3_phone_ns: int


def build_sync_request(
    seq: int,
    t1_pc_ns: int,
) -> str:

    if seq < 0:
        raise ValueError(
            "seq must be >= 0"
        )

    if t1_pc_ns < 0:
        raise ValueError(
            "t1_pc_ns must be >= 0"
        )

    return (
        f"SYNC_REQ,"
        f"{SYNC_PROTOCOL_VERSION},"
        f"{seq},"
        f"{t1_pc_ns}"
    )


def parse_sync_response(
    message: str,
    *,
    expected_seq: int,
    expected_t1_pc_ns: int,
) -> SyncResponse:

    parts = message.strip().split(",")

    if len(parts) != 6:
        raise ValueError(
            f"expected 6 fields, got {len(parts)}"
        )

    if parts[0] != "SYNC_RESP":
        raise ValueError(
            f"invalid message type: {parts[0]}"
        )

    try:
        version = int(parts[1])
        seq = int(parts[2])
        t1_pc_ns = int(parts[3])
        t2_phone_ns = int(parts[4])
        t3_phone_ns = int(parts[5])

    except ValueError as exc:
        raise ValueError(
            "numeric field parse error"
        ) from exc

    if version != SYNC_PROTOCOL_VERSION:
        raise ValueError(
            f"unsupported protocol version: "
            f"{version}"
        )

    if seq != expected_seq:
        raise ValueError(
            f"sequence mismatch: "
            f"expected {expected_seq}, "
            f"got {seq}"
        )

    if t1_pc_ns != expected_t1_pc_ns:
        raise ValueError(
            "t1 echo mismatch"
        )

    if t3_phone_ns < t2_phone_ns:
        raise ValueError(
            "t3 before t2"
        )

    return SyncResponse(
        seq=seq,
        t1_pc_ns=t1_pc_ns,
        t2_phone_ns=t2_phone_ns,
        t3_phone_ns=t3_phone_ns,
    )