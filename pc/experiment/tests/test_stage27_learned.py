"""Synthetic engineering qualification for Stage 2.7 learned candidates.

Coefficients, capacities, and windows here are NOT research defaults;
they only exercise the frozen machinery end to end.
"""

import pytest
import torch

from pc.experiment.controllers.learned import (
    CAPACITIES, WINDOWS, LearnedConfig, LearnedController, build_encoder,
    parameter_count,
)
from pc.experiment.controllers.learned.adaptation import fit_l2c
from pc.experiment.controllers.learned.config import CAPACITY_LATENT
from pc.experiment.controllers.learned.data import (
    CHANNELS, extract_samples, build_windows, learned_dataset_sha256,
    labelled_targets,
)
from pc.experiment.controllers.data import (
    IDENTITY, preprocessing_policy_sha256,
)
from pc.experiment.preprocessing.artifacts import build_stage25_from_artifacts
from pc.experiment.preprocessing.synthetic_qualification import _fixture, IDENTITY as SYNTHETIC_ID

REVISION = "2" * 40


def candidate(**changes):
    values = dict(
        schema_version="stage2.7-learned-candidate-v1",
        status="DEVELOPMENT_CANDIDATE",
        configuration_id="synthetic-test-only",
        development_evidence="synthetic unit test; not pilot",
        functional_commit=REVISION,
        preprocessing_policy_sha256="B" * 64,
        grid_interval_ns=10_000_000,
        capacity="SMALL", window=32, latent_dim=16,
        max_speed_px_s=1500.0, seed=7,
    )
    values.update(changes)
    return LearnedConfig(**values)


@pytest.fixture(scope="module")
def stage25_bundle(tmp_path_factory):
    fixture = _fixture(tmp_path_factory.mktemp("stage27") / "input", "baseline", REVISION)
    return build_stage25_from_artifacts(session_root=fixture["root"],
                                        preprocessing_config=fixture["config"], **SYNTHETIC_ID)


def inputs(bundle):
    config = candidate(preprocessing_policy_sha256=preprocessing_policy_sha256(
        bundle["preprocessing_config"]))
    return config


def test_config_rejects_out_of_family_choices():
    with pytest.raises(ValueError):
        candidate(capacity="XL")
    with pytest.raises(ValueError):
        candidate(window=33)
    with pytest.raises(ValueError):
        candidate(latent_dim=20)
    with pytest.raises(ValueError):
        candidate(schema_version="stage2.8-learned-v1")


def test_config_digest_is_deterministic():
    assert candidate().sha256 == candidate().sha256
    assert candidate().sha256 != candidate(window=48).sha256


def test_architecture_matches_frozen_policy():
    for capacity in CAPACITIES:
        net = build_encoder(candidate(capacity=capacity))
        assert parameter_count(net) > 0
    assert set(WINDOWS) == {32, 48, 64}
    assert CAPACITY_LATENT == {"SMALL": 12, "MEDIUM": 24, "LARGE": 48}


def test_causality_of_encoder_output():
    torch.manual_seed(0)
    net = build_encoder(candidate())
    net.eval()  # disable dropout for the causality comparison
    x = torch.randn(1, 64, 6)  # (batch, window, channels)
    full = net(x)
    truncated = net(x[:, :33, :])
    assert torch.allclose(full[:, :33, :], truncated, atol=1e-5)


def test_extract_samples_requires_valid_labels(stage25_bundle):
    config = inputs(stage25_bundle)
    rows = stage25_bundle["common_grid_rows"]
    samples, labels, times, flags, run_starts = extract_samples(rows, config)
    assert len(samples) == len(labels) == len(times) == len(flags)
    assert all(len(s) == len(CHANNELS) for s in samples)
    assert run_starts[0] == 0


def test_build_windows_is_causal_and_correct_length(stage25_bundle):
    config = inputs(stage25_bundle)
    rows = stage25_bundle["common_grid_rows"]
    samples, labels, times, flags, run_starts = extract_samples(rows, config)
    X, y, active = build_windows(samples, labels, flags, config, run_starts)
    assert len(X[0]) == config.window
    # The last window of the first run must end with that run's last sample.
    first_run_end = (run_starts[1] if len(run_starts) > 1 else len(samples)) - 1
    last_of_first_run = [w for w in X if w[-1] == list(samples[first_run_end])]
    assert last_of_first_run
    # Unlabelled context rows must never become supervision targets.
    indices, targets = labelled_targets(y)
    assert indices and len(indices) == len(targets)
    unlabelled = [i for i, label in enumerate(y) if label is None]
    assert all(i not in indices for i in unlabelled)


def test_dataset_digest_is_deterministic(stage25_bundle):
    config = inputs(stage25_bundle)
    rows = stage25_bundle["common_grid_rows"]
    packed = extract_samples(rows, config)
    first = learned_dataset_sha256(*packed)
    second = learned_dataset_sha256(*packed)
    assert first == second and len(first) == 64


def test_controller_replay_contract(stage25_bundle):
    config = inputs(stage25_bundle)
    net = build_encoder(config)
    controller = LearnedController(config, net, initial_position=(100., 50.))
    assert controller.condition == "L0"
    rows = [r for r in stage25_bundle["common_grid_rows"]
            if r.get("sensor_status") == "VALID"][:config.window + 2]
    results = [controller.step(r) for r in rows]
    assert all(r["condition"] == "L0" for r in results)
    valid = [r for r in results if r["status"] == "VALID"]
    assert valid


def test_controller_clamps_speed(stage25_bundle):
    config = inputs(stage25_bundle)
    net = build_encoder(config)
    controller = LearnedController(config, net)
    row = dict(stage25_bundle["common_grid_rows"][0])
    row.update(sensor_status="VALID")
    for tick in range(config.window):
        stepped = dict(row)
        stepped["grid_pc_time_ns"] = int(row["grid_pc_time_ns"]) + \
            tick * config.grid_interval_ns
        result = controller.step(stepped)
    assert result["status"] == "VALID"
    assert (result["vx_px_s"] ** 2 + result["vy_px_s"] ** 2) <= \
        config.max_speed_px_s ** 2 + 1e-6


def test_controller_invalid_sensor_resets_window(stage25_bundle):
    config = inputs(stage25_bundle)
    net = build_encoder(config)
    controller = LearnedController(config, net)
    valid = [r for r in stage25_bundle["common_grid_rows"]
             if r.get("sensor_status") == "VALID"][:config.window]
    for r in valid:
        controller.step(dict(r))
    bad = dict(valid[-1])
    bad["sensor_status"] = "INVALID"
    result = controller.step(bad)
    assert result["status"] == "INVALID_SENSOR"
    assert controller._window == []
    result = controller.step(dict(valid[-1]))
    assert result["status"] == "CLOCK_RESET"


def test_controller_condition_l2c_and_position_bounds(stage25_bundle):
    config = inputs(stage25_bundle)
    net = build_encoder(config)
    controller = LearnedController(config, net, initial_position=(0., 0.),
                                   viewport=(10., 10.), condition="L2C")
    assert controller.condition == "L2C"
    valid = [r for r in stage25_bundle["common_grid_rows"]
             if r.get("sensor_status") == "VALID"][:config.window]
    for r in valid:
        result = controller.step(dict(r))
    assert result["status"] == "VALID"
    assert 0. <= result["x_px"] <= 10.
    assert 0. <= result["y_px"] <= 10.


def test_fit_l2c_freezes_encoder_and_adapts_output(stage25_bundle):
    config = inputs(stage25_bundle)
    net = build_encoder(config)
    before = [p.detach().clone() for p in net.parameters()]
    declaration = {k: stage25_bundle["preprocessing_manifest"][k] for k in IDENTITY}
    result = fit_l2c(config, net, stage25_bundle["common_grid_rows"],
                     identity=declaration, steps=25, lr=1e-2)
    after = [p.detach().clone() for p in net.parameters()]
    for a, b in zip(before, after):
        assert torch.equal(a, b)
    assert len(result.gamma) == len(result.beta) == 2
    assert len(result.dataset_sha256) == 64
    assert 1 <= result.steps <= 25
    assert result.final_loss >= 0


def test_fit_l2c_compensates_constant_label_bias(stage25_bundle):
    config = inputs(stage25_bundle)
    net = build_encoder(config)
    rows = [dict(r) for r in stage25_bundle["common_grid_rows"]]
    # Bias every VALID label by +30 px/s on vx: gamma/beta must compensate.
    for r in rows:
        if r.get("label_status") == "VALID":
            r["ref_vx_px_s"] = float(r["ref_vx_px_s"]) + 30.0
    declaration = {k: stage25_bundle["preprocessing_manifest"][k] for k in IDENTITY}
    result = fit_l2c(config, net, rows, identity=declaration, steps=400, lr=5e-2)
    assert abs(result.beta[0]) > 1.0

