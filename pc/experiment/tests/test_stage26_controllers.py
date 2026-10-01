"""Synthetic engineering qualification; coefficients are NOT research defaults."""

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from pc.experiment.controllers import AffineConfig, AffineController, fit_p2c
from pc.experiment.controllers.config import canonical_json, sha256
from pc.experiment.controllers.data import (
    IDENTITY, SEQUENCES, calibration_arrays, preprocessing_policy_sha256,
)
from pc.experiment.controllers.solver import solve_box_ridge
from pc.experiment.preprocessing.artifacts import build_stage25_from_artifacts
from pc.experiment.preprocessing.synthetic_qualification import _fixture, IDENTITY as SYNTHETIC_ID

REVISION = "1" * 40


def candidate(**changes):
    values = dict(
        schema_version="stage2.6-affine-candidate-v1", status="DEVELOPMENT_CANDIDATE",
        configuration_id="synthetic-test-only", development_evidence="synthetic unit test; not pilot",
        functional_commit=REVISION, preprocessing_policy_sha256="A" * 64,
        grid_interval_ns=10_000_000, feature_axes=("gyro_x", "gyro_y"),
        theta0=(1., 0., 0., 1., 0., 0.), lower_bounds=(-10.,) * 6,
        upper_bounds=(10.,) * 6, ridge_lambda=0.01, dead_zone_rad_s=0.,
        smoothing_alpha=1., max_speed_px_s=1000., min_samples_per_sequence=3,
        max_invalid_fraction=0.1, condition_number_limit=1e12, kkt_tolerance=1e-9,
    )
    values.update(changes)
    return AffineConfig(**values)


@pytest.fixture(scope="module")
def stage25_bundle(tmp_path_factory):
    fixture = _fixture(tmp_path_factory.mktemp("stage26") / "input", "baseline", REVISION)
    return build_stage25_from_artifacts(session_root=fixture["root"],
                                       preprocessing_config=fixture["config"], **SYNTHETIC_ID)


def inputs(bundle):
    config = candidate(preprocessing_policy_sha256=preprocessing_policy_sha256(
        bundle["preprocessing_config"]),
        # This short engineering fixture deliberately has 65/193 unlabelled rows.
        # This tolerance is NOT a proposed development/participant policy.
        max_invalid_fraction=0.35)
    declaration = dict(schema_version="stage2.6-data-v1", purpose="CALIBRATION_2C",
                       **{k: bundle["preprocessing_manifest"][k] for k in IDENTITY})
    return config, declaration


def sensor_row(index, u=1., v=0., **extra):
    return dict(grid_pc_time_ns=index * 10_000_000, gyro_x=u, gyro_y=v,
                sensor_status="VALID", **extra)


def test_stage25_fit_is_deterministic_and_preserves_inputs(stage25_bundle):
    bundle = deepcopy(stage25_bundle)
    before = deepcopy(bundle)
    config, declaration = inputs(bundle)
    a, timing_a = fit_p2c(bundle, config, declaration)
    b, timing_b = fit_p2c(bundle, config, declaration)
    assert canonical_json(a) == canonical_json(b)
    assert bundle == before
    assert len(a["theta"]) == 6
    assert a["selection"]["selected_row_count"] == 128
    assert len(a["selection"]["valid_samples_per_sequence"]) == 16
    assert a["fit"]["penalized_objective"] <= a["fit"]["calibration_mse_prior"] + 1e-8
    for timing in (timing_a, timing_b):
        assert timing["adapter_sha256"] == a["adapter_sha256"]
        assert 0 < timing["solver_elapsed_ns"] <= timing["adaptation_elapsed_ns"]
    identity = {k: declaration[k] for k in IDENTITY}
    controller = AffineController.from_adapter(config, a, identity=identity)
    assert controller.condition == "P2C"
    assert controller.theta == tuple(a["theta"])


def test_unconstrained_ridge_matches_closed_form():
    x = np.array([[1., 0., 1.], [0., 1., 1.], [-1., 2., 1.], [3., -2., 1.]])
    y = x @ np.array([[2., -1.], [3., 2.], [.5, -.7]])
    config = candidate()
    theta, diag = solve_box_ridge(x, y, config.theta0, config.lower_bounds,
                                 config.upper_bounds, .01, 1e12, 1e-9)
    prior = np.array([[1., 0.], [0., 1.], [0., 0.]])
    solution = np.linalg.solve(x.T @ x / len(x) + .01 * np.eye(3),
                               x.T @ y / len(x) + .01 * prior)
    assert theta == pytest.approx([*solution[:2, 0], *solution[:2, 1], *solution[2]])
    assert diag["faces_per_output"] == 27


def test_box_solver_is_not_unconstrained_then_clipped():
    x = np.array([[1., 1., 1.], [2., 1., 1.], [3., 2., 1.], [4., 3., 1.]])
    y = np.column_stack((4 * x[:, 0], -4 * x[:, 0]))
    theta, _ = solve_box_ridge(x, y, [0.] * 6, [-1.] * 6, [1.] * 6, .1, 1e12, 1e-9)
    assert all(-1 <= v <= 1 for v in theta)
    assert theta[0] == 1 and theta[2] == -1
    raw = np.linalg.solve(x.T @ x / len(x) + .1 * np.eye(3), x.T @ y / len(x))
    bounded = np.array([[theta[0], theta[2]], [theta[1], theta[3]], [theta[4], theta[5]]])
    def objective(coefficients):
        return np.mean(np.sum((x @ coefficients - y) ** 2, axis=1)) + .1 * np.sum(coefficients ** 2)
    assert objective(bounded) < objective(np.clip(raw, -1, 1))


@pytest.mark.parametrize("changes", [
    {"status": "FROZEN"}, {"functional_commit": "short"},
    {"preprocessing_policy_sha256": "not-a-hash"},
    {"feature_axes": ("gyro_x", "gyro_x")},
    {"feature_axes": ("accel_x", "gyro_y")},
    {"theta0": (0.,) * 5}, {"theta0": (float("nan"),) * 6},
    {"lower_bounds": (11.,) * 6}, {"upper_bounds": (-11.,) * 6},
    {"grid_interval_ns": True}, {"grid_interval_ns": 0},
    {"min_samples_per_sequence": 0}, {"ridge_lambda": 0.},
    {"dead_zone_rad_s": -1.}, {"smoothing_alpha": 0.},
    {"smoothing_alpha": 1.1}, {"max_speed_px_s": float("inf")},
    {"max_invalid_fraction": -0.1}, {"max_invalid_fraction": 1.},
    {"condition_number_limit": 0.}, {"kkt_tolerance": 0.},
])
def test_candidate_rejects_unsafe_policy(changes):
    with pytest.raises(ValueError):
        candidate(**changes)


def test_candidate_round_trip_and_canonical_unicode():
    config = candidate(configuration_id="synthetic-\u03b1")
    restored = AffineConfig(**config.to_dict())
    assert restored == config
    assert restored.sha256 == config.sha256
    assert "\u03b1" in canonical_json(config.to_dict())
    with pytest.raises(ValueError):
        canonical_json({"bad": float("nan")})


@pytest.mark.parametrize("purpose", ["DEVELOPMENT", "EVALUATION", "TEST", "MAIN_TASK"])
def test_fit_rejects_non_calibration_purpose(stage25_bundle, purpose):
    config, declaration = inputs(stage25_bundle)
    declaration["purpose"] = purpose
    with pytest.raises(ValueError, match="CALIBRATION_2C"):
        fit_p2c(stage25_bundle, config, declaration)


@pytest.mark.parametrize("component", [
    "row", "quality", "manifest", "manifest_hash", "declaration", "policy", "grid",
])
def test_fit_rejects_tampering_and_mismatched_bindings(stage25_bundle, component):
    bundle = deepcopy(stage25_bundle)
    config, declaration = inputs(bundle)
    if component == "row":
        next(r for r in bundle["common_grid_rows"] if r["label_status"] == "VALID")["gyro_x"] += 1
    elif component == "quality":
        bundle["preprocessing_quality"]["status"] = "TECHNICAL_INVALID"
    elif component == "manifest":
        bundle["preprocessing_manifest"]["session_id"] = "other-session"
    elif component == "manifest_hash":
        bundle["preprocessing_manifest_sha256"] = "0" * 64
    elif component == "declaration":
        declaration["participant_id"] = "other-participant"
    elif component == "policy":
        config = replace(config, preprocessing_policy_sha256="0" * 64)
    elif component == "grid":
        config = replace(config, grid_interval_ns=20_000_000)
    with pytest.raises(ValueError):
        fit_p2c(bundle, config, declaration)


def test_calibration_selection_and_invalid_fraction(stage25_bundle):
    config, _ = inputs(stage25_bundle)
    rows = stage25_bundle["common_grid_rows"]
    x, y, indices, counts = calibration_arrays(rows, config)
    assert len(x) == len(y) == len(indices) == 128
    assert counts == {key: 8 for key in SEQUENCES}
    assert all(rows[i]["label_status"] == rows[i]["sensor_status"] == "VALID" for i in indices)
    assert {rows[i]["phase"] for i in indices} == {
        "CENTER_HOLD", "OUTBOUND", "TARGET_HOLD", "RETURN"}
    with pytest.raises(ValueError, match="excessive invalid"):
        calibration_arrays(rows, replace(config, max_invalid_fraction=0.1))
    with pytest.raises(ValueError, match="insufficient valid samples"):
        calibration_arrays(rows, replace(config, min_samples_per_sequence=9))


@pytest.mark.parametrize("field,value", [
    ("direction_code", "UNKNOWN"), ("sequence_id", "C03_D01"),
    ("gyro_status", "INVALID"), ("accel_status", "INVALID"),
    ("gyro_x", float("nan")), ("ref_vx_px_s", float("inf")),
    ("grid_index", True), ("grid_pc_time_ns", -1),
])
def test_calibration_rejects_inconsistent_valid_rows(stage25_bundle, field, value):
    rows = deepcopy(stage25_bundle["common_grid_rows"])
    config, _ = inputs(stage25_bundle)
    next(r for r in rows if r["label_status"] == "VALID")[field] = value
    with pytest.raises(ValueError):
        calibration_arrays(rows, config)


def test_calibration_rejects_duplicate_ids_and_sequence_reordering(stage25_bundle):
    config, _ = inputs(stage25_bundle)
    rows = deepcopy(stage25_bundle["common_grid_rows"])
    rows[1]["grid_record_id"] = rows[0]["grid_record_id"]
    with pytest.raises(ValueError, match="record identity"):
        calibration_arrays(rows, config)
    rows = deepcopy(stage25_bundle["common_grid_rows"])
    first = next(r for r in rows if r["label_status"] == "VALID")
    first.update(sequence_id="C02_D08", direction_code=SEQUENCES["C02_D08"])
    with pytest.raises(ValueError, match="sequence"):
        calibration_arrays(rows, config)


def test_p0_affine_order_fixed_dt_and_label_independence():
    config = candidate(theta0=(2., 3., -4., 5., 6., -7.))
    controller = AffineController(config)
    first = controller.step(sensor_row(0, 2., 3.))
    assert first["condition"] == "P0" and first["status"] == "CLOCK_RESET"
    assert (first["vx_px_s"], first["vy_px_s"]) == (19., 0.)
    assert (first["x_px"], first["y_px"]) == (0., 0.)
    second = controller.step(sensor_row(1, 2., 3., ref_vx_px_s=1e9, ref_vy_px_s=-1e9))
    assert second["status"] == "VALID"
    assert (second["x_px"], second["y_px"]) == pytest.approx((.19, 0.))
    assert controller.theta == config.theta0


def test_replay_dead_zone_ema_norm_clamp_and_viewport():
    config = candidate(dead_zone_rad_s=.5, smoothing_alpha=.5, max_speed_px_s=2.)
    controller = AffineController(config, viewport=(.03, .02))
    assert controller.step(sensor_row(0, .4, -.4))["vx_px_s"] == 0.
    # Per-axis dead-zone precedes affine; EMA precedes vector-norm clamp.
    sample = controller.step(sensor_row(1, 6., 8.))
    assert (sample["vx_px_s"], sample["vy_px_s"]) == pytest.approx((1.2, 1.6))
    assert (sample["x_px"], sample["y_px"]) == pytest.approx((.012, .016))
    sample = controller.step(sensor_row(2, 0., 0.))
    assert (sample["vx_px_s"], sample["vy_px_s"]) == pytest.approx((.6, .8))
    assert (sample["x_px"], sample["y_px"]) == pytest.approx((.018, .02))
    sample = controller.step(sensor_row(3, -100., -100.))
    assert sample["y_px"] >= 0.
    assert np.hypot(sample["vx_px_s"], sample["vy_px_s"]) <= 2. + 1e-12


def test_replay_invalid_and_gap_hold_position_reset_smoothing():
    controller = AffineController(candidate(smoothing_alpha=.5))
    controller.step(sensor_row(0, 4.))
    before = controller.step(sensor_row(1, 4.))
    invalid = controller.step(dict(grid_pc_time_ns=20_000_000, sensor_status="INVALID"))
    assert invalid["status"] == "INVALID_SENSOR"
    assert invalid["x_px"] == before["x_px"]
    assert invalid["vx_px_s"] == 0.
    resumed = controller.step(sensor_row(3, 4.))
    assert resumed["vx_px_s"] == 2.  # No stale EMA from before invalid sensor.
    assert resumed["x_px"] == pytest.approx(before["x_px"] + .02)
    gap = controller.step(sensor_row(10, 8.))
    assert gap["status"] == "CLOCK_RESET" and gap["vx_px_s"] == 4.
    assert gap["x_px"] == resumed["x_px"]  # Never integrate across missing rows.


@pytest.mark.parametrize("bad", [
    {"grid_pc_time_ns": 0}, {"grid_pc_time_ns": -1}, {"grid_pc_time_ns": True},
    {"gyro_x": float("nan")}, {"gyro_y": float("inf")},
])
def test_replay_rejects_bad_samples_without_changing_state(bad):
    controller = AffineController(candidate())
    control = AffineController(candidate())
    controller.step(sensor_row(0))
    control.step(sensor_row(0))
    row = sensor_row(1)
    row.update(bad)
    with pytest.raises(ValueError):
        controller.step(row)
    assert controller.step(sensor_row(1)) == control.step(sensor_row(1))


def test_p0_and_p2c_with_same_parameters_have_same_dynamics(stage25_bundle):
    config, declaration = inputs(stage25_bundle)
    adapter, _ = fit_p2c(stage25_bundle, config, declaration)
    identity = {k: declaration[k] for k in IDENTITY}
    # Synthetic parity check only: copy the six learned values into a separate
    # P0 candidate so any difference must come from the shared replay pipeline.
    p0 = AffineController(replace(config, theta0=tuple(adapter["theta"])))
    p2c = AffineController.from_adapter(config, adapter, identity=identity)
    for index in range(20):
        row = sensor_row(index, index * .5, -index * .25, **identity)
        a, b = p0.step(row), p2c.step(row)
        assert a.pop("condition") == "P0" and b.pop("condition") == "P2C"
        assert a == b


@pytest.mark.parametrize("change", ["hash", "identity", "config", "bound", "condition"])
def test_adapter_rejects_corruption_and_incompatibility(stage25_bundle, change):
    config, declaration = inputs(stage25_bundle)
    adapter, _ = fit_p2c(stage25_bundle, config, declaration)
    identity = {k: declaration[k] for k in IDENTITY}
    if change == "hash":
        adapter["theta"][0] += .01
    elif change == "identity":
        identity["session_id"] = "other-session"
    elif change == "config":
        config = replace(config, smoothing_alpha=.5)
    else:
        if change == "bound":
            adapter["theta"][0] = 11.
        else:
            adapter["condition"] = "P0"
        adapter["adapter_sha256"] = sha256({
            k: v for k, v in adapter.items() if k != "adapter_sha256"})
    with pytest.raises(ValueError):
        AffineController.from_adapter(config, adapter, identity=identity)


def test_p2c_rejects_cross_session_replay(stage25_bundle):
    config, declaration = inputs(stage25_bundle)
    adapter, _ = fit_p2c(stage25_bundle, config, declaration)
    identity = {k: declaration[k] for k in IDENTITY}
    controller = AffineController.from_adapter(config, adapter, identity=identity)
    wrong = dict(identity, calibration_id="other-calibration")
    with pytest.raises(ValueError):
        controller.step(sensor_row(0, **wrong))
    assert controller.step(sensor_row(0, **identity))["status"] == "CLOCK_RESET"


def test_regularization_handles_rank_deficiency_and_condition_guard():
    x, y = np.ones((8, 3)), np.zeros((8, 2))
    args = (x, y, [0.] * 6, [-1.] * 6, [1.] * 6, .1)
    theta, diagnostics = solve_box_ridge(*args, 1e12, 1e-9)
    assert theta == pytest.approx([0.] * 6)
    assert max(diagnostics["scaled_kkt_residual_by_output"]) <= 1e-9
    with pytest.raises(ValueError, match="condition"):
        solve_box_ridge(*args, 2., 1e-9)
