import math
from collections.abc import Mapping
from typing import Any

from pc.experiment.calibration.schema import (
    DIRECTION_CODES,
    PAUSE_FLAG_BY_PHASE,
    REFERENCE_TRAJECTORY_COLUMNS,
)


_DIRECTION_VECTORS = {
    "RIGHT": (1.0, 0.0),
    "UP_RIGHT": (
        1.0 / math.sqrt(2.0),
        -1.0 / math.sqrt(2.0),
    ),
    "UP": (0.0, -1.0),
    "UP_LEFT": (
        -1.0 / math.sqrt(2.0),
        -1.0 / math.sqrt(2.0),
    ),
    "LEFT": (-1.0, 0.0),
    "DOWN_LEFT": (
        -1.0 / math.sqrt(2.0),
        1.0 / math.sqrt(2.0),
    ),
    "DOWN": (0.0, 1.0),
    "DOWN_RIGHT": (
        1.0 / math.sqrt(2.0),
        1.0 / math.sqrt(2.0),
    ),
}


_REQUIRED_CONFIG_FIELDS = (
    "center_x_px",
    "center_y_px",
    "radius_px",
    "center_hold_ns",
    "outbound_ns",
    "target_hold_ns",
    "return_ns",
    "sample_interval_ns",
    "speed_profile_code",
    "trajectory_version",
)


def _require_config(
    config: Mapping[str, Any],
) -> None:
    missing = [
        field
        for field in _REQUIRED_CONFIG_FIELDS
        if field not in config
    ]

    if missing:
        raise ValueError(
            "Missing trajectory config field(s): "
            f"{missing!r}"
        )

    sample_interval_ns = int(
        config["sample_interval_ns"]
    )

    if sample_interval_ns <= 0:
        raise ValueError(
            "sample_interval_ns must be positive."
        )

    if float(config["radius_px"]) <= 0.0:
        raise ValueError(
            "radius_px must be positive."
        )

    for field in (
        "center_hold_ns",
        "outbound_ns",
        "target_hold_ns",
        "return_ns",
    ):
        duration_ns = int(config[field])

        if duration_ns <= 0:
            raise ValueError(
                f"{field} must be positive."
            )

        if duration_ns % sample_interval_ns != 0:
            raise ValueError(
                f"{field} must be an exact multiple "
                "of sample_interval_ns."
            )


def _sample_count(
    duration_ns: int,
    sample_interval_ns: int,
) -> int:
    return duration_ns // sample_interval_ns


def _make_row(
    *,
    reference_sample_id: str,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    cycle_index: int,
    sequence_id: str,
    segment_index: int,
    direction_code: str,
    phase: str,
    pc_time_ns: int,
    relative_time_ns: int,
    ref_x_px: float,
    ref_y_px: float,
    ref_vx_px_s: float,
    ref_vy_px_s: float,
    speed_profile_code: str,
    pause_flag: int,
    trajectory_version: str,
) -> dict[str, object]:
    row = {
        "reference_sample_id":
            reference_sample_id,
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "cycle_index":
            cycle_index,
        "sequence_id":
            sequence_id,
        "segment_index":
            segment_index,
        "direction_code":
            direction_code,
        "phase":
            phase,
        "pc_time_ns":
            pc_time_ns,
        "relative_time_ns":
            relative_time_ns,
        "ref_x_px":
            ref_x_px,
        "ref_y_px":
            ref_y_px,
        "ref_vx_px_s":
            ref_vx_px_s,
        "ref_vy_px_s":
            ref_vy_px_s,
        "speed_profile_code":
            speed_profile_code,
        "pause_flag":
            pause_flag,
        "trajectory_version":
            trajectory_version,
    }

    if tuple(row.keys()) != REFERENCE_TRAJECTORY_COLUMNS:
        raise RuntimeError(
            "Internal reference trajectory schema "
            "order mismatch."
        )

    return row


def generate_guided_2c(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    start_pc_time_ns: int,
    config: Mapping[str, Any],
) -> list[dict[str, object]]:
    """
    Generate a deterministic synthetic/candidate guided 2C
    reference trajectory.

    Numerical configuration values supplied here are
    engineering parameters. This function does not declare
    them to be final participant-study parameters.
    """
    _require_config(config)

    center_x = float(config["center_x_px"])
    center_y = float(config["center_y_px"])
    radius = float(config["radius_px"])

    center_hold_ns = int(
        config["center_hold_ns"]
    )
    outbound_ns = int(
        config["outbound_ns"]
    )
    target_hold_ns = int(
        config["target_hold_ns"]
    )
    return_ns = int(
        config["return_ns"]
    )
    sample_interval_ns = int(
        config["sample_interval_ns"]
    )

    speed_profile_code = str(
        config["speed_profile_code"]
    )
    trajectory_version = str(
        config["trajectory_version"]
    )

    start_pc_time_ns = int(start_pc_time_ns)

    phase_counts = {
        "CENTER_HOLD": _sample_count(
            center_hold_ns,
            sample_interval_ns,
        ),
        "OUTBOUND": _sample_count(
            outbound_ns,
            sample_interval_ns,
        ),
        "TARGET_HOLD": _sample_count(
            target_hold_ns,
            sample_interval_ns,
        ),
        "RETURN": _sample_count(
            return_ns,
            sample_interval_ns,
        ),
    }

    rows: list[dict[str, object]] = []

    global_sample_index = 0
    reference_counter = 1

    for cycle_index in (1, 2):
        for direction_index, direction_code in enumerate(
            DIRECTION_CODES,
            start=1,
        ):
            sequence_id = (
                f"C{cycle_index:02d}_"
                f"D{direction_index:02d}"
            )

            dx, dy = _DIRECTION_VECTORS[
                direction_code
            ]

            target_x = center_x + radius * dx
            target_y = center_y + radius * dy

            outbound_duration_s = (
                outbound_ns / 1_000_000_000.0
            )
            return_duration_s = (
                return_ns / 1_000_000_000.0
            )

            outbound_vx = (
                radius * dx
                / outbound_duration_s
            )
            outbound_vy = (
                radius * dy
                / outbound_duration_s
            )

            return_vx = (
                -radius * dx
                / return_duration_s
            )
            return_vy = (
                -radius * dy
                / return_duration_s
            )

            phase_specs = (
                (
                    1,
                    "CENTER_HOLD",
                    phase_counts["CENTER_HOLD"],
                ),
                (
                    2,
                    "OUTBOUND",
                    phase_counts["OUTBOUND"],
                ),
                (
                    3,
                    "TARGET_HOLD",
                    phase_counts["TARGET_HOLD"],
                ),
                (
                    4,
                    "RETURN",
                    phase_counts["RETURN"],
                ),
            )

            for (
                segment_index,
                phase,
                count,
            ) in phase_specs:
                for local_index in range(count):
                    relative_time_ns = (
                        global_sample_index
                        * sample_interval_ns
                    )

                    pc_time_ns = (
                        start_pc_time_ns
                        + relative_time_ns
                    )

                    if phase == "CENTER_HOLD":
                        ref_x = center_x
                        ref_y = center_y
                        ref_vx = 0.0
                        ref_vy = 0.0

                    elif phase == "OUTBOUND":
                        progress = (
                            local_index + 1
                        ) / count

                        ref_x = (
                            center_x
                            + radius * dx * progress
                        )
                        ref_y = (
                            center_y
                            + radius * dy * progress
                        )

                        ref_vx = outbound_vx
                        ref_vy = outbound_vy

                    elif phase == "TARGET_HOLD":
                        ref_x = target_x
                        ref_y = target_y
                        ref_vx = 0.0
                        ref_vy = 0.0

                    elif phase == "RETURN":
                        progress = (
                            local_index + 1
                        ) / count

                        ref_x = (
                            target_x
                            - radius * dx * progress
                        )
                        ref_y = (
                            target_y
                            - radius * dy * progress
                        )

                        ref_vx = return_vx
                        ref_vy = return_vy

                    else:
                        raise RuntimeError(
                            f"Unsupported phase: {phase!r}"
                        )

                    rows.append(
                        _make_row(
                            reference_sample_id=(
                                f"REF"
                                f"{reference_counter:06d}"
                            ),
                            participant_id=participant_id,
                            session_id=session_id,
                            calibration_id=calibration_id,
                            cycle_index=cycle_index,
                            sequence_id=sequence_id,
                            segment_index=segment_index,
                            direction_code=(
                                direction_code
                            ),
                            phase=phase,
                            pc_time_ns=pc_time_ns,
                            relative_time_ns=(
                                relative_time_ns
                            ),
                            ref_x_px=ref_x,
                            ref_y_px=ref_y,
                            ref_vx_px_s=ref_vx,
                            ref_vy_px_s=ref_vy,
                            speed_profile_code=(
                                speed_profile_code
                            ),
                            pause_flag=(
                                PAUSE_FLAG_BY_PHASE[
                                    phase
                                ]
                            ),
                            trajectory_version=(
                                trajectory_version
                            ),
                        )
                    )

                    reference_counter += 1
                    global_sample_index += 1

    return rows