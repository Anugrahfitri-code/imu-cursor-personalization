"""Fail-closed Stage 2.7 feature/label extraction from the common grid."""

from ..config import sha256

CHANNELS = ("accel_x", "accel_y", "accel_z",
            "gyro_x", "gyro_y", "gyro_z")
LABELS = ("ref_vx_px_s", "ref_vy_px_s")
REQUIRED = ("grid_pc_time_ns", "sensor_status", "label_status",
            "sequence_id", "active_motion_flag", *CHANNELS, *LABELS)
PADDING_POLICY = "REPEAT_FIRST"
PADDING_VALUE = 0.0


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    return value


def extract_samples(rows, config, *, expect_identity=None):
    """Return (samples, labels, times, flags, run_starts); fails closed.

    Context rows require sensor_status == VALID; label_status != VALID
    yields a None label (that row can still serve as window context but
    never as a supervision target). Rows must already have passed the
    Stage 2.6 bundle boundary checks; every consumed field is re-checked.
    """
    from pc.experiment.preprocessing.schema import COMMON_GRID_COLUMNS
    missing = [column for column in REQUIRED if column not in COMMON_GRID_COLUMNS]
    if missing:
        raise ValueError(f"grid schema no longer provides {missing}")
    if expect_identity is not None:
        for key in ("participant_id", "session_id", "calibration_id"):
            if rows and rows[0].get(key) != expect_identity.get(key):
                raise ValueError("sample rows do not match expected identity")
    samples, labels, times, flags = [], [], [], []
    run_starts = []
    expected = config.grid_interval_ns
    for row in rows:
        if row.get("sensor_status") != "VALID":
            continue
        try:
            channel_values = tuple(
                _number(row[column], column) for column in CHANNELS)
        except ValueError:
            continue
        if row.get("label_status") == "VALID":
            try:
                label_values = tuple(
                    _number(row[column], column) for column in LABELS)
            except ValueError:
                label_values = None
        else:
            label_values = None
        t = int(row["grid_pc_time_ns"])
        if not times or times[-1] + expected != t:
            run_starts.append(len(times))
        times.append(t)
        samples.append(channel_values)
        labels.append(label_values)
        flags.append(bool(row.get("active_motion_flag")))
    if not samples:
        raise ValueError("no VALID sensor rows for learned candidate")
    return samples, labels, times, flags, run_starts


def build_windows(samples, labels, flags, config, run_starts):
    """Causal windows within each contiguous sensor run; REPEAT_FIRST pad.

    A run shorter than the window contributes nothing: padding across a
    gap would fabricate context that never existed.
    """
    window = config.window
    X, y, active = [], [], []
    bounds = list(run_starts) + [len(samples)]
    for start, end in zip(bounds, bounds[1:]):
        if end - start < window:
            continue
        run = samples[start:end]
        padded = [run[0]] * (window - 1) + list(run)
        for offset in range(end - start):
            frame = padded[offset:offset + window]
            if len(frame) != window:
                raise ValueError("window construction invariant violated")
            X.append([list(frame_i) for frame_i in frame])
            index = start + offset
            y.append(list(labels[index]) if labels[index] is not None else None)
            active.append(flags[index])
    if not X:
        raise ValueError(f"no contiguous run reaches window {window}")
    return X, y, active


def labelled_targets(y):
    """Fail-closed (indices, values) of supervisable windows."""
    indices = [i for i, label in enumerate(y) if label is not None]
    if not indices:
        raise ValueError("no VALID labels inside any causal window")
    return indices, [y[i] for i in indices]


def learned_dataset_sha256(samples, labels, times, flags, run_starts):
    """Content digest over the exact arrays consumed by training/replay."""
    return sha256({"samples": samples, "labels": [list(l) if l else None for l in labels],
                   "times": times, "active_motion": flags,
                   "run_starts": run_starts})

