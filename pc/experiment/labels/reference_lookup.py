from collections.abc import Mapping, Sequence
from typing import Any


_REQUIRED_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
    "sequence_id",
    "segment_index",
    "direction_code",
    "phase",
    "pc_time_ns",
    "ref_x_px",
    "ref_y_px",
    "ref_vx_px_s",
    "ref_vy_px_s",
)


def _empty_result(
    status: str,
) -> dict[str, object]:
    return {
        "label_status": status,
        "ref_x_px": None,
        "ref_y_px": None,
        "ref_vx_px_s": None,
        "ref_vy_px_s": None,
        "direction_code": None,
        "phase": None,
        "sequence_id": None,
    }


def _valid_result(
    *,
    ref_x_px: float,
    ref_y_px: float,
    ref_vx_px_s: float,
    ref_vy_px_s: float,
    direction_code: str,
    phase: str,
    sequence_id: str,
) -> dict[str, object]:
    return {
        "label_status": "VALID",
        "ref_x_px": ref_x_px,
        "ref_y_px": ref_y_px,
        "ref_vx_px_s": ref_vx_px_s,
        "ref_vy_px_s": ref_vy_px_s,
        "direction_code": direction_code,
        "phase": phase,
        "sequence_id": sequence_id,
    }


def _validate_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[int]:
    if not rows:
        raise ValueError(
            "reference trajectory must not be empty."
        )

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        missing = [
            field
            for field in _REQUIRED_FIELDS
            if field not in row
        ]

        if missing:
            raise ValueError(
                "reference trajectory row "
                f"{row_index} missing fields: "
                f"{missing!r}"
            )

    participant_id = rows[0]["participant_id"]
    session_id = rows[0]["session_id"]
    calibration_id = rows[0]["calibration_id"]

    if any(
        row["participant_id"] != participant_id
        for row in rows
    ):
        raise ValueError(
            "reference trajectory contains mixed "
            "participant identity."
        )

    if any(
        row["session_id"] != session_id
        for row in rows
    ):
        raise ValueError(
            "reference trajectory contains mixed "
            "session identity."
        )

    if any(
        row["calibration_id"] != calibration_id
        for row in rows
    ):
        raise ValueError(
            "reference trajectory contains mixed "
            "calibration identity."
        )

    times: list[int] = []

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        try:
            timestamp = int(
                row["pc_time_ns"]
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "reference trajectory contains "
                "invalid pc_time_ns at "
                f"row {row_index}."
            ) from exc

        times.append(timestamp)

    for index in range(
        1,
        len(times),
    ):
        if times[index] < times[index - 1]:
            raise ValueError(
                "reference trajectory pc_time_ns "
                "must be non-decreasing."
            )

    return times


def _exact_result(
    row: Mapping[str, Any],
) -> dict[str, object]:
    return _valid_result(
        ref_x_px=float(
            row["ref_x_px"]
        ),
        ref_y_px=float(
            row["ref_y_px"]
        ),
        ref_vx_px_s=float(
            row["ref_vx_px_s"]
        ),
        ref_vy_px_s=float(
            row["ref_vy_px_s"]
        ),
        direction_code=str(
            row["direction_code"]
        ),
        phase=str(
            row["phase"]
        ),
        sequence_id=str(
            row["sequence_id"]
        ),
    )


def _same_lookup_domain(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    boundary_fields = (
        "calibration_id",
        "sequence_id",
        "segment_index",
        "direction_code",
        "phase",
    )

    return all(
        left[field] == right[field]
        for field in boundary_fields
    )


def _linear(
    left: float,
    right: float,
    fraction: float,
) -> float:
    return (
        left
        + (right - left) * fraction
    )


def lookup_reference_state(
    reference_trajectory: Sequence[
        Mapping[str, Any]
    ],
    label_pc_time_ns: int,
) -> dict[str, object]:
    """
    Resolve reference state at a PC label timestamp.

    Exact timestamp matches take precedence. Interpolation
    is allowed only inside one calibration/sequence/
    segment/direction/phase domain. Extrapolation and
    boundary crossing fail closed.
    """
    rows = reference_trajectory

    times = _validate_rows(rows)

    try:
        query_time = int(
            label_pc_time_ns
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "label_pc_time_ns must be an integer."
        ) from exc

    first_time = times[0]
    last_time = times[-1]

    if (
        query_time < first_time
        or query_time > last_time
    ):
        return _empty_result(
            "OUTSIDE_REFERENCE"
        )

    exact_indices = [
        index
        for index, timestamp in enumerate(times)
        if timestamp == query_time
    ]

    if exact_indices:
        exact_rows = [
            rows[index]
            for index in exact_indices
        ]

        first_exact = exact_rows[0]

        if not all(
            _same_lookup_domain(
                first_exact,
                row,
            )
            for row in exact_rows[1:]
        ):
            return _empty_result(
                "UNRESOLVED_BOUNDARY"
            )

        return _exact_result(
            first_exact
        )

    left_index: int | None = None

    for index in range(
        len(times) - 1
    ):
        if (
            times[index]
            < query_time
            < times[index + 1]
        ):
            left_index = index
            break

    if left_index is None:
        return _empty_result(
            "UNRESOLVED_BOUNDARY"
        )

    right_index = left_index + 1

    left = rows[left_index]
    right = rows[right_index]

    if not _same_lookup_domain(
        left,
        right,
    ):
        return _empty_result(
            "UNRESOLVED_BOUNDARY"
        )

    left_time = times[left_index]
    right_time = times[right_index]

    denominator = (
        right_time - left_time
    )

    if denominator <= 0:
        return _empty_result(
            "UNRESOLVED_BOUNDARY"
        )

    fraction = (
        query_time - left_time
    ) / denominator

    ref_x = _linear(
        float(left["ref_x_px"]),
        float(right["ref_x_px"]),
        fraction,
    )

    ref_y = _linear(
        float(left["ref_y_px"]),
        float(right["ref_y_px"]),
        fraction,
    )

    ref_vx = _linear(
        float(left["ref_vx_px_s"]),
        float(right["ref_vx_px_s"]),
        fraction,
    )

    ref_vy = _linear(
        float(left["ref_vy_px_s"]),
        float(right["ref_vy_px_s"]),
        fraction,
    )

    return _valid_result(
        ref_x_px=ref_x,
        ref_y_px=ref_y,
        ref_vx_px_s=ref_vx,
        ref_vy_px_s=ref_vy,
        direction_code=str(
            left["direction_code"]
        ),
        phase=str(
            left["phase"]
        ),
        sequence_id=str(
            left["sequence_id"]
        ),
    )