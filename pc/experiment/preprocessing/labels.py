from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pc.experiment.labels.reference_lookup import (
    lookup_reference_state,
)


_IDENTITY_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
)


_REFERENCE_RESULT_FIELDS = (
    "label_status",
    "ref_x_px",
    "ref_y_px",
    "ref_vx_px_s",
    "ref_vy_px_s",
    "direction_code",
    "phase",
    "sequence_id",
)


def _parse_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be an integer."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be an integer."
        ) from exc

    return parsed


def _validate_common_grid_identity(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not rows:
        raise ValueError(
            "common grid must not be empty."
        )

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        if not isinstance(
            row,
            Mapping,
        ):
            raise ValueError(
                "common grid row "
                f"{row_index} must be a mapping."
            )

        required_fields = (
            *_IDENTITY_FIELDS,
            "grid_pc_time_ns",
        )

        missing = [
            field
            for field in required_fields
            if field not in row
        ]

        if missing:
            raise ValueError(
                "common grid row "
                f"{row_index} missing fields: "
                f"{missing!r}."
            )

    identity = {
        field:
            rows[0][field]
        for field in _IDENTITY_FIELDS
    }

    for field in _IDENTITY_FIELDS:
        if any(
            row[field] != identity[field]
            for row in rows
        ):
            identity_name = (
                field
                .replace("_id", "")
                .replace("_", " ")
            )

            raise ValueError(
                "common grid contains mixed "
                f"{identity_name} identity."
            )

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        _parse_integer(
            row["grid_pc_time_ns"],
            field_name=(
                "common grid "
                f"grid_pc_time_ns at row {row_index}"
            ),
        )

    return identity


def _validate_reference_identity(
    reference_trajectory: Sequence[
        Mapping[str, Any]
    ],
    *,
    expected_identity: Mapping[str, Any],
) -> None:
    if not reference_trajectory:
        raise ValueError(
            "reference trajectory must not be empty."
        )

    for row_index, row in enumerate(
        reference_trajectory,
        start=1,
    ):
        if not isinstance(
            row,
            Mapping,
        ):
            raise ValueError(
                "reference trajectory row "
                f"{row_index} must be a mapping."
            )

        missing = [
            field
            for field in _IDENTITY_FIELDS
            if field not in row
        ]

        if missing:
            raise ValueError(
                "reference trajectory row "
                f"{row_index} missing identity fields: "
                f"{missing!r}."
            )

    for field in _IDENTITY_FIELDS:
        first_value = (
            reference_trajectory[0][field]
        )

        if any(
            row[field] != first_value
            for row in reference_trajectory
        ):
            identity_name = (
                field
                .replace("_id", "")
                .replace("_", " ")
            )

            raise ValueError(
                "reference trajectory contains mixed "
                f"{identity_name} identity."
            )

        if (
            first_value
            != expected_identity[field]
        ):
            identity_name = (
                field
                .replace("_id", "")
                .replace("_", " ")
            )

            raise ValueError(
                "reference trajectory "
                f"{identity_name} identity does not "
                "match common grid."
            )


def attach_common_grid_reference_labels(
    *,
    common_grid_rows: Sequence[
        Mapping[str, Any]
    ],
    reference_trajectory: Sequence[
        Mapping[str, Any]
    ],
    alignment_lag_ns: int,
) -> list[dict[str, Any]]:
    """
    Attach Stage 2.4 reference supervision to Stage 2.5
    common-grid rows.

    Frozen lag-sign convention:

        grid_label_pc_time_ns
            = grid_pc_time_ns - alignment_lag_ns

    Reference lookup semantics are delegated to the
    Stage 2.4 boundary-safe lookup engine. Sensor
    validity and supervision validity remain separate.
    """
    identity = (
        _validate_common_grid_identity(
            common_grid_rows
        )
    )

    _validate_reference_identity(
        reference_trajectory,
        expected_identity=identity,
    )

    lag_ns = _parse_integer(
        alignment_lag_ns,
        field_name="alignment_lag_ns",
    )

    result_rows: list[
        dict[str, Any]
    ] = []

    for row_index, source_row in enumerate(
        common_grid_rows,
        start=1,
    ):
        grid_pc_time_ns = _parse_integer(
            source_row[
                "grid_pc_time_ns"
            ],
            field_name=(
                "common grid "
                f"grid_pc_time_ns at row {row_index}"
            ),
        )

        grid_label_pc_time_ns = (
            grid_pc_time_ns
            - lag_ns
        )

        reference_state = (
            lookup_reference_state(
                reference_trajectory,
                grid_label_pc_time_ns,
            )
        )

        result = deepcopy(
            dict(source_row)
        )

        result[
            "grid_label_pc_time_ns"
        ] = grid_label_pc_time_ns

        for field in _REFERENCE_RESULT_FIELDS:
            result[field] = (
                reference_state[field]
            )

        result_rows.append(
            result
        )

    return result_rows