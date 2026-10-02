"""Fitts trial construction and outcome classification (stage 2.8).

The builder records the *actual* target-to-target amplitude from the
previous target's real endpoint. After a miss the cursor is never
teleported: the next movement origin is the miss endpoint.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .schema import HIT_OUTCOMES


#: Fraction of the tolerance band treated as the centre region.
CENTER_FRACTION = 0.25

#: Overshoot beyond the target edge required to call a
#: serial overshoot-reverse.
SERIAL_OVERSHOOT_FRACTION = 1.0


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        raise TypeError(f"{name} must be a real number.")

    number = float(value)

    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")

    return number


def _timestamp(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")

    number = int(value)

    if number <= 0:
        raise ValueError(f"{name} must be positive.")

    return number


def _project(
    point: tuple[float, float],
    origin: tuple[float, float],
    target: tuple[float, float],
) -> tuple[float, float, float]:
    """
    Project ``point`` into movement-axis coordinates.

    Returns ``(axial, orthogonal, radial)`` where ``axial`` is signed
    along origin->target, ``orthogonal`` is the perpendicular offset
    magnitude, and ``radial`` is the planar distance to the target.
    """
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    length = math.hypot(dx, dy)

    if length <= 0.0:
        raise ValueError(
            "movement origin must differ from the target centre."
        )

    ux = dx / length
    uy = dy / length

    px = point[0] - target[0]
    py = point[1] - target[1]

    axial = px * ux + py * uy
    orthogonal = abs(-px * uy + py * ux)
    radial = math.hypot(px, py)

    return axial, orthogonal, radial


def _classify_hit(
    axial: float,
    orthogonal: float,
    peak_axial: float,
    tolerance: float,
) -> str:
    """
    Classify a trial whose endpoint lies inside tolerance.

    A movement that passes the far edge of the target and returns is
    a serial overshoot-reverse. It is retained as a hit but flagged,
    because it violates the ballistic straight-line assumption used
    by the submovement decomposition.
    """
    overshoot_edge = tolerance * SERIAL_OVERSHOOT_FRACTION

    if peak_axial > overshoot_edge:
        return "SERIAL_OVERSHOOT_REVERSE"

    centre_band = tolerance * CENTER_FRACTION

    if abs(axial) <= centre_band and orthogonal <= centre_band:
        return "CENTER_HIT"

    if axial < 0.0:
        return "UNDERSHOOT"

    return "OVERSHOOT"


def _classify_miss(
    axial: float,
    orthogonal: float,
    tolerance: float,
) -> str:
    """
    Classify a trial whose endpoint lies outside tolerance.

    An orthogonal miss is dominated by the perpendicular error
    component; everything else is a plain valid miss.
    """
    if orthogonal > abs(axial):
        return "ORTHOGONAL_MISS"

    return "VALID_MISS"


def _peak_axial(
    path: Sequence[tuple[float, float]],
    origin: tuple[float, float],
    target: tuple[float, float],
    fallback: float,
) -> float:
    """Largest axial excursion observed along the movement path."""
    peak = fallback

    for point in path:
        try:
            candidate = (
                _finite(point[0], "path_x"),
                _finite(point[1], "path_y"),
            )
            axial, _, _ = _project(candidate, origin, target)
        except (TypeError, ValueError, IndexError):
            continue

        peak = max(peak, axial)

    return peak


def classify_trial(
    *,
    origin: tuple[float, float],
    target: tuple[float, float],
    diameter_px: float,
    endpoint: tuple[float, float],
    path: Sequence[tuple[float, float]] = (),
    onset_pc_time_ns: object = 0,
    end_pc_time_ns: object = 0,
) -> dict[str, Any]:
    """
    Classify one pointing movement.

    Returns the outcome plus the geometric evidence used to justify
    it. An out-of-order or non-positive timestamp yields
    ``INVALID_TIMESTAMP`` so the trial is excluded from statistics
    instead of silently biasing them.
    """
    diameter = _finite(diameter_px, "diameter_px")

    if diameter <= 0.0:
        raise ValueError("target diameter must be positive.")

    tolerance = diameter / 2.0

    origin = (
        _finite(origin[0], "origin_x"),
        _finite(origin[1], "origin_y"),
    )
    target = (
        _finite(target[0], "target_x"),
        _finite(target[1], "target_y"),
    )
    endpoint = (
        _finite(endpoint[0], "endpoint_x"),
        _finite(endpoint[1], "endpoint_y"),
    )

    axial, orthogonal, radial = _project(
        endpoint, origin, target
    )

    amplitude = math.hypot(
        target[0] - origin[0], target[1] - origin[1]
    )

    timestamp_valid = True
    movement_time_ns = 0
    onset = 0
    end = 0

    try:
        onset = _timestamp(onset_pc_time_ns, "onset_pc_time_ns")
        end = _timestamp(end_pc_time_ns, "end_pc_time_ns")
    except (TypeError, ValueError):
        timestamp_valid = False
    else:
        if end <= onset:
            timestamp_valid = False
        else:
            movement_time_ns = end - onset

    peak = _peak_axial(path, origin, target, axial)

    if not timestamp_valid:
        outcome = "INVALID_TIMESTAMP"
    elif radial <= tolerance:
        outcome = _classify_hit(
            axial, orthogonal, peak, tolerance
        )
    else:
        outcome = _classify_miss(axial, orthogonal, tolerance)

    return {
        "outcome": outcome,
        "movement_time_ns": movement_time_ns,
        "amplitude_px": amplitude,
        "tolerance_px": tolerance,
        "endpoint_error_px": radial,
        "signed_axial_error_px": axial,
        "orthogonal_error_px": orthogonal,
        "peak_overshoot_px": max(0.0, peak),
        "hit": outcome in HIT_OUTCOMES,
    }