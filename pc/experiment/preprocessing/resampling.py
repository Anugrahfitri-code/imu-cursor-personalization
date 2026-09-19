from collections.abc import Mapping, Sequence
from typing import Any


SUPPORTED_RESAMPLING_METHODS = (
    "PREVIOUS_SAMPLE_HOLD",
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
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be an integer."
        ) from exc


def _validate_stream(
    stream: Sequence[Mapping[str, Any]],
) -> tuple[list[int], list[Mapping[str, Any]]]:
    if not stream:
        raise ValueError(
            "source stream must not be empty."
        )

    timestamps: list[int] = []
    rows: list[Mapping[str, Any]] = []

    for row_index, row in enumerate(
        stream,
        start=1,
    ):
        for field in (
            "pc_mapped_ts_ns",
            "x",
            "y",
            "z",
        ):
            if field not in row:
                raise ValueError(
                    "source stream row "
                    f"{row_index} missing "
                    f"{field}."
                )

        timestamp = _parse_integer(
            row["pc_mapped_ts_ns"],
            field_name=(
                "pc_mapped_ts_ns"
            ),
        )

        timestamps.append(timestamp)
        rows.append(row)

    for index in range(
        1,
        len(timestamps),
    ):
        if (
            timestamps[index]
            < timestamps[index - 1]
        ):
            raise ValueError(
                "source stream must be sorted "
                "by pc_mapped_ts_ns."
            )

    return timestamps, rows


def _validate_grid_times(
    grid_pc_times_ns: Sequence[Any],
) -> list[int]:
    grid_times = [
        _parse_integer(
            value,
            field_name="grid_pc_time_ns",
        )
        for value in grid_pc_times_ns
    ]

    for index in range(
        1,
        len(grid_times),
    ):
        if (
            grid_times[index]
            < grid_times[index - 1]
        ):
            raise ValueError(
                "grid timestamps must be sorted."
            )

    return grid_times


def _invalid_output(
    *,
    grid_time_ns: int,
    status: str,
    source_time_ns: int | None,
    source_age_ns: int | None,
) -> dict[str, Any]:
    return {
        "grid_pc_time_ns":
            grid_time_ns,
        "source_pc_mapped_ts_ns":
            source_time_ns,
        "source_age_ns":
            source_age_ns,
        "status":
            status,
        "x":
            None,
        "y":
            None,
        "z":
            None,
    }


def _valid_output(
    *,
    grid_time_ns: int,
    source_time_ns: int,
    source_age_ns: int,
    source_row: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "grid_pc_time_ns":
            grid_time_ns,
        "source_pc_mapped_ts_ns":
            source_time_ns,
        "source_age_ns":
            source_age_ns,
        "status":
            "VALID",
        "x":
            source_row["x"],
        "y":
            source_row["y"],
        "z":
            source_row["z"],
    }


def resample_sensor_stream(
    *,
    stream: Sequence[Mapping[str, Any]],
    grid_pc_times_ns: Sequence[Any],
    method: str,
    max_source_gap_ns: int,
) -> list[dict[str, Any]]:
    """
    Resolve one timestamped sensor stream onto a common
    PC-time grid.

    The PREVIOUS_SAMPLE_HOLD candidate is strictly
    backward-looking: at grid time t, only a source
    observation whose mapped timestamp is <= t can
    supply the value.

    This function never uses pc_receive_ts_ns,
    sensor_sequence, or source_row_index for temporal
    pairing.
    """
    if method not in SUPPORTED_RESAMPLING_METHODS:
        raise ValueError(
            "unsupported resampling method: "
            f"{method!r}."
        )

    gap_limit = _parse_integer(
        max_source_gap_ns,
        field_name="source gap limit",
    )

    if gap_limit < 0:
        raise ValueError(
            "source gap limit must be "
            "non-negative."
        )

    source_times, source_rows = (
        _validate_stream(
            stream
        )
    )

    grid_times = _validate_grid_times(
        grid_pc_times_ns
    )

    first_source_time = source_times[0]
    last_source_time = source_times[-1]

    result: list[dict[str, Any]] = []

    source_index = 0

    for grid_time in grid_times:
        # No backward or forward extrapolation outside
        # the recorded native source coverage.
        if grid_time < first_source_time:
            result.append(
                _invalid_output(
                    grid_time_ns=grid_time,
                    status="NO_SOURCE",
                    source_time_ns=None,
                    source_age_ns=None,
                )
            )
            continue

        if grid_time > last_source_time:
            result.append(
                _invalid_output(
                    grid_time_ns=grid_time,
                    status="NO_SOURCE",
                    source_time_ns=None,
                    source_age_ns=None,
                )
            )
            continue

        # Advance only through observations whose mapped
        # timestamp is not later than the current grid
        # timestamp.
        while (
            source_index + 1
            < len(source_times)
            and source_times[
                source_index + 1
            ]
            <= grid_time
        ):
            source_index += 1

        source_time = source_times[
            source_index
        ]

        if source_time > grid_time:
            raise RuntimeError(
                "future source observation selected."
            )

        source_age = (
            grid_time
            - source_time
        )

        if source_age > gap_limit:
            result.append(
                _invalid_output(
                    grid_time_ns=grid_time,
                    status="GAP_EXCEEDED",
                    source_time_ns=(
                        source_time
                    ),
                    source_age_ns=(
                        source_age
                    ),
                )
            )
            continue

        result.append(
            _valid_output(
                grid_time_ns=grid_time,
                source_time_ns=source_time,
                source_age_ns=source_age,
                source_row=source_rows[
                    source_index
                ],
            )
        )

    return result


def resample_sensor_streams(
    *,
    accel_stream: Sequence[
        Mapping[str, Any]
    ],
    gyro_stream: Sequence[
        Mapping[str, Any]
    ],
    grid_pc_times_ns: Sequence[Any],
    accel_method: str,
    gyro_method: str,
    max_source_gap_ns: int,
) -> dict[str, list[dict[str, Any]]]:
    """
    Resample accelerometer and gyroscope independently
    onto the same mapped-PC-time grid.
    """
    accel_result = resample_sensor_stream(
        stream=accel_stream,
        grid_pc_times_ns=grid_pc_times_ns,
        method=accel_method,
        max_source_gap_ns=max_source_gap_ns,
    )

    gyro_result = resample_sensor_stream(
        stream=gyro_stream,
        grid_pc_times_ns=grid_pc_times_ns,
        method=gyro_method,
        max_source_gap_ns=max_source_gap_ns,
    )

    return {
        "ACCEL":
            accel_result,
        "GYRO":
            gyro_result,
    }

def detect_source_gap_events(
    *,
    stream: Sequence[Mapping[str, Any]],
    expected_interval_ns: int,
    max_source_gap_ns: int,
) -> list[dict[str, Any]]:
    """
    Detect explicit source-timestamp gaps.

    A gap equal to or smaller than the expected interval
    is treated as normal sampling variation for this
    contract.

    A larger gap is classified as BOUNDED_GAP when it is
    within max_source_gap_ns, otherwise EXCESSIVE_GAP.

    Numeric thresholds supplied here remain configuration
    values; this function does not freeze participant-study
    thresholds.
    """
    expected_interval = _parse_integer(
        expected_interval_ns,
        field_name="expected interval",
    )

    if expected_interval <= 0:
        raise ValueError(
            "expected interval must be positive."
        )

    gap_limit = _parse_integer(
        max_source_gap_ns,
        field_name="source gap limit",
    )

    if gap_limit < 0:
        raise ValueError(
            "source gap limit must be non-negative."
        )

    timestamps: list[int] = []

    for row_index, row in enumerate(
        stream,
        start=1,
    ):
        if "pc_mapped_ts_ns" not in row:
            raise ValueError(
                "source gap row "
                f"{row_index} missing "
                "pc_mapped_ts_ns."
            )

        timestamp = _parse_integer(
            row["pc_mapped_ts_ns"],
            field_name="pc_mapped_ts_ns",
        )

        timestamps.append(
            timestamp
        )

    for index in range(
        1,
        len(timestamps),
    ):
        if (
            timestamps[index]
            < timestamps[index - 1]
        ):
            raise ValueError(
                "source stream must be sorted "
                "by pc_mapped_ts_ns."
            )

    events: list[dict[str, Any]] = []

    for index in range(
        1,
        len(timestamps),
    ):
        previous_timestamp = (
            timestamps[index - 1]
        )

        timestamp = timestamps[index]

        observed_gap = (
            timestamp
            - previous_timestamp
        )

        if observed_gap <= expected_interval:
            continue

        if observed_gap <= gap_limit:
            event_type = "BOUNDED_GAP"
        else:
            event_type = "EXCESSIVE_GAP"

        # Equivalent to ceil(
        # observed_gap / expected_interval
        # ) - 1 using integer arithmetic.
        estimated_missing_count = (
            observed_gap - 1
        ) // expected_interval

        events.append(
            {
                "event_type":
                    event_type,
                "previous_pc_mapped_ts_ns":
                    previous_timestamp,
                "pc_mapped_ts_ns":
                    timestamp,
                "observed_gap_ns":
                    observed_gap,
                "expected_interval_ns":
                    expected_interval,
                "estimated_missing_count":
                    estimated_missing_count,
            }
        )

    return events