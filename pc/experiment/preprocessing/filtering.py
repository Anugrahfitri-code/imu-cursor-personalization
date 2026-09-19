import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


SUPPORTED_FILTER_FAMILIES = (
    "ONE_POLE_IIR",
)


SUPPORTED_INITIALIZATION_POLICIES = (
    "FIRST_SAMPLE",
)


SUPPORTED_RESET_POLICIES = (
    "EXPLICIT_BOUNDARIES",
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


def _integer(
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


def one_pole_alpha(
    *,
    cutoff_hz: float,
    grid_frequency_hz: float,
) -> float:
    """
    Compute the causal one-pole low-pass coefficient:

        dt = 1 / fs
        RC = 1 / (2*pi*fc)
        alpha = dt / (RC + dt)

    This defines filter mechanics only. It does not freeze
    the scientific cutoff or analysis-grid frequency.
    """
    cutoff = _finite_float(
        cutoff_hz,
        field_name="filter cutoff",
    )

    frequency = _finite_float(
        grid_frequency_hz,
        field_name="grid frequency",
    )

    if frequency <= 0.0:
        raise ValueError(
            "grid frequency must be positive."
        )

    if cutoff <= 0.0:
        raise ValueError(
            "filter cutoff must be positive."
        )

    nyquist = (
        frequency
        / 2.0
    )

    if cutoff >= nyquist:
        raise ValueError(
            "filter cutoff must be below "
            "the Nyquist frequency."
        )

    dt = (
        1.0
        / frequency
    )

    rc = (
        1.0
        / (
            2.0
            * math.pi
            * cutoff
        )
    )

    return (
        dt
        / (
            rc
            + dt
        )
    )


def _validate_channels(
    channels: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(
        channels
    )

    if not normalized:
        raise ValueError(
            "filter channel list must not be empty."
        )

    if (
        len(set(normalized))
        != len(normalized)
    ):
        raise ValueError(
            "filter channel list contains "
            "duplicate channels."
        )

    for channel in normalized:
        if channel not in _SUPPORTED_CHANNELS:
            raise ValueError(
                "unsupported filter channel: "
                f"{channel!r}."
            )

    return normalized


def _validate_filter_config(
    filter_config: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        filter_config,
        Mapping,
    ):
        raise ValueError(
            "filter configuration must be a mapping."
        )

    required = (
        "family",
        "order",
        "cutoff_hz",
        "grid_frequency_hz",
        "initialization",
        "reset_policy",
    )

    missing = [
        field
        for field in required
        if field not in filter_config
    ]

    if missing:
        raise ValueError(
            "filter configuration missing fields: "
            f"{missing!r}."
        )

    family = filter_config[
        "family"
    ]

    if family not in SUPPORTED_FILTER_FAMILIES:
        raise ValueError(
            "unsupported filter family: "
            f"{family!r}."
        )

    order = _integer(
        filter_config[
            "order"
        ],
        field_name="filter order",
    )

    if order != 1:
        raise ValueError(
            "ONE_POLE_IIR filter order "
            "must be exactly 1."
        )

    initialization = filter_config[
        "initialization"
    ]

    if (
        initialization
        not in SUPPORTED_INITIALIZATION_POLICIES
    ):
        raise ValueError(
            "unsupported filter initialization "
            f"policy: {initialization!r}."
        )

    reset_policy = filter_config[
        "reset_policy"
    ]

    if (
        reset_policy
        not in SUPPORTED_RESET_POLICIES
    ):
        raise ValueError(
            "unsupported filter reset policy: "
            f"{reset_policy!r}."
        )

    cutoff = _finite_float(
        filter_config[
            "cutoff_hz"
        ],
        field_name="filter cutoff",
    )

    frequency = _finite_float(
        filter_config[
            "grid_frequency_hz"
        ],
        field_name="grid frequency",
    )

    alpha = one_pole_alpha(
        cutoff_hz=cutoff,
        grid_frequency_hz=frequency,
    )

    return {
        "family":
            family,
        "order":
            order,
        "cutoff_hz":
            cutoff,
        "grid_frequency_hz":
            frequency,
        "initialization":
            initialization,
        "reset_policy":
            reset_policy,
        "alpha":
            alpha,
    }


def _validate_reset_indices(
    reset_before_indices: Sequence[Any],
    *,
    stream_length: int,
) -> set[int]:
    normalized: set[int] = set()

    for value in reset_before_indices:
        index = _integer(
            value,
            field_name="filter reset index",
        )

        if (
            index < 0
            or index >= stream_length
        ):
            raise ValueError(
                "filter reset index is outside "
                "the stream."
            )

        normalized.add(
            index
        )

    return normalized


def filter_sensor_stream(
    *,
    stream: Sequence[Mapping[str, Any]],
    filter_config: Mapping[str, Any],
    channels: Sequence[str],
    reset_before_indices: Sequence[Any] = (),
) -> list[dict[str, Any]]:
    """
    Apply a strictly causal first-order one-pole IIR
    low-pass filter.

    For each selected channel:

        y[t] = y[t-1] + alpha * (x[t] - y[t-1])

    The first sample, and every explicit reset boundary,
    initializes filter state directly from the current
    input sample.

    No future observation participates in an earlier
    output.
    """
    config = _validate_filter_config(
        filter_config
    )

    normalized_channels = _validate_channels(
        channels
    )

    reset_indices = _validate_reset_indices(
        reset_before_indices,
        stream_length=len(stream),
    )

    alpha = config[
        "alpha"
    ]

    previous_state: dict[
        str,
        float,
    ] = {}

    result_rows: list[
        dict[str, Any]
    ] = []

    for row_index, source_row in enumerate(
        stream
    ):
        if not isinstance(
            source_row,
            Mapping,
        ):
            raise ValueError(
                "filter source row must be a mapping."
            )

        result = deepcopy(
            dict(source_row)
        )

        current_values: dict[
            str,
            float,
        ] = {}

        for channel in normalized_channels:
            if channel not in source_row:
                raise ValueError(
                    "filter source row missing "
                    f"channel {channel!r}."
                )

            current_values[
                channel
            ] = _finite_float(
                source_row[
                    channel
                ],
                field_name=(
                    f"filter channel {channel}"
                ),
            )

        should_reset = (
            row_index == 0
            or row_index in reset_indices
        )

        if should_reset:
            for channel in normalized_channels:
                output_value = (
                    current_values[
                        channel
                    ]
                )

                previous_state[
                    channel
                ] = output_value

                result[
                    channel
                ] = output_value

        else:
            for channel in normalized_channels:
                previous_value = (
                    previous_state[
                        channel
                    ]
                )

                current_value = (
                    current_values[
                        channel
                    ]
                )

                output_value = (
                    previous_value
                    + alpha
                    * (
                        current_value
                        - previous_value
                    )
                )

                previous_state[
                    channel
                ] = output_value

                result[
                    channel
                ] = output_value

        result_rows.append(
            result
        )

    return result_rows