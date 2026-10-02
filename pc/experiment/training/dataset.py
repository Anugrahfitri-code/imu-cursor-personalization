"""L0 supervised dataset: causal windows that never cross a user boundary.

The mapping is X[t-T+1 : t] -> Y(t). Every window is built strictly
backwards from its own target index, so no sample at time > t can ever
influence the prediction. Windows are additionally cut at participant
boundaries: a window is never formed across two participant codes.

Labels are reference velocity in px/s as stored on the common grid
(COMMON_GRID_COLUMNS.ref_vx_px_s / ref_vy_px_s).
"""

from types import SimpleNamespace

import numpy as np
import torch
from torch.utils.data import Dataset

from ..controllers.learned.data import CHANNELS, LABELS

PARTICIPANT_COLUMN = "participant_id"  # the grid's user column
PARTICIPANT_CODE_ALIAS = "participant_code"


IMU_CHANNELS = CHANNELS
TARGET_LABELS = LABELS


def participant_code(row):
    """Resolve the user identity of a common-grid row.

    The grid column is `participant_id`; the training pipeline exposes it
    under the `participant_code` name required by the L0 protocol.
    """
    for key in (PARTICIPANT_CODE_ALIAS, PARTICIPANT_COLUMN):
        if key in row and row[key] is not None:
            return str(row[key])
    raise ValueError(
        f"row has no participant identity; expected {PARTICIPANT_CODE_ALIAS} "
        f"or {PARTICIPANT_COLUMN}")


def group_rows_by_participant(rows):
    """Split common-grid rows into per-user groups, preserving order.

    Grouping BEFORE window construction is what keeps a window from ever
    spanning two participants.
    """
    groups = {}
    for row in rows:
        groups.setdefault(participant_code(row), []).append(row)
    return groups


def build_user_windows(rows, window, grid_interval_ns):
    """Causal windows for ONE user, delegating to the tested Stage 2.7
    extractor and window builder.

    Returns (X, y, active) as float32 numpy arrays where
    X.shape == (N, T, 6) and y.shape == (N, 2) in px/s.
    """
    from ..controllers.learned.data import build_windows, labelled_targets

    samples, labels, _times, flags, run_starts = _extract(
        rows, grid_interval_ns)
    config = SimpleNamespace(window=int(window))
    X, y, active = build_windows(samples, labels, flags, config, run_starts)
    # Unlabelled rows may provide context but never supervise, so they are
    # dropped here rather than silently filled with a zero target.
    indices, targets = labelled_targets(y)
    if not indices:
        raise ValueError(
            f"no labelled window at T={window} for a single participant")
    return (np.asarray([X[i] for i in indices], dtype=np.float32),
            np.asarray(targets, dtype=np.float32),
            np.asarray([active[i] for i in indices], dtype=bool))


def _extract(rows, grid_interval_ns):
    """Apply the Stage 2.7 fail-closed rules to one user's grid rows.

    Rows are kept only when sensor_status is VALID; a row whose
    label_status is not VALID still contributes window context but
    carries a None label, so it can never become a supervision target.
    Contiguous runs are identified from the grid timestamps, so a gap
    splits a run rather than being windowed across.
    """
    interval = int(grid_interval_ns)
    samples, labels, times, flags = [], [], [], []
    run_starts = []
    for row in rows:
        if row.get("sensor_status") != "VALID":
            continue
        try:
            channel_values = tuple(
                float(row[column]) for column in CHANNELS)
        except (KeyError, TypeError, ValueError):
            continue
        if row.get("label_status") == "VALID":
            try:
                label_values = tuple(
                    float(row[column]) for column in LABELS)
            except (KeyError, TypeError, ValueError):
                label_values = None
        else:
            label_values = None
        t = int(row["grid_pc_time_ns"])
        if not times or times[-1] + interval != t:
            run_starts.append(len(times))
        times.append(t)
        samples.append(channel_values)
        labels.append(label_values)
        flags.append(bool(row.get("active_motion_flag")))
    if not samples:
        raise ValueError("no VALID sensor rows for L0 user")
    return samples, labels, times, flags, run_starts


class StandardScaler:
    """Per-channel standardisation fitted on training windows only.

    The scaler is fitted exclusively from the samples handed to `fit`, so
    a held-out participant can never influence these statistics.
    """

    def __init__(self, epsilon=1e-8):
        self.epsilon = float(epsilon)
        self.mean_ = None
        self.scale_ = None

    def fit(self, X):
        if len(X) == 0:
            raise ValueError("cannot fit a scaler on zero windows")
        array = np.asarray(X, dtype=np.float64)
        if array.ndim != 3:
            raise ValueError("expected (N, T, C) window array")
        flat = array.reshape(-1, array.shape[-1])
        self.mean_ = flat.mean(axis=0)
        variance = flat.var(axis=0)
        self.scale_ = np.sqrt(np.maximum(variance, 0.0)) + self.epsilon
        if not np.all(self.scale_ > 0.0):
            raise ValueError("degenerate scaler statistics")
        return self

    def transform(self, X):
        if self.mean_ is None:
            raise ValueError("scaler is not fitted")
        array = np.asarray(X, dtype=np.float32)
        if len(array) == 0:
            return array
        return ((array - self.mean_.astype(np.float32))
                / self.scale_.astype(np.float32)).astype(np.float32)

    def state_dict(self):
        if self.mean_ is None:
            raise ValueError("scaler is not fitted")
        return {
            "method": "standard",
            "epsilon": self.epsilon,
            "mean": [float(v) for v in self.mean_],
            "scale": [float(v) for v in self.scale_],
        }

    @classmethod
    def from_state_dict(cls, state):
        scaler = cls(epsilon=state.get("epsilon", 1e-8))
        if state.get("method") != "standard":
            raise ValueError(f"unsupported scaler method {state.get('method')!r}")
        scaler.mean_ = np.asarray(state["mean"], dtype=np.float64)
        scaler.scale_ = np.asarray(state["scale"], dtype=np.float64)
        return scaler


class L0WindowDataset(Dataset):
    """Torch dataset over pre-built causal windows for several users."""

    def __init__(self, windows, targets, participant_codes, active, scaler=None):
        if not (len(windows) == len(targets) == len(participant_codes)
                == len(active)):
            raise ValueError("window/target/user/active arrays must align")
        self.X = np.asarray(windows, dtype=np.float32)
        self.y = np.asarray(targets, dtype=np.float32)
        self.participants = [str(code) for code in participant_codes]
        self.active = np.asarray(active, dtype=bool)
        if self.X.ndim != 3:
            raise ValueError("windows must be (N, T, C)")
        if self.y.ndim != 2 or self.y.shape[-1] != len(LABELS):
            raise ValueError("targets must be (N, 2) reference velocity")
        self.scaler = scaler
        features = scaler.transform(self.X) if scaler is not None else self.X

    def __len__(self):
        return int(self.X.shape[0])

    def __getitem__(self, index):
        features = self.scaler.transform(self.X[index:index + 1])[0] \
            if self.scaler is not None else self.X[index]
        return {
            "x": torch.from_numpy(np.ascontiguousarray(features)),
            "y": torch.from_numpy(np.ascontiguousarray(self.y[index])),
            "participant_code": self.participants[index],
            "active_motion": bool(self.active[index]),
        }

    @property
    def participant_set(self):
        return set(self.participants)


def build_l0_datasets(rows, window, grid_interval_ns, user_codes):
    """Build one dataset per requested participant code.

    Only users present in `user_codes` are built, which is how the
    evaluation cohort is kept out of training and of the scaler.
    """
    groups = group_rows_by_participant(rows)
    missing = [code for code in user_codes if code not in groups]
    if missing:
        raise ValueError(f"no rows for participants: {missing}")
    built = {}
    for code in user_codes:
        X, y, active = build_user_windows(
            groups[code], window, grid_interval_ns)
        if len(X) == 0:
            raise ValueError(
                f"participant {code} produced no causal window at "
                f"T={window}; a shorter run or a longer window is required")
        built[code] = (X, y, active)
    return built


def concatenate_users(built, user_codes):
    """Concatenate per-user arrays into a single dataset object."""
    windows, targets, codes, active = [], [], [], []
    for code in user_codes:
        X, y, flags = built[code]
        windows.append(X)
        targets.append(y)
        codes.extend([code] * len(X))
        active.append(flags)
    return (np.concatenate(windows, axis=0),
            np.concatenate(targets, axis=0),
            codes,
            np.concatenate(active, axis=0))
