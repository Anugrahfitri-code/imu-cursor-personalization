from collections.abc import Mapping, Sequence
from string import hexdigits
from typing import Any

from pc.experiment.labels.schema import (
    MAPPED_SENSOR_TIME_COLUMNS,
)


def _validate_non_empty_string(
    value: str,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            f"{field_name} must be a "
            "non-empty string."
        )

    return value.strip()


def _validate_sha256(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string."
        )

    normalized = value.strip().upper()

    if len(normalized) != 64:
        raise ValueError(
            f"{field_name} must contain exactly "
            "64 hexadecimal characters."
        )

    if any(
        char not in hexdigits
        for char in normalized
    ):
        raise ValueError(
            f"{field_name} must be hexadecimal."
        )

    return normalized


def _parse_phone_sensor_ts_ns(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed


def _make_row(
    *,
    mapped_record_id: str,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    source_file: str,
    source_row_index: Any,
    phone_sensor_ts_ns: Any,
    pc_mapped_ts_ns: int | None,
    clock_model_sha256: str,
    mapping_status: str,
    derivation_version: str,
) -> dict[str, object]:
    row = {
        "mapped_record_id":
            mapped_record_id,
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "source_file":
            source_file,
        "source_row_index":
            source_row_index,
        "phone_sensor_ts_ns":
            phone_sensor_ts_ns,
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
        "clock_model_sha256":
            clock_model_sha256,
        "mapping_status":
            mapping_status,
        "derivation_version":
            derivation_version,
    }

    if tuple(row.keys()) != MAPPED_SENSOR_TIME_COLUMNS:
        raise RuntimeError(
            "Internal mapped sensor schema "
            "order mismatch."
        )

    return row


def map_sensor_records(
    *,
    records: Sequence[Mapping[str, Any]],
    participant_id: str,
    session_id: str,
    calibration_id: str,
    source_file: str,
    clock_model: Any,
    clock_model_sha256: str,
    clock_quality_passed: bool,
    derivation_version: str,
) -> list[dict[str, object]]:
    """
    Map native phone sensor timestamps into PC time.

    This function deliberately delegates timestamp mapping
    to the already-qualified clock model through
    map_phone_to_pc_ns(). It does not estimate alpha/beta
    and does not use pc_receive_ts_ns for supervision.
    """
    if not clock_quality_passed:
        raise ValueError(
            "clock quality gate failed; "
            "native timestamp mapping is invalid."
        )

    if not hasattr(
        clock_model,
        "map_phone_to_pc_ns",
    ):
        raise ValueError(
            "clock model must expose "
            "map_phone_to_pc_ns()."
        )

    participant_id = _validate_non_empty_string(
        participant_id,
        field_name="participant_id",
    )

    session_id = _validate_non_empty_string(
        session_id,
        field_name="session_id",
    )

    calibration_id = _validate_non_empty_string(
        calibration_id,
        field_name="calibration_id",
    )

    source_file = _validate_non_empty_string(
        source_file,
        field_name="source_file",
    )

    derivation_version = (
        _validate_non_empty_string(
            derivation_version,
            field_name="derivation_version",
        )
    )

    clock_model_sha256 = _validate_sha256(
        clock_model_sha256,
        field_name="clock_model_sha256",
    )

    rows: list[dict[str, object]] = []

    for record_index, record in enumerate(
        records,
        start=1,
    ):
        source_row_index = record.get(
            "source_row_index"
        )

        original_phone_time = record.get(
            "phone_sensor_ts_ns"
        )

        phone_time = (
            _parse_phone_sensor_ts_ns(
                original_phone_time
            )
        )

        if phone_time is None:
            mapped_time = None
            mapping_status = (
                "INVALID_SOURCE_TIMESTAMP"
            )
        else:
            mapped_time = int(
                clock_model.map_phone_to_pc_ns(
                    phone_time
                )
            )

            mapping_status = "MAPPED"

        rows.append(
            _make_row(
                mapped_record_id=(
                    f"MAP{record_index:06d}"
                ),
                participant_id=participant_id,
                session_id=session_id,
                calibration_id=calibration_id,
                source_file=source_file,
                source_row_index=(
                    source_row_index
                ),
                phone_sensor_ts_ns=(
                    original_phone_time
                    if phone_time is None
                    else phone_time
                ),
                pc_mapped_ts_ns=mapped_time,
                clock_model_sha256=(
                    clock_model_sha256
                ),
                mapping_status=mapping_status,
                derivation_version=(
                    derivation_version
                ),
            )
        )

    return rows