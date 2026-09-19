from collections.abc import Mapping, Sequence
from typing import Any

from pc.experiment.labels.reference_lookup import (
    lookup_reference_state,
)
from pc.experiment.labels.schema import (
    NATIVE_LABEL_COLUMNS,
)


_MAPPED_REQUIRED_FIELDS = (
    "mapped_record_id",
    "participant_id",
    "session_id",
    "calibration_id",
    "source_file",
    "source_row_index",
    "phone_sensor_ts_ns",
    "pc_mapped_ts_ns",
    "mapping_status",
)


def _validate_non_empty_string(
    value: Any,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value.strip()


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


def _validate_reference_identity(
    reference_trajectory: Sequence[
        Mapping[str, Any]
    ],
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
) -> None:
    if not reference_trajectory:
        raise ValueError(
            "reference trajectory must not be empty."
        )

    first = reference_trajectory[0]

    required = (
        "participant_id",
        "session_id",
        "calibration_id",
    )

    missing = [
        field
        for field in required
        if field not in first
    ]

    if missing:
        raise ValueError(
            "reference trajectory identity fields "
            f"missing: {missing!r}"
        )

    if (
        first["participant_id"]
        != participant_id
    ):
        raise ValueError(
            "participant identity mismatch between "
            "mapped sensor data and reference trajectory."
        )

    if first["session_id"] != session_id:
        raise ValueError(
            "session identity mismatch between "
            "mapped sensor data and reference trajectory."
        )

    if (
        first["calibration_id"]
        != calibration_id
    ):
        raise ValueError(
            "calibration identity mismatch between "
            "mapped sensor data and reference trajectory."
        )


def _make_label_row(
    *,
    label_record_id: str,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    source_file: str,
    source_row_index: Any,
    phone_sensor_ts_ns: Any,
    pc_mapped_ts_ns: int,
    alignment_lag_ns: int,
    label_pc_time_ns: int,
    lookup_result: Mapping[str, Any],
    derivation_version: str,
) -> dict[str, object]:
    row = {
        "label_record_id":
            label_record_id,
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
        "alignment_lag_ns":
            alignment_lag_ns,
        "label_pc_time_ns":
            label_pc_time_ns,
        "sequence_id":
            lookup_result["sequence_id"],
        "direction_code":
            lookup_result["direction_code"],
        "phase":
            lookup_result["phase"],
        "ref_x_px":
            lookup_result["ref_x_px"],
        "ref_y_px":
            lookup_result["ref_y_px"],
        "ref_vx_px_s":
            lookup_result["ref_vx_px_s"],
        "ref_vy_px_s":
            lookup_result["ref_vy_px_s"],
        "label_status":
            lookup_result["label_status"],
        "derivation_version":
            derivation_version,
    }

    if tuple(row.keys()) != NATIVE_LABEL_COLUMNS:
        raise RuntimeError(
            "Internal native label schema "
            "order mismatch."
        )

    return row


def build_native_labels(
    *,
    mapped_sensor_times: Sequence[
        Mapping[str, Any]
    ],
    reference_trajectory: Sequence[
        Mapping[str, Any]
    ],
    alignment_lag_ns: int,
    derivation_version: str,
) -> list[dict[str, object]]:
    """
    Build native-event reference labels.

    Frozen lag convention:

        label_pc_time_ns
        =
        pc_mapped_ts_ns - alignment_lag_ns

    Positive lag therefore queries an earlier reference
    state. This function does not create the final common
    IMU grid or model windows.
    """
    lag_ns = _parse_integer(
        alignment_lag_ns,
        field_name="alignment_lag_ns",
    )

    derivation_version = (
        _validate_non_empty_string(
            derivation_version,
            field_name="derivation_version",
        )
    )

    if not mapped_sensor_times:
        return []

    first_mapped = mapped_sensor_times[0]

    identity_fields = (
        "participant_id",
        "session_id",
        "calibration_id",
    )

    missing_identity = [
        field
        for field in identity_fields
        if field not in first_mapped
    ]

    if missing_identity:
        raise ValueError(
            "mapped sensor identity fields missing: "
            f"{missing_identity!r}"
        )

    expected_participant = (
        first_mapped["participant_id"]
    )
    expected_session = (
        first_mapped["session_id"]
    )
    expected_calibration = (
        first_mapped["calibration_id"]
    )

    _validate_reference_identity(
        reference_trajectory,
        participant_id=expected_participant,
        session_id=expected_session,
        calibration_id=expected_calibration,
    )

    rows: list[dict[str, object]] = []

    for row_index, mapped in enumerate(
        mapped_sensor_times,
        start=1,
    ):
        missing = [
            field
            for field in _MAPPED_REQUIRED_FIELDS
            if field not in mapped
        ]

        if missing:
            raise ValueError(
                "mapped sensor row "
                f"{row_index} missing fields: "
                f"{missing!r}"
            )

        if (
            mapped["participant_id"]
            != expected_participant
        ):
            raise ValueError(
                "mapped sensor participant identity "
                "is inconsistent."
            )

        if (
            mapped["session_id"]
            != expected_session
        ):
            raise ValueError(
                "mapped sensor session identity "
                "is inconsistent."
            )

        if (
            mapped["calibration_id"]
            != expected_calibration
        ):
            raise ValueError(
                "mapped sensor calibration identity "
                "is inconsistent."
            )

        if mapped["mapping_status"] != "MAPPED":
            raise ValueError(
                "mapping status must be MAPPED "
                "before label construction."
            )

        mapped_time = _parse_integer(
            mapped["pc_mapped_ts_ns"],
            field_name="pc_mapped_ts_ns",
        )

        label_time = (
            mapped_time - lag_ns
        )

        lookup_result = (
            lookup_reference_state(
                reference_trajectory,
                label_time,
            )
        )

        rows.append(
            _make_label_row(
                label_record_id=(
                    f"LBL{row_index:06d}"
                ),
                participant_id=str(
                    mapped["participant_id"]
                ),
                session_id=str(
                    mapped["session_id"]
                ),
                calibration_id=str(
                    mapped["calibration_id"]
                ),
                source_file=str(
                    mapped["source_file"]
                ),
                source_row_index=(
                    mapped["source_row_index"]
                ),
                phone_sensor_ts_ns=(
                    mapped["phone_sensor_ts_ns"]
                ),
                pc_mapped_ts_ns=mapped_time,
                alignment_lag_ns=lag_ns,
                label_pc_time_ns=label_time,
                lookup_result=lookup_result,
                derivation_version=(
                    derivation_version
                ),
            )
        )

    return rows