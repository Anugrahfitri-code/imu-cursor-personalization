"""L2C latent affine adapter: z_new = gamma * z + beta on the frozen latent.

These tests pin the personalisation contract from the proposal: the global
model never moves, and the only per-user parameters are the 2*d adapter
coefficients (32 / 64 / 128 for d = 16 / 32 / 64).
"""

import copy

import pytest
import torch
import yaml

from pc.experiment.controllers.learned.adapter import LatentAffineAdapter
from pc.experiment.controllers.learned.adaptation import fit_l2c
from pc.experiment.controllers.learned.config import (ADAPTER_USER_PARAMETERS,
                                                      LATENT_DIMS,
                                                      MAX_USER_PARAMETERS)
from pc.experiment.controllers.learned.controller import LearnedController
from pc.experiment.controllers.learned.data import CHANNELS
from pc.experiment.controllers.learned.l2c_policy import load_l2c_policy
from pc.experiment.controllers.learned.network import build_encoder
from pc.experiment.preprocessing.artifacts import build_stage25_from_artifacts
from pc.experiment.preprocessing.synthetic_qualification import _fixture
from pc.experiment.preprocessing.synthetic_qualification import \
    IDENTITY as SYNTHETIC_ID
from pc.experiment.tests.test_stage27_learned import IDENTITY, inputs


def test_adapter_parameter_count_is_two_times_latent_dim():
    assert ADAPTER_USER_PARAMETERS == {16: 32, 32: 64, 64: 128}
    assert MAX_USER_PARAMETERS == 128
    for latent_dim, expected in ADAPTER_USER_PARAMETERS.items():
        adapter = LatentAffineAdapter(latent_dim)
        fitted = sum(p.numel() for p in adapter.parameters() if p.requires_grad)
        assert fitted == expected == adapter.user_parameter_count()


def test_adapter_only_holds_gamma_and_beta():
    adapter = LatentAffineAdapter(16)
    assert [name for name, _ in adapter.named_parameters()] == ["gamma", "beta"]
    assert all(p.requires_grad for p in adapter.parameters())


def test_gamma_initialises_to_ones():
    for latent_dim in LATENT_DIMS:
        gamma = LatentAffineAdapter(latent_dim).gamma.detach()
        assert gamma.shape == (latent_dim,)
        assert torch.equal(gamma, torch.ones(latent_dim))


def test_beta_initialises_to_zeros():
    for latent_dim in LATENT_DIMS:
        beta = LatentAffineAdapter(latent_dim).beta.detach()
        assert beta.shape == (latent_dim,)
        assert torch.equal(beta, torch.zeros(latent_dim))


def test_identity_adapter_reproduces_the_latent():
    z = torch.randn(3, 5, 32)
    adapter = LatentAffineAdapter(32)
    assert adapter.is_identity()
    assert torch.equal(adapter(z), z)


def test_adapter_applies_coordinate_wise_affine_map():
    adapter = LatentAffineAdapter(16)
    gamma = torch.arange(1, 17, dtype=torch.float32)
    beta = torch.linspace(-1.0, 1.0, 16)
    with torch.no_grad():
        adapter.gamma.copy_(gamma)
        adapter.beta.copy_(beta)
    z = torch.ones(1, 16)
    assert torch.allclose(adapter(z), (gamma + beta).reshape(1, 16))
    assert torch.allclose(adapter(z * 2.0), (2.0 * gamma + beta).reshape(1, 16))


def test_adapter_rejects_latent_dim_outside_the_family():
    for bad in (0, 8, 12, 20, 24, 48, 128, True):
        with pytest.raises(ValueError):
            LatentAffineAdapter(bad)


def test_adapter_rejects_mismatched_latent_width():
    with pytest.raises(ValueError):
        LatentAffineAdapter(16)(torch.randn(2, 3, 32))


REVISION = "2" * 40


@pytest.fixture(scope="module")
def stage25_bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("l2c_adapter") / "input"
    fixture = _fixture(root, "baseline", REVISION)
    return build_stage25_from_artifacts(session_root=fixture["root"],
                                        preprocessing_config=fixture["config"],
                                        **SYNTHETIC_ID)


def _adapt(stage25_bundle, config, network):
    declaration = {k: stage25_bundle["preprocessing_manifest"][k]
                   for k in IDENTITY}
    return fit_l2c(config, network, stage25_bundle["common_grid_rows"],
                   identity=declaration, steps=400, lr=5e-2)


def test_encoder_and_head_stay_frozen_during_adaptation(stage25_bundle):
    config = inputs(stage25_bundle)
    network = build_encoder(config)
    before = [p.detach().clone() for p in network.parameters()]
    adaptation = _adapt(stage25_bundle, config, network)
    assert all(not p.requires_grad for p in network.parameters())
    for old, new in zip(before, network.parameters()):
        assert torch.equal(old, new.detach())
    assert adaptation.user_parameter_count == 2 * config.latent_dim


def test_no_gradient_reaches_the_encoder_or_the_head(stage25_bundle):
    config = inputs(stage25_bundle)
    network = build_encoder(config)
    adapter = LatentAffineAdapter(config.latent_dim)
    windows = torch.randn(6, config.window, len(CHANNELS))
    targets = torch.randn(6, 2)

    # Control: without the freeze the same graph DOES hand gradients to the
    # network, so the assertions below cannot pass vacuously.
    control = build_encoder(config)
    z_control = control.encode(windows)[:, -1, :]
    assert z_control.shape == (6, config.latent_dim)
    torch.mean((control.decode(adapter(z_control)) - targets) ** 2).backward()
    assert adapter.gamma.grad is not None
    assert any(p.grad is not None for p in control.parameters())

    # Frozen network, identical graph: only the adapter keeps its gradient.
    for parameter in network.parameters():
        parameter.requires_grad_(False)
    z = network.encode(windows)[:, -1, :]
    torch.mean((network.decode(adapter(z)) - targets) ** 2).backward()
    for name, parameter in network.named_parameters():
        assert parameter.grad is None, f"{name} received a gradient"
        assert not parameter.requires_grad


def test_adaptation_is_latent_width_not_output_width(stage25_bundle):
    config = inputs(stage25_bundle)
    network = build_encoder(config)
    adaptation = _adapt(stage25_bundle, config, network)
    assert adaptation.latent_dim == config.latent_dim
    assert len(adaptation.gamma) == len(adaptation.beta) == config.latent_dim
    assert adaptation.gamma != [1.0, 1.0]
    assert 1 <= adaptation.steps <= 400
    assert adaptation.final_loss >= 0.0
    assert len(adaptation.dataset_sha256) == 64


def test_l2c_controller_applies_the_adapter_only_for_l2c(stage25_bundle):
    config = inputs(stage25_bundle)
    network = build_encoder(config)
    adaptation = _adapt(stage25_bundle, config, network)
    with pytest.raises(ValueError):
        LearnedController(config, network, condition="L0",
                          adapter=adaptation.adapter)
    controller = LearnedController(config, network, condition="L2C",
                                   adapter=adaptation.adapter)
    assert controller.adapter is adaptation.adapter
    batch = torch.randn(1, config.window, len(CHANNELS))
    assert controller.network(batch, controller.adapter).shape \
        == (1, config.window, 2)


def test_l2c_policy_declares_a_latent_adapter_with_the_code_budget():
    policy = load_l2c_policy()
    assert policy["adapter"]["kind"] == "latent_affine"
    assert policy["adapter"]["apply_point"] == "latent"
    assert policy["adapter"]["gamma_init"] == "ones"
    assert policy["adapter"]["beta_init"] == "zeros"
    assert policy["frozen_modules"] == {"encoder": True,
                                        "latent_projection": True,
                                        "head": True}
    assert tuple(policy["latent_dims"]) == LATENT_DIMS


def test_l2c_policy_fails_closed_on_a_tampered_declaration(tmp_path):
    mutations = (
        lambda p: p["adapter"].__setitem__("apply_point", "output"),
        lambda p: p["adapter"].__setitem__("kind", "output_affine"),
        lambda p: p["adapter"].__setitem__("gamma_init", "zeros"),
        lambda p: p["adapter"].__setitem__("beta_init", "ones"),
        lambda p: p["frozen_modules"].__setitem__("head", False),
        lambda p: p["frozen_modules"].__setitem__("encoder", False),
        lambda p: p.__setitem__("latent_dims", [8, 16, 32]),
        lambda p: p.__setitem__("schema_version", "other"),
    )
    for mutate in mutations:
        broken = copy.deepcopy(load_l2c_policy())
        mutate(broken)
        target = tmp_path / "l2c_config.yaml"
        target.write_text(yaml.safe_dump(broken), encoding="utf-8")
        with pytest.raises(ValueError):
            load_l2c_policy(target)
