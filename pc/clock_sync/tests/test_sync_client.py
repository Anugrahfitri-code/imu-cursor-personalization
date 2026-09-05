import socket
import threading
import csv
import pc.clock_sync.sync_client as sync_client_module
import pytest

from pc.clock_sync.sync_client import (
    BACKGROUND_BURST_INTERVAL_S,
    BACKGROUND_BURST_SIZE,
    BACKGROUND_PROBE_INTERVAL_S,
    BURST_COUNT,
    BURST_INTERVAL_S,
    ProbeResult,
    ScheduledProbe,
    build_arg_parser,
    build_probe_schedule,
    execute_probe,
    run_sync_session,
    write_probe_csv,
)


def test_probe_schedule_uses_r1_microbursts():
    schedule = build_probe_schedule(
        background_duration_s=20.0
    )

    startup = [
        item
        for item in schedule
        if item.phase == "startup"
    ]

    background = [
        item
        for item in schedule
        if item.phase == "background"
    ]

    shutdown = [
        item
        for item in schedule
        if item.phase == "shutdown"
    ]

    assert len(startup) == 30
    assert len(background) == 10
    assert len(shutdown) == 30

    background_offsets = [
        item.target_offset_s
        for item in background
    ]

    expected = [
        1.50,
        1.55,
        1.60,
        1.65,
        1.70,
        11.50,
        11.55,
        11.60,
        11.65,
        11.70,
    ]

    assert background_offsets == pytest.approx(
        expected,
        abs=1e-12,
    )

def test_r1_120s_schedule_keeps_same_probe_budget():
    schedule = build_probe_schedule(
        background_duration_s=120.0
    )

    startup = [
        p
        for p in schedule
        if p.phase == "startup"
    ]

    background = [
        p
        for p in schedule
        if p.phase == "background"
    ]

    shutdown = [
        p
        for p in schedule
        if p.phase == "shutdown"
    ]

    assert len(startup) == 30
    assert len(background) == 60
    assert len(shutdown) == 30

    assert len(schedule) == 120

def test_r1_background_microburst_constants_are_frozen():
    assert BURST_COUNT == 30
    assert BURST_INTERVAL_S == 0.05

    assert BACKGROUND_BURST_SIZE == 5
    assert BACKGROUND_PROBE_INTERVAL_S == 0.05
    assert BACKGROUND_BURST_INTERVAL_S == 10.0


def test_schedule_offsets_are_monotonic():
    schedule = build_probe_schedule(
        background_duration_s=10.0
    )

    offsets = [
        item.target_offset_s
        for item in schedule
    ]

    assert offsets == sorted(offsets)


def test_write_probe_csv_contains_required_schema(
    tmp_path,
):
    out = (
        tmp_path
        / "sync_probes.csv"
    )

    row = ProbeResult(
        session_id="m2_clock_test",
        probe_phase="startup",
        probe_seq=1,

        t1_pc_ns=100,
        t2_phone_ns=200,
        t3_phone_ns=210,
        t4_pc_ns=130,

        response_valid=True,
        invalid_reason="",
    )

    write_probe_csv(
        out,
        [row],
    )

    header = out.read_text(
        encoding="utf-8"
    ).splitlines()[0]

    assert header == (
        "session_id,probe_phase,probe_seq,"
        "t1_pc_ns,t2_phone_ns,t3_phone_ns,"
        "t4_pc_ns,pc_rtt_ns,"
        "phone_processing_ns,delay_like_ns,"
        "phone_mid_ns,pc_mid_ns,"
        "response_valid,invalid_reason,"
        "selected_low_delay,robust_inlier,"
        "model_residual_ns"
    )


def test_valid_probe_derived_metrics_are_correct():
    row = ProbeResult(
        session_id="m2_clock_test",
        probe_phase="background",
        probe_seq=7,

        t1_pc_ns=1_000,
        t2_phone_ns=2_000,
        t3_phone_ns=2_100,
        t4_pc_ns=1_500,

        response_valid=True,
        invalid_reason="",
    )

    assert row.pc_rtt_ns == 500
    assert row.phone_processing_ns == 100
    assert row.delay_like_ns == 400
    assert row.phone_mid_ns == 2_050
    assert row.pc_mid_ns == 1_250


def test_timeout_row_retains_probe_attempt_for_audit():
    row = ProbeResult.timeout(
        session_id="m2_clock_test",
        probe_phase="background",
        probe_seq=7,
        t1_pc_ns=1_000,
        t4_pc_ns=1_250,
    )

    assert row.session_id == "m2_clock_test"
    assert row.probe_phase == "background"
    assert row.probe_seq == 7

    assert row.response_valid is False
    assert row.invalid_reason == "timeout"

    assert row.t2_phone_ns is None
    assert row.t3_phone_ns is None

    assert row.pc_rtt_ns is None
    assert row.phone_processing_ns is None
    assert row.delay_like_ns is None
    assert row.phone_mid_ns is None


def test_zero_background_duration_has_only_bursts():
    schedule = build_probe_schedule(
        background_duration_s=0.0
    )

    startup = [
        p
        for p in schedule
        if p.phase == "startup"
    ]

    background = [
        p
        for p in schedule
        if p.phase == "background"
    ]

    shutdown = [
        p
        for p in schedule
        if p.phase == "shutdown"
    ]

    assert len(startup) == 30
    assert len(background) == 0
    assert len(shutdown) == 30
    
def _start_udp_responder(handler):
    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    server.bind(
        ("127.0.0.1", 0)
    )

    port = server.getsockname()[1]

    finished = threading.Event()

    def run():
        try:
            data, address = server.recvfrom(
                4096
            )

            handler(
                server,
                data.decode("utf-8"),
                address,
            )

        finally:
            server.close()
            finished.set()

    thread = threading.Thread(
        target=run,
        daemon=True,
    )

    thread.start()

    return (
        port,
        finished,
        thread,
    )


def _request_fields(message):
    parts = message.split(",")

    assert parts[0] == "SYNC_REQ"
    assert parts[1] == "1"

    seq = int(parts[2])
    t1_pc_ns = int(parts[3])

    return seq, t1_pc_ns


def test_execute_probe_accepts_valid_udp_response():

    def responder(
        server,
        message,
        address,
    ):
        seq, t1 = _request_fields(
            message
        )

        response = (
            f"SYNC_RESP,1,"
            f"{seq},"
            f"{t1},"
            f"1000000,"
            f"1001000"
        )

        server.sendto(
            response.encode("utf-8"),
            address,
        )

    port, finished, thread = (
        _start_udp_responder(
            responder
        )
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        result = execute_probe(
            sock,
            phone_ip="127.0.0.1",
            port=port,
            timeout_s=0.25,
            session_id="test",
            phase="background",
            seq=17,
        )

    finally:
        sock.close()

    finished.wait(1.0)
    thread.join(timeout=1.0)

    assert result.response_valid is True
    assert result.invalid_reason == ""

    assert result.probe_seq == 17

    assert result.t2_phone_ns == 1_000_000
    assert result.t3_phone_ns == 1_001_000

    assert (
        result.t4_pc_ns
        >= result.t1_pc_ns
    )


def test_execute_probe_ignores_stale_response_then_accepts_correct_one():

    def responder(
        server,
        message,
        address,
    ):
        seq, t1 = _request_fields(
            message
        )

        stale = (
            f"SYNC_RESP,1,"
            f"{seq + 999},"
            f"{t1},"
            f"2000000,"
            f"2001000"
        )

        correct = (
            f"SYNC_RESP,1,"
            f"{seq},"
            f"{t1},"
            f"3000000,"
            f"3001000"
        )

        server.sendto(
            stale.encode("utf-8"),
            address,
        )

        server.sendto(
            correct.encode("utf-8"),
            address,
        )

    port, finished, thread = (
        _start_udp_responder(
            responder
        )
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        result = execute_probe(
            sock,
            phone_ip="127.0.0.1",
            port=port,
            timeout_s=0.25,
            session_id="test",
            phase="background",
            seq=20,
        )

    finally:
        sock.close()

    finished.wait(1.0)
    thread.join(timeout=1.0)

    assert result.response_valid is True

    assert result.t2_phone_ns == 3_000_000
    assert result.t3_phone_ns == 3_001_000


def test_execute_probe_timeout_is_auditable():

    temporary = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    temporary.bind(
        ("127.0.0.1", 0)
    )

    unused_port = (
        temporary.getsockname()[1]
    )

    temporary.close()

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        result = execute_probe(
            sock,
            phone_ip="127.0.0.1",
            port=unused_port,
            timeout_s=0.03,
            session_id="test",
            phase="background",
            seq=21,
        )

    finally:
        sock.close()

    assert result.response_valid is False

    assert (
        result.invalid_reason
        == "timeout"
    )

    assert result.probe_seq == 21

    assert (
        result.t4_pc_ns
        >= result.t1_pc_ns
    )


def test_execute_probe_rejects_negative_delay():

    def responder(
        server,
        message,
        address,
    ):
        seq, t1 = _request_fields(
            message
        )

        # Deliberately impossible:
        # phone processing duration is far
        # greater than the PC round trip.
        response = (
            f"SYNC_RESP,1,"
            f"{seq},"
            f"{t1},"
            f"1000,"
            f"100000001000"
        )

        server.sendto(
            response.encode("utf-8"),
            address,
        )

    port, finished, thread = (
        _start_udp_responder(
            responder
        )
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        result = execute_probe(
            sock,
            phone_ip="127.0.0.1",
            port=port,
            timeout_s=0.25,
            session_id="test",
            phase="background",
            seq=22,
        )

    finally:
        sock.close()

    finished.wait(1.0)
    thread.join(timeout=1.0)

    assert result.response_valid is False

    assert (
        result.invalid_reason
        == "negative_delay"
    )


def test_execute_probe_records_last_invalid_response_reason():

    def responder(
        server,
        message,
        address,
    ):
        seq, t1 = _request_fields(
            message
        )

        wrong_seq = (
            f"SYNC_RESP,1,"
            f"{seq + 1},"
            f"{t1},"
            f"5000000,"
            f"5001000"
        )

        server.sendto(
            wrong_seq.encode("utf-8"),
            address,
        )

    port, finished, thread = (
        _start_udp_responder(
            responder
        )
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        result = execute_probe(
            sock,
            phone_ip="127.0.0.1",
            port=port,
            timeout_s=0.05,
            session_id="test",
            phase="background",
            seq=30,
        )

    finally:
        sock.close()

    finished.wait(1.0)
    thread.join(timeout=1.0)

    assert result.response_valid is False

    assert (
        result.invalid_reason
        == "seq_mismatch"
    )
    
def test_run_sync_session_persists_scheduled_probe_rows(
    tmp_path,
    monkeypatch,
):
    schedule = [
        ScheduledProbe(
            phase="startup",
            target_offset_s=0.0,
        ),
        ScheduledProbe(
            phase="background",
            target_offset_s=0.0,
        ),
        ScheduledProbe(
            phase="shutdown",
            target_offset_s=0.0,
        ),
    ]

    monkeypatch.setattr(
        sync_client_module,
        "build_probe_schedule",
        lambda *,
        background_duration_s: schedule,
    )

    def fake_execute_probe(
        sock,
        **kwargs,
    ):
        seq = kwargs["seq"]
        phase = kwargs["phase"]

        t1 = (
            1_000_000
            + seq * 10_000
        )

        return ProbeResult(
            session_id=(
                kwargs["session_id"]
            ),
            probe_phase=phase,
            probe_seq=seq,
            t1_pc_ns=t1,
            t2_phone_ns=(
                2_000_000
                + seq * 10_000
            ),
            t3_phone_ns=(
                2_000_100
                + seq * 10_000
            ),
            t4_pc_ns=t1 + 1_000,
            response_valid=True,
            invalid_reason="",
        )

    monkeypatch.setattr(
        sync_client_module,
        "execute_probe",
        fake_execute_probe,
    )

    monkeypatch.setattr(
        sync_client_module.time,
        "monotonic",
        lambda: 0.0,
    )

    monkeypatch.setattr(
        sync_client_module.time,
        "sleep",
        lambda _seconds: None,
    )

    csv_path = run_sync_session(
        phone_ip="127.0.0.1",
        session_id="runner_test",
        background_duration_s=10.0,
        output_root=tmp_path,
    )

    assert csv_path == (
        tmp_path
        / "runner_test"
        / "sync_probes.csv"
    )

    assert csv_path.exists()

    with csv_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert len(rows) == 3

    assert [
        row["probe_phase"]
        for row in rows
    ] == [
        "startup",
        "background",
        "shutdown",
    ]

    assert [
        int(row["probe_seq"])
        for row in rows
    ] == [
        1,
        2,
        3,
    ]


def test_run_sync_session_preserves_partial_log_on_interrupt(
    tmp_path,
    monkeypatch,
):
    schedule = [
        ScheduledProbe(
            phase="startup",
            target_offset_s=0.0,
        ),
        ScheduledProbe(
            phase="background",
            target_offset_s=0.0,
        ),
    ]

    monkeypatch.setattr(
        sync_client_module,
        "build_probe_schedule",
        lambda *,
        background_duration_s: schedule,
    )

    call_count = 0

    def fake_execute_probe(
        sock,
        **kwargs,
    ):
        nonlocal call_count

        call_count += 1

        if call_count == 2:
            raise KeyboardInterrupt

        return ProbeResult(
            session_id=(
                kwargs["session_id"]
            ),
            probe_phase=(
                kwargs["phase"]
            ),
            probe_seq=(
                kwargs["seq"]
            ),
            t1_pc_ns=1_000,
            t2_phone_ns=2_000,
            t3_phone_ns=2_100,
            t4_pc_ns=1_500,
            response_valid=True,
            invalid_reason="",
        )

    monkeypatch.setattr(
        sync_client_module,
        "execute_probe",
        fake_execute_probe,
    )

    monkeypatch.setattr(
        sync_client_module.time,
        "monotonic",
        lambda: 0.0,
    )

    monkeypatch.setattr(
        sync_client_module.time,
        "sleep",
        lambda _seconds: None,
    )

    with pytest.raises(
        KeyboardInterrupt
    ):
        run_sync_session(
            phone_ip="127.0.0.1",
            session_id=(
                "interrupt_test"
            ),
            background_duration_s=10.0,
            output_root=tmp_path,
        )

    csv_path = (
        tmp_path
        / "interrupt_test"
        / "sync_probes.csv"
    )

    assert csv_path.exists()

    with csv_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert len(rows) == 1
    assert rows[0]["probe_seq"] == "1"


def test_cli_parser_accepts_required_session_arguments():

    parser = build_arg_parser()

    args = parser.parse_args(
        [
            "--phone-ip",
            "192.168.8.112",

            "--session-id",
            "m2_clock_02min_01",

            "--duration-s",
            "120",
        ]
    )

    assert (
        args.phone_ip
        == "192.168.8.112"
    )

    assert (
        args.session_id
        == "m2_clock_02min_01"
    )

    assert args.duration_s == 120.0