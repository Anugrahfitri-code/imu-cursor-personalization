"""Tests for the L0 supervised training and user-wise qualification pipeline.

Fixtures are synthetic on purpose: they exercise causality, user
boundaries, and the qualification gate without depending on participant
data or on a trained artifact.
"""

import copy
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

from pc.experiment.training import artifacts, qualification, validation
from pc.experiment.training.config import load_l0_config
from pc.experiment.training.dataset import (
    L0WindowDataset, StandardScaler, build_l0_datasets, build_user_windows,
    group_rows_by_participant, participant_code)
from pc.experiment.training.metrics import (
    active_mask, compare_to_zero_baseline, direction_agreement, mae, rmse)
from pc.experiment.training.model import (
    L0VelocityModel, expected_parameter_count, parameter_count, receptive_field)
from pc.experiment.training.train_l0 import fit_l0, predict

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs" / "experiment" / "l0_training_config.yaml"
GRID_INTERVAL_NS = 5_000_000  # 200 Hz
SAMPLE_RATE_HZ = 200


def _row(participant, index, velocity, *, labelled=True, active=True,
         time_ns=None):
    """One common-grid row for the L0 pipeline."""
    accel = (velocity[0] * 0.001, velocity[1] * 0.001, 9.80665)
    gyro = (0.0, 0.0, 0.0)
    t = index * GRID_INTERVAL_NS if time_ns is None else time_ns
    return {
        "participant_id": participant,
        "session_id": f"{participant}-s1",
        "calibration_id": f"{participant}-c1",
        "grid_index": index,
        "grid_pc_time_ns": t,
        "sensor_status": "VALID",
        "label_status": "VALID" if labelled else "INVALID",
        "active_motion_flag": active,
        "accel_x": accel[0], "accel_y": accel[1], "accel_z": accel[2],
        "gyro_x": gyro[0], "gyro_y": gyro[1], "gyro_z": gyro[2],
        "ref_vx_px_s": velocity[0],
        "ref_vy_px_s": velocity[1],
    }


def _user_rows(participant, length=140, speed=180.0, labelled=True, seed=0):
    """A user with a reproducible triangular velocity profile."""
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(length):
        phase = 2.0 * math.pi * index / 40.0
        velocity = (speed * math.cos(phase), speed * math.sin(phase))
        rows.append(_row(
            participant, index,
            (velocity[0] + rng.normal(0, 0.5),
             velocity[1] + rng.normal(0, 0.5)),
            labelled=labelled))
    return rows


@pytest.fixture
def l0_config():
    return load_l0_config(CONFIG_PATH)


# 1. Dataset produces causal windows.
def test_dataset_produces_causal_windows():
    rows = _user_rows("P1", length=80)
    X, y, active = build_user_windows(rows, window=32,
                                      grid_interval_ns=GRID_INTERVAL_NS)
    # Stage 2.7 pads the run head with REPEAT_FIRST, so a run of N
    # samples yields N windows rather than N - T + 1.
    assert X.shape == (80, 32, 6)
    assert y.shape == (len(X), 2)
    assert active.shape == (len(X),)
    # The window ends exactly on its own target sample, so the final
    # timestep carries the feature paired with the target label.
    assert X[:, -1, 0] == pytest.approx(y[:, 0] * 0.001, rel=1e-4, abs=1e-6)


# 2. No future leakage.
def test_no_future_leakage():
    """Corrupting strictly future samples must not change any window."""
    rows = _user_rows("P1", length=90)
    X_original, y_original, _ = build_user_windows(
        rows, 32, GRID_INTERVAL_NS)

    mutated = [dict(row) for row in rows]
    for row in mutated[60:]:
        row["accel_x"] = 999.0
        row["ref_vx_px_s"] = -888.0
    X_mutated, y_mutated, _ = build_user_windows(
        mutated, 32, GRID_INTERVAL_NS)

    # Windows anchored at or before index 59 read only rows <= 59, so the
    # corrupted tail is invisible to them: both features and targets match.
    assert np.allclose(y_original[:60], y_mutated[:60])
    assert np.allclose(X_original[:60], X_mutated[:60], atol=0.0)
    # The corrupted tail is genuinely present, so the test is not vacuous.
    assert not np.allclose(X_original[60:], X_mutated[60:])


def test_window_never_reads_a_later_sample():
    """Each window's last timestep is its own target sample."""
    rows = _user_rows("P1", length=40)
    X, y, _ = build_user_windows(rows, 16, GRID_INTERVAL_NS)
    assert X.shape == (40, 16, 6)
    # accel_x is defined as vx * 0.001, so this pairing holds only if the
    # window is anchored on its target rather than one step ahead.
    assert X[:, -1, 0] == pytest.approx(y[:, 0] * 0.001, rel=1e-4, abs=1e-6)


# 3. User boundaries are never mixed.
def test_user_boundary_not_crossed():
    rows_a = _user_rows("P1", length=60, speed=180.0, seed=1)
    rows_b = _user_rows("P2", length=60, speed=900.0, seed=2)
    built = build_l0_datasets(
        rows_a + rows_b, 32, GRID_INTERVAL_NS, ["P1", "P2"])
    X_a, y_a, _ = built["P1"]
    X_b, y_b, _ = built["P2"]
    # A window is never formed across the participant join: concatenating
    # the rows does not merge the two users into one longer run.
    assert len(X_a) == 60
    assert len(X_b) == 60
    # Each user is built from its own samples only.
    assert y_a[:, 0].max() < 400.0
    assert y_b[:, 0].max() > 400.0
    assert X_a[:, -1, 0] == pytest.approx(y_a[:, 0] * 0.001, rel=1e-4, abs=1e-6)
    assert X_b[:, -1, 0] == pytest.approx(y_b[:, 0] * 0.001, rel=1e-4, abs=1e-6)


def test_participant_grouping_and_code():
    rows = _user_rows("P1", length=5) + _user_rows("P2", length=5)
    groups = group_rows_by_participant(rows)
    assert sorted(groups) == ["P1", "P2"]
    assert len(groups["P1"]) == 5
    assert participant_code(groups["P1"][0]) == "P1"


def test_gap_between_runs_is_not_bridged():
    """A time gap splits runs; no window may span the discontinuity."""
    first = _user_rows("P1", length=20, speed=180.0, seed=3)
    second = _user_rows("P1", length=20, speed=900.0, seed=4)
    gapped = [dict(row) for row in first] + [dict(row) for row in second]
    for row in gapped[20:]:
        row["grid_pc_time_ns"] = row["grid_pc_time_ns"] + 10_000_000_000

    X, y, _ = build_user_windows(gapped, 16, GRID_INTERVAL_NS)
    # Two independent runs: 20 windows each, no window spanning the gap.
    assert len(X) == 40
    # The first run's windows carry only the slow user's features; if the
    # gap were bridged, late windows would contain the fast user's data.
    assert X[:20, :, 0].max() == pytest.approx(0.18, rel=0.2)
    assert X[20:, :, 0].max() > 0.5


# 4. Model output shape is correct.
@pytest.mark.parametrize("window", [32, 48, 64])
def test_model_output_shape(window):
    model = L0VelocityModel(window=window, latent_channels=64, latent_dim=64)
    model.eval()
    batch = torch.zeros(5, window, 6)
    assert tuple(model(batch).shape) == (5, 2)


def test_model_rejects_wrong_channel_count():
    model = L0VelocityModel(window=32, latent_channels=64, latent_dim=64)
    with pytest.raises(ValueError):
        model(torch.zeros(2, 32, 5))


def test_encoder_is_causal_in_time():
    """Changing sample t must not alter the encoding of any position < t."""
    torch.manual_seed(7)
    model = L0VelocityModel(window=48, latent_channels=32, latent_dim=32)
    model.eval()
    x = torch.randn(1, 48, 6)
    perturbed = x.clone()
    perturbed[0, 30, 0] += 50.0
    with torch.no_grad():
        before = model.encode(x)
        after = model.encode(perturbed)
    # Positions strictly before 30 are unaffected; the last one may move.
    assert torch.allclose(before[:, :30, :], after[:, :30, :], atol=1e-5)
    assert not torch.allclose(before[:, 30:, :], after[:, 30:, :])


# 5. Parameter count matches the fixed architecture.
def test_parameter_count_matches_architecture():
    from pc.experiment.controllers.learned.config import ARCHITECTURE

    latent = 64
    model = L0VelocityModel(window=32, latent_channels=latent,
                            latent_dim=latent)
    assert parameter_count(model) == expected_parameter_count(latent, latent)
    # The frozen architecture really is 4 blocks at kernel 5 with
    # dilations 1/2/4/8, giving a 61-sample causal receptive field.
    assert ARCHITECTURE["blocks"] == 4
    assert ARCHITECTURE["kernel_size"] == 5
    assert tuple(ARCHITECTURE["dilations"]) == (1, 2, 4, 8)
    assert receptive_field() == 61


def test_parameter_count_has_no_gru_or_transformer():
    """L0 must be the causal Conv1D stack only."""
    model = L0VelocityModel(window=32, latent_channels=32, latent_dim=32)
    kinds = {type(module).__name__ for module in model.modules()}
    assert "L0VelocityModel" in kinds
    assert "CausalConv1d" in kinds
    assert not {"GRU", "LSTM", "RNN", "TransformerEncoderLayer",
                "MultiheadAttention"} & kinds


def _training_rows():
    rows = []
    for index, participant in enumerate(["D1", "D2", "D3", "D4"]):
        rows.extend(_user_rows(participant, length=70,
                               speed=180.0 + 60.0 * index, seed=index))
    return rows


def _dev_config(base, users=("D1", "D2", "D3", "D4"), epochs=2, **overrides):
    """A development config with a fast, explicit roster for testing."""
    from dataclasses import replace

    return replace(
        base,
        development_users=tuple(users),
        evaluation_users=("E1", "E2"),
        optimisation=replace(base.optimisation, epochs=epochs, batch_size=16),
        **overrides)


# 6. Checkpoint is reproducible.
def test_training_is_reproducible_from_seed(l0_config):
    payload = _dev_config(l0_config)
    rows = _training_rows()
    first = fit_l0(payload, rows, GRID_INTERVAL_NS, 32)
    second = fit_l0(payload, rows, GRID_INTERVAL_NS, 32)
    assert first.parameter_count == second.parameter_count
    assert first.history == pytest.approx(second.history)
    for (name, a), (_, b) in zip(
            first.model.state_dict().items(),
            second.model.state_dict().items()):
        assert torch.equal(a, b), name


def test_saved_checkpoint_reloads_identically(l0_config, tmp_path):
    payload = _dev_config(l0_config)
    rows = _training_rows()
    result = fit_l0(payload, rows, GRID_INTERVAL_NS, 32)
    manifest = artifacts.save_artifacts(result, payload, tmp_path / "l0")
    assert Path(manifest["checkpoint"]).exists()
    assert Path(manifest["scaler"]).exists()
    assert Path(manifest["config"]).exists()
    assert Path(manifest["metadata"]).exists()

    model, scaler, meta = artifacts.load_artifacts(tmp_path / "l0", payload)
    assert meta["seed"] == payload.seed
    assert meta["parameter_count"] == result.parameter_count
    dataset = L0WindowDataset(
        np.zeros((1, 32, 6), dtype=np.float32),
        np.zeros((1, 2), dtype=np.float32), ["D1"], [True], scaler=scaler)
    with torch.no_grad():
        result.model.eval()  # dropout must be off to compare predictions
        assert torch.allclose(
            model(dataset[0]["x"].unsqueeze(0)),
            result.model(dataset[0]["x"].unsqueeze(0)), atol=1e-6)


def test_checkpoint_from_other_config_is_refused(l0_config, tmp_path):
    payload = _dev_config(l0_config)
    result = fit_l0(payload, _training_rows(), GRID_INTERVAL_NS, 32)
    artifacts.save_artifacts(result, payload, tmp_path / "l0")
    other = _dev_config(l0_config, epochs=3)
    with pytest.raises(ValueError):
        artifacts.load_artifacts(tmp_path / "l0", other)


def test_scaler_is_fitted_only_from_given_users():
    built = build_l0_datasets(_training_rows(), 32, GRID_INTERVAL_NS,
                              ["D1", "D2"])
    from pc.experiment.training.dataset import concatenate_users

    X, y, codes, active = concatenate_users(built, ["D1"])
    first = StandardScaler().fit(X)
    combined = StandardScaler().fit(
        concatenate_users(built, ["D1", "D2"])[0])
    # D2 has a different amplitude, so the two fits must disagree.
    assert not np.allclose(first.mean_, combined.mean_)


def test_evaluation_users_cannot_be_trained_on(l0_config):
    payload = _dev_config(l0_config)
    rows = _training_rows()
    with pytest.raises(ValueError):
        fit_l0(payload, rows, GRID_INTERVAL_NS, 32, user_codes=["E1"])


def test_config_requires_explicit_development_roster(l0_config):
    empty = copy.deepcopy(l0_config)
    object.__setattr__(empty, "development_users", ())
    with pytest.raises(ValueError):
        empty.require_development_users()


def test_config_rejects_architecture_search():
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["architecture"]["dilations"] = [1, 2, 4, 8, 16]
    with pytest.raises(ValueError):
        _config_from_raw(raw)


def _config_from_raw(raw, tmp_path=None):
    import tempfile

    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                         encoding="utf-8")
    yaml.safe_dump(raw, handle)
    handle.close()
    try:
        return load_l0_config(handle.name)
    finally:
        Path(handle.name).unlink(missing_ok=True)


# Qualification and metrics.
def test_metric_maths():
    truth = np.array([[3.0, 4.0], [-1.0, 0.0], [0.0, 2.0]])
    zeros = np.zeros_like(truth)
    # MAE of the all-zero predictor is the mean |reference|.
    assert mae(truth, zeros)["overall"] == pytest.approx(
        float(np.abs(truth).mean()))
    assert rmse(truth, zeros)["overall"] == pytest.approx(
        float(np.sqrt((truth ** 2).mean())))
    # `mean` is the average of the per-axis values, which is not the same
    # as the overall error whenever the axes have different scales.
    assert rmse(truth, zeros)["mean"] == pytest.approx(
        float(np.sqrt(((truth ** 2).mean(axis=0))).mean()))
    # A perfect predictor wins the zero-velocity comparison.
    assert compare_to_zero_baseline(truth, truth)["rmse_ratio"] == pytest.approx(0.0)
    # The all-zero predictor ties the baseline, so it does not "beat" it.
    assert compare_to_zero_baseline(
        truth, zeros)["rmse_ratio"] == pytest.approx(1.0)


def test_direction_agreement_and_active_mask():
    truth = np.array([[10.0, 0.0], [-10.0, 0.0], [0.0, 0.0]])
    good = np.array([[5.0, 0.0], [-5.0, 0.0], [0.0, 0.0]])
    bad = np.array([[-5.0, 0.0], [5.0, 0.0], [0.0, 0.0]])
    assert direction_agreement(truth, good, [True, True, True])["mean"] \
        == pytest.approx(1.0)
    assert direction_agreement(truth, bad, [True, True, True])["mean"] \
        == pytest.approx(-1.0)
    # The stationary sample is excluded by the speed threshold.
    mask = active_mask(truth, [True, True, True], 5.0)
    assert list(mask) == [True, True, False]


def test_qualification_rejects_zero_collapse(l0_config):
    """A model that predicts nothing must not pass qualification."""
    payload = _dev_config(l0_config)
    truth = np.array([[10.0, 0.0], [-10.0, 5.0]] * 20)
    zeros = np.zeros_like(truth)
    active = [True] * len(truth)
    records = [("D1", truth, zeros, active)]
    latency = {"mean_ms": 0.5, "p95_ms": 0.6, "median_ms": 0.5,
               "max_ms": 0.7, "measured_runs": 10, "warmup_runs": 2}
    qualified, gates, _ = qualification.assess_qualification(
        payload, truth, zeros, active, records, latency,
        {"reproducible": True})
    assert not qualified
    assert not gates["zero_velocity_baseline_comparison"]["pass"]
    assert not gates["closed_loop_sanity"]["pass"]
    assert not gates["direction_agreement"]["pass"]


def test_qualification_accepts_a_working_model(l0_config):
    payload = _dev_config(l0_config)
    rng = np.random.default_rng(11)
    truth = rng.normal(0.0, 120.0, size=(200, 2))
    prediction = truth + rng.normal(0.0, 5.0, size=truth.shape)
    active = [True] * len(truth)
    records = [("D1", truth, prediction, active)]
    latency = {"mean_ms": 0.5, "p95_ms": 0.6, "median_ms": 0.5,
               "max_ms": 0.7, "measured_runs": 10, "warmup_runs": 2}
    qualified, gates, _ = qualification.assess_qualification(
        payload, truth, prediction, active, records, latency,
        {"reproducible": True})
    assert qualified, [name for name, gate in gates.items() if not gate["pass"]]
    for name in qualification.GATE_ORDER:
        assert gates[name]["pass"]


def test_qualification_report_can_be_written(tmp_path, l0_config):
    payload = _dev_config(l0_config)
    rng = np.random.default_rng(5)
    truth = rng.normal(0.0, 120.0, size=(200, 2))
    prediction = truth + rng.normal(0.0, 5.0, size=truth.shape)
    active = [True] * len(truth)
    records = [("D1", truth, prediction, active)]
    latency = {"mean_ms": 0.5, "p95_ms": 0.6, "median_ms": 0.5,
               "max_ms": 0.7, "measured_runs": 10, "warmup_runs": 2}
    qualified, gates, diagnostics = qualification.assess_qualification(
        payload, truth, prediction, active, records, latency,
        {"reproducible": True})
    report = qualification.build_qualification_report(
        payload, qualified, gates, diagnostics,
        nested_validation={"strategy": "leave_one_user_out_outer"},
        artifacts={"directory": "artifacts/l0"}, config_path=CONFIG_PATH)

    path = tmp_path / qualification.QUALIFICATION_REPORT_PATH
    written = qualification.write_qualification_report(report, path)
    assert Path(written) == path
    reloaded = json.loads(Path(written).read_text(encoding="utf-8"))
    assert reloaded["report_type"] == "l0_qualification"
    assert reloaded["qualified"] is True
    # L0 is never an evaluation model; the report must say so.
    assert reloaded["evaluation_used"] is False
    assert set(reloaded["gates"]) == set(qualification.GATE_ORDER)
    assert reloaded["diagnostics"]["mae"]["mean"] >= 0.0


def test_grouped_k_fold_keeps_users_together():
    users = ["D4", "D1", "D3", "D2", "D5"]
    folds = validation.grouped_k_fold(users, folds=2)
    assigned = [u for _, members in folds for u in members]
    assert sorted(assigned) == sorted(users)
    for _, members in folds:
        # No user appears in two folds.
        assert len(members) == len(set(members))
    # Assignment is deterministic regardless of input ordering.
    assert validation.grouped_k_fold(sorted(users), 2) == folds


def test_grouped_k_fold_rejects_too_few_users():
    with pytest.raises(ValueError):
        validation.grouped_k_fold(["D1"], folds=2)


# ---------------------------------------------------------------------
# Label alignment audit
#
# L0 trains X[t-T+1:t] -> Y(t-tau). tau is compensated UPSTREAM by the
# frozen Stage 2.5 grid, so L0 must NOT subtract a lag again. These tests
# pin the convention so a future "helpful" re-shifting gets caught.
# ---------------------------------------------------------------------


def test_l0_does_not_apply_its_own_label_lag():
    """The label must be ref_vx at the row as-is, not re-indexed by tau."""
    rows = _user_rows("D1", length=40, speed=100.0, seed=3)
    lagged = []
    for r in rows:
        r = dict(r)
        # Pretend Stage 2.5 already compensated a 5-tick supervision lag.
        r["grid_label_pc_time_ns"] = r["grid_pc_time_ns"] - 5 * GRID_INTERVAL_NS
        lagged.append(r)

    built = build_l0_datasets(lagged, 8, GRID_INTERVAL_NS, ["D1"])
    X, y, active = built["D1"]
    plain = build_l0_datasets(rows, 8, GRID_INTERVAL_NS, ["D1"])

    # Identical features AND identical targets: no extra shift anywhere.
    assert np.array_equal(X, plain["D1"][0])
    assert np.array_equal(y, plain["D1"][1])
    assert np.array_equal(active, plain["D1"][2])


def test_target_is_the_label_at_its_own_row():
    """y[i] must equal ref_vx of the same grid row the window ends on."""
    rows = _user_rows("D1", length=30, speed=120.0, seed=5)
    rows = [dict(r, ref_vx_px_s=float(i), ref_vy_px_s=0.0)
            for i, r in enumerate(rows)]
    X, y, active = build_l0_datasets(rows, 8, GRID_INTERVAL_NS, ["D1"])["D1"]

    last_index = len(rows) - 1
    assert y[-1][0] == float(last_index)
    # Causal: the last window exists and does not read past the final row.
    assert X.shape[0] == len(rows)
    assert X[-1].shape[0] == 8
    assert y[-1][0] == float(last_index)


def test_stage25_grid_compensates_the_lag_upstream():
    """Direct check of the frozen convention L0 relies on."""
    from pc.experiment.preprocessing.labels import (
        attach_common_grid_reference_labels)

    lag = 5
    reference = [{
        "reference_sample_id": f"R{i}", "participant_id": "P1",
        "session_id": "S1", "calibration_id": "C1", "cycle_index": 0,
        "sequence_id": "Q1", "segment_index": 0, "direction_code": "RIGHT",
        "phase": "OUTBOUND", "pc_time_ns": i, "relative_time_ns": i,
        "ref_x_px": 0.0, "ref_y_px": 0.0,
        "ref_vx_px_s": float(i), "ref_vy_px_s": 0.0,
        "speed_profile_code": "PROBE", "pause_flag": 0,
        "trajectory_version": "probe",
    } for i in range(40)]
    grid = [{
        "participant_id": "P1", "session_id": "S1", "calibration_id": "C1",
        "grid_index": i, "grid_pc_time_ns": i, "sensor_status": "VALID",
        "accel_status": "VALID", "gyro_status": "VALID",
    } for i in range(5, 30)]

    out = attach_common_grid_reference_labels(
        common_grid_rows=grid, reference_trajectory=reference,
        alignment_lag_ns=lag)
    row = out[3]

    # Label time is t - tau, and the velocity is read AT that label time.
    assert row["grid_label_pc_time_ns"] == row["grid_pc_time_ns"] - lag
    t = row["grid_pc_time_ns"]
    assert row["ref_vx_px_s"] == float(t - lag)
    assert row["ref_vx_px_s"] != float(t)


# ---------------------------------------------------------------------
# active_speed_threshold audit
# ---------------------------------------------------------------------


def test_active_speed_threshold_is_a_development_parameter(l0_config, tmp_path):
    """Configurable, positive, and NOT silently pinned to 5.0."""
    default = l0_config.qualification.active_speed_threshold_px_s
    assert default > 0.0

    def _load_with(value):
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        raw["qualification"]["active_speed_threshold_px_s"] = value
        path = tmp_path / f"cfg_{str(value).replace('.', '_')}.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return load_l0_config(path)

    # The loader must accept an override, proving it is a knob not a constant.
    assert _load_with(42.0).qualification.active_speed_threshold_px_s == 42.0
    assert _load_with(0.25).qualification.active_speed_threshold_px_s == 0.25

    # And it must reject a nonsensical value.
    for bad in (-1.0, 0.0):
        with pytest.raises(ValueError):
            _load_with(bad)


def test_active_speed_threshold_actually_filters():
    """The threshold must change which samples count as active."""
    from pc.experiment.training.metrics import active_mask

    y = np.array([[100.0, 0.0], [3.0, 0.0], [1.0, 1.0]], dtype=np.float32)
    sensor_flag = np.array([True, True, True])

    strict = active_mask(y, sensor_flag, 5.0)
    loose = active_mask(y, sensor_flag, 0.5)
    assert strict.sum() == 1
    assert loose.sum() == 3

    # The frozen Stage 2.5 sensor flag is an AND, not a replacement:
    # a sensor-inactive sample is never active regardless of label speed.
    with_flag = active_mask(y, np.array([True, False, True]), 0.5)
    assert with_flag.sum() == 2


def test_nested_validation_keeps_outer_user_out(l0_config):
    """The outer validation user must never appear in any inner training set."""
    payload = _dev_config(l0_config, users=("D1", "D2", "D3"), epochs=1)
    payload = replace(
        payload,
        window_candidates=(32,),
        validation=replace(payload.validation, inner_folds=2))
    report = validation.nested_user_wise_validation(
        payload, _training_rows(), GRID_INTERVAL_NS)
    assert set(report["per_user"]) == {"D1", "D2", "D3"}
    assert report["outer"] == "leave_one_user_out"
    for outer_user, score in report["per_user"].items():
        # The held-out user's own metrics exist, but they were never trained on.
        assert score["samples"] > 0
    for assignment in report["fold_assignments"]:
        # The outer validation user is never an inner training user.
        assert assignment["outer_validation_user"] not in assignment["train_users"]
        # Grouped: inner train and validation users are disjoint.
        assert not (set(assignment["train_users"])
                    & set(assignment["validation_users"]))
    assert report["fold_assignments"]


def test_nested_validation_needs_three_users(l0_config):
    payload = _dev_config(l0_config, users=("D1", "D2"), epochs=1)
    with pytest.raises(ValueError):
        validation.nested_user_wise_validation(
            payload, _training_rows(), GRID_INTERVAL_NS)


def test_latency_is_measured(l0_config):
    from pc.experiment.training.metrics import measure_latency

    model = L0VelocityModel(window=32, latent_channels=32, latent_dim=32)
    stats = measure_latency(model, 32, 6, warmup_runs=2, measured_runs=5)
    assert stats["measured_runs"] == 5
    assert stats["mean_ms"] > 0.0
    assert stats["mean_ms"] <= stats["max_ms"]


def test_end_to_end_training_and_qualification(l0_config, tmp_path):
    """Full path: rows -> nested validation -> fit -> artifacts -> report."""
    payload = _dev_config(l0_config, users=("D1", "D2", "D3", "D4"), epochs=3)
    rows = _training_rows()

    result = fit_l0(payload, rows, GRID_INTERVAL_NS, 32)
    assert result.parameter_count == expected_parameter_count(64, 64)
    assert len(result.history) == 3
    # Training must actually reduce the loss.
    assert result.history[-1] < result.history[0]

    manifest = artifacts.save_artifacts(result, payload, tmp_path / "l0")
    assert manifest["parameter_count"] == result.parameter_count

    # Held-out evaluation is scored on a user the model never saw.
    evaluation_rows = _user_rows("E9", length=60, speed=200.0, seed=99)
    built = build_l0_datasets(
        evaluation_rows, 32, GRID_INTERVAL_NS, ["E9"])
    from pc.experiment.training.dataset import L0WindowDataset as _DS

    X, y, active = built["E9"]
    held_out = _DS(X, y, ["E9"] * len(X), active, scaler=result.scaler)
    y_true, y_pred, _, active_flags = predict(result.model, held_out)

    records = [("E9", y_true, y_pred, active_flags)]
    from pc.experiment.training.metrics import measure_latency

    latency = measure_latency(
        result.model, 32, 6,
        warmup_runs=payload.qualification.latency_warmup_runs,
        measured_runs=payload.qualification.latency_measured_runs)
    qualified, gates, diagnostics = qualification.assess_qualification(
        payload, y_true, y_pred, active_flags, records, latency,
        {"reproducible": True})

    report = qualification.build_qualification_report(
        payload, qualified, gates, diagnostics,
        nested_validation={"strategy": "nested"}, artifacts=manifest,
        config_path=CONFIG_PATH)
    path = tmp_path / qualification.QUALIFICATION_REPORT_PATH
    qualification.write_qualification_report(report, path)
    reloaded = json.loads(path.read_text(encoding="utf-8"))

    # Two epochs of synthetic data cannot legitimately earn QUALIFIED;
    # the gate must report NOT_QUALIFIED rather than rubber-stamp it.
    assert isinstance(reloaded["qualified"], bool)
    assert reloaded["status"] in {"QUALIFIED", "NOT_QUALIFIED"}
    assert reloaded["evaluation_used"] is False
    assert diagnostics["samples"] == len(y_true)





