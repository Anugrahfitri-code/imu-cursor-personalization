"""Build trial rows for a Fitts sequence (stage 2.8)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .outcome import classify_trial
from .schema import (
    HIT_OUTCOMES,
    INVALID_OUTCOMES,
    MISS_OUTCOMES,
    OUTCOMES,
    TASK_SCHEMA_VERSION,
    TRIAL_COLUMNS,
    TRIAL_ROLES,
    VALIDITY_RULES,
)
from .sequence import task_config_sha256


def _validate_enumerations() -> None:
    """Guard the schema enumerations against drift."""
    if len(set(OUTCOMES)) != len(OUTCOMES):
        raise AssertionError("OUTCOMES must be unique.")

    if len(set(TRIAL_ROLES)) != len(TRIAL_ROLES):
        raise AssertionError("TRIAL_ROLES must be unique.")

    if HIT_OUTCOMES & MISS_OUTCOMES:
        raise AssertionError(
            "HIT_OUTCOMES and MISS_OUTCOMES must be disjoint."
        )

    if HIT_OUTCOMES | MISS_OUTCOMES | INVALID_OUTCOMES != set(
        OUTCOMES
    ):
        raise AssertionError(
            "outcome categories must partition OUTCOMES."
        )

    if len(set(VALIDITY_RULES)) != len(VALIDITY_RULES):
        raise AssertionError("VALIDITY_RULES must be unique.")


def _validity(
    outcome: str,
    trial_role: str,
) -> tuple[bool, str, str]:
    """
    Resolve validity, rule, and exclusion reason for one trial.

    Single definition of miss handling for the whole pipeline:

    * hit                -> in MT, in throughput, error=0
    * valid miss         -> in MT, in throughput, error=1
    * technical failure  -> not in throughput
    * initial acquisition-> stored for audit, not in the denominator
    """
    if trial_role == "INITIAL_ACQUISITION":
        return False, "NOT_IN_DENOMINATOR", "INITIAL_ACQUISITION"

    if outcome in INVALID_OUTCOMES:
        return False, "INVALID", "INVALID_TIMESTAMP"

    if outcome in MISS_OUTCOMES:
        # A valid miss is a real observation: it has a real endpoint and
        # a real movement time, so it enters the MT and throughput
        # aggregates and is flagged error=1. Dropping it would delete
        # the slowest, most errorful movements and inflate throughput.
        return True, "MEASURED_MISS", ""

    if outcome in HIT_OUTCOMES:
        return True, "MEASURED_HIT", ""

    raise ValueError(f"unknown outcome: {outcome!r}")


def build_sequence_trials(
    *,
    participant_id: str,
    session_id: str,
    condition: str,
    sequence_index: int,
    targets: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Build one trial row per target.

    ``observations[i]`` supplies the recorded endpoint, optional path,
    and timestamps for target ``i``. The movement origin is the
    previous target's *actual* endpoint, so a miss never teleports
    the cursor.
    """
    _validate_enumerations()

    if len(targets) != len(observations):
        raise ValueError(
            "targets and observations must have equal length: "
            f"{len(targets)} != {len(observations)}"
        )

    if not targets:
        raise ValueError("a sequence must contain at least one target.")

    measured = len(targets) - 1

    if measured <= 0:
        raise ValueError(
            "a sequence needs at least one measured transition "
            "after the initial acquisition target."
        )

    if measured % 2 == 0:
        raise ValueError(
            "measured transition count must be odd: "
            f"{measured} transitions were supplied."
        )

    sequence_index = int(sequence_index)

    if sequence_index < 0:
        raise ValueError("sequence_index must be non-negative.")

    for name, value in (
        ("participant_id", participant_id),
        ("session_id", session_id),
        ("condition", condition),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string.")

    config_sha = task_config_sha256(config)

    cursor_x = float(config["start_x_px"])
    cursor_y = float(config["start_y_px"])

    rows: list[dict[str, Any]] = []

    for position, (target, observation) in enumerate(
        zip(targets, observations)
    ):
        target_index = int(target["target_index"])

        if target_index != position:
            raise ValueError(
                "target_index must match the sequential position: "
                f"{target_index} != {position}"
            )

        target_x = float(target["target_x_px"])
        target_y = float(target["target_y_px"])
        diameter = float(target["target_diameter_px"])

        endpoint_x = float(observation["endpoint_x_px"])
        endpoint_y = float(observation["endpoint_y_px"])

        result = classify_trial(
            origin=(cursor_x, cursor_y),
            target=(target_x, target_y),
            diameter_px=diameter,
            endpoint=(endpoint_x, endpoint_y),
            path=tuple(
                (float(point[0]), float(point[1]))
                for point in observation.get("path", ())
            ),
            onset_pc_time_ns=observation.get("onset_pc_time_ns", 0),
            end_pc_time_ns=observation.get("end_pc_time_ns", 0),
        )

        outcome = str(result["outcome"])

        trial_role = (
            "INITIAL_ACQUISITION"
            if target_index == 0
            else "MEASURED"
        )

        valid, rule, excluded = _validity(outcome, trial_role)

        rows.append(
            {
                "trial_record_id": (
                    f"{session_id}:{condition}:"
                    f"{sequence_index}:{target_index}"
                ),
                "participant_id": participant_id,
                "session_id": session_id,
                "condition": condition,
                "sequence_index": sequence_index,
                "target_index": target_index,
                "difficulty_id": str(target["difficulty_id"]),
                "trial_role": trial_role,
                "movement_start_x_px": cursor_x,
                "movement_start_y_px": cursor_y,
                "target_x_px": target_x,
                "target_y_px": target_y,
                "target_diameter_px": diameter,
                "origin_is_actual_endpoint": True,
                "amplitude_px": result["amplitude_px"],
                "tolerance_px": result["tolerance_px"],
                "onset_pc_time_ns": observation.get(
                    "onset_pc_time_ns", 0
                ),
                "end_pc_time_ns": observation.get("end_pc_time_ns", 0),
                "movement_time_ns": result["movement_time_ns"],
                "peak_overshoot_px": result["peak_overshoot_px"],
                "endpoint_error_px": result["endpoint_error_px"],
                "signed_axial_error_px": result[
                    "signed_axial_error_px"
                ],
                "orthogonal_error_px": result["orthogonal_error_px"],
                "outcome": outcome,
                "valid_trial": valid,
                "validity_rule": rule,
                "hit": bool(result["hit"]),
                # A valid miss is an error but is NOT excluded: it keeps
                # its endpoint and its movement time in the aggregate.
                "error": int(outcome in MISS_OUTCOMES),
                "excluded_reason": excluded,
                "task_config_sha256": config_sha,
                "task_schema_version": TASK_SCHEMA_VERSION,
            }
        )

        # Never teleport: the next origin is the real endpoint.
        cursor_x = endpoint_x
        cursor_y = endpoint_y

    if tuple(rows[0]) != TRIAL_COLUMNS:
        raise AssertionError(
            "trial row columns do not match TRIAL_COLUMNS."
        )

    return rows