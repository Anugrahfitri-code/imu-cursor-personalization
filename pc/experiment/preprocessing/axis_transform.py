import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pc.experiment.preprocessing.schema import (
    SENSOR_FAMILIES,
)


_AXES = (
    "x",
    "y",
    "z",
)

_ALLOWED_SIGNS = (
    -1,
    1,
)


def _validate_family_transform(
    *,
    family_transform: Mapping[str, Any],
    sensor_family: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(
        family_transform,
        Mapping,
    ):
        raise ValueError(
            f"{sensor_family} axis transform "
            "must be a mapping."
        )

    if set(family_transform.keys()) != set(_AXES):
        raise ValueError(
            f"{sensor_family} axis transform "
            "must define exactly x, y, z axes."
        )

    normalized: dict[
        str,
        dict[str, Any],
    ] = {}

    used_source_axes: list[str] = []

    for output_axis in _AXES:
        rule = family_transform[
            output_axis
        ]

        if not isinstance(
            rule,
            Mapping,
        ):
            raise ValueError(
                f"{sensor_family} axis rule for "
                f"{output_axis} must be a mapping."
            )

        if (
            "source_axis" not in rule
            or "sign" not in rule
        ):
            raise ValueError(
                f"{sensor_family} axis rule for "
                f"{output_axis} must define "
                "source_axis and sign."
            )

        source_axis = rule[
            "source_axis"
        ]

        sign = rule[
            "sign"
        ]

        if source_axis not in _AXES:
            raise ValueError(
                f"{sensor_family} source axis "
                f"{source_axis!r} is invalid."
            )

        if (
            isinstance(sign, bool)
            or sign not in _ALLOWED_SIGNS
        ):
            raise ValueError(
                f"{sensor_family} axis sign "
                "must be exactly -1 or 1."
            )

        used_source_axes.append(
            source_axis
        )

        normalized[
            output_axis
        ] = {
            "source_axis":
                source_axis,
            "sign":
                int(sign),
        }

    if (
        len(set(used_source_axes))
        != len(_AXES)
        or set(used_source_axes)
        != set(_AXES)
    ):
        raise ValueError(
            f"{sensor_family} axis mapping must "
            "use each source axis exactly once."
        )

    return normalized


def _normalize_axis_transform(
    axis_transform: Mapping[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    if not isinstance(
        axis_transform,
        Mapping,
    ):
        raise ValueError(
            "axis transform must be a mapping."
        )

    if (
        set(axis_transform.keys())
        != set(SENSOR_FAMILIES)
    ):
        raise ValueError(
            "axis transform must define exactly "
            f"the sensor families "
            f"{SENSOR_FAMILIES!r}."
        )

    normalized: dict[
        str,
        dict[str, dict[str, Any]],
    ] = {}

    for sensor_family in SENSOR_FAMILIES:
        normalized[
            sensor_family
        ] = _validate_family_transform(
            family_transform=axis_transform[
                sensor_family
            ],
            sensor_family=sensor_family,
        )

    return normalized


def transform_sensor_sample(
    *,
    sample: Mapping[str, Any],
    sensor_family: str,
    axis_transform: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Apply an explicit axis permutation and sign transform.

    Non-axis fields are preserved.

    The input sample and transform configuration are not
    mutated.
    """
    if sensor_family not in SENSOR_FAMILIES:
        raise ValueError(
            "sensor family must be one of "
            f"{SENSOR_FAMILIES!r}; "
            f"got {sensor_family!r}."
        )

    if not isinstance(
        sample,
        Mapping,
    ):
        raise ValueError(
            "sensor sample must be a mapping."
        )

    for axis in _AXES:
        if axis not in sample:
            raise ValueError(
                f"sensor sample missing axis "
                f"{axis!r}."
            )

    normalized_transform = (
        _normalize_axis_transform(
            axis_transform
        )
    )

    family_transform = (
        normalized_transform[
            sensor_family
        ]
    )

    source_values = {
        axis:
            sample[axis]
        for axis in _AXES
    }

    result = deepcopy(
        dict(sample)
    )

    for output_axis in _AXES:
        rule = family_transform[
            output_axis
        ]

        source_axis = rule[
            "source_axis"
        ]

        sign = rule[
            "sign"
        ]

        result[
            output_axis
        ] = (
            source_values[
                source_axis
            ]
            * sign
        )

    return result


def canonical_axis_transform_json(
    axis_transform: Mapping[str, Any],
) -> str:
    """
    Return deterministic canonical JSON for one complete
    accel/gyro axis-transform configuration.
    """
    normalized = (
        _normalize_axis_transform(
            axis_transform
        )
    )

    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )


def axis_transform_sha256(
    axis_transform: Mapping[str, Any],
) -> str:
    """
    Return uppercase SHA-256 of canonical axis-transform
    JSON.
    """
    canonical_json = (
        canonical_axis_transform_json(
            axis_transform
        )
    )

    return hashlib.sha256(
        canonical_json.encode(
            "utf-8"
        )
    ).hexdigest().upper()