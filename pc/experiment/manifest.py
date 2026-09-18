import json
from pathlib import Path

from pc.experiment.contracts import (
    ALLOWED_CONDITIONS,
    ALLOWED_DATASET_ROLES,
    ALLOWED_SESSION_STATUSES,
    SCHEMA_VERSION,
)


MANIFEST_REQUIRED_FIELDS = (
    "schema_version",
    "participant_id",
    "session_id",
    "dataset_role",
    "session_status",
    "experiment_protocol_version",
    "condition_order",
    "functional_commit",
    "experiment_software_version",
    "device",
    "display",
    "android_evidence",
    "clock_evidence",
    "files",
)


def load_manifest(path: Path) -> dict[str, object]:
    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError(
            "Manifest root must be a JSON object."
        )

    return data


def validate_manifest(
    manifest: dict[str, object],
) -> list[str]:
    errors: list[str] = []

    for field in MANIFEST_REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(
                f"Missing required manifest field: {field}"
            )

    if "schema_version" in manifest:
        schema_version = manifest["schema_version"]

        if schema_version != SCHEMA_VERSION:
            errors.append(
                "Invalid schema_version: "
                f"expected={SCHEMA_VERSION!r}, "
                f"actual={schema_version!r}"
            )

    if "dataset_role" in manifest:
        dataset_role = manifest["dataset_role"]

        if (
            not isinstance(dataset_role, str)
            or dataset_role not in ALLOWED_DATASET_ROLES
        ):
            errors.append(
                f"Invalid dataset_role: {dataset_role!r}"
            )

    if "session_status" in manifest:
        session_status = manifest["session_status"]

        if (
            not isinstance(session_status, str)
            or session_status
            not in ALLOWED_SESSION_STATUSES
        ):
            errors.append(
                f"Invalid session_status: {session_status!r}"
            )

    if "condition_order" in manifest:
        condition_order = manifest["condition_order"]

        if (
            not isinstance(condition_order, list)
            or not all(
                isinstance(condition, str)
                for condition in condition_order
            )
        ):
            errors.append(
                "condition_order must be a list of strings."
            )
        else:
            unknown_conditions = [
                condition
                for condition in condition_order
                if condition not in ALLOWED_CONDITIONS
            ]

            if unknown_conditions:
                errors.append(
                    "Unknown condition(s) in condition_order: "
                    f"{unknown_conditions!r}"
                )

            if len(condition_order) != len(
                set(condition_order)
            ):
                errors.append(
                    "condition_order contains duplicate "
                    "conditions."
                )

    if "participant_id" in manifest:
        participant_id = manifest["participant_id"]

        if (
            not isinstance(participant_id, str)
            or not participant_id.strip()
        ):
            errors.append(
                "participant_id must be a non-empty string."
            )

    if "session_id" in manifest:
        session_id = manifest["session_id"]

        if (
            not isinstance(session_id, str)
            or not session_id.strip()
        ):
            errors.append(
                "session_id must be a non-empty string."
            )

    return errors
