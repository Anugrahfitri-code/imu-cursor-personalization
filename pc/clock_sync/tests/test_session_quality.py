import csv
import json
from pathlib import Path

from pc.clock_sync.session_quality import QualityRule, evaluate_session


LOCAL_FIELDS = [
    "session_id", "record_name", "seq_global", "seq_sensor", "sensor_type",
    "sensor_ts_phone_ns", "callback_elapsed_ns", "x", "y", "z", "accuracy",
]
PC_FIELDS = [
    "pc_receive_monotonic_ns", "pc_receive_wall_ns", "source_ip", "source_port",
    "protocol_version", "session_id", "record_name", "seq_global", "seq_sensor",
    "sensor_type", "sensor_ts_phone_ns", "callback_elapsed_ns", "send_elapsed_ns",
    "x", "y", "z", "accuracy",
]


def _write_fixture(
    root: Path,
    *,
    total_samples: int = 200,
    missing_pc_global: set[int] | None = None,
    payload_mismatch_seq: int | None = None,
    response_rate: float = 1.0,
    residual_p95_ms: float = 0.5,
    residual_max_ms: float = 1.0,
    queue_drops: int = 0,
):
    missing_pc_global = missing_pc_global or set()
    meta = root / "meta.txt"
    local = root / "android.csv"
    pc = root / "pc.csv"
    model = root / "clock_model.json"
    sync = root / "sync_probes.csv"

    meta.write_text(
        "\n".join([
            "session_id=test-session",
            "record_name=test-run",
            "model=SM-A175F",
            f"final_total_samples={total_samples}",
            f"final_acc_samples={(total_samples + 1) // 2}",
            f"final_gyro_samples={total_samples // 2}",
            f"final_udp_packets_sent={total_samples}",
            f"final_network_queue_drops={queue_drops}",
            "final_udp_send_errors=0",
            "final_local_queue_remaining=0",
            "final_network_queue_remaining=0",
        ]) + "\n",
        encoding="utf-8",
    )

    rows = []
    sensor_counts = {"ACC": 0, "GYRO": 0}
    sensor_ts = {"ACC": 1_000_000_000, "GYRO": 1_004_000_000}
    for seq in range(1, total_samples + 1):
        sensor = "ACC" if seq % 2 else "GYRO"
        sensor_counts[sensor] += 1
        if sensor_counts[sensor] > 1:
            sensor_ts[sensor] += 8_000_000
        rows.append({
            "session_id": "test-session",
            "record_name": "test-run",
            "seq_global": str(seq),
            "seq_sensor": str(sensor_counts[sensor]),
            "sensor_type": sensor,
            "sensor_ts_phone_ns": str(sensor_ts[sensor]),
            "callback_elapsed_ns": str(sensor_ts[sensor] + 2_000_000),
            "x": "0.1",
            "y": "-0.2",
            "z": "0.3",
            "accuracy": "3",
        })

    with local.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOCAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with pc.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PC_FIELDS)
        writer.writeheader()
        for row in rows:
            seq = int(row["seq_global"])
            if seq in missing_pc_global:
                continue
            out = {
                "pc_receive_monotonic_ns": str(5_000_000_000 + seq * 1_000_000),
                "pc_receive_wall_ns": str(9_000_000_000 + seq * 1_000_000),
                "source_ip": "192.168.8.124",
                "source_port": "40000",
                "protocol_version": "1",
                **row,
                "send_elapsed_ns": str(int(row["callback_elapsed_ns"]) + 500_000),
            }
            if seq == payload_mismatch_seq:
                out["x"] = "9.9"
            writer.writerow(out)

    probe_total = 120
    probe_valid = round(probe_total * response_rate)
    probe_invalid = probe_total - probe_valid
    actual_response_rate = probe_valid / probe_total

    with sync.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["session_id", "probe_phase", "probe_seq", "response_valid", "invalid_reason"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for probe_seq in range(1, probe_total + 1):
            is_valid = probe_seq <= probe_valid
            writer.writerow({
                "session_id": "test-run",
                "probe_phase": "background",
                "probe_seq": str(probe_seq),
                "response_valid": "True" if is_valid else "False",
                "invalid_reason": "" if is_valid else "timeout",
            })

    model.write_text(json.dumps({
        "model": "affine_phone_to_pc",
        "alpha": 0.99999,
        "beta_ns": -1000.0,
        "skew_ppm": -10.0,
        "response_rate": actual_response_rate,
        "probe_counts": {
            "sent": probe_total,
            "valid": probe_valid,
            "invalid": probe_invalid,
        },
        "absolute_residual_ms": {"p50": 0.2, "p95": residual_p95_ms, "max": residual_max_ms},
        "delay_like_ms": {"p50": 5.0, "p95": 20.0},
        "phone_processing_ms": {"p50": 0.2, "p95": 0.3},
    }), encoding="utf-8")

    return meta, local, pc, model, sync


def _evaluate(paths, *, rule=QualityRule()):
    meta, local, pc, model, sync = paths
    return evaluate_session(
        android_meta_path=meta,
        android_csv_path=local,
        pc_udp_csv_path=pc,
        clock_model_path=model,
        sync_probes_path=sync,
        rule=rule,
    )


def test_clean_session_passes(tmp_path):
    report = _evaluate(_write_fixture(tmp_path))
    assert report["final_session_status"] == "PASS"
    assert report["failed_gates"] == []


def test_clock_response_below_95_percent_fails(tmp_path):
    report = _evaluate(_write_fixture(tmp_path, response_rate=0.94))
    assert "CLOCK_RESPONSE_RATE" in report["failed_gates"]


def test_clock_residual_boundaries_are_hard_gates(tmp_path):
    report = _evaluate(_write_fixture(tmp_path, residual_p95_ms=1.001, residual_max_ms=5.001))
    assert "CLOCK_RESIDUAL_P95" in report["failed_gates"]
    assert "CLOCK_RESIDUAL_MAX" in report["failed_gates"]


def test_packet_loss_gate_uses_android_local_denominator(tmp_path):
    paths = _write_fixture(tmp_path, total_samples=1000, missing_pc_global={100, 200})
    report = _evaluate(paths)
    assert report["transport"]["missing_packets"] == 2
    assert report["transport"]["packet_loss_percent"] == 0.2
    assert "PACKET_LOSS" in report["failed_gates"]


def test_burst_gap_can_fail_even_when_loss_gate_passes(tmp_path):
    # Five consecutive missing ACC updates: 6 native ~8 ms intervals = 48 ms;
    # six consecutive missing ACC updates: 7 intervals = 56 ms and should fail.
    total = 12_000
    # ACC uses odd global seq; remove six consecutive ACC samples.
    missing = {2001, 2003, 2005, 2007, 2009, 2011}
    report = _evaluate(_write_fixture(tmp_path, total_samples=total, missing_pc_global=missing))
    assert report["transport"]["packet_loss_percent"] <= 0.10
    assert report["transport"]["max_per_sensor_delivery_gap_ms"] == 56.0
    assert "PACKET_LOSS" not in report["failed_gates"]
    assert "MAX_SENSOR_DELIVERY_GAP" in report["failed_gates"]


def test_payload_mismatch_fails(tmp_path):
    report = _evaluate(_write_fixture(tmp_path, payload_mismatch_seq=10))
    assert report["transport"]["payload_mismatch_count"] == 1
    assert "PAYLOAD_INTEGRITY" in report["failed_gates"]


def test_android_queue_drop_fails(tmp_path):
    report = _evaluate(_write_fixture(tmp_path, queue_drops=1))
    assert "ANDROID_QUEUE_SEND_INTEGRITY" in report["failed_gates"]


def test_session_identity_mismatch_fails(tmp_path):
    paths = _write_fixture(tmp_path)
    meta, local, pc, model, sync = paths

    rows = list(csv.DictReader(pc.open(newline="", encoding="utf-8")))
    rows[0]["record_name"] = "foreign-run"
    with pc.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    report = _evaluate(paths)
    assert "SESSION_IDENTITY" in report["failed_gates"]


def test_sync_probe_session_identity_mismatch_fails(tmp_path):
    paths = _write_fixture(tmp_path)
    meta, local, pc, model, sync = paths

    rows = list(csv.DictReader(sync.open(newline="", encoding="utf-8")))
    rows[0]["session_id"] = "foreign-run"
    with sync.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["session_id", "probe_phase", "probe_seq", "response_valid", "invalid_reason"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    report = _evaluate(paths)
    assert "SESSION_IDENTITY" in report["failed_gates"]


def test_clock_model_must_match_sync_probe_counts(tmp_path):
    paths = _write_fixture(tmp_path)
    meta, local, pc, model, sync = paths

    data = json.loads(model.read_text(encoding="utf-8"))
    data["probe_counts"]["valid"] -= 1
    data["probe_counts"]["invalid"] += 1
    model.write_text(json.dumps(data), encoding="utf-8")

    report = _evaluate(paths)
    assert "CLOCK_ARTIFACT_CONSISTENCY" in report["failed_gates"]
