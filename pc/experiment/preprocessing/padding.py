from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


SUPPORTED_PADDING_POLICIES = (
    "REPEAT_FIRST",
    "CONSTANT",
)


_IDENTITY_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
)


def _parse_window_length(
    value: Any,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            "window length must be a positive integer."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "window length must be a positive integer."
        ) from exc

    if parsed <= 0:
        raise ValueError(
            "window length must be positive."
        )

    return parsed


def _validate_feature_fields(
    feature_fields: Sequence[str],
) -> tuple[str, ...]:
    if isinstance(
        feature_fields,
        (str, bytes),
    ):
        raise ValueError(
            "feature fields must be a sequence "
            "of feature names."
        )

    normalized = tuple(
        feature_fields
    )

    if not normalized:
        raise ValueError(
            "feature field list must not be empty."
        )

    if (
        len(set(normalized))
        != len(normalized)
    ):
        raise ValueError(
            "feature field list contains "
            "duplicate feature names."
        )

    for field in normalized:
        if (
            not isinstance(field, str)
            or not field
        ):
            raise ValueError(
                "feature names must be non-empty "
                "strings."
            )

    return normalized


def _validate_rows(
    *,
    rows: Sequence[Mapping[str, Any]],
    feature_fields: tuple[str, ...],
) -> None:
    if not rows:
        raise ValueError(
            "padding input rows must not be empty."
        )

    required_fields = (
        *_IDENTITY_FIELDS,
        "sequence_id",
        *feature_fields,
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
                "padding row "
                f"{row_index} must be a mapping."
            )

        missing = [
            field
            for field in required_fields
            if field not in row
        ]

        if missing:
            if "sequence_id" in missing:
                raise ValueError(
                    "padding row "
                    f"{row_index} missing sequence_id."
                )

            missing_features = [
                field
                for field in feature_fields
                if field in missing
            ]

            if missing_features:
                raise ValueError(
                    "padding row "
                    f"{row_index} missing feature "
                    f"fields: {missing_features!r}."
                )

            raise ValueError(
                "padding row "
                f"{row_index} missing identity "
                f"fields: {missing!r}."
            )

    for identity_field in _IDENTITY_FIELDS:
        first_value = rows[0][
            identity_field
        ]

        if any(
            row[identity_field] != first_value
            for row in rows
        ):
            identity_name = (
                identity_field
                .replace("_id", "")
                .replace("_", " ")
            )

            raise ValueError(
                "padding input contains mixed "
                f"{identity_name} identity."
            )


def _feature_vector(
    row: Mapping[str, Any],
    *,
    feature_fields: tuple[str, ...],
) -> tuple[Any, ...]:
    return tuple(
        row[field]
        for field in feature_fields
    )


def _constant_vector(
    *,
    feature_count: int,
    padding_value: Any,
) -> tuple[Any, ...]:
    return tuple(
        padding_value
        for _ in range(feature_count)
    )


def build_causal_sequence_windows(
    *,
    rows: Sequence[Mapping[str, Any]],
    feature_fields: Sequence[str],
    window_length: int,
    padding_policy: str,
    padding_value: Any,
) -> list[dict[str, Any]]:
    """
    Build causal fixed-length feature windows.

    Each output window ends at the current row and may use
    only current/past rows from the same contiguous sequence
    run.

    When sequence_id changes, history resets immediately.
    Returning later to an earlier sequence_id starts a new
    run rather than recovering old history.

    Padding policy remains explicit and configurable.
    """
    normalized_features = (
        _validate_feature_fields(
            feature_fields
        )
    )

    normalized_window_length = (
        _parse_window_length(
            window_length
        )
    )

    if (
        padding_policy
        not in SUPPORTED_PADDING_POLICIES
    ):
        raise ValueError(
            "unsupported padding policy: "
            f"{padding_policy!r}."
        )

    _validate_rows(
        rows=rows,
        feature_fields=normalized_features,
    )

    result_rows: list[
        dict[str, Any]
    ] = []

    current_sequence_id: Any = None

    sequence_history: list[
        tuple[Any, ...]
    ] = []

    for source_row in rows:
        sequence_id = source_row[
            "sequence_id"
        ]

        current_vector = _feature_vector(
            source_row,
            feature_fields=normalized_features,
        )

        if (
            not sequence_history
            or sequence_id
            != current_sequence_id
        ):
            current_sequence_id = (
                sequence_id
            )

            sequence_history = []

        sequence_history.append(
            current_vector
        )

        history_slice = (
            sequence_history[
                -normalized_window_length:
            ]
        )

        missing_count = (
            normalized_window_length
            - len(history_slice)
        )

        if padding_policy == "REPEAT_FIRST":
            first_vector = sequence_history[
                0
            ]

            padded_prefix = [
                first_vector
                for _ in range(
                    missing_count
                )
            ]

        elif padding_policy == "CONSTANT":
            constant_vector = (
                _constant_vector(
                    feature_count=len(
                        normalized_features
                    ),
                    padding_value=padding_value,
                )
            )

            padded_prefix = [
                constant_vector
                for _ in range(
                    missing_count
                )
            ]

        else:
            raise RuntimeError(
                "unsupported padding execution path."
            )

        window = tuple(
            [
                *padded_prefix,
                *history_slice,
            ]
        )

        padding_mask = tuple(
            [
                *(
                    True
                    for _ in range(
                        missing_count
                    )
                ),
                *(
                    False
                    for _ in range(
                        len(history_slice)
                    )
                ),
            ]
        )

        result = deepcopy(
            dict(source_row)
        )

        result[
            "window"
        ] = window

        result[
            "padding_mask"
        ] = padding_mask

        result_rows.append(
            result
        )

    return result_rows