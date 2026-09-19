from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pc.experiment.preprocessing.schema import (
    DUPLICATE_EVENT_TYPES,
    REORDER_EVENT_TYPES,
    SENSOR_FAMILIES,
)


_REQUIRED_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
    "sensor_family",
    "source_file",
    "source_row_index",
    "sensor_sequence",
    "phone_sensor_ts_ns",
    "pc_mapped_ts_ns",
    "pc_receive_ts_ns",
    "mapping_status",
    "x",
    "y",
    "z",
)


def _parse_timestamp(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_identity(
    row: Mapping[str, Any],
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
) -> None:
    if row["participant_id"] != participant_id:
        raise ValueError(
            "participant identity mismatch."
        )

    if row["session_id"] != session_id:
        raise ValueError(
            "session identity mismatch."
        )

    if row["calibration_id"] != calibration_id:
        raise ValueError(
            "calibration identity mismatch."
        )


def _duplicate_event(
    *,
    event_type: str,
    sensor_family: str,
    source_row_index: Any,
    value: Any,
) -> dict[str, Any]:
    if event_type not in DUPLICATE_EVENT_TYPES:
        raise RuntimeError(
            f"Unknown duplicate event type: "
            f"{event_type}"
        )

    return {
        "event_type":
            event_type,
        "sensor_family":
            sensor_family,
        "source_row_index":
            source_row_index,
        "value":
            value,
    }


def normalize_sensor_streams(
    *,
    records: Sequence[Mapping[str, Any]],
    participant_id: str,
    session_id: str,
    calibration_id: str,
) -> dict[str, Any]:
    """
    Normalize mapped IMU records into independent accel and
    gyro streams.

    Temporal ordering is based only on pc_mapped_ts_ns.

    pc_receive_ts_ns is preserved as source provenance but
    is never used to determine sensor ordering.

    Duplicate and reorder anomalies are detected and
    reported without silently discarding valid mapped rows.
    """
    streams: dict[str, list[dict[str, Any]]] = {
        "ACCEL": [],
        "GYRO": [],
    }

    reorder_events: list[dict[str, Any]] = []
    duplicate_events: list[dict[str, Any]] = []
    invalid_timestamp_rows: list[Any] = []

    previous_mapped_time: dict[
        str,
        int | None,
    ] = {
        "ACCEL": None,
        "GYRO": None,
    }

    seen_source_identity: dict[
        str,
        set[tuple[Any, Any]],
    ] = {
        "ACCEL": set(),
        "GYRO": set(),
    }

    seen_native_time: dict[
        str,
        set[Any],
    ] = {
        "ACCEL": set(),
        "GYRO": set(),
    }

    seen_mapped_time: dict[
        str,
        set[int],
    ] = {
        "ACCEL": set(),
        "GYRO": set(),
    }

    source_counts = {
        "ACCEL": 0,
        "GYRO": 0,
    }

    for input_index, source_row in enumerate(
        records,
        start=1,
    ):
        missing = [
            field
            for field in _REQUIRED_FIELDS
            if field not in source_row
        ]

        if missing:
            raise ValueError(
                "sensor source row "
                f"{input_index} missing fields: "
                f"{missing!r}"
            )

        _validate_identity(
            source_row,
            participant_id=participant_id,
            session_id=session_id,
            calibration_id=calibration_id,
        )

        sensor_family = source_row[
            "sensor_family"
        ]

        if sensor_family not in SENSOR_FAMILIES:
            raise ValueError(
                "sensor family must be one of "
                f"{SENSOR_FAMILIES!r}; "
                f"got {sensor_family!r}."
            )

        source_counts[sensor_family] += 1

        mapped_time = _parse_timestamp(
            source_row["pc_mapped_ts_ns"]
        )

        if (
            source_row["mapping_status"]
            != "MAPPED"
            or mapped_time is None
        ):
            invalid_timestamp_rows.append(
                source_row["source_row_index"]
            )
            continue

        # -------------------------------------------------
        # Reorder detection uses original source order.
        # -------------------------------------------------

        previous = previous_mapped_time[
            sensor_family
        ]

        if (
            previous is not None
            and mapped_time < previous
        ):
            reorder_events.append(
                {
                    "event_type":
                        REORDER_EVENT_TYPES[0],
                    "sensor_family":
                        sensor_family,
                    "source_row_index":
                        source_row[
                            "source_row_index"
                        ],
                    "previous_pc_mapped_ts_ns":
                        previous,
                    "pc_mapped_ts_ns":
                        mapped_time,
                }
            )

        previous_mapped_time[
            sensor_family
        ] = mapped_time

        # -------------------------------------------------
        # Duplicate source identity.
        #
        # source_file + source_row_index together identify
        # the physical source row.
        # -------------------------------------------------

        source_identity = (
            source_row["source_file"],
            source_row["source_row_index"],
        )

        if (
            source_identity
            in seen_source_identity[
                sensor_family
            ]
        ):
            duplicate_events.append(
                _duplicate_event(
                    event_type=(
                        "DUPLICATE_SOURCE_IDENTITY"
                    ),
                    sensor_family=sensor_family,
                    source_row_index=(
                        source_row[
                            "source_row_index"
                        ]
                    ),
                    value=source_identity,
                )
            )
        else:
            seen_source_identity[
                sensor_family
            ].add(
                source_identity
            )

        # -------------------------------------------------
        # Duplicate native timestamp.
        # -------------------------------------------------

        native_time = source_row[
            "phone_sensor_ts_ns"
        ]

        if (
            native_time
            in seen_native_time[
                sensor_family
            ]
        ):
            duplicate_events.append(
                _duplicate_event(
                    event_type=(
                        "DUPLICATE_NATIVE_TIMESTAMP"
                    ),
                    sensor_family=sensor_family,
                    source_row_index=(
                        source_row[
                            "source_row_index"
                        ]
                    ),
                    value=native_time,
                )
            )
        else:
            seen_native_time[
                sensor_family
            ].add(
                native_time
            )

        # -------------------------------------------------
        # Duplicate mapped PC timestamp.
        # -------------------------------------------------

        if (
            mapped_time
            in seen_mapped_time[
                sensor_family
            ]
        ):
            duplicate_events.append(
                _duplicate_event(
                    event_type=(
                        "DUPLICATE_MAPPED_TIMESTAMP"
                    ),
                    sensor_family=sensor_family,
                    source_row_index=(
                        source_row[
                            "source_row_index"
                        ]
                    ),
                    value=mapped_time,
                )
            )
        else:
            seen_mapped_time[
                sensor_family
            ].add(
                mapped_time
            )

        # Preserve original provenance and values.
        normalized_row = deepcopy(
            dict(source_row)
        )

        normalized_row[
            "pc_mapped_ts_ns"
        ] = mapped_time

        streams[
            sensor_family
        ].append(
            normalized_row
        )

    # -----------------------------------------------------
    # Deterministic final temporal ordering.
    #
    # source_row_index is only a deterministic tie-breaker;
    # it is not the primary timing variable.
    # -----------------------------------------------------

    for sensor_family in SENSOR_FAMILIES:
        streams[sensor_family].sort(
            key=lambda row: (
                row["pc_mapped_ts_ns"],
                str(row["source_file"]),
                str(row["source_row_index"]),
                str(row["sensor_sequence"]),
            )
        )

    diagnostics = {
        "source_counts":
            source_counts,
        "valid_source_count":
            sum(
                len(streams[family])
                for family
                in SENSOR_FAMILIES
            ),
        "invalid_timestamp_count":
            len(
                invalid_timestamp_rows
            ),
        "invalid_timestamp_rows":
            invalid_timestamp_rows,
        "reorder_count":
            len(reorder_events),
        "reorder_events":
            reorder_events,
        "duplicate_count":
            len(duplicate_events),
        "duplicate_events":
            duplicate_events,
    }

    return {
        "streams":
            streams,
        "diagnostics":
            diagnostics,
    }

def apply_stream_anomaly_policy(
    *,
    normalized_result: Mapping[str, Any],
    reorder_policy: str,
    duplicate_policy: str,
) -> dict[str, Any]:
    """
    Apply explicit deterministic anomaly policies to a
    previously normalized sensor-stream bundle.

    Reorder detection itself occurs before temporal
    sorting in normalize_sensor_streams().

    This function records the chosen policy and applies
    duplicate handling without silently changing rows.
    """
    supported_reorder_policies = (
        "SORT_AND_REPORT",
    )

    supported_duplicate_policies = (
        "KEEP_ALL_REPORT",
        "KEEP_FIRST",
    )

    if (
        reorder_policy
        not in supported_reorder_policies
    ):
        raise ValueError(
            "unsupported reorder policy: "
            f"{reorder_policy!r}."
        )

    if (
        duplicate_policy
        not in supported_duplicate_policies
    ):
        raise ValueError(
            "unsupported duplicate policy: "
            f"{duplicate_policy!r}."
        )

    if "streams" not in normalized_result:
        raise ValueError(
            "normalized result missing streams."
        )

    if "diagnostics" not in normalized_result:
        raise ValueError(
            "normalized result missing diagnostics."
        )

    result = deepcopy(
        dict(normalized_result)
    )

    streams = result["streams"]
    diagnostics = result["diagnostics"]

    diagnostics[
        "reorder_policy"
    ] = reorder_policy

    diagnostics[
        "duplicate_policy"
    ] = duplicate_policy

    dropped_count = 0
    dropped_rows: list[dict[str, Any]] = []

    if duplicate_policy == "KEEP_FIRST":
        for sensor_family in SENSOR_FAMILIES:
            source_rows = streams.get(
                sensor_family,
                [],
            )

            seen_source_identity: set[
                tuple[Any, Any]
            ] = set()

            seen_native_timestamp: set[
                Any
            ] = set()

            seen_mapped_timestamp: set[
                Any
            ] = set()

            kept_rows: list[
                dict[str, Any]
            ] = []

            for row in source_rows:
                source_identity = (
                    row["source_file"],
                    row["source_row_index"],
                )

                native_timestamp = row[
                    "phone_sensor_ts_ns"
                ]

                mapped_timestamp = row[
                    "pc_mapped_ts_ns"
                ]

                duplicate_types: list[str] = []

                if (
                    source_identity
                    in seen_source_identity
                ):
                    duplicate_types.append(
                        "DUPLICATE_SOURCE_IDENTITY"
                    )

                if (
                    native_timestamp
                    in seen_native_timestamp
                ):
                    duplicate_types.append(
                        "DUPLICATE_NATIVE_TIMESTAMP"
                    )

                if (
                    mapped_timestamp
                    in seen_mapped_timestamp
                ):
                    duplicate_types.append(
                        "DUPLICATE_MAPPED_TIMESTAMP"
                    )

                # Every original occurrence participates
                # in first-occurrence bookkeeping even if
                # this row is dropped for another duplicate
                # dimension.
                seen_source_identity.add(
                    source_identity
                )

                seen_native_timestamp.add(
                    native_timestamp
                )

                seen_mapped_timestamp.add(
                    mapped_timestamp
                )

                if duplicate_types:
                    dropped_count += 1

                    dropped_rows.append(
                        {
                            "sensor_family":
                                sensor_family,
                            "source_file":
                                row[
                                    "source_file"
                                ],
                            "source_row_index":
                                row[
                                    "source_row_index"
                                ],
                            "duplicate_types":
                                duplicate_types,
                        }
                    )

                    continue

                kept_rows.append(
                    row
                )

            streams[
                sensor_family
            ] = kept_rows

    diagnostics[
        "policy_duplicate_dropped_count"
    ] = dropped_count

    diagnostics[
        "policy_duplicate_dropped_rows"
    ] = dropped_rows

    return result