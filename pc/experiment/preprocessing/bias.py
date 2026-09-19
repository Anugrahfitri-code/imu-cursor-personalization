import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pc.experiment.preprocessing.schema import (
    SENSOR_FAMILIES,
)


SUPPORTED_BIAS_METHODS = (
    "MEAN_PC_WINDOW",
)


_SUPPORTED_CHANNELS = (
    "x",
    "y",
    "z",
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


def _validate_channels(
    channels: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(channels)

    if not normalized:
        raise ValueError(
            "bias channel list must not be empty."
        )

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            "bias channel list contains duplicate "
            "channel entries."
        )

    for channel in normalized:
        if channel not in _SUPPORTED_CHANNELS:
            raise ValueError(
                "unsupported bias channel: "
                f"{channel!r}."
            )

    return normalized


def _finite_numeric(
    value: Any,
    *,
    channel: str,
) -> float:
    if isinstance(value, bool):
        raise ValueError(
            f"bias channel {channel!r} must contain "
            "finite numeric values."
        )

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"bias channel {channel!r} must contain "
            "finite numeric values."
        ) from exc

    if not math.isfinite(numeric):
        raise ValueError(
            f"bias channel {channel!r} must contain "
            "finite numeric values."
        )

    return numeric


def estimate_sensor_bias(
    *,
    stream: Sequence[Mapping[str, Any]],
    sensor_family: str,
    method: str,
    window_start_pc_ns: int,
    window_end_pc_ns: int,
    channels: Sequence[str],
    minimum_samples: int,
) -> dict[str, Any]:
    """
    Estimate additive sensor bias from an explicit mapped
    PC-time window.

    Only sensor timestamps and selected sensor channels
    participate in estimation. Reference labels and
    evaluation outcomes are ignored.
    """
    if sensor_family not in SENSOR_FAMILIES:
        raise ValueError(
            "sensor family must be one of "
            f"{SENSOR_FAMILIES!r}; "
            f"got {sensor_family!r}."
        )

    if method not in SUPPORTED_BIAS_METHODS:
        raise ValueError(
            "unsupported bias method: "
            f"{method!r}."
        )

    window_start = _parse_integer(
        window_start_pc_ns,
        field_name="bias window start",
    )

    window_end = _parse_integer(
        window_end_pc_ns,
        field_name="bias window end",
    )

    if window_start > window_end:
        raise ValueError(
            "bias window start must not be later "
            "than bias window end."
        )

    minimum = _parse_integer(
        minimum_samples,
        field_name="minimum samples",
    )

    if minimum <= 0:
        raise ValueError(
            "minimum sample count must be positive."
        )

    normalized_channels = _validate_channels(
        channels
    )

    eligible_rows: list[
        tuple[int, Mapping[str, Any]]
    ] = []

    for row_index, row in enumerate(
        stream,
        start=1,
    ):
        if "pc_mapped_ts_ns" not in row:
            raise ValueError(
                "bias source row "
                f"{row_index} missing "
                "pc_mapped_ts_ns."
            )

        timestamp = _parse_integer(
            row["pc_mapped_ts_ns"],
            field_name="pc_mapped_ts_ns",
        )

        if (
            timestamp < window_start
            or timestamp > window_end
        ):
            continue

        for channel in normalized_channels:
            if channel not in row:
                raise ValueError(
                    "bias source row "
                    f"{row_index} missing channel "
                    f"{channel!r}."
                )

        eligible_rows.append(
            (
                timestamp,
                row,
            )
        )

    if len(eligible_rows) < minimum:
        raise ValueError(
            "insufficient eligible samples for "
            "bias estimation."
        )

    channel_values: dict[
        str,
        list[float],
    ] = {
        channel: []
        for channel in normalized_channels
    }

    for _, row in eligible_rows:
        for channel in normalized_channels:
            channel_values[
                channel
            ].append(
                _finite_numeric(
                    row[channel],
                    channel=channel,
                )
            )

    bias = {
        channel: (
            sum(channel_values[channel])
            / len(channel_values[channel])
        )
        for channel in normalized_channels
    }

    eligible_times = [
        timestamp
        for timestamp, _ in eligible_rows
    ]

    return {
        "sensor_family":
            sensor_family,
        "method":
            method,
        "window_start_pc_ns":
            window_start,
        "window_end_pc_ns":
            window_end,
        "channels":
            normalized_channels,
        "minimum_samples":
            minimum,
        "sample_count":
            len(eligible_rows),
        "first_eligible_pc_time_ns":
            min(eligible_times),
        "last_eligible_pc_time_ns":
            max(eligible_times),
        "bias":
            bias,
    }


def apply_sensor_bias_correction(
    *,
    stream: Sequence[Mapping[str, Any]],
    bias_estimate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Subtract a previously estimated additive bias from
    selected sensor channels while preserving all other
    row fields.
    """
    if not isinstance(
        bias_estimate,
        Mapping,
    ):
        raise ValueError(
            "bias estimate must be a mapping."
        )

    if "channels" not in bias_estimate:
        raise ValueError(
            "bias estimate missing channels."
        )

    if "bias" not in bias_estimate:
        raise ValueError(
            "bias estimate missing bias values."
        )

    channels = _validate_channels(
        bias_estimate["channels"]
    )

    bias_values = bias_estimate[
        "bias"
    ]

    if not isinstance(
        bias_values,
        Mapping,
    ):
        raise ValueError(
            "bias values must be a mapping."
        )

    normalized_bias: dict[
        str,
        float,
    ] = {}

    for channel in channels:
        if channel not in bias_values:
            raise ValueError(
                "bias estimate missing bias value "
                f"for channel {channel!r}."
            )

        normalized_bias[
            channel
        ] = _finite_numeric(
            bias_values[channel],
            channel=channel,
        )

    corrected_rows: list[
        dict[str, Any]
    ] = []

    for row_index, source_row in enumerate(
        stream,
        start=1,
    ):
        result = deepcopy(
            dict(source_row)
        )

        for channel in channels:
            if channel not in source_row:
                raise ValueError(
                    "bias correction source row "
                    f"{row_index} missing channel "
                    f"{channel!r}."
                )

            source_value = _finite_numeric(
                source_row[channel],
                channel=channel,
            )

            result[channel] = (
                source_value
                - normalized_bias[channel]
            )

        corrected_rows.append(
            result
        )

    return corrected_rows