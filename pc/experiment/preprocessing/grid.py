from collections.abc import Mapping, Sequence
from typing import Any


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


def _stream_times(
    stream: Sequence[Mapping[str, Any]],
    *,
    stream_name: str,
) -> list[int]:
    if not stream:
        raise ValueError(
            f"{stream_name} stream must not be empty."
        )

    times: list[int] = []

    for row_index, row in enumerate(
        stream,
        start=1,
    ):
        if "pc_mapped_ts_ns" not in row:
            raise ValueError(
                f"{stream_name} row {row_index} "
                "missing pc_mapped_ts_ns."
            )

        timestamp = _parse_integer(
            row["pc_mapped_ts_ns"],
            field_name=(
                f"{stream_name}.pc_mapped_ts_ns"
            ),
        )

        times.append(timestamp)

    for index in range(
        1,
        len(times),
    ):
        if times[index] < times[index - 1]:
            raise ValueError(
                f"{stream_name} stream must be "
                "sorted by pc_mapped_ts_ns."
            )

    return times


def _ceil_div(
    numerator: int,
    denominator: int,
) -> int:
    return -(
        (-numerator)
        // denominator
    )


def build_common_grid(
    *,
    accel_stream: Sequence[
        Mapping[str, Any]
    ],
    gyro_stream: Sequence[
        Mapping[str, Any]
    ],
    grid_interval_ns: int,
    grid_origin_pc_ns: int,
    grid_domain_rule: str,
) -> dict[str, object]:
    """
    Construct a deterministic regular PC-time grid.

    Only pc_mapped_ts_ns controls the temporal domain.

    Source row indices, sensor sequence numbers, and
    pc_receive_ts_ns have no influence on grid timing.
    """
    interval_ns = _parse_integer(
        grid_interval_ns,
        field_name="grid interval",
    )

    if interval_ns <= 0:
        raise ValueError(
            "grid interval must be positive."
        )

    origin_ns = _parse_integer(
        grid_origin_pc_ns,
        field_name="grid origin",
    )

    if grid_domain_rule != "INTERSECTION":
        raise ValueError(
            "grid domain rule must be INTERSECTION."
        )

    accel_times = _stream_times(
        accel_stream,
        stream_name="accel",
    )

    gyro_times = _stream_times(
        gyro_stream,
        stream_name="gyro",
    )

    coverage_start = max(
        accel_times[0],
        gyro_times[0],
    )

    coverage_end = min(
        accel_times[-1],
        gyro_times[-1],
    )

    if coverage_start > coverage_end:
        raise ValueError(
            "accel and gyro coverage do not overlap."
        )

    delta = (
        coverage_start
        - origin_ns
    )

    first_index = _ceil_div(
        delta,
        interval_ns,
    )

    first_grid_time = (
        origin_ns
        + first_index * interval_ns
    )

    if first_grid_time > coverage_end:
        raise ValueError(
            "sensor coverage overlap contains "
            "no common-grid timestamp."
        )

    grid_count = (
        (
            coverage_end
            - first_grid_time
        )
        // interval_ns
    ) + 1

    grid_times = [
        first_grid_time
        + index * interval_ns
        for index in range(
            grid_count
        )
    ]

    if any(
        timestamp < coverage_start
        or timestamp > coverage_end
        for timestamp in grid_times
    ):
        raise RuntimeError(
            "Internal grid extrapolation detected."
        )

    if any(
        right <= left
        for left, right in zip(
            grid_times,
            grid_times[1:],
            strict=False,
        )
    ):
        raise RuntimeError(
            "Internal grid timestamps are not "
            "strictly increasing."
        )

    return {
        "grid_domain_rule":
            grid_domain_rule,
        "grid_interval_ns":
            interval_ns,
        "grid_origin_pc_ns":
            origin_ns,
        "coverage_start_pc_ns":
            coverage_start,
        "coverage_end_pc_ns":
            coverage_end,
        "grid_pc_times_ns":
            grid_times,
    }