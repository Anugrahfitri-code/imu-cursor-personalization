import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from string import hexdigits
from typing import Any

from pc.experiment.calibration.schema import (
    CALIBRATION_MANIFEST_REQUIRED_FIELDS,
)


_SOURCE_SELECTION_REQUIRED_FIELDS = (
    "source_file",
    "source_file_sha256",
    "source_first_row",
    "source_last_row",
    "source_first_sequence",
    "source_last_sequence",
    "calibration_start_pc_ns",
    "calibration_end_pc_ns",
    "calibration_id",
)


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


def _validate_source_selection(
    source_selection: Mapping[str, Any],
    *,
    raw_imu_sha256: str,
) -> dict[str, Any]:
    if not isinstance(
        source_selection,
        Mapping,
    ):
        raise ValueError(
            "source_selection must be a mapping."
        )

    missing = [
        field
        for field
        in _SOURCE_SELECTION_REQUIRED_FIELDS
        if field not in source_selection
    ]

    if missing:
        raise ValueError(
            "Missing source_selection field(s): "
            f"{missing!r}"
        )

    selection = deepcopy(
        dict(source_selection)
    )

    selection["source_file"] = (
        _validate_non_empty_string(
            selection["source_file"],
            field_name="source_file",
        )
    )

    selection_hash = _validate_sha256(
        selection["source_file_sha256"],
        field_name="source_file_sha256",
    )

    if selection_hash != raw_imu_sha256:
        raise ValueError(
            "source_file_sha256 must match "
            "raw_imu_sha256."
        )

    selection["source_file_sha256"] = (
        selection_hash
    )

    integer_fields = (
        "source_first_row",
        "source_last_row",
        "source_first_sequence",
        "source_last_sequence",
        "calibration_start_pc_ns",
        "calibration_end_pc_ns",
    )

    for field in integer_fields:
        try:
            selection[field] = int(
                selection[field]
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field} must be an integer."
            ) from exc

    if (
        selection["source_first_row"]
        > selection["source_last_row"]
    ):
        raise ValueError(
            "source_first_row must not exceed "
            "source_last_row."
        )

    if (
        selection["source_first_sequence"]
        > selection["source_last_sequence"]
    ):
        raise ValueError(
            "source_first_sequence must not exceed "
            "source_last_sequence."
        )

    if (
        selection["calibration_start_pc_ns"]
        > selection["calibration_end_pc_ns"]
    ):
        raise ValueError(
            "calibration_start_pc_ns must not "
            "exceed calibration_end_pc_ns."
        )

    selection["calibration_id"] = (
        _validate_non_empty_string(
            selection["calibration_id"],
            field_name="calibration_id",
        )
    )

    return selection


def build_calibration_manifest(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    calibration_start_pc_ns: int,
    calibration_end_pc_ns: int,
    cycle_count: int,
    reference_trajectory_file: str,
    trajectory_version: str,
    trajectory_config_sha256: str,
    raw_imu_sha256: str,
    clock_model_sha256: str,
    source_selection: Mapping[str, Any],
) -> dict[str, Any]:
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

    reference_trajectory_file = (
        _validate_non_empty_string(
            reference_trajectory_file,
            field_name=(
                "reference_trajectory_file"
            ),
        )
    )

    trajectory_version = (
        _validate_non_empty_string(
            trajectory_version,
            field_name="trajectory_version",
        )
    )

    trajectory_config_sha256 = (
        _validate_sha256(
            trajectory_config_sha256,
            field_name=(
                "trajectory_config_sha256"
            ),
        )
    )

    raw_imu_sha256 = _validate_sha256(
        raw_imu_sha256,
        field_name="raw_imu_sha256",
    )

    clock_model_sha256 = _validate_sha256(
        clock_model_sha256,
        field_name="clock_model_sha256",
    )

    try:
        calibration_start_pc_ns = int(
            calibration_start_pc_ns
        )
        calibration_end_pc_ns = int(
            calibration_end_pc_ns
        )
        cycle_count = int(
            cycle_count
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Calibration timing and cycle count "
            "must be integers."
        ) from exc

    if (
        calibration_start_pc_ns
        > calibration_end_pc_ns
    ):
        raise ValueError(
            "calibration_start_pc_ns must not "
            "exceed calibration_end_pc_ns."
        )

    if cycle_count != 2:
        raise ValueError(
            "Guided 2C calibration requires "
            "cycle_count=2."
        )

    selection = _validate_source_selection(
        source_selection,
        raw_imu_sha256=raw_imu_sha256,
    )

    if (
        selection["calibration_id"]
        != calibration_id
    ):
        raise ValueError(
            "source_selection calibration_id "
            "must match manifest calibration_id."
        )

    if (
        selection["calibration_start_pc_ns"]
        != calibration_start_pc_ns
        or
        selection["calibration_end_pc_ns"]
        != calibration_end_pc_ns
    ):
        raise ValueError(
            "source_selection calibration window "
            "must match manifest calibration window."
        )

    manifest = {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "calibration_start_pc_ns":
            calibration_start_pc_ns,
        "calibration_end_pc_ns":
            calibration_end_pc_ns,
        "cycle_count":
            cycle_count,
        "reference_trajectory_file":
            reference_trajectory_file,
        "trajectory_version":
            trajectory_version,
        "trajectory_config_sha256":
            trajectory_config_sha256,
        "raw_imu_sha256":
            raw_imu_sha256,
        "clock_model_sha256":
            clock_model_sha256,
        "source_selection":
            selection,
    }

    for field in (
        CALIBRATION_MANIFEST_REQUIRED_FIELDS
    ):
        if field not in manifest:
            raise RuntimeError(
                "Internal calibration manifest "
                f"missing field: {field}"
            )

    return manifest


def calibration_provenance_sha256(
    manifest: Mapping[str, Any],
) -> str:
    if not isinstance(manifest, Mapping):
        raise ValueError(
            "manifest must be a mapping."
        )

    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest().upper()
