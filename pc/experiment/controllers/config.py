"""Explicit, immutable candidate policy; no implicit research hyperparameters."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re

PARAMETER_NAMES = ("B11", "B12", "B21", "B22", "bias_x", "bias_y")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def digest(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", value):
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    return value.upper()


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


@dataclass(frozen=True)
class AffineConfig:
    schema_version: str
    status: str
    configuration_id: str
    development_evidence: str
    functional_commit: str
    preprocessing_policy_sha256: str
    grid_interval_ns: int
    feature_axes: tuple[str, str]
    theta0: tuple[float, ...]
    lower_bounds: tuple[float, ...]
    upper_bounds: tuple[float, ...]
    ridge_lambda: float
    dead_zone_rad_s: float
    smoothing_alpha: float
    max_speed_px_s: float
    min_samples_per_sequence: int
    max_invalid_fraction: float
    condition_number_limit: float
    kkt_tolerance: float

    def __post_init__(self):
        if self.schema_version != "stage2.6-affine-candidate-v1":
            raise ValueError("unsupported controller schema_version")
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
        if (not isinstance(self.feature_axes, (tuple, list)) or
                len(self.feature_axes) != 2 or len(set(self.feature_axes)) != 2 or
                not set(self.feature_axes) <= {"gyro_x", "gyro_y", "gyro_z"}):
            raise ValueError("feature_axes must select two distinct preprocessed gyro axes")
        object.__setattr__(self, "feature_axes", tuple(self.feature_axes))
        for name in ("theta0", "lower_bounds", "upper_bounds"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or len(values) != 6:
                raise ValueError(f"{name} must contain exactly six parameters")
            object.__setattr__(self, name, tuple(finite(v, name) for v in values))
        if any(not lo < hi or not lo <= p <= hi for lo, p, hi in
               zip(self.lower_bounds, self.theta0, self.upper_bounds)):
            raise ValueError("strict lower < upper bounds must contain theta0")
        for name, minimum in (("grid_interval_ns", 1), ("min_samples_per_sequence", 3)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        for name in ("ridge_lambda", "dead_zone_rad_s", "smoothing_alpha",
                     "max_speed_px_s", "max_invalid_fraction",
                     "condition_number_limit", "kkt_tolerance"):
            object.__setattr__(self, name, finite(getattr(self, name), name))
        if not (self.ridge_lambda > 0 and self.dead_zone_rad_s >= 0 and
                0 < self.smoothing_alpha <= 1 and self.max_speed_px_s > 0 and
                0 <= self.max_invalid_fraction < 1 and self.condition_number_limit > 1 and
                0 < self.kkt_tolerance < 1):
            raise ValueError("invalid candidate numerical policy")

    def to_dict(self):
        # Round-trip to lists so JSON-loaded and in-memory configurations agree.
        return json.loads(canonical_json(asdict(self)))

    @property
    def sha256(self):
        return sha256(self.to_dict())


def features(row, config):
    """No second axis transform/bias correction/filter after Stage 2.5."""
    values = tuple(finite(row[axis], axis) for axis in config.feature_axes)
    return tuple(0.0 if abs(v) < config.dead_zone_rad_s else v for v in values)
