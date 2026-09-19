from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any

from pc.experiment.calibration.schema import (
    DIRECTION_CODES,
    PAUSE_FLAG_BY_PHASE,
    PHASE_CODES,
    REFERENCE_TRAJECTORY_COLUMNS,
)


def _error(
    code: str,
    detail: str | None = None,
) -> str:
    if detail is None:
        return code

    return f"{code}: {detail}"


def _collapsed_phases(
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    phases: list[str] = []

    for row in rows:
        phase = str(row["phase"])

        if not phases or phases[-1] != phase:
            phases.append(phase)

    return phases


def _ordered_sequence_groups(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[str, list[Mapping[str, Any]]]]:
    groups: OrderedDict[
        str,
        list[Mapping[str, Any]],
    ] = OrderedDict()

    for row in rows:
        sequence_id = str(row["sequence_id"])

        groups.setdefault(
            sequence_id,
            [],
        ).append(row)

    return list(groups.items())


def validate_reference_trajectory(
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []

    if not rows:
        return [
            _error(
                "EMPTY_REFERENCE_TRAJECTORY"
            )
        ]

    required = set(
        REFERENCE_TRAJECTORY_COLUMNS
    )

    # --------------------------------------------------
    # Required columns
    # --------------------------------------------------

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        missing = [
            column
            for column in
            REFERENCE_TRAJECTORY_COLUMNS
            if column not in row
        ]

        if missing:
            errors.append(
                _error(
                    "MISSING_REQUIRED_COLUMN",
                    (
                        f"row={row_index}, "
                        f"missing={missing!r}"
                    ),
                )
            )

    # Further semantic checks require complete rows.
    if any(
        not required.issubset(row.keys())
        for row in rows
    ):
        return errors

    # --------------------------------------------------
    # Identity consistency
    # --------------------------------------------------

    participant_id = rows[0]["participant_id"]
    session_id = rows[0]["session_id"]
    calibration_id = rows[0]["calibration_id"]

    if any(
        row["participant_id"] != participant_id
        for row in rows
    ):
        errors.append(
            _error(
                "PARTICIPANT_ID_MISMATCH"
            )
        )

    if any(
        row["session_id"] != session_id
        for row in rows
    ):
        errors.append(
            _error(
                "SESSION_ID_MISMATCH"
            )
        )

    if any(
        row["calibration_id"] != calibration_id
        for row in rows
    ):
        errors.append(
            _error(
                "CALIBRATION_ID_MISMATCH"
            )
        )

    # --------------------------------------------------
    # Reference sample ID uniqueness
    # --------------------------------------------------

    reference_ids = [
        str(row["reference_sample_id"])
        for row in rows
    ]

    if len(reference_ids) != len(
        set(reference_ids)
    ):
        errors.append(
            _error(
                "DUPLICATE_REFERENCE_SAMPLE_ID"
            )
        )

    # --------------------------------------------------
    # Cycle validity
    # --------------------------------------------------

    cycle_values: list[int] = []

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        try:
            cycle_index = int(
                row["cycle_index"]
            )
        except (TypeError, ValueError):
            errors.append(
                _error(
                    "INVALID_CYCLE_INDEX",
                    f"row={row_index}",
                )
            )
            continue

        cycle_values.append(cycle_index)

        if cycle_index not in (1, 2):
            errors.append(
                _error(
                    "INVALID_CYCLE_INDEX",
                    (
                        f"row={row_index}, "
                        f"value={cycle_index!r}"
                    ),
                )
            )

    if set(cycle_values) != {1, 2}:
        errors.append(
            _error(
                "INVALID_CYCLE_COUNT",
                (
                    "expected cycles={1, 2}, "
                    f"actual={sorted(set(cycle_values))!r}"
                ),
            )
        )

    # --------------------------------------------------
    # Direction and phase vocabularies
    # --------------------------------------------------

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        direction = str(
            row["direction_code"]
        )

        phase = str(
            row["phase"]
        )

        if direction not in DIRECTION_CODES:
            errors.append(
                _error(
                    "INVALID_DIRECTION_CODE",
                    (
                        f"row={row_index}, "
                        f"value={direction!r}"
                    ),
                )
            )

        if phase not in PHASE_CODES:
            errors.append(
                _error(
                    "INVALID_PHASE",
                    (
                        f"row={row_index}, "
                        f"value={phase!r}"
                    ),
                )
            )
            continue

        expected_pause = (
            PAUSE_FLAG_BY_PHASE[phase]
        )

        if row["pause_flag"] != expected_pause:
            errors.append(
                _error(
                    "INVALID_PAUSE_FLAG",
                    (
                        f"row={row_index}, "
                        f"phase={phase!r}"
                    ),
                )
            )

        if phase in {
            "CENTER_HOLD",
            "TARGET_HOLD",
        }:
            try:
                vx = float(
                    row["ref_vx_px_s"]
                )
                vy = float(
                    row["ref_vy_px_s"]
                )
            except (TypeError, ValueError):
                errors.append(
                    _error(
                        "INVALID_HOLD_VELOCITY",
                        f"row={row_index}",
                    )
                )
            else:
                if vx != 0.0 or vy != 0.0:
                    errors.append(
                        _error(
                            "INVALID_HOLD_VELOCITY",
                            (
                                f"row={row_index}, "
                                f"vx={vx!r}, vy={vy!r}"
                            ),
                        )
                    )

    # --------------------------------------------------
    # Timestamp monotonicity
    # --------------------------------------------------

    previous_pc: int | None = None
    previous_relative: int | None = None

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        try:
            pc_time = int(
                row["pc_time_ns"]
            )
        except (TypeError, ValueError):
            pc_time = None

        try:
            relative_time = int(
                row["relative_time_ns"]
            )
        except (TypeError, ValueError):
            relative_time = None

        if (
            pc_time is not None
            and previous_pc is not None
            and pc_time < previous_pc
        ):
            errors.append(
                _error(
                    "DECREASING_PC_TIME",
                    f"row={row_index}",
                )
            )

        if (
            relative_time is not None
            and previous_relative is not None
            and relative_time
            < previous_relative
        ):
            errors.append(
                _error(
                    "DECREASING_RELATIVE_TIME",
                    f"row={row_index}",
                )
            )

        if pc_time is not None:
            previous_pc = pc_time

        if relative_time is not None:
            previous_relative = (
                relative_time
            )

    # --------------------------------------------------
    # Sequence structure
    # --------------------------------------------------

    groups = _ordered_sequence_groups(
        rows
    )

    cycle_groups: dict[
        int,
        list[
            tuple[
                str,
                list[Mapping[str, Any]],
            ]
        ],
    ] = {
        1: [],
        2: [],
    }

    for sequence_id, sequence_rows in groups:
        try:
            cycle_index = int(
                sequence_rows[0][
                    "cycle_index"
                ]
            )
        except (TypeError, ValueError):
            continue

        if cycle_index in cycle_groups:
            cycle_groups[
                cycle_index
            ].append(
                (
                    sequence_id,
                    sequence_rows,
                )
            )

    for cycle_index in (1, 2):
        actual_groups = cycle_groups[
            cycle_index
        ]

        if len(actual_groups) != 8:
            errors.append(
                _error(
                    "INVALID_CYCLE_COUNT",
                    (
                        f"cycle={cycle_index}, "
                        "expected_sequences=8, "
                        f"actual={len(actual_groups)}"
                    ),
                )
            )

        actual_directions = [
            str(
                sequence_rows[0][
                    "direction_code"
                ]
            )
            for _, sequence_rows
            in actual_groups
        ]

        if actual_directions != list(
            DIRECTION_CODES
        ):
            errors.append(
                _error(
                    "DIRECTION_ORDER_MISMATCH",
                    (
                        f"cycle={cycle_index}, "
                        f"actual={actual_directions!r}"
                    ),
                )
            )

    # --------------------------------------------------
    # Per-sequence phase order and center-return
    # --------------------------------------------------

    try:
        global_center_x = float(
            rows[0]["ref_x_px"]
        )
        global_center_y = float(
            rows[0]["ref_y_px"]
        )
    except (TypeError, ValueError):
        global_center_x = None
        global_center_y = None

    for sequence_id, sequence_rows in groups:
        collapsed = _collapsed_phases(
            sequence_rows
        )

        if collapsed != list(
            PHASE_CODES
        ):
            errors.append(
                _error(
                    "PHASE_ORDER_MISMATCH",
                    (
                        f"sequence_id="
                        f"{sequence_id!r}, "
                        f"actual={collapsed!r}"
                    ),
                )
            )

        if (
            global_center_x is None
            or global_center_y is None
        ):
            continue

        first = sequence_rows[0]
        last = sequence_rows[-1]

        try:
            first_x = float(
                first["ref_x_px"]
            )
            first_y = float(
                first["ref_y_px"]
            )
            last_x = float(
                last["ref_x_px"]
            )
            last_y = float(
                last["ref_y_px"]
            )
        except (TypeError, ValueError):
            continue

        if (
            first_x != global_center_x
            or first_y != global_center_y
            or last_x != global_center_x
            or last_y != global_center_y
        ):
            errors.append(
                _error(
                    "MISSING_RETURN_TO_CENTER",
                    (
                        f"sequence_id="
                        f"{sequence_id!r}"
                    ),
                )
            )

    return errors