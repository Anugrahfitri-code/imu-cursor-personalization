"""Causal common-grid P0/P2C replay; no OS pointer injection."""

import math

from .config import PARAMETER_NAMES, digest, features, finite, sha256
from .data import IDENTITY


def adapter_parameters(adapter, config, identity):
    expected = {"schema_version", "condition", "status", "controller_config_sha256",
                "parameter_names", "theta", "provenance", "selection", "fit",
                "numeric_environment", "adapter_sha256"}
    if set(adapter) != expected:
        raise ValueError("adapter schema mismatch")
    body = {k: v for k, v in adapter.items() if k != "adapter_sha256"}
    if digest(adapter["adapter_sha256"], "adapter hash") != sha256(body):
        raise ValueError("adapter hash mismatch")
    if (adapter["schema_version"] != "stage2.6-adapter-v1" or adapter["condition"] != "P2C" or
            adapter["status"] != "DEVELOPMENT_CANDIDATE" or
            adapter["controller_config_sha256"] != config.sha256 or
            adapter["parameter_names"] != list(PARAMETER_NAMES)):
        raise ValueError("adapter is incompatible with controller candidate")
    if set(identity) != set(IDENTITY) or any(
            adapter["provenance"][k] != identity[k] for k in IDENTITY):
        raise ValueError("adapter participant/session/calibration mismatch")
    theta = adapter["theta"]
    if not isinstance(theta, list) or len(theta) != 6:
        raise ValueError("adapter must contain exactly six parameters")
    theta = tuple(finite(v, "adapter parameter") for v in theta)
    if any(not lo <= v <= hi for lo, v, hi in
           zip(config.lower_bounds, theta, config.upper_bounds)):
        raise ValueError("adapter violates fixed bounds")
    return theta


class AffineController:
    """P0 constructor has no calibration input and never learns from labels.

    Both conditions share dead-zone, identity response curve, EMA, norm clamp,
    fixed-dt integration and optional viewport clipping. First valid sample
    initializes the clock without displacement; gaps/invalid samples reset EMA.
    """

    def __init__(self, config, *, initial_position=(0., 0.), viewport=None):
        self.config = config
        self.theta = config.theta0
        self.condition = "P0"
        self._identity = None
        self.position = tuple(finite(v, "initial position") for v in initial_position)
        if len(self.position) != 2:
            raise ValueError("position must have two coordinates")
        self.viewport = None if viewport is None else tuple(finite(v, "viewport") for v in viewport)
        if self.viewport is not None and (len(self.viewport) != 2 or
                any(v <= 0 for v in self.viewport) or any(
                    p < 0 or p > bound for p, bound in zip(self.position, self.viewport))):
            raise ValueError("invalid viewport/initial position")
        self._last_time = None
        self._velocity = (0., 0.)

    @classmethod
    def from_adapter(cls, config, adapter, *, identity, **kwargs):
        theta = adapter_parameters(adapter, config, identity)
        result = cls(config, **kwargs)
        result.theta = theta
        result.condition = "P2C"
        result._identity = dict(identity)
        return result

    def step(self, row):
        t = row["grid_pc_time_ns"]
        if type(t) is not int or t < 0 or (self._last_time is not None and t <= self._last_time):
            raise ValueError("controller timestamps must be increasing nonnegative integers")
        if self._identity is not None and any(row[k] != self._identity[k] for k in IDENTITY):
            raise ValueError("controller row identity mismatch")
        contiguous = self._last_time is not None and t - self._last_time == self.config.grid_interval_ns
        if row["sensor_status"] != "VALID":
            self._last_time = t
            self._velocity = (0., 0.)
            return self._result(t, "INVALID_SENSOR", (0., 0.))
        u, v = features(row, self.config)
        a, b, c, d, e, f = self.theta
        affine = (a * u + b * v + e, c * u + d * v + f)
        if not all(math.isfinite(value) for value in affine):
            raise ValueError("nonfinite affine velocity")
        previous = self._velocity if contiguous else (0., 0.)
        alpha = self.config.smoothing_alpha
        velocity = tuple(alpha * new + (1 - alpha) * old for new, old in zip(affine, previous))
        magnitude = math.hypot(*velocity)
        if not math.isfinite(magnitude):
            raise ValueError("unsafe velocity norm")
        if magnitude > self.config.max_speed_px_s:
            velocity = tuple(value * (self.config.max_speed_px_s / magnitude) for value in velocity)
        position = self.position
        if contiguous:
            dt = self.config.grid_interval_ns / 1e9
            position = tuple(p + vel * dt for p, vel in zip(position, velocity))
            if not all(math.isfinite(p) for p in position):
                raise ValueError("nonfinite cursor position")
            if self.viewport is not None:
                position = tuple(min(max(p, 0.), limit) for p, limit in zip(position, self.viewport))
        self.position, self._last_time, self._velocity = position, t, velocity
        return self._result(t, "VALID" if contiguous else "CLOCK_RESET", velocity)

    def _result(self, t, status, velocity):
        return {"grid_pc_time_ns": t, "condition": self.condition, "status": status,
                "vx_px_s": velocity[0], "vy_px_s": velocity[1],
                "x_px": self.position[0], "y_px": self.position[1]}
