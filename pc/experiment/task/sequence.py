"""Deterministic Fitts target-sequence generation (stage 2.8)."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from typing import Any

from .schema import TARGET_COLUMNS, TASK_SCHEMA_VERSION


REQUIRED_CONFIG_FIELDS = (
    "task_id",
    "canvas_width_px",
    "canvas_height_px",
    "start_x_px",
    "start_y_px",
    "target_count",
    "measured_transitions",
    "difficulty_ids",
    "amplitude_px_by_difficulty",
    "diameter_px_by_difficulty",
    "task_config_version",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any, name: str) -> str:
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def index_of_difficulty(
    amplitude_px: float,
    diameter_px: float,
) -> float:
    """Shannon formulation of Fitts' index of difficulty."""
    if diameter_px <= 0.0:
        raise ValueError("target diameter must be positive.")

    if amplitude_px <= 0.0:
        raise ValueError("amplitude must be positive.")

    return math.log2(amplitude_px / diameter_px + 1.0)


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        raise TypeError(f"{name} must be a real number.")

    number = float(value)

    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")

    return number


def _require_config(config: Mapping[str, Any]) -> None:
    missing = [
        field
        for field in REQUIRED_CONFIG_FIELDS
        if field not in config
    ]

    if missing:
        raise ValueError(
            "task config missing required fields: "
            f"{missing!r}"
        )

    for field in (
        "canvas_width_px",
        "canvas_height_px",
        "target_count",
        "measured_transitions",
    ):
        _finite(config[field], field)

    if config["task_id"] != "fitts_pointing":
        raise ValueError("task_id must be 'fitts_pointing'.")


def _candidate_positions(
    amplitude_px: float,
    diameter_px: float,
    config: Mapping[str, Any],
) -> list[tuple[float, float]]:
    """
    Build angularly spaced in-bounds candidate target positions.

    Candidates sit on a ring of ``amplitude_px`` around the start
    point. The origin itself is never emitted, so the first
    measured movement is never zero-amplitude.
    """
    start_x = _finite(config["start_x_px"], "start_x_px")
    start_y = _finite(config["start_y_px"], "start_y_px")

    width = _finite(
        config["canvas_width_px"], "canvas_width_px"
    )
    height = _finite(
        config["canvas_height_px"], "canvas_height_px"
    )

    margin = diameter_px / 2.0 + 1.0

    ratio = min(
        1.0, (diameter_px + 4.0) / (2.0 * amplitude_px)
    )
    step = max(math.degrees(2.0 * math.asin(ratio)), 15.0)

    positions: list[tuple[float, float]] = []
    angle = 0.0

    while angle < 360.0:
        radians = math.radians(angle)
        x = start_x + amplitude_px * math.cos(radians)
        y = start_y + amplitude_px * math.sin(radians)

        if (
            margin <= x <= width - margin
            and margin <= y <= height - margin
        ):
            positions.append((x, y))

        angle += step

    return positions


def _difficulty_plan(config: Mapping[str, Any]) -> list[str]:
    """
    Build the per-target difficulty plan.

    The plan is odd-length by construction because ``target_count``
    must be odd, which keeps the sequence start and end on
    opposite halves of the ring.
    """
    target_count = int(config["target_count"])
    measured = int(config["measured_transitions"])

    if measured <= 0:
        raise ValueError("measured_transitions must be positive.")

    if measured % 2 == 0:
        raise ValueError(
            "measured_transitions must be odd so the sequence ends "
            "on the opposite half of the ring from where it began."
        )

    if target_count != measured + 1:
        raise ValueError(
            "target_count must equal measured_transitions + 1 "
            "because the first target is the initial acquisition "
            "trial that is excluded from the movement denominator."
        )

    difficulties = list(config["difficulty_ids"])

    if not difficulties:
        raise ValueError("difficulty_ids must not be empty.")

    return [
        difficulties[index % len(difficulties)]
        for index in range(target_count)
    ]


def generate_target_sequence(
    *,
    config: Mapping[str, Any],
    sequence_index: int,
    seed: int,
) -> list[dict[str, object]]:
    """
    Generate one deterministic target sequence.

    The first target is the initial acquisition. Its trial role is
    assigned by the trial builder, which excludes it from the
    movement denominator.
    """
    _require_config(config)

    sequence_index = int(sequence_index)

    if sequence_index < 0:
        raise ValueError("sequence_index must be non-negative.")

    plan = _difficulty_plan(config)

    seed_material = {
        "task_id": config["task_id"],
        "sequence_index": sequence_index,
        "seed": int(seed),
        "task_config_version": config["task_config_version"],
        "target_count": int(config["target_count"]),
        "plan": plan,
    }

    sequence_seed = int(
        digest(seed_material, "sequence_seed")[:16], 16
    )

    generator = random.Random(sequence_seed)

    amplitudes = config["amplitude_px_by_difficulty"]
    diameters = config["diameter_px_by_difficulty"]

    rows: list[dict[str, object]] = []
    previous_x = _finite(config["start_x_px"], "start_x_px")
    previous_y = _finite(config["start_y_px"], "start_y_px")
    used_positions: list[tuple[float, float]] = []

    for target_index, difficulty_id in enumerate(plan):
        if difficulty_id not in amplitudes:
            raise ValueError(
                "difficulty_ids references unknown difficulty: "
                f"{difficulty_id!r}"
            )

        amplitude = _finite(
            amplitudes[difficulty_id],
            f"amplitude_px_by_difficulty[{difficulty_id}]",
        )
        diameter = _finite(
            diameters[difficulty_id],
            f"diameter_px_by_difficulty[{difficulty_id}]",
        )

        candidates = _candidate_positions(
            amplitude, diameter, config
        )

        if not candidates:
            raise ValueError(
                "no in-bounds target position for difficulty "
                f"{difficulty_id!r}; check canvas size and "
                "amplitude."
            )

        ordered = generator.sample(
            candidates, k=len(candidates)
        )

        best: tuple[float, float] | None = None
        best_score = -math.inf

        for candidate in ordered:
            distance = math.hypot(
                candidate[0] - previous_x,
                candidate[1] - previous_y,
            )

            # Prefer positions whose actual target-to-target
            # amplitude is close to the nominal amplitude while
            # still varying across the sequence.
            score = -abs(distance - amplitude)

            # Penalise positions already used earlier in the same
            # sequence so consecutive blocks do not repeat the
            # same three movements.
            if any(
                math.hypot(
                    candidate[0] - used_x,
                    candidate[1] - used_y,
                ) < diameter
                for used_x, used_y in used_positions
            ):
                score -= amplitude

            if score > best_score:
                best_score = score
                best = candidate

        if best is None:
            raise ValueError(
                "target selection failed for difficulty "
                f"{difficulty_id!r}."
            )

        target_x, target_y = best

        rows.append(
            {
                "target_index": target_index,
                "sequence_index": sequence_index,
                "difficulty_id": difficulty_id,
                "target_x_px": target_x,
                "target_y_px": target_y,
                "target_diameter_px": diameter,
            }
        )

        previous_x = target_x
        previous_y = target_y
        used_positions.append((target_x, target_y))

    if tuple(rows[0]) != TARGET_COLUMNS:
        raise AssertionError(
            "target row columns do not match TARGET_COLUMNS."
        )

    return rows


def task_config_sha256(config: Mapping[str, Any]) -> str:
    """Stable SHA-256 over the task configuration."""
    _require_config(config)

    return digest(
        {
            "schema_version": TASK_SCHEMA_VERSION,
            "config": {
                field: config[field]
                for field in REQUIRED_CONFIG_FIELDS
            },
        },
        "task_config",
    )