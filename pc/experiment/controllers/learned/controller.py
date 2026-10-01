"""Causal L0/L2C replay on the common grid; no OS pointer injection."""

import math

from .data import CHANNELS


class LearnedController:
    """Replays a frozen L0 (or L2C) network step by step.

    Contract mirrors AffineController.step: first valid sample initializes
    the clock without displacement; gaps or INVALID_SENSOR rows reset the
    causal window to empty and emit zero velocity for that tick.
    """

    def __init__(self, config, network, *, initial_position=(0., 0.),
                 viewport=None, condition="L0"):
        self.config = config
        self.network = network
        self.network.eval()
        if condition not in ("L0", "L2C"):
            raise ValueError("condition must be L0 or L2C")
        self.condition = condition
        self.position = tuple(float(v) for v in initial_position)
        if any(not math.isfinite(v) for v in self.position):
            raise ValueError("initial position must be finite")
        if viewport is not None:
            self.viewport = tuple(float(v) for v in viewport)
            if len(self.viewport) != 2 or any(
                    bound <= 0 or p < 0 or p > bound for p, bound in
                    zip(self.position, self.viewport)):
                raise ValueError("invalid viewport/initial position")
        else:
            self.viewport = None
        self._last_time = None
        self._window = []

    def step(self, row):
        import torch
        t = int(row["grid_pc_time_ns"])
        expected = self.config.grid_interval_ns
        contiguous = self._last_time is not None and t - self._last_time == expected
        if not contiguous:
            self._window = []
        self._last_time = t
        if row.get("sensor_status") != "VALID":
            self._window = []
            return self._result(t, "INVALID_SENSOR", (0., 0.))
        values = []
        for column in CHANNELS:
            value = row[column]
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value):
                self._window = []
                return self._result(t, "INVALID_SENSOR", (0., 0.))
            values.append(float(value))
        self._window.append(values)
        if len(self._window) > self.config.window:
            self._window.pop(0)
        if len(self._window) < self.config.window:
            return self._result(t, "CLOCK_RESET", (0., 0.))
        with torch.no_grad():
            batch = torch.tensor([self._window], dtype=torch.float64).float()
            velocity = self.network(batch)[0, -1].tolist()
        velocity = self._clamp(velocity)
        dt = expected / 1e9
        self.position = (
            self.position[0] + velocity[0] * dt,
            self.position[1] + velocity[1] * dt,
        )
        if self.viewport is not None:
            self.position = (
                min(max(self.position[0], 0.), self.viewport[0]),
                min(max(self.position[1], 0.), self.viewport[1]),
            )
        return self._result(t, "VALID", velocity)

    def _clamp(self, velocity):
        limit = self.config.max_speed_px_s
        norm = math.hypot(velocity[0], velocity[1])
        if not all(math.isfinite(v) for v in velocity):
            raise ValueError("nonfinite network velocity")
        if norm > limit and norm > 0:
            scale = limit / norm
            velocity = (velocity[0] * scale, velocity[1] * scale)
        return tuple(velocity)

    def _result(self, t, status, velocity):
        return {"grid_pc_time_ns": t, "condition": self.condition, "status": status,
                "vx_px_s": velocity[0], "vy_px_s": velocity[1],
                "x_px": self.position[0], "y_px": self.position[1]}
