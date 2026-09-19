from collections.abc import Mapping, Sequence
from typing import Any

from pc.experiment.labels.schema import (
    LABEL_STATUSES,
)

from pc.experiment.preprocessing.schema import (
    GAP_EVENT_TYPES,
    GRID_ROW_STATUSES,
    PREPROCESSING_BUILD_STATUSES,
    PREPROCESSING_QUALITY_REQUIRED_FIELDS,
    SENSOR_COVERAGE_STATUSES,
    SENSOR_FAMILIES,
)


_IDENTITY_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
)


def _parse_nonnegative_count(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} count must be a "
            "non-negative integer."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} count must be a "
            "non-negative integer."
        ) from exc

    if parsed < 0:
        raise ValueError(
            f"{field_name} count must be "
            "non-negative."
        )

    return parsed


def _parse_integer_timestamp(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be an integer."
        )

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be an integer."
        ) from exc


def _identity_name(
    field: str,
) -> str:
    return (
        field
        .replace("_id", "")
        .replace("_", " ")
    )


def _validate_identity(
    *,
    row: Mapping[str, Any],
    expected_identity: Mapping[str, Any],
    context: str,
) -> None:
    for field in _IDENTITY_FIELDS:
        if field not in row:
            raise ValueError(
                f"{context} missing "
                f"{_identity_name(field)} identity."
            )

        if (
            row[field]
            != expected_identity[field]
        ):
            raise ValueError(
                f"{context} "
                f"{_identity_name(field)} identity "
                "does not match quality identity."
            )


def _validate_source_streams(
    *,
    source_streams: Mapping[
        str,
        Sequence[Mapping[str, Any]]
    ],
    expected_identity: Mapping[str, Any],
) -> list[int]:
    if not isinstance(
        source_streams,
        Mapping,
    ):
        raise ValueError(
            "source streams must be a mapping."
        )

    if (
        set(source_streams.keys())
        != set(SENSOR_FAMILIES)
    ):
        raise ValueError(
            "source streams must contain exactly "
            f"{SENSOR_FAMILIES!r}."
        )

    mapped_timestamps: list[int] = []

    for sensor_family in SENSOR_FAMILIES:
        stream = source_streams[
            sensor_family
        ]

        for row_index, row in enumerate(
            stream,
            start=1,
        ):
            if not isinstance(
                row,
                Mapping,
            ):
                raise ValueError(
                    f"{sensor_family} source row "
                    f"{row_index} must be a mapping."
                )

            _validate_identity(
                row=row,
                expected_identity=expected_identity,
                context=(
                    f"{sensor_family} source row "
                    f"{row_index}"
                ),
            )

            if "pc_mapped_ts_ns" not in row:
                raise ValueError(
                    f"{sensor_family} source row "
                    f"{row_index} missing "
                    "pc_mapped_ts_ns."
                )

            mapped_timestamps.append(
                _parse_integer_timestamp(
                    row["pc_mapped_ts_ns"],
                    field_name=(
                        f"{sensor_family} "
                        "pc_mapped_ts_ns"
                    ),
                )
            )

    return mapped_timestamps


def _read_source_diagnostics(
    source_diagnostics: Mapping[str, Any],
) -> dict[str, int]:
    if not isinstance(
        source_diagnostics,
        Mapping,
    ):
        raise ValueError(
            "source diagnostics must be a mapping."
        )

    if "source_counts" not in source_diagnostics:
        raise ValueError(
            "source diagnostics missing "
            "source_counts."
        )

    source_counts = source_diagnostics[
        "source_counts"
    ]

    if not isinstance(
        source_counts,
        Mapping,
    ):
        raise ValueError(
            "source_counts must be a mapping."
        )

    counts: dict[str, int] = {}

    for sensor_family in SENSOR_FAMILIES:
        if sensor_family not in source_counts:
            raise ValueError(
                "source diagnostic count missing "
                f"{sensor_family}."
            )

        counts[
            sensor_family
        ] = _parse_nonnegative_count(
            source_counts[
                sensor_family
            ],
            field_name=(
                f"{sensor_family} source"
            ),
        )

    for field in (
        "reorder_count",
        "duplicate_count",
        "invalid_timestamp_count",
    ):
        if field not in source_diagnostics:
            raise ValueError(
                "source diagnostics missing "
                f"{field}."
            )

        counts[field] = (
            _parse_nonnegative_count(
                source_diagnostics[field],
                field_name=field,
            )
        )

    return counts


def _summarize_gap_events(
    gap_events: Mapping[
        str,
        Sequence[Mapping[str, Any]]
    ],
) -> tuple[int, int]:
    if not isinstance(
        gap_events,
        Mapping,
    ):
        raise ValueError(
            "gap events must be a mapping."
        )

    if (
        set(gap_events.keys())
        != set(SENSOR_FAMILIES)
    ):
        raise ValueError(
            "gap events must contain exactly "
            f"{SENSOR_FAMILIES!r}."
        )

    gap_count = 0
    maximum_gap = 0

    for sensor_family in SENSOR_FAMILIES:
        events = gap_events[
            sensor_family
        ]

        for event_index, event in enumerate(
            events,
            start=1,
        ):
            if not isinstance(
                event,
                Mapping,
            ):
                raise ValueError(
                    f"{sensor_family} gap event "
                    f"{event_index} must be a mapping."
                )

            event_type = event.get(
                "event_type"
            )

            if event_type not in GAP_EVENT_TYPES:
                raise ValueError(
                    f"{sensor_family} gap event "
                    "has unsupported event type."
                )

            if "observed_gap_ns" not in event:
                raise ValueError(
                    f"{sensor_family} gap event "
                    "missing observed_gap_ns."
                )

            observed_gap = (
                _parse_nonnegative_count(
                    event[
                        "observed_gap_ns"
                    ],
                    field_name=(
                        f"{sensor_family} gap"
                    ),
                )
            )

            gap_count += 1

            if observed_gap > maximum_gap:
                maximum_gap = observed_gap

    return (
        gap_count,
        maximum_gap,
    )


def _summarize_common_grid(
    *,
    common_grid_rows: Sequence[
        Mapping[str, Any]
    ],
    expected_identity: Mapping[str, Any],
) -> dict[str, int]:
    invalid_accel = 0
    invalid_gyro = 0
    invalid_sensor = 0
    valid_supervision = 0
    invalid_supervision = 0

    for row_index, row in enumerate(
        common_grid_rows,
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

        _validate_identity(
            row=row,
            expected_identity=expected_identity,
            context=(
                f"common grid row {row_index}"
            ),
        )

        for required_field in (
            "accel_status",
            "gyro_status",
            "sensor_status",
            "label_status",
        ):
            if required_field not in row:
                raise ValueError(
                    "common grid row "
                    f"{row_index} missing "
                    f"{required_field}."
                )

        accel_status = row[
            "accel_status"
        ]

        gyro_status = row[
            "gyro_status"
        ]

        sensor_status = row[
            "sensor_status"
        ]

        label_status = row[
            "label_status"
        ]

        if (
            accel_status
            not in SENSOR_COVERAGE_STATUSES
        ):
            raise ValueError(
                "unsupported accel status: "
                f"{accel_status!r}."
            )

        if (
            gyro_status
            not in SENSOR_COVERAGE_STATUSES
        ):
            raise ValueError(
                "unsupported gyro status: "
                f"{gyro_status!r}."
            )

        if (
            sensor_status
            not in GRID_ROW_STATUSES
        ):
            raise ValueError(
                "unsupported sensor status: "
                f"{sensor_status!r}."
            )

        if label_status not in LABEL_STATUSES:
            raise ValueError(
                "unsupported label status: "
                f"{label_status!r}."
            )

        if accel_status != "VALID":
            invalid_accel += 1

        if gyro_status != "VALID":
            invalid_gyro += 1

        if sensor_status != "VALID":
            invalid_sensor += 1

        if label_status == "VALID":
            valid_supervision += 1
        else:
            invalid_supervision += 1

    return {
        "grid_row_count":
            len(common_grid_rows),
        "invalid_accel_row_count":
            invalid_accel,
        "invalid_gyro_row_count":
            invalid_gyro,
        "invalid_sensor_row_count":
            invalid_sensor,
        "valid_supervision_count":
            valid_supervision,
        "invalid_supervision_count":
            invalid_supervision,
    }


def _normalize_technical_errors(
    technical_errors: Sequence[Any],
) -> list[str]:
    if isinstance(
        technical_errors,
        (str, bytes),
    ):
        raise ValueError(
            "technical errors must be a sequence."
        )

    normalized: list[str] = []

    for index, error in enumerate(
        technical_errors,
        start=1,
    ):
        if not isinstance(
            error,
            str,
        ):
            raise ValueError(
                "technical error "
                f"{index} must be a string."
            )

        normalized.append(
            error
        )

    return normalized


def assess_preprocessing_quality(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    source_streams: Mapping[
        str,
        Sequence[Mapping[str, Any]]
    ],
    source_diagnostics: Mapping[str, Any],
    gap_events: Mapping[
        str,
        Sequence[Mapping[str, Any]]
    ],
    common_grid_rows: Sequence[
        Mapping[str, Any]
    ],
    technical_errors: Sequence[Any],
    derivation_version: str,
) -> dict[str, Any]:
    """
    Build the Stage 2.5 preprocessing quality summary.

    Row-level invalidity is summarized numerically and
    remains distinct from technical build invalidity.

    Build status is TECHNICAL_INVALID only when explicit
    technical_errors are present.
    """
    expected_identity = {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
    }

    mapped_timestamps = (
        _validate_source_streams(
            source_streams=source_streams,
            expected_identity=expected_identity,
        )
    )

    diagnostics = (
        _read_source_diagnostics(
            source_diagnostics
        )
    )

    (
        gap_event_count,
        max_observed_source_gap_ns,
    ) = _summarize_gap_events(
        gap_events
    )

    grid_summary = (
        _summarize_common_grid(
            common_grid_rows=common_grid_rows,
            expected_identity=expected_identity,
        )
    )

    normalized_errors = (
        _normalize_technical_errors(
            technical_errors
        )
    )

    if normalized_errors:
        status = "TECHNICAL_INVALID"
    else:
        status = "VALID"

    if status not in PREPROCESSING_BUILD_STATUSES:
        raise RuntimeError(
            "unsupported preprocessing build status."
        )

    if mapped_timestamps:
        first_mapped_pc_time_ns = min(
            mapped_timestamps
        )

        last_mapped_pc_time_ns = max(
            mapped_timestamps
        )
    else:
        first_mapped_pc_time_ns = None
        last_mapped_pc_time_ns = None

    result = {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "status":
            status,
        "accel_source_count":
            diagnostics["ACCEL"],
        "gyro_source_count":
            diagnostics["GYRO"],
        "reorder_count":
            diagnostics["reorder_count"],
        "duplicate_count":
            diagnostics["duplicate_count"],
        "invalid_timestamp_count":
            diagnostics[
                "invalid_timestamp_count"
            ],
        "first_mapped_pc_time_ns":
            first_mapped_pc_time_ns,
        "last_mapped_pc_time_ns":
            last_mapped_pc_time_ns,
        "max_observed_source_gap_ns":
            max_observed_source_gap_ns,
        "gap_event_count":
            gap_event_count,
        "grid_row_count":
            grid_summary[
                "grid_row_count"
            ],
        "invalid_accel_row_count":
            grid_summary[
                "invalid_accel_row_count"
            ],
        "invalid_gyro_row_count":
            grid_summary[
                "invalid_gyro_row_count"
            ],
        "invalid_sensor_row_count":
            grid_summary[
                "invalid_sensor_row_count"
            ],
        "valid_supervision_count":
            grid_summary[
                "valid_supervision_count"
            ],
        "invalid_supervision_count":
            grid_summary[
                "invalid_supervision_count"
            ],
        "technical_errors":
            normalized_errors,
        "derivation_version":
            derivation_version,
    }

    if (
        tuple(result.keys())
        != PREPROCESSING_QUALITY_REQUIRED_FIELDS
    ):
        raise RuntimeError(
            "preprocessing quality output does not "
            "match frozen schema order."
        )

    return result