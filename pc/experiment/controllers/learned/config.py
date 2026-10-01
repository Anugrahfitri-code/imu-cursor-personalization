"""Explicit, immutable learned candidate policy; architecture is fixed by plan."""

from dataclasses import asdict, dataclass
import json
import math
import re

from ..config import canonical_json, digest, finite, sha256

# Frozen candidate family (Subtahap 2.7): causal Conv1D, four blocks,
# kernel 5, dilations 1/2/4/8, LayerNorm, GELU, dropout 0.10, latent
# projection, linear head to vx/vy. Changing any constant here is a
# development reset, not a tuning knob.
ARCHITECTURE = {
    "blocks": 4,
    "kernel_size": 5,
    "dilations": (1, 2, 4, 8),
    "dropout": 0.10,
    "channels_in": 6,
    "outputs": 2,
}
CAPACITIES = ("SMALL", "MEDIUM", "LARGE")
CAPACITY_LATENT = {"SMALL": 12, "MEDIUM": 24, "LARGE": 48}
WINDOWS = (32, 48, 64)
LATENT_DIMS = (16, 32, 64)  # L2C user-specific adaptation dims d.

# Per-user parameter budget of the latent affine adapter: 2 * d (gamma + beta).
ADAPTER_USER_PARAMETERS = {d: 2 * d for d in LATENT_DIMS}
MAX_USER_PARAMETERS = max(ADAPTER_USER_PARAMETERS.values())


@dataclass(frozen=True)
class LearnedConfig:
    schema_version: str
    status: str
    configuration_id: str
    development_evidence: str
    functional_commit: str
    preprocessing_policy_sha256: str
    grid_interval_ns: int
    capacity: str
    window: int
    latent_dim: int
    max_speed_px_s: float
    seed: int

    def __post_init__(self):
        if self.schema_version != "stage2.7-learned-candidate-v1":
            raise ValueError("unsupported learned controller schema_version")
        if self.status != "DEVELOPMENT_CANDIDATE":
            raise ValueError("this implementation is not a participant release")
        for name in ("configuration_id", "development_evidence"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be nonempty")
        if not isinstance(self.functional_commit, str) or not re.fullmatch(
                r"[a-fA-F0-9]{40}", self.functional_commit):
            raise ValueError("functional_commit must be a full Git commit")
        object.__setattr__(self, "preprocessing_policy_sha256", digest(
            self.preprocessing_policy_sha256, "preprocessing_policy_sha256"))
        if (not isinstance(self.grid_interval_ns, int) or isinstance(
                self.grid_interval_ns, bool) or self.grid_interval_ns <= 0):
            raise ValueError("grid_interval_ns must be a positive integer")
        if self.capacity not in CAPACITIES:
            raise ValueError(f"capacity must be one of {CAPACITIES}")
        if not isinstance(self.window, int) or isinstance(self.window, bool) \
                or self.window not in WINDOWS:
            raise ValueError(f"window must be one of {WINDOWS}")
        if not isinstance(self.latent_dim, int) or isinstance(self.latent_dim, bool) \
                or self.latent_dim not in LATENT_DIMS:
            raise ValueError(f"latent_dim must be one of {LATENT_DIMS}")
        object.__setattr__(self, "max_speed_px_s", finite(
            self.max_speed_px_s, "max_speed_px_s"))
        if self.max_speed_px_s <= 0:
            raise ValueError("max_speed_px_s must be positive")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) \
                or not 0 <= self.seed < 2 ** 31:
            raise ValueError("seed must be a reproducible 31-bit integer")

    @property
    def latent_channels(self):
        return CAPACITY_LATENT[self.capacity]

    def to_dict(self):
        # Round-trip to lists so JSON-loaded and in-memory configurations agree.
        return json.loads(canonical_json(asdict(self)))

    @property
    def sha256(self):
        return sha256(self.to_dict())