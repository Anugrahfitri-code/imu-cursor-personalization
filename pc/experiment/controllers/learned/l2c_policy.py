"""Fail-closed loader for configs/experiment/l2c_config.yaml.

The YAML is a human-readable declaration. This module re-derives the adapter
parameter budget from the code and refuses to load if the declaration and the
implementation disagree, so the document cannot silently drift away from the
frozen per-user parameter budget.
"""

from pathlib import Path

import yaml

from .config import ADAPTER_USER_PARAMETERS, LATENT_DIMS, MAX_USER_PARAMETERS

DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "configs" / "experiment" / "l2c_config.yaml"
)
SCHEMA_VERSION = "stage2.9-l2c-latent-adapter-v1"
REQUIRED_FROZEN = ("encoder", "latent_projection", "head")


def load_l2c_policy(path=None):
    path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    with path.open("r", encoding="utf-8") as handle:
        policy = yaml.safe_load(handle)
    if not isinstance(policy, dict):
        raise ValueError("L2C policy must be a mapping")
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported L2C policy schema_version")

    adapter = policy.get("adapter")
    if not isinstance(adapter, dict):
        raise ValueError("L2C policy must declare an adapter")
    if adapter.get("kind") != "latent_affine":
        raise ValueError("L2C adapter must be latent_affine")
    if adapter.get("apply_point") != "latent":
        raise ValueError("L2C adapter must be applied at the latent")
    if adapter.get("gamma_init") != "ones" or adapter.get("beta_init") != "zeros":
        raise ValueError("L2C adapter must initialise as the identity")

    frozen = policy.get("frozen_modules")
    if not isinstance(frozen, dict):
        raise ValueError("L2C policy must declare frozen_modules")
    unfrozen = [name for name in REQUIRED_FROZEN if frozen.get(name) is not True]
    if unfrozen:
        raise ValueError(f"L2C policy must freeze {', '.join(REQUIRED_FROZEN)}")

    if tuple(policy.get("latent_dims") or ()) != LATENT_DIMS:
        raise ValueError("L2C policy latent_dims disagree with the code")
    if ADAPTER_USER_PARAMETERS != {d: 2 * d for d in LATENT_DIMS}:
        raise ValueError("adapter parameter budget must be 2 * d")

    return policy


def user_parameter_count(latent_dim):
    """Per-participant parameter budget for an adapter of width d."""
    if latent_dim not in ADAPTER_USER_PARAMETERS:
        raise ValueError(f"latent_dim must be one of {LATENT_DIMS}")
    return ADAPTER_USER_PARAMETERS[latent_dim]


__all__ = ["DEFAULT_POLICY_PATH", "SCHEMA_VERSION", "load_l2c_policy",
           "user_parameter_count", "MAX_USER_PARAMETERS"]