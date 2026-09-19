from collections.abc import Mapping, Sequence
from string import hexdigits
from typing import Any

from pc.experiment.labels.schema import (
    LABEL_BUILD_STATUSES,
    LABEL_MANIFEST_REQUIRED_FIELDS,
    LABEL_STATUSES,
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
            f"{field_name} must be a "
            "non-empty string."
        )

    return value.strip()


def _validate_sha256(
    value: Any,
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
        character not in hexdigits
        for character in normalized
    ):
        raise ValueError(
            f"{field_name} must be hexadecimal."
        )

    return normalized


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


def build_label_manifest(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    label_rows: Sequence[
        Mapping[str, Any]
    ],
    assessment: Mapping[str, Any],
    raw_imu_sha256: str,
    reference_trajectory_sha256: str,
    clock_model_sha256: str,
    label_config_sha256: str,
    derivation_version: str,
    functional_commit: str,
) -> dict[str, object]:
    """
    Build the frozen Stage 2.4 label manifest.

    Row-level invalid labels remain represented by the
    valid/invalid counts. Build-level status comes from the
    technical assessment.
    """
    participant_id = (
        _validate_non_empty_string(
            participant_id,
            field_name="participant_id",
        )
    )

    session_id = _validate_non_empty_string(
        session_id,
        field_name="session_id",
    )

    calibration_id = (
        _validate_non_empty_string(
            calibration_id,
            field_name="calibration_id",
        )
    )

    derivation_version = (
        _validate_non_empty_string(
            derivation_version,
            field_name="derivation_version",
        )
    )

    functional_commit = (
        _validate_non_empty_string(
            functional_commit,
            field_name="functional_commit",
        )
    )

    raw_imu_sha256 = _validate_sha256(
        raw_imu_sha256,
        field_name="raw_imu_sha256",
    )

    reference_trajectory_sha256 = (
        _validate_sha256(
            reference_trajectory_sha256,
            field_name=(
                "reference_trajectory_sha256"
            ),
        )
    )

    clock_model_sha256 = _validate_sha256(
        clock_model_sha256,
        field_name="clock_model_sha256",
    )

    label_config_sha256 = _validate_sha256(
        label_config_sha256,
        field_name="label_config_sha256",
    )

    if not isinstance(
        assessment,
        Mapping,
    ):
        raise ValueError(
            "assessment must be a mapping."
        )

    required_assessment_fields = (
        "status",
        "mapped_record_count",
        "valid_label_count",
        "invalid_label_count",
    )

    missing_assessment = [
        field
        for field in required_assessment_fields
        if field not in assessment
    ]

    if missing_assessment:
        raise ValueError(
            "assessment missing field(s): "
            f"{missing_assessment!r}"
        )

    status = assessment["status"]

    if status not in LABEL_BUILD_STATUSES:
        raise ValueError(
            "assessment status is invalid."
        )

    expected_identity = (
        participant_id,
        session_id,
        calibration_id,
    )

    mapped_times: list[int] = []

    actual_valid_count = 0

    for row_index, row in enumerate(
        label_rows,
        start=1,
    ):
        row_identity = (
            row.get("participant_id"),
            row.get("session_id"),
            row.get("calibration_id"),
        )

        if row_identity != expected_identity:
            raise ValueError(
                "label row identity does not "
                "match manifest identity at "
                f"row {row_index}."
            )

        row_status = row.get(
            "label_status"
        )

        if row_status not in LABEL_STATUSES:
            raise ValueError(
                "label row contains invalid "
                f"label_status at row {row_index}."
            )

        if row_status == "VALID":
            actual_valid_count += 1

        mapped_times.append(
            _parse_integer(
                row.get("pc_mapped_ts_ns"),
                field_name="pc_mapped_ts_ns",
            )
        )

    actual_mapped_count = len(
        label_rows
    )

    actual_invalid_count = (
        actual_mapped_count
        - actual_valid_count
    )

    assessment_mapped_count = _parse_integer(
        assessment["mapped_record_count"],
        field_name=(
            "assessment.mapped_record_count"
        ),
    )

    assessment_valid_count = _parse_integer(
        assessment["valid_label_count"],
        field_name=(
            "assessment.valid_label_count"
        ),
    )

    assessment_invalid_count = _parse_integer(
        assessment["invalid_label_count"],
        field_name=(
            "assessment.invalid_label_count"
        ),
    )

    if (
        assessment_mapped_count
        != actual_mapped_count
        or assessment_valid_count
        != actual_valid_count
        or assessment_invalid_count
        != actual_invalid_count
    ):
        raise ValueError(
            "assessment counts do not match "
            "label rows."
        )

    if mapped_times:
        first_mapped_pc_time_ns = min(
            mapped_times
        )

        last_mapped_pc_time_ns = max(
            mapped_times
        )
    else:
        first_mapped_pc_time_ns = None
        last_mapped_pc_time_ns = None

    manifest = {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "status":
            status,
        "raw_imu_sha256":
            raw_imu_sha256,
        "reference_trajectory_sha256":
            reference_trajectory_sha256,
        "clock_model_sha256":
            clock_model_sha256,
        "label_config_sha256":
            label_config_sha256,
        "mapped_record_count":
            actual_mapped_count,
        "valid_label_count":
            actual_valid_count,
        "invalid_label_count":
            actual_invalid_count,
        "first_mapped_pc_time_ns":
            first_mapped_pc_time_ns,
        "last_mapped_pc_time_ns":
            last_mapped_pc_time_ns,
        "derivation_version":
            derivation_version,
        "functional_commit":
            functional_commit,
    }

    if (
        tuple(manifest.keys())
        != LABEL_MANIFEST_REQUIRED_FIELDS
    ):
        raise RuntimeError(
            "Internal label manifest schema "
            "order mismatch."
        )

    return manifest