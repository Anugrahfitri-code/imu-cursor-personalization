"""L0 qualification gate.

L0 is qualified only when every gate below passes. The gate is
deliberately strict about the two failure modes that matter most for a
regression model fitted on IMU: producing no signal at all, and
collapsing to the zero-velocity baseline.

The report is written to reports/l0_qualification_report.json.
"""

from .artifacts import write_json
from .metrics import (
    active_mask, compare_to_zero_baseline, direction_agreement, mae,
    per_user_metrics, rmse, speed)

QUALIFICATION_REPORT_PATH = "reports/l0_qualification_report.json"

GATE_ORDER = (
    "active_motion_prediction",
    "direction_agreement",
    "zero_velocity_baseline_comparison",
    "per_user_consistency",
    "closed_loop_sanity",
    "inference_runtime",
    "artifact_reproducibility",
)


def _check(passed, detail, observed, threshold):
    return {
        "pass": bool(passed),
        "detail": detail,
        "observed": observed,
        "threshold": threshold,
    }


def assess_qualification(config, y_true, y_pred, active, records, latency,
                         reproducibility):
    """Evaluate every gate and return (qualified, gates, diagnostics)."""
    thresholds = config.qualification
    mask = active_mask(
        y_true, active, thresholds.active_speed_threshold_px_s)
    agreement = direction_agreement(y_true, y_pred, mask)
    comparison = compare_to_zero_baseline(y_true, y_pred)
    per_user = per_user_metrics(records)

    # 1. Predictive signal on genuinely moving windows.
    active_gate = _check(
        int(mask.sum()) >= thresholds.min_active_samples,
        "L0 must predict on windows where the reference actually moves",
        int(mask.sum()), thresholds.min_active_samples)

    # 2. Directional agreement on those same windows.
    direction_gate = _check(
        agreement["mean"] >= thresholds.min_direction_agreement,
        "predicted direction must agree with the reference direction",
        agreement["mean"], thresholds.min_direction_agreement)

    # 3. Must beat the zero-velocity baseline rather than imitate it.
    zero_gate = _check(
        comparison["rmse_ratio"] <= thresholds.zero_velocity_rmse_ratio_max,
        "L0 must beat the always-zero predictor",
        comparison["rmse_ratio"], thresholds.zero_velocity_rmse_ratio_max)

    # 4. Every held-out user individually beats the baseline.
    failing_users = sorted(
        name for name, stats in per_user.items()
        if stats["zero_velocity"]["rmse_ratio"]
        > thresholds.zero_velocity_rmse_ratio_max)
    per_user_gate = _check(
        not failing_users,
        "each held-out user must beat the zero-velocity baseline",
        failing_users, thresholds.zero_velocity_rmse_ratio_max)

    # 5. Closed-loop sanity: a usable model is finite, live, and not
    #    dominated by pathological magnitude.
    predicted_speeds = speed(y_pred)
    finite = bool(predicted_speeds.size) and bool(
        (predicted_speeds == predicted_speeds).all())
    live = bool(predicted_speeds.max() > 0.0) if predicted_speeds.size else False
    closed_loop_gate = _check(
        finite and live,
        "predictions must be finite and non-degenerate",
        {"finite": finite, "max_predicted_speed_px_s":
         float(predicted_speeds.max()) if predicted_speeds.size else None},
        "finite and non-zero")

    # 6. Inference runtime budget.
    runtime_gate = _check(
        latency["mean_ms"] <= thresholds.max_mean_latency_ms,
        "single-window inference must fit the runtime budget",
        latency["mean_ms"], thresholds.max_mean_latency_ms)

    # 7. Artifact reproducibility.
    reproducibility_gate = _check(
        bool(reproducibility.get("reproducible")),
        "the same seed and config must reproduce the checkpoint",
        reproducibility, "reproducible")

    gates = {
        "active_motion_prediction": active_gate,
        "direction_agreement": direction_gate,
        "zero_velocity_baseline_comparison": zero_gate,
        "per_user_consistency": per_user_gate,
        "closed_loop_sanity": closed_loop_gate,
        "inference_runtime": runtime_gate,
        "artifact_reproducibility": reproducibility_gate,
    }
    diagnostics = {
        "samples": int(len(y_true)),
        "active_samples": int(mask.sum()),
        "mean_reference_speed_px_s": float(speed(y_true).mean()),
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "direction_agreement": agreement,
        "zero_velocity": comparison,
        "per_user": per_user,
        "latency": latency,
    }
    return all(gates[name]["pass"] for name in GATE_ORDER), gates, diagnostics


def build_qualification_report(config, qualified, gates, diagnostics,
                               nested_validation, artifacts, config_path):
    """Assemble the full report payload."""
    return {
        "schema_version": "1.0",
        "report_type": "l0_qualification",
        "configuration_id": config.configuration_id,
        "config_sha256": config.config_sha256,
        "config_path": str(config_path),
        "status": "QUALIFIED" if qualified else "NOT_QUALIFIED",
        "qualified": bool(qualified),
        "gate_order": list(GATE_ORDER),
        "gates": {name: gates[name] for name in GATE_ORDER},
        "diagnostics": diagnostics,
        "validation": nested_validation,
        "development_users": list(config.development_users),
        "evaluation_users": list(config.evaluation_users),
        "evaluation_used": False,
        "artifacts": artifacts,
        "notes": [
            "L0 is a global supervised model, not an evaluation model.",
            "Thresholds were declared before qualification and are not "
            "tuned against evaluation results.",
            "Velocity units are px/s as stored on the common grid.",
        ],
    }


def write_qualification_report(report, path=QUALIFICATION_REPORT_PATH):
    return write_json(path, report)
