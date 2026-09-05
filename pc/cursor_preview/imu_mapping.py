from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean


def apply_dead_zone(
    value: float,
    threshold: float,
    enabled: bool = True,
) -> float:
    if threshold < 0:
        raise ValueError(
            "dead-zone threshold must be >= 0"
        )

    if enabled and abs(value) < threshold:
        return 0.0

    return value


def gyro_to_velocity(
    gx: float,
    gz: float,
    *,
    bias_x: float,
    bias_z: float,
    gain: float,
    x_sign: int,
    y_sign: int,
    dead_zone: float,
    dead_zone_enabled: bool = True,
) -> tuple[float, float]:

    if x_sign not in (-1, 1):
        raise ValueError(
            "x_sign must be -1 or +1"
        )

    if y_sign not in (-1, 1):
        raise ValueError(
            "y_sign must be -1 or +1"
        )

    if gain < 0:
        raise ValueError(
            "gain must be >= 0"
        )

    corrected_x = apply_dead_zone(
        gx - bias_x,
        dead_zone,
        dead_zone_enabled,
    )

    corrected_z = apply_dead_zone(
        gz - bias_z,
        dead_zone,
        dead_zone_enabled,
    )

    vx = (
        float(x_sign)
        * gain
        * corrected_z
    )

    vy = (
        float(y_sign)
        * gain
        * corrected_x
    )

    return vx, vy


def integrate_cursor(
    x: float,
    y: float,
    vx: float,
    vy: float,
    dt: float,
    width: int,
    height: int,
) -> tuple[float, float]:

    if dt < 0:
        raise ValueError(
            "dt must be >= 0"
        )

    if width <= 0 or height <= 0:
        raise ValueError(
            "window dimensions must be > 0"
        )

    new_x = min(
        float(width),
        max(
            0.0,
            x + vx * dt,
        ),
    )

    new_y = min(
        float(height),
        max(
            0.0,
            y + vy * dt,
        ),
    )

    return new_x, new_y


@dataclass
class NeutralBiasEstimator:

    duration_s: float = 2.0

    _start_time_s: float | None = None

    _gx: list[float] = field(
        default_factory=list
    )

    _gy: list[float] = field(
        default_factory=list
    )

    _gz: list[float] = field(
        default_factory=list
    )


    def __post_init__(self) -> None:

        if self.duration_s <= 0:
            raise ValueError(
                "duration_s must be > 0"
            )


    def add_sample(
        self,
        t_monotonic_s: float,
        gx: float,
        gy: float,
        gz: float,
    ) -> None:

        if self._start_time_s is None:
            self._start_time_s = (
                t_monotonic_s
            )

        self._gx.append(gx)
        self._gy.append(gy)
        self._gz.append(gz)


    def ready(
        self,
        current_time_s: float,
    ) -> bool:

        if (
            self._start_time_s is None
            or not self._gx
        ):
            return False

        return (
            current_time_s
            - self._start_time_s
            >= self.duration_s
        )


    def bias(
        self,
    ) -> tuple[float, float, float]:

        if not self._gx:
            raise RuntimeError(
                "bias is not ready"
            )

        return (
            fmean(self._gx),
            fmean(self._gy),
            fmean(self._gz),
        )


    def reset(self) -> None:

        self._start_time_s = None

        self._gx.clear()
        self._gy.clear()
        self._gz.clear()