import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


SUPPORTED_ACTIVE_MOTION_METHODS = (
    "L2_NORM_THRESHOLD",
)


SUPPORTED_COMPARISONS = (
    "GREATER_EQUAL",
)


_SUPPORTED_CHANNELS = (
    "x",
    "y",
    "z",
)


def _finite_float(
    value: Any,
    *,
    field_name: str,
) -> float:
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be finite numeric."
        )

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be finite numeric."
        ) from exc

    if not math.isfinite(numeric):
        raise ValueError(
            f"{field_name} must be finite numeric."
        )

    return numeric


def _validate_channels(
    channels: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(
        channels
    )

    if not normalized:
        raise ValueError(
            "active-motion channel list must "
            "not be empty."
        )

    if (
        len(set(normalized))
        != len(normalized)
    ):
        raise ValueError(
            "active-motion channel list contains "
            "duplicate channel entries."
        )

    for channel in normalized:
        if channel not in _SUPPORTED_CHANNELS:
            raise ValueError(
                "unsupported active-motion channel: "
                f"{channel!r}."
            )

    return normalized


def _validate_config(
    active_motion_config: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        active_motion_config,
        Mapping,
    ):
        raise ValueError(
            "active-motion configuration must "
            "be a mapping."
        )

    required_fields = (
        "method",
        "channels",
        "threshold",
        "comparison",
    )

    missing_fields = [
        field
        for field in required_fields
        if field not in active_motion_config
    ]

    if missing_fields:
        raise ValueError(
            "active-motion configuration missing "
            f"fields: {missing_fields!r}."
        )

    method = active_motion_config[
        "method"
    ]

    if (
        method
        not in SUPPORTED_ACTIVE_MOTION_METHODS
    ):
        raise ValueError(
            "unsupported active-motion method: "
            f"{method!r}."
        )

    comparison = active_motion_config[
        "comparison"
    ]

    if comparison not in SUPPORTED_COMPARISONS:
        raise ValueError(
            "unsupported active-motion comparison: "
            f"{comparison!r}."
        )

    channels = _validate_channels(
        active_motion_config[
            "channels"
        ]
    )

    threshold = _finite_float(
        active_motion_config[
            "threshold"
        ],
        field_name="active-motion threshold",
    )

    if threshold < 0.0:
        raise ValueError(
            "active-motion threshold must be "
            "non-negative."
        )

    return {
        "method":
            method,
        "channels":
            channels,
        "threshold":
            threshold,
        "comparison":
            comparison,
    }


def classify_active_motion_sample(
    *,
    sample: Mapping[str, Any],
    active_motion_config: Mapping[str, Any],
) -> bool:
    """
    Classify one sample using only the current row and
    explicit active-motion configuration.
    """
    if not isinstance(
        sample,
        Mapping,
    ):
        raise ValueError(
            "active-motion sample must be a mapping."
        )

    config = _validate_config(
        active_motion_config
    )

    values: list[float] = []

    for channel in config[
        "channels"
    ]:
        if channel not in sample:
            raise ValueError(
                "active-motion sample missing "
                f"channel {channel!r}."
            )

        values.append(
            _finite_float(
                sample[channel],
                field_name=(
                    "active-motion sensor value "
                    f"for channel {channel}"
                ),
            )
        )

    magnitude = math.sqrt(
        sum(
            value * value
            for value in values
        )
    )

    if (
        config["method"]
        == "L2_NORM_THRESHOLD"
        and config["comparison"]
        == "GREATER_EQUAL"
    ):
        return bool(
            magnitude
            >= config["threshold"]
        )

    raise RuntimeError(
        "unsupported active-motion execution path."
    )


def annotate_active_motion_stream(
    *,
    stream: Sequence[Mapping[str, Any]],
    active_motion_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Add active_motion_flag independently to every row.

    Future rows cannot influence earlier classifications.
    """
    _validate_config(
        active_motion_config
    )

    result_rows: list[
        dict[str, Any]
    ] = []

    for source_row in stream:
        if not isinstance(
            source_row,
            Mapping,
        ):
            raise ValueError(
                "active-motion stream row must "
                "be a mapping."
            )

        result = deepcopy(
            dict(source_row)
        )

        result[
            "active_motion_flag"
        ] = classify_active_motion_sample(
            sample=source_row,
            active_motion_config=(
                active_motion_config
            ),
        )

        result_rows.append(
            result
        )

    return result_rows