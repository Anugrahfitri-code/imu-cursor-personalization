from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pc.clock_sync.analyze_sync import _half_summary, _residual_summary, _row_to_probe
from pc.clock_sync.clock_model import (
    ProbeObservation, fit_half_diagnostics, fit_robust_clock_model, percentile,
)


RULE_VERSION = "v1.0-frozen"
EXPECTED_DEVICE_MODEL = "SM-A175F"
MIN_CLOCK_RESPONSE_RATE = 0.95
MAX_CLOCK_RESIDUAL_P95_MS = 1.0
MAX_CLOCK_RESIDUAL_MAX_MS = 5.0
SKEW_SANITY_PPM = 1000.0
MAX_PACKET_LOSS_PERCENT = 0.10
MAX_PER_SENSOR_DELIVERY_GAP_MS = 50.0

SHARED_PAYLOAD_FIELDS = (
    "session_id",
    "record_name",
    "seq_sensor",
    "sensor_type",
    "sensor_ts_phone_ns",
    "callback_elapsed_ns",
    "accuracy",
)
FLOAT_PAYLOAD_FIELDS = ("x", "y", "z")


@dataclass(frozen=True)
class QualityRule:
    version: str = RULE_VERSION
    expected_device_model: str = EXPECTED_DEVICE_MODEL
    min_clock_response_rate: float = MIN_CLOCK_RESPONSE_RATE
    max_clock_residual_p95_ms: float = MAX_CLOCK_RESIDUAL_P95_MS
    max_clock_residual_max_ms: float = MAX_CLOCK_RESIDUAL_MAX_MS
    skew_sanity_ppm: float = SKEW_SANITY_PPM
    max_packet_loss_percent: float = MAX_PACKET_LOSS_PERCENT
    max_per_sensor_delivery_gap_ms: float = MAX_PER_SENSOR_DELIVERY_GAP_MS


@dataclass
class GateResult:
    name: str
    passed: bool
    observed: Any
    criterion: str


class QualityEvaluationError(ValueError):
    pass


def _parse_meta(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _required_int(meta: dict[str, str], key: str) -> int:
    if key not in meta:
        raise QualityEvaluationError(f"metadata missing required key: {key}")
    try:
        return int(meta[key])
    except ValueError as exc:
        raise QualityEvaluationError(f"metadata key {key} is not an integer: {meta[key]!r}") from exc


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _assert_fields(rows: list[dict[str, str]], required: set[str], label: str) -> None:
    if not rows:
        raise QualityEvaluationError(f"{label} CSV has no data rows")
    missing = required - set(rows[0])
    if missing:
        raise QualityEvaluationError(f"{label} CSV missing fields: {sorted(missing)}")


def _to_int(row: dict[str, str], field: str, label: str) -> int:
    try:
        return int(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise QualityEvaluationError(f"invalid {label}.{field}: {row.get(field)!r}") from exc


def _local_integrity(rows: list[dict[str, str]], meta: dict[str, str]) -> dict[str, Any]:
    required = {
        "seq_global",
        "seq_sensor",
        "sensor_type",
        "sensor_ts_phone_ns",
        "session_id",
        "record_name",
        "callback_elapsed_ns",
        "x",
        "y",
        "z",
        "accuracy",
    }
    _assert_fields(rows, required, "Android local")

    seqs = [_to_int(row, "seq_global", "Android local") for row in rows]
    unique_seqs = set(seqs)
    minimum = min(seqs)
    maximum = max(seqs)
    expected_range = maximum - minimum + 1
    missing_within_range = expected_range - len(unique_seqs)
    duplicate_extra = len(seqs) - len(unique_seqs)

    per_sensor_monotonic: dict[str, bool] = {}
    per_sensor_seq_contiguous: dict[str, bool] = {}
    per_sensor_max_interval_ms: dict[str, float] = {}

    by_sensor: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_sensor.setdefault(row["sensor_type"], []).append(row)

    for sensor, sensor_rows in by_sensor.items():
        sensor_rows = sorted(sensor_rows, key=lambda r: _to_int(r, "seq_sensor", "Android local"))
        sensor_seq = [_to_int(r, "seq_sensor", "Android local") for r in sensor_rows]
        sensor_ts = [_to_int(r, "sensor_ts_phone_ns", "Android local") for r in sensor_rows]
        per_sensor_seq_contiguous[sensor] = (
            len(set(sensor_seq)) == len(sensor_seq)
            and sensor_seq == list(range(sensor_seq[0], sensor_seq[-1] + 1))
        )
        deltas = [b - a for a, b in zip(sensor_ts, sensor_ts[1:])]
        per_sensor_monotonic[sensor] = all(delta > 0 for delta in deltas)
        per_sensor_max_interval_ms[sensor] = max(deltas, default=0) / 1_000_000.0

    meta_total = _required_int(meta, "final_total_samples")

    return {
        "rows": len(rows),
        "meta_total_samples": meta_total,
        "seq_min": minimum,
        "seq_max": maximum,
        "unique_sequences": len(unique_seqs),
        "missing_within_local_range": missing_within_range,
        "duplicate_extra_rows": duplicate_extra,
        "row_count_matches_metadata": len(rows) == meta_total,
        "sequence_span_matches_metadata": expected_range == meta_total,
        "sequence_starts_at_one": minimum == 1,
        "sequence_ends_at_metadata_total": maximum == meta_total,
        "per_sensor_timestamp_monotonic": per_sensor_monotonic,
        "per_sensor_seq_contiguous": per_sensor_seq_contiguous,
        "per_sensor_max_interval_ms": per_sensor_max_interval_ms,
    }


def _transport_integrity(
    local_rows: list[dict[str, str]],
    pc_rows: list[dict[str, str]],
) -> dict[str, Any]:
    pc_required = {
        "seq_global",
        "seq_sensor",
        "sensor_type",
        "sensor_ts_phone_ns",
        "session_id",
        "record_name",
        "callback_elapsed_ns",
        "x",
        "y",
        "z",
        "accuracy",
    }
    _assert_fields(pc_rows, pc_required, "PC UDP")

    local_by_seq: dict[int, dict[str, str]] = {}
    for row in local_rows:
        seq = _to_int(row, "seq_global", "Android local")
        if seq not in local_by_seq:
            local_by_seq[seq] = row

    pc_unique_by_seq: dict[int, dict[str, str]] = {}
    pc_order: list[int] = []
    duplicate_extra = 0
    out_of_order_events = 0
    max_seen: int | None = None

    for row in pc_rows:
        seq = _to_int(row, "seq_global", "PC UDP")
        pc_order.append(seq)
        if max_seen is not None and seq < max_seen:
            out_of_order_events += 1
        max_seen = seq if max_seen is None else max(max_seen, seq)
        if seq in pc_unique_by_seq:
            duplicate_extra += 1
        else:
            pc_unique_by_seq[seq] = row

    local_set = set(local_by_seq)
    pc_set = set(pc_unique_by_seq)
    missing = sorted(local_set - pc_set)
    unexpected = sorted(pc_set - local_set)
    loss_percent = 100.0 * len(missing) / len(local_set)

    payload_mismatch_count = 0
    payload_mismatch_examples: list[int] = []
    for seq in sorted(local_set & pc_set):
        left = local_by_seq[seq]
        right = pc_unique_by_seq[seq]
        mismatch = False
        for field in SHARED_PAYLOAD_FIELDS:
            if left[field].strip() != right[field].strip():
                mismatch = True
                break
        if not mismatch:
            for field in FLOAT_PAYLOAD_FIELDS:
                try:
                    if float(left[field]) != float(right[field]):
                        mismatch = True
                        break
                except ValueError:
                    mismatch = True
                    break
        if mismatch:
            payload_mismatch_count += 1
            if len(payload_mismatch_examples) < 10:
                payload_mismatch_examples.append(seq)

    local_by_sensor: dict[str, list[dict[str, str]]] = {}
    for row in local_rows:
        local_by_sensor.setdefault(row["sensor_type"], []).append(row)

    pc_received_sensor_seqs: dict[str, set[int]] = {}
    for row in pc_unique_by_seq.values():
        pc_received_sensor_seqs.setdefault(row["sensor_type"], set()).add(
            _to_int(row, "seq_sensor", "PC UDP")
        )

    per_sensor: dict[str, dict[str, Any]] = {}
    max_gap_ms = 0.0
    max_gap_sensor = ""

    for sensor, sensor_rows in local_by_sensor.items():
        ordered = sorted(sensor_rows, key=lambda r: _to_int(r, "seq_sensor", "Android local"))
        received_sensor_seq = pc_received_sensor_seqs.get(sensor, set())
        received_positions = [
            (idx, _to_int(row, "sensor_ts_phone_ns", "Android local"))
            for idx, row in enumerate(ordered)
            if _to_int(row, "seq_sensor", "Android local") in received_sensor_seq
        ]
        sensor_missing = len(ordered) - len(received_positions)
        sensor_max_gap_ms = 0.0

        if received_positions:
            first_idx, first_ts = received_positions[0]
            last_idx, last_ts = received_positions[-1]
            if first_idx > 0:
                first_local_ts = _to_int(ordered[0], "sensor_ts_phone_ns", "Android local")
                sensor_max_gap_ms = max(sensor_max_gap_ms, (first_ts - first_local_ts) / 1_000_000.0)
            for (_, prev_ts), (_, current_ts) in zip(received_positions, received_positions[1:]):
                sensor_max_gap_ms = max(sensor_max_gap_ms, (current_ts - prev_ts) / 1_000_000.0)
            if last_idx < len(ordered) - 1:
                last_local_ts = _to_int(ordered[-1], "sensor_ts_phone_ns", "Android local")
                sensor_max_gap_ms = max(sensor_max_gap_ms, (last_local_ts - last_ts) / 1_000_000.0)
        elif ordered:
            first_ts = _to_int(ordered[0], "sensor_ts_phone_ns", "Android local")
            last_ts = _to_int(ordered[-1], "sensor_ts_phone_ns", "Android local")
            sensor_max_gap_ms = (last_ts - first_ts) / 1_000_000.0

        per_sensor[sensor] = {
            "local_samples": len(ordered),
            "received_unique_samples": len(received_positions),
            "missing_samples": sensor_missing,
            "max_delivery_gap_ms": sensor_max_gap_ms,
        }
        if sensor_max_gap_ms > max_gap_ms:
            max_gap_ms = sensor_max_gap_ms
            max_gap_sensor = sensor

    return {
        "pc_rows": len(pc_rows),
        "pc_unique_received": len(pc_unique_by_seq),
        "missing_packets": len(missing),
        "packet_loss_percent": loss_percent,
        "duplicate_extra_rows": duplicate_extra,
        "out_of_order_events": out_of_order_events,
        "unexpected_pc_sequences": len(unexpected),
        "payload_mismatch_count": payload_mismatch_count,
        "payload_mismatch_example_seq": payload_mismatch_examples,
        "max_per_sensor_delivery_gap_ms": max_gap_ms,
        "max_gap_sensor": max_gap_sensor,
        "per_sensor": per_sensor,
    }


def _clock_values(data: dict[str, Any]) -> dict[str, float | int]:
    """Validate the numerical schema emitted by the official frozen analyzer."""
    sections = {
        "": ("alpha", "beta_ns", "skew_ppm", "response_rate"),
        "absolute_residual_ms": ("p50", "p95", "max"),
        "delay_like_ms": ("p50", "p95"),
        "phone_processing_ms": ("p50", "p95"),
        "first_half": ("alpha", "skew_ppm", "residual_p50_ms", "residual_p95_ms"),
        "second_half": ("alpha", "skew_ppm", "residual_p50_ms", "residual_p95_ms"),
        "probe_counts": ("sent", "valid", "invalid", "selected", "inliers"),
    }
    values: dict[str, float | int] = {}
    try:
        for section, fields in sections.items():
            source = data[section] if section else data
            for field in fields:
                key = f"{section}.{field}" if section else field
                value = source[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{key} must be numeric")
                if not math.isfinite(value):
                    raise ValueError(f"{key} must be finite")
                if section == "probe_counts" and (not isinstance(value, int) or value < 0):
                    raise ValueError(f"{key} must be a nonnegative integer")
                values[key] = value
        if values["alpha"] <= 0:
            raise ValueError("alpha must be positive")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise QualityEvaluationError(f"invalid clock model schema: {exc}") from exc
    return values


def _clock_summary(data: dict[str, Any]) -> dict[str, Any]:
    values = _clock_values(data)
    return {
        "model_present": True,
        "model": data.get("model"),
        "alpha": values["alpha"],
        "beta_ns": values["beta_ns"],
        "response_rate": values["response_rate"],
        "skew_ppm": values["skew_ppm"],
        "residual_p50_ms": values["absolute_residual_ms.p50"],
        "residual_p95_ms": values["absolute_residual_ms.p95"],
        "residual_max_ms": values["absolute_residual_ms.max"],
        "probe_counts": data["probe_counts"],
        "model_values": values,
    }


def _clock_metrics(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"model_present": False}
    except json.JSONDecodeError as exc:
        raise QualityEvaluationError(f"invalid clock model JSON: {exc}") from exc
    return _clock_summary(data)


def _reconstruct_clock(probes: list[ProbeObservation], total: int) -> dict[str, Any]:
    # The frozen analyzer exposes no per-run fit settings: use its same robust
    # fit, low-delay selection, half diagnostics, and residual summaries. Unlike
    # analyze_session, this path does not rewrite any evidence artifacts.
    try:
        model = fit_robust_clock_model(probes)
        first, second = fit_half_diagnostics(probes)
        return _clock_summary({
            "model": "affine_phone_to_pc",
            "alpha": model.alpha,
            "beta_ns": model.beta_ns,
            "skew_ppm": model.skew_ppm,
            "response_rate": len(probes) / total,
            "probe_counts": {
                "sent": total,
                "valid": len(probes),
                "invalid": total - len(probes),
                "selected": len(model.selected_probe_seqs),
                "inliers": len(model.inlier_probe_seqs),
            },
            "absolute_residual_ms": _residual_summary(model),
            "delay_like_ms": {
                label: percentile((p.delay_like_ns for p in probes), q) / 1_000_000
                for label, q in (("p50", 0.5), ("p95", 0.95))
            },
            "phone_processing_ms": {
                label: percentile((p.phone_processing_ns for p in probes), q) / 1_000_000
                for label, q in (("p50", 0.5), ("p95", 0.95))
            },
            "first_half": _half_summary(first),
            "second_half": _half_summary(second),
        })
    except (ValueError, OverflowError) as exc:
        raise QualityEvaluationError(f"clock model cannot be reconstructed: {exc}") from exc


def _sync_probe_metrics(path: Path) -> dict[str, Any]:
    rows = _read_csv(path)
    required = {
        "session_id", "probe_phase", "probe_seq", "response_valid", "invalid_reason",
        "t1_pc_ns", "t2_phone_ns", "t3_phone_ns", "t4_pc_ns",
    }
    _assert_fields(rows, required, "Clock sync probes")

    session_ids = sorted({row["session_id"].strip() for row in rows})
    probes: list[ProbeObservation] = []
    invalid_reason_counts: dict[str, int] = {}
    for row in rows:
        flag = str(row["response_valid"]).strip().lower()
        if flag not in {"true", "false"}:
            raise QualityEvaluationError("clock response_valid must be True or False")
        if flag == "true":
            try:
                probe = _row_to_probe(row)
            except (KeyError, TypeError, AttributeError) as exc:
                raise QualityEvaluationError("invalid clock probe timestamp fields") from exc
            if probe is None:
                raise QualityEvaluationError(
                    f"valid clock probe {row['probe_seq']} has invalid timestamps"
                )
            probes.append(probe)
        else:
            reason = row.get("invalid_reason", "").strip() or "unspecified"
            invalid_reason_counts[reason] = invalid_reason_counts.get(reason, 0) + 1

    total = len(rows)
    valid = len(probes)
    return {
        "rows": total,
        "session_ids": session_ids,
        "valid": valid,
        "invalid": total - valid,
        "response_rate": valid / total,
        "invalid_reason_counts": invalid_reason_counts,
        "reconstructed_clock": _reconstruct_clock(probes, total),
    }


def _identity_metrics(
    local_rows: list[dict[str, str]],
    pc_rows: list[dict[str, str]],
    sync: dict[str, Any],
    meta: dict[str, str],
) -> dict[str, Any]:
    expected_android_session_id = meta.get("session_id", "").strip()
    expected_record_name = meta.get("record_name", "").strip()

    local_session_ids = sorted({row.get("session_id", "").strip() for row in local_rows})
    local_record_names = sorted({row.get("record_name", "").strip() for row in local_rows})
    pc_session_ids = sorted({row.get("session_id", "").strip() for row in pc_rows})
    pc_record_names = sorted({row.get("record_name", "").strip() for row in pc_rows})
    sync_session_ids = sync["session_ids"]

    passed = (
        bool(expected_android_session_id)
        and bool(expected_record_name)
        and local_session_ids == [expected_android_session_id]
        and local_record_names == [expected_record_name]
        and pc_session_ids == [expected_android_session_id]
        and pc_record_names == [expected_record_name]
        and sync_session_ids == [expected_record_name]
    )

    return {
        "passed": passed,
        "expected_android_session_id": expected_android_session_id,
        "expected_record_name": expected_record_name,
        "local_session_ids": local_session_ids,
        "local_record_names": local_record_names,
        "pc_session_ids": pc_session_ids,
        "pc_record_names": pc_record_names,
        "sync_session_ids": sync_session_ids,
    }


def _clock_artifact_consistency(clock: dict[str, Any], sync: dict[str, Any]) -> dict[str, Any]:
    if not clock.get("model_present"):
        return {
            "passed": False,
            "clock_model_present": False,
            "sync_probe_rows": sync["rows"],
        }

    counts = clock.get("probe_counts", {})
    model_sent = int(counts.get("sent", -1))
    model_valid = int(counts.get("valid", -1))
    model_invalid = int(counts.get("invalid", -1))
    model_rate = float(clock["response_rate"])

    reconstructed = sync["reconstructed_clock"]["model_values"]
    mismatched_fields = []
    for key, expected in reconstructed.items():
        observed = clock["model_values"][key]
        if key.startswith("probe_counts."):
            matches = observed == expected
        else:
            # Serialization/float tolerance, not a scientific quality threshold.
            tolerance = 1.0 if key == "beta_ns" else 1e-6
            if key.endswith("alpha") or key == "response_rate":
                tolerance = 1e-12
            matches = math.isclose(observed, expected, rel_tol=0.0, abs_tol=tolerance)
        if not matches:
            mismatched_fields.append(key)

    passed = (
        not mismatched_fields
        and model_sent == sync["rows"]
        and model_valid == sync["valid"]
        and model_invalid == sync["invalid"]
        and math.isclose(model_rate, sync["response_rate"], rel_tol=0.0, abs_tol=1e-12)
    )

    return {
        "passed": passed,
        "model_sent": model_sent,
        "sync_rows": sync["rows"],
        "model_valid": model_valid,
        "sync_valid": sync["valid"],
        "model_invalid": model_invalid,
        "sync_invalid": sync["invalid"],
        "mismatched_model_fields": mismatched_fields,
        "model_response_rate": model_rate,
        "sync_response_rate": sync["response_rate"],
    }


def _clock_quality_gates(clock: dict[str, Any], rule: QualityRule) -> list[GateResult]:
    return [
        GateResult(
            "CLOCK_MODEL_RECONSTRUCTABLE",
            bool(clock.get("model_present")) and clock.get("model") == "affine_phone_to_pc",
            clock.get("model") if clock.get("model_present") else None,
            "official affine clock model reconstructed from raw timestamp exchanges",
        ),
        GateResult(
            "CLOCK_RESPONSE_RATE",
            bool(clock.get("model_present"))
            and clock["response_rate"] >= rule.min_clock_response_rate,
            clock.get("response_rate"),
            f">= {rule.min_clock_response_rate:.3f}",
        ),
        GateResult(
            "CLOCK_RESIDUAL_P95",
            bool(clock.get("model_present"))
            and clock["residual_p95_ms"] <= rule.max_clock_residual_p95_ms,
            clock.get("residual_p95_ms"),
            f"<= {rule.max_clock_residual_p95_ms:.3f} ms",
        ),
        GateResult(
            "CLOCK_RESIDUAL_MAX",
            bool(clock.get("model_present"))
            and clock["residual_max_ms"] <= rule.max_clock_residual_max_ms,
            clock.get("residual_max_ms"),
            f"<= {rule.max_clock_residual_max_ms:.3f} ms",
        ),
        GateResult(
            "CLOCK_SKEW_SANITY",
            bool(clock.get("model_present"))
            and abs(clock["skew_ppm"]) < rule.skew_sanity_ppm,
            clock.get("skew_ppm"),
            f"abs(skew_ppm) < {rule.skew_sanity_ppm:.1f}",
        ),
    ]


def verify_clock_artifacts(
    *,
    clock_model_path: Path,
    sync_probes_path: Path,
    expected_session_id: str,
    rule: QualityRule = QualityRule(),
) -> dict[str, Any]:
    """Verify clock evidence read-only; this is not full session qualification.

    The returned ``clock`` contains reconstructed affine parameters and metrics.
    ``passed`` requires matching session identity, a consistent saved model, and
    all five frozen clock quality gates. Device and transport qualification are
    outside this boundary. Missing/malformed evidence raises QualityEvaluationError;
    valid evidence that mismatches or fails a quality threshold returns passed=False.
    """
    try:
        saved_clock = _clock_metrics(clock_model_path)
        if not saved_clock.get("model_present"):
            raise QualityEvaluationError(f"clock model missing: {clock_model_path}")
        sync = _sync_probe_metrics(sync_probes_path)
    except (OSError, UnicodeError, csv.Error, AttributeError, TypeError) as exc:
        raise QualityEvaluationError(f"invalid clock artifact: {exc}") from exc

    consistency = _clock_artifact_consistency(saved_clock, sync)
    identity_matches = (
        isinstance(expected_session_id, str)
        and bool(expected_session_id.strip())
        and sync["session_ids"] == [expected_session_id]
    )
    clock = sync["reconstructed_clock"]
    # Gate the declared model type while taking numerical evidence from raw fit.
    gate_clock = {**clock, "model": saved_clock.get("model")}
    gates = [
        GateResult(
            "SESSION_IDENTITY", identity_matches, sync["session_ids"],
            "sync-probe session identity equals expected_session_id",
        ),
        GateResult(
            "CLOCK_ARTIFACT_CONSISTENCY", consistency["passed"], consistency,
            "saved clock model matches reconstruction from raw timestamp exchanges",
        ),
        *_clock_quality_gates(gate_clock, rule),
    ]
    return {
        "passed": all(gate.passed for gate in gates),
        "consistency": consistency,
        "clock": clock,
        "session_ids": sync["session_ids"],
        "expected_session_id": expected_session_id,
        "identity_matches": identity_matches,
        "gates": [asdict(gate) for gate in gates],
        "failed_gates": [gate.name for gate in gates if not gate.passed],
    }


def evaluate_session(
    *,
    android_meta_path: Path,
    android_csv_path: Path,
    pc_udp_csv_path: Path,
    clock_model_path: Path,
    sync_probes_path: Path,
    rule: QualityRule = QualityRule(),
) -> dict[str, Any]:
    meta = _parse_meta(android_meta_path)
    local_rows = _read_csv(android_csv_path)
    pc_rows = _read_csv(pc_udp_csv_path)

    local = _local_integrity(local_rows, meta)
    transport = _transport_integrity(local_rows, pc_rows)
    clock = _clock_metrics(clock_model_path)
    sync = _sync_probe_metrics(sync_probes_path)
    identity = _identity_metrics(local_rows, pc_rows, sync, meta)
    clock_consistency = _clock_artifact_consistency(clock, sync)
    if clock.get("model_present") and clock.get("model") == "affine_phone_to_pc":
        # All numerical gates consume reconstructed evidence, never saved claims.
        clock = sync["reconstructed_clock"]

    local_monotonic = all(local["per_sensor_timestamp_monotonic"].values())
    local_sensor_seq_contiguous = all(local["per_sensor_seq_contiguous"].values())

    gates = [
        GateResult(
            "DEVICE_MODEL",
            meta.get("model") == rule.expected_device_model,
            meta.get("model", ""),
            f"model == {rule.expected_device_model}",
        ),
        GateResult(
            "SESSION_IDENTITY",
            identity["passed"],
            {k: v for k, v in identity.items() if k != "passed"},
            "Android local, PC UDP, and sync-probe evidence all match metadata session/record identity",
        ),
        GateResult(
            "CLOCK_ARTIFACT_CONSISTENCY",
            clock_consistency["passed"],
            {k: v for k, v in clock_consistency.items() if k != "passed"},
            "clock_model parameters, counts, and diagnostics match reconstruction from sync_probes.csv",
        ),
        GateResult(
            "LOCAL_SEQUENCE_INTEGRITY",
            local["missing_within_local_range"] == 0
            and local["duplicate_extra_rows"] == 0
            and local["row_count_matches_metadata"]
            and local["sequence_span_matches_metadata"]
            and local["sequence_starts_at_one"]
            and local["sequence_ends_at_metadata_total"]
            and local_sensor_seq_contiguous,
            {
                "missing": local["missing_within_local_range"],
                "duplicates": local["duplicate_extra_rows"],
                "row_count_matches_metadata": local["row_count_matches_metadata"],
                "sequence_starts_at_one": local["sequence_starts_at_one"],
                "sequence_ends_at_metadata_total": local["sequence_ends_at_metadata_total"],
                "sensor_seq_contiguous": local_sensor_seq_contiguous,
            },
            "local seq_global exactly 1..final_total_samples; no duplicates; per-sensor seq contiguous",
        ),
        GateResult(
            "LOCAL_TIMESTAMP_MONOTONIC",
            local_monotonic,
            local["per_sensor_timestamp_monotonic"],
            "sensor timestamps strictly monotonic per sensor",
        ),
        GateResult(
            "ANDROID_QUEUE_SEND_INTEGRITY",
            _required_int(meta, "final_network_queue_drops") == 0
            and _required_int(meta, "final_udp_send_errors") == 0
            and _required_int(meta, "final_local_queue_remaining") == 0
            and _required_int(meta, "final_network_queue_remaining") == 0
            and _required_int(meta, "final_udp_packets_sent") == _required_int(meta, "final_total_samples"),
            {
                "queue_drops": _required_int(meta, "final_network_queue_drops"),
                "send_errors": _required_int(meta, "final_udp_send_errors"),
                "local_queue_remaining": _required_int(meta, "final_local_queue_remaining"),
                "network_queue_remaining": _required_int(meta, "final_network_queue_remaining"),
                "sent": _required_int(meta, "final_udp_packets_sent"),
                "total": _required_int(meta, "final_total_samples"),
            },
            "queue drops/errors/remaining = 0 and UDP sent == total samples",
        ),
        *_clock_quality_gates(clock, rule),
        GateResult(
            "PACKET_LOSS",
            transport["packet_loss_percent"] <= rule.max_packet_loss_percent,
            transport["packet_loss_percent"],
            f"<= {rule.max_packet_loss_percent:.3f}%",
        ),
        GateResult(
            "MAX_SENSOR_DELIVERY_GAP",
            transport["max_per_sensor_delivery_gap_ms"] <= rule.max_per_sensor_delivery_gap_ms,
            transport["max_per_sensor_delivery_gap_ms"],
            f"<= {rule.max_per_sensor_delivery_gap_ms:.3f} ms",
        ),
        GateResult(
            "PAYLOAD_INTEGRITY",
            transport["payload_mismatch_count"] == 0
            and transport["unexpected_pc_sequences"] == 0,
            {
                "payload_mismatch_count": transport["payload_mismatch_count"],
                "unexpected_pc_sequences": transport["unexpected_pc_sequences"],
            },
            "payload mismatch = 0 and PC has no sequence absent from Android local evidence",
        ),
    ]

    all_pass = all(gate.passed for gate in gates)
    return {
        "rule": asdict(rule),
        "session": {
            "session_id": meta.get("session_id", ""),
            "record_name": meta.get("record_name", ""),
            "device_model": meta.get("model", ""),
        },
        "local": local,
        "transport": transport,
        "clock": clock,
        "sync_probes": sync,
        "identity": identity,
        "clock_artifact_consistency": clock_consistency,
        "gates": [asdict(gate) for gate in gates],
        "evaluation_context": "participant_representative",
        "final_session_status": "PASS" if all_pass else "FAIL",
        "failed_gates": [gate.name for gate in gates if not gate.passed],
        "diagnostic_only": {
            "pc_duplicate_extra_rows": transport["duplicate_extra_rows"],
            "pc_out_of_order_events": transport["out_of_order_events"],
        },
    }


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        "M2.3 Session Quality Evaluation",
        "===============================",
        f"Rule: {report['rule']['version']}",
        f"Session: {report['session']['session_id']}",
        f"Record: {report['session']['record_name']}",
        "",
    ]
    for gate in report["gates"]:
        status = "PASS" if gate["passed"] else "FAIL"
        lines.append(f"{gate['name']:<30} {status}")
        lines.append(f"  observed: {gate['observed']}")
        lines.append(f"  criterion: {gate['criterion']}")
    lines.extend(
        [
            "",
            f"PARTICIPANT_SESSION_QUALITY_STATUS = {report['final_session_status']}",
            f"FAILED_GATES = {', '.join(report['failed_gates']) if report['failed_gates'] else 'NONE'}",
            "",
            "Diagnostics only:",
            f"  pc_duplicate_extra_rows = {report['diagnostic_only']['pc_duplicate_extra_rows']}",
            f"  pc_out_of_order_events = {report['diagnostic_only']['pc_out_of_order_events']}",
        ]
    )
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic M2.3 A17 session-quality evaluator (pre-freeze rule draft)."
    )
    parser.add_argument("--android-meta", type=Path, required=True)
    parser.add_argument("--android-csv", type=Path, required=True)
    parser.add_argument("--pc-udp-csv", type=Path, required=True)
    parser.add_argument("--clock-model", type=Path, required=True)
    parser.add_argument("--sync-probes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = evaluate_session(
        android_meta_path=args.android_meta,
        android_csv_path=args.android_csv,
        pc_udp_csv_path=args.pc_udp_csv,
        clock_model_path=args.clock_model,
        sync_probes_path=args.sync_probes,
    )
    text = _format_text(report)
    print(text, end="")
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "SESSION_QUALITY.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        (args.output_dir / "SESSION_QUALITY.txt").write_text(text, encoding="utf-8")
    return 0 if report["final_session_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
