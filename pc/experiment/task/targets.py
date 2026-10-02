"""Circular target layout for the reciprocal pointing task (stage 2.11).

This module is additive: it does not import from or modify the frozen
stage 2.8 modules (``schema``, ``sequence``, ``trials``, ``outcome``).
Layout generation is separated from outcome classification so that the
geometry used for a sequence can be validated before any observation
exists.

Design notes
------------
The layout is a *regular odd-sided polygon* inscribed in a circle of a
given ``radius`` around ``center``. Two properties motivate the odd
cardinality required by :func:`generate_circular_targets`:

1. An odd number of vertices places exactly one target on the
   reference axis, so the layout has a single unambiguous anchor
   rather than a mirror pair. ``target_id = 0`` is that anchor and the
   initial-acquisition target.
2. The reciprocal sequence closes its loop, so an odd polygon is
   traversed in an odd number of measured transitions. Even counts
   would split the ring into two disjoint halves and leave the anchor
   unreachable as a measured destination.

Determinism
-----------
``seed`` is the *only* source of variation. Given identical arguments
the same seed reproduces the same layout bit-for-bit, so a task
configuration can be replayed exactly. With the default ``seed`` of
``0`` and ``jitter_px`` of ``0.0`` the polygon is perfectly regular.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


#: Minimum number of targets in a reciprocal ring.
MIN_TARGET_COUNT = 3


#: Reference axis for ``target_id = 0``, in radians. ``-pi / 2`` places
#: the anchor target directly above the centre of the display.
REFERENCE_ANGLE_RAD = -math.pi / 2.0


@dataclass(frozen=True)
class Target:
    """One selectable target on the circular layout."""

    target_id: int
    x: float
    y: float
    width: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x, self.y)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "target_id": self.target_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
        }


def _finite_positive(value: float, name: str) -> float:
    number = float(value)

    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite: {value!r}")

    if number <= 0.0:
        raise ValueError(f"{name} must be positive: {value!r}")

    return number


def _center(center: tuple[float, float]) -> tuple[float, float]:
    try:
        x, y = center
    except (TypeError, ValueError) as exc:
        raise ValueError("center must be an (x, y) pair.") from exc

    x = float(x)
    y = float(y)

    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"center must be finite: {center!r}")

    return (x, y)


def validate_target_count(target_count: int) -> int:
    """Validate a target count for a reciprocal ring.

    Exposed separately so sequence builders can reject an odd/even
    violation before computing any geometry.
    """
    count = int(target_count)

    if count < MIN_TARGET_COUNT:
        raise ValueError(
            f"target_count must be at least {MIN_TARGET_COUNT}: {count}"
        )

    if count % 2 == 0:
        raise ValueError(
            f"target_count must be odd: {count} targets were supplied."
        )

    return count


def generate_circular_targets(
    *,
    screen_width: float,
    screen_height: float,
    center: tuple[float, float],
    radius: float,
    target_count: int,
    target_width: float,
    seed: int = 0,
    jitter_px: float = 0.0,
) -> list[Target]:
    """Build a deterministic circular target layout.

    Parameters
    ----------
    screen_width, screen_height:
        Display size in pixels. Used only to guarantee that every
        target is fully visible.
    center:
        ``(x, y)`` centre of the layout circle in display pixels.
    radius:
        Distance from ``center`` to each target centre, in pixels.
    target_count:
        Number of targets. **Must be odd** and at least
        ``MIN_TARGET_COUNT``.
    target_width:
        Target width in pixels; equal to the diameter.
    seed:
        Seed for the layout. The same seed always reproduces the same
        layout.
    jitter_px:
        Maximum deterministic positional jitter, in pixels, applied
        along each target's own radial direction.

    Returns
    -------
    list[Target]
        Targets ordered by ``target_id`` from ``0`` to
        ``target_count - 1``.

    Raises
    ------
    ValueError
        If the target count is even or too small, if a dimension is
        non-positive or non-finite, or if the ring would fall outside
        the display.
    """
    width_px = _finite_positive(screen_width, "screen_width")
    height_px = _finite_positive(screen_height, "screen_height")
    ring_radius = _finite_positive(radius, "radius")
    diameter = _finite_positive(target_width, "target_width")
    jitter = float(jitter_px)

    if not math.isfinite(jitter) or jitter < 0.0:
        raise ValueError(
            "jitter_px must be a non-negative finite number: "
            f"{jitter_px!r}"
        )

    count = validate_target_count(target_count)
    origin_x, origin_y = _center(center)
    extent = ring_radius + diameter / 2.0 + jitter

    if origin_x - extent < 0.0 or origin_y - extent < 0.0:
        raise ValueError(
            "the ring extends past the top or left edge of the display: "
            f"center={center!r}, radius={ring_radius}."
        )

    if origin_x + extent > width_px or origin_y + extent > height_px:
        raise ValueError(
            "the ring extends past the bottom or right edge of the "
            f"display: center={center!r}, radius={ring_radius}."
        )


    # Adjacent targets are separated by the chord of one step. Refuse a
    # ring whose targets would touch or overlap, because a hit test
    # could then be ambiguous for points lying between them.
    step_rad = 2.0 * math.pi / count
    chord = 2.0 * ring_radius * math.sin(step_rad / 2.0)

    if chord <= diameter + 2.0 * jitter:
        raise ValueError(
            "target layout would overlap: adjacent targets are "
            f"{chord:.4f}px apart but require "
            f"{diameter + 2.0 * jitter:.4f}px."
        )

    rng = random.Random(seed)
    start_angle = rng.uniform(0.0, 2.0 * math.pi)

    targets: list[Target] = []

    for index in range(count):
        angle = REFERENCE_ANGLE_RAD + start_angle + index * step_rad

        if jitter:
            distance = ring_radius + rng.uniform(-jitter, jitter)
        else:
            distance = ring_radius

        targets.append(
            Target(
                target_id=index,
                x=origin_x + distance * math.cos(angle),
                y=origin_y + distance * math.sin(angle),
                width=diameter,
            )
        )

    return targets

