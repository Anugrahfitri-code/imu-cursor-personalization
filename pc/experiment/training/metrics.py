"""Diagnostic and qualification metrics for the L0 global model.

Targets are reference velocity in px/s. Every metric is computed in
physical units, never in a rescaled space, so the numbers in the
qualification report are interpretable on their own.
"""

import time

import numpy as np
import torch

from .dataset import TARGET_LABELS

# The zero-velocity baseline: predict no motion at all.
ZERO_PREDICTION = (0.0, 0.0)


def _as_array(value):
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != len(TARGET_LABELS):
        raise ValueError(
            f"expected (N, {len(TARGET_LABELS)}) velocity array, got {array.shape}")
    return array


def mae(y_true, y_pred):
    """Mean absolute error per component, plus the mean of those.

    `overall` is the error over every scalar entry; `mean` is the mean of
    the per-axis values. Both are reported so the aggregate is unambiguous.
    """
    true, pred = _as_array(y_true), _as_array(y_pred)
    if len(true) == 0:
        raise ValueError("MAE requires at least one sample")
    per_axis = np.abs(true - pred).mean(axis=0)
    return {
        "per_axis": {name: float(v)
                     for name, v in zip(TARGET_LABELS, per_axis)},
        "mean": float(per_axis.mean()),
        "overall": float(np.abs(true - pred).mean()),
    }


def rmse(y_true, y_pred):
    """Root mean squared error per component, plus the mean of those."""
    true, pred = _as_array(y_true), _as_array(y_pred)
    if len(true) == 0:
        raise ValueError("RMSE requires at least one sample")
    per_axis = np.sqrt(((true - pred) ** 2).mean(axis=0))
    return {
        "per_axis": {name: float(v)
                     for name, v in zip(TARGET_LABELS, per_axis)},
        "mean": float(per_axis.mean()),
        "overall": float(np.sqrt(((true - pred) ** 2).mean())),
    }


def speed(velocity):
    return np.linalg.norm(_as_array(velocity), axis=1)


def active_mask(y_true, active_motion, active_speed_threshold):
    """Windows that genuinely move: flagged by the gate AND fast enough.

    The speed test uses the reference itself so a model cannot pass by
    predicting motion for samples that are not actually moving.
    """
    flags = np.asarray(active_motion, dtype=bool)
    if len(flags) != len(_as_array(y_true)):
        raise ValueError("active_motion must align with y_true")
    return flags & (speed(y_true) >= float(active_speed_threshold))


def direction_agreement(y_true, y_pred, mask):
    """Cosine agreement of predicted vs reference direction on active windows.

    Magnitude-free on purpose: this catches a model that gets the sign or
    the axis right but the scale wrong, and it ignores the sign of
    samples whose reference is near zero, where direction is meaningless.
    """
    true, pred = _as_array(y_true), _as_array(y_pred)
    mask = np.asarray(mask, dtype=bool)
    if mask.sum() == 0:
        return {"count": 0, "mean": 0.0, "per_axis": {}}
    true_norm = np.linalg.norm(true[mask], axis=1)
    usable = true_norm > 0.0
    if usable.sum() == 0:
        return {"count": int(mask.sum()), "mean": 0.0, "per_axis": {}}
    unit_true = true[mask][usable] / true_norm[usable][:, None]
    unit_pred = pred[mask][usable]
    pred_norm = np.linalg.norm(unit_pred, axis=1)
    good = pred_norm > 0.0
    if good.sum() == 0:
        return {"count": int(mask.sum()), "mean": 0.0, "per_axis": {}}
    unit_pred = unit_pred[good] / pred_norm[good][:, None]
    cosines = (unit_true[good] * unit_pred).sum(axis=1)
    per_axis = cosines.mean(axis=0) if cosines.ndim > 1 else np.array(
        [cosines.mean()])
    return {
        "count": int(mask.sum()),
        "scored": int(good.sum()),
        "mean": float(cosines.mean()),
        "per_axis": {name: float(v) for name, v in zip(TARGET_LABELS, per_axis)},
    }


def zero_velocity_baseline(y_true):
    """RMSE of the trivial always-zero predictor, in px/s."""
    true = _as_array(y_true)
    zeros = np.zeros_like(true)
    return {
        "rmse": rmse(true, zeros),
        "mean_speed_px_s": float(speed(true).mean()),
    }


def compare_to_zero_baseline(y_true, y_pred):
    """Ratio of model RMSE to the zero-velocity RMSE (lower is better).

    A ratio at or below 1.0 means the model beats predicting no motion.
    """
    true, pred = _as_array(y_true), _as_array(y_pred)
    model_rmse = rmse(true, pred)["mean"]
    baseline_rmse = rmse(true, np.zeros_like(true))["mean"]
    if baseline_rmse <= 0.0:
        raise ValueError("zero-velocity baseline RMSE is zero")
    return {
        "model_rmse_px_s": float(model_rmse),
        "zero_velocity_rmse_px_s": float(baseline_rmse),
        "rmse_ratio": float(model_rmse / baseline_rmse),
    }


def per_user_metrics(records):
    """Group (participant_code, y_true, y_pred, active) records by user."""
    grouped = {}
    for participant, true, pred, active in records:
        grouped.setdefault(str(participant), []).append(
            (np.asarray(true), np.asarray(pred), np.asarray(active)))
    results = {}
    for participant, entries in sorted(grouped.items()):
        true = np.concatenate([e[0] for e in entries], axis=0)
        pred = np.concatenate([e[1] for e in entries], axis=0)
        active = np.concatenate([e[2] for e in entries], axis=0)
        results[participant] = {
            "samples": int(len(true)),
            "mae": mae(true, pred),
            "rmse": rmse(true, pred),
            "zero_velocity": compare_to_zero_baseline(true, pred),
            "active_samples": int(active.sum()),
        }
    return results


def measure_latency(model, window, channels, warmup_runs, measured_runs):
    """Single-window inference latency, the quantity a closed loop cares about.

    Reports the mean and p95 wall time for one forward pass, after
    warmup so that first-call allocation does not dominate.
    """
    from .model import L0VelocityModel

    if not isinstance(model, L0VelocityModel):
        raise ValueError("latency must be measured on an L0VelocityModel")
    if measured_runs < 1 or warmup_runs < 0:
        raise ValueError("measured_runs must be >= 1 and warmup_runs >= 0")
    model.eval()
    sample = torch.zeros(1, int(window), int(channels), dtype=torch.float32)
    with torch.no_grad():
        for _ in range(int(warmup_runs)):
            model(sample)
        timings = []
        for _ in range(int(measured_runs)):
            start = time.perf_counter()
            model(sample)
            timings.append((time.perf_counter() - start) * 1000.0)
    array = np.asarray(timings, dtype=np.float64)
    return {
        "measured_runs": int(measured_runs),
        "warmup_runs": int(warmup_runs),
        "mean_ms": float(array.mean()),
        "median_ms": float(np.median(array)),
        "p95_ms": float(np.percentile(array, 95)),
        "max_ms": float(array.max()),
    }

