import csv
import json
from pathlib import Path

import pytest

from pc.clock_sync.analyze_sync import analyze_session

from pc.clock_sync.session_quality import QualityEvaluationError, QualityRule, evaluate_session


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
    clock_jitter_ns: int = 0,
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

    # Real timestamp exchanges; the official analyzer owns the saved model.
    # Alternating offsets exercise the numerical residual gates when requested.
    with sync.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "session_id", "probe_phase", "probe_seq", "response_valid", "invalid_reason",
            "t1_pc_ns", "t2_phone_ns", "t3_phone_ns", "t4_pc_ns",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for probe_seq in range(1, 121):
            burst = (probe_seq - 61) // 5
            phone_mid = 1_000_000_000_000 + probe_seq * 2_000_000_000
            pc_mid = phone_mid + 4_000_000_000
            if probe_seq > 60:
                pc_mid += clock_jitter_ns * (1 if burst % 2 else -1)
            writer.writerow({
                "session_id": "test-run",
                "probe_phase": "startup" if probe_seq <= 60 else "background",
                "probe_seq": probe_seq,
                "response_valid": "True",
                "invalid_reason": "",
                "t1_pc_ns": pc_mid - 20_100_000,
                "t2_phone_ns": phone_mid - 100_000,
                "t3_phone_ns": phone_mid + 100_000,
                "t4_pc_ns": pc_mid + 20_100_000,
            })
    analyze_session(root)

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
    paths = _write_fixture(tmp_path)
    rows = _probe_rows(paths)
    for row in rows[:8]:
        row["response_valid"] = "False"
        row["invalid_reason"] = "timeout"
    _write_probe_rows(paths, rows)
    # Keep the low-rate artifact internally consistent; analyzer itself correctly
    # refuses such a session, so this must never become a quality PASS.
    data = json.loads(paths[3].read_text())
    data["response_rate"] = 112 / 120
    data["probe_counts"].update(valid=112, invalid=8)
    paths[3].write_text(json.dumps(data))
    report = _evaluate(paths)
    assert "CLOCK_RESPONSE_RATE" in report["failed_gates"]


def test_clock_residual_boundaries_are_hard_gates(tmp_path):
    report = _evaluate(_write_fixture(tmp_path, clock_jitter_ns=8_000_000))
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
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
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


def _probe_rows(paths):
    with paths[4].open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_probe_rows(paths, rows):
    with paths[4].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("field", ["alpha", "beta_ns"])
def test_clock_parameters_are_required(tmp_path, field):
    paths = _write_fixture(tmp_path)
    data = json.loads(paths[3].read_text())
    del data[field]
    paths[3].write_text(json.dumps(data))
    with pytest.raises(QualityEvaluationError):
        _evaluate(paths)


@pytest.mark.parametrize("field", ["alpha", "beta_ns"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_clock_parameters_must_be_finite(tmp_path, field, value):
    paths = _write_fixture(tmp_path)
    data = json.loads(paths[3].read_text())
    data[field] = value
    paths[3].write_text(json.dumps(data))
    with pytest.raises(QualityEvaluationError):
        _evaluate(paths)


def test_probe_timestamp_columns_are_required(tmp_path):
    paths = _write_fixture(tmp_path)
    rows = _probe_rows(paths)
    for row in rows:
        for field in ("t1_pc_ns", "t2_phone_ns", "t3_phone_ns", "t4_pc_ns"):
            del row[field]
    _write_probe_rows(paths, rows)
    with pytest.raises(QualityEvaluationError):
        _evaluate(paths)


def test_valid_probe_must_contain_reconstructable_timestamps(tmp_path):
    paths = _write_fixture(tmp_path)
    rows = _probe_rows(paths)
    rows[0]["t2_phone_ns"] = ""
    _write_probe_rows(paths, rows)
    with pytest.raises(QualityEvaluationError):
        _evaluate(paths)


@pytest.mark.parametrize("field,delta", [("alpha", 0.000001), ("beta_ns", 10_000_000)])
def test_saved_clock_mapping_must_match_raw_probe_fit(tmp_path, field, delta):
    paths = _write_fixture(tmp_path)
    data = json.loads(paths[3].read_text())
    data[field] += delta
    paths[3].write_text(json.dumps(data))
    report = _evaluate(paths)
    assert report["final_session_status"] == "FAIL"
    assert "CLOCK_ARTIFACT_CONSISTENCY" in report["failed_gates"]


def test_stale_clock_model_rejected_when_probe_timing_changes(tmp_path):
    paths = _write_fixture(tmp_path)
    rows = _probe_rows(paths)
    for row in rows:
        row["t2_phone_ns"] = str(int(row["t2_phone_ns"]) + 10_000_000)
        row["t3_phone_ns"] = str(int(row["t3_phone_ns"]) + 10_000_000)
    _write_probe_rows(paths, rows)
    report = _evaluate(paths)
    assert report["final_session_status"] == "FAIL"
    assert "CLOCK_ARTIFACT_CONSISTENCY" in report["failed_gates"]


def test_residual_gate_uses_reconstructed_evidence_not_saved_claim(tmp_path):
    paths = _write_fixture(tmp_path, clock_jitter_ns=8_000_000)
    data = json.loads(paths[3].read_text())
    data["absolute_residual_ms"] = {"p50": 0.0, "p95": 0.0, "max": 0.0}
    paths[3].write_text(json.dumps(data))
    report = _evaluate(paths)
    assert report["final_session_status"] == "FAIL"
    assert "CLOCK_ARTIFACT_CONSISTENCY" in report["failed_gates"]
    assert "CLOCK_RESIDUAL_P95" in report["failed_gates"]
    assert "CLOCK_RESIDUAL_MAX" in report["failed_gates"]


def _verify_clock(paths, *, expected_session_id="test-run", rule=QualityRule()):
    from pc.clock_sync import session_quality

    verify = getattr(session_quality, "verify_clock_artifacts", None)
    assert callable(verify), "public artifact-only clock verifier is required"
    return verify(
        clock_model_path=paths[3],
        sync_probes_path=paths[4],
        expected_session_id=expected_session_id,
        rule=rule,
    )


def test_artifact_clock_verification_accepts_matching_evidence_without_mutation(tmp_path):
    paths = _write_fixture(tmp_path)
    before = {p: p.read_bytes() for p in paths[3:]}
    report = _verify_clock(paths)
    assert report["passed"] is True
    assert report["consistency"]["passed"] is True
    assert report["session_ids"] == ["test-run"]
    assert report["identity_matches"] is True
    assert report["failed_gates"] == []
    assert report["clock"]["alpha"] == 1.0
    assert report["clock"]["beta_ns"] == 4_000_000_000
    assert before == {p: p.read_bytes() for p in paths[3:]}


def test_artifact_clock_verification_rejects_foreign_session(tmp_path):
    report = _verify_clock(_write_fixture(tmp_path), expected_session_id="other-run")
    assert report["passed"] is False
    assert "SESSION_IDENTITY" in report["failed_gates"]


def test_artifact_clock_verification_rejects_stale_model(tmp_path):
    paths = _write_fixture(tmp_path)
    data = json.loads(paths[3].read_text())
    data["beta_ns"] += 10_000_000
    paths[3].write_text(json.dumps(data))
    report = _verify_clock(paths)
    assert report["passed"] is False
    assert "CLOCK_ARTIFACT_CONSISTENCY" in report["failed_gates"]


@pytest.mark.parametrize("artifact", [3, 4])
def test_artifact_clock_verification_missing_files_raise_quality_error(tmp_path, artifact):
    paths = _write_fixture(tmp_path)
    paths[artifact].unlink()
    with pytest.raises(QualityEvaluationError):
        _verify_clock(paths)


@pytest.mark.parametrize("artifact", [3, 4])
def test_artifact_clock_verification_malformed_files_raise_quality_error(tmp_path, artifact):
    paths = _write_fixture(tmp_path)
    paths[artifact].write_text("malformed")
    with pytest.raises(QualityEvaluationError):
        _verify_clock(paths)


@pytest.mark.parametrize("gate,rule", [
    ("CLOCK_RESPONSE_RATE", QualityRule(min_clock_response_rate=1.01)),
    ("CLOCK_RESIDUAL_P95", QualityRule(max_clock_residual_p95_ms=-1.0)),
    ("CLOCK_RESIDUAL_MAX", QualityRule(max_clock_residual_max_ms=-1.0)),
    ("CLOCK_SKEW_SANITY", QualityRule(skew_sanity_ppm=0.0)),
])
def test_artifact_clock_verification_applies_supplied_quality_rule(tmp_path, gate, rule):
    report = _verify_clock(_write_fixture(tmp_path), rule=rule)
    assert report["passed"] is False
    assert gate in report["failed_gates"]


def test_artifact_clock_verification_enforces_frozen_residual_limits(tmp_path):
    report = _verify_clock(_write_fixture(tmp_path, clock_jitter_ns=8_000_000))
    assert report["passed"] is False
    assert "CLOCK_RESIDUAL_P95" in report["failed_gates"]
    assert "CLOCK_RESIDUAL_MAX" in report["failed_gates"]


def test_artifact_clock_verification_rejects_unknown_model_type(tmp_path):
    paths = _write_fixture(tmp_path)
    data = json.loads(paths[3].read_text())
    data["model"] = "unknown_mapping"
    paths[3].write_text(json.dumps(data))
    report = _verify_clock(paths)
    assert report["passed"] is False
    assert "CLOCK_MODEL_RECONSTRUCTABLE" in report["failed_gates"]
