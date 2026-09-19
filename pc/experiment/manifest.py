import json
import math
import re
from pathlib import Path

from pc.experiment.contracts import (
    ALLOWED_CONDITIONS,
    ALLOWED_DATASET_ROLES,
    ALLOWED_SESSION_STATUSES,
    SCHEMA_VERSION,
)
from pc.experiment.session_hash import (
    HASH_MANIFEST_NAME,
    is_session_relative_path,
)


EVIDENCE_FIELDS = {
    "android_evidence": (
        ("imu_file", "imu_sha256"),
        ("android_metadata_file", "android_metadata_sha256"),
    ),
    "clock_evidence": (
        ("clock_model_file", "clock_model_sha256"),
        ("sync_probes_file", "sync_probes_sha256"),
    ),
}


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _hash_string(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9A-Fa-f]{64}", value) is not None
    )


def _evidence_path(value: object) -> bool:
    return is_session_relative_path(value) and value not in (
        "manifest.json", HASH_MANIFEST_NAME,
    )


def _positive_number(value: object) -> bool:
    return (
        type(value) is int and value > 0
        or type(value) is float and math.isfinite(value) and value > 0
    )


def _positive_integer(value: object) -> bool:
    # JSON Schema integers include integral floating-point JSON numbers.
    return _positive_number(value) and (
        type(value) is int or value.is_integer()
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
    if not isinstance(manifest, dict):
        return ["Manifest root must be a JSON object."]
    for field in sorted(set(manifest) - set(MANIFEST_REQUIRED_FIELDS)):
        errors.append(f"Unknown manifest field: {field}")

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

            if manifest.get("session_status") == "closed" and not condition_order:
                errors.append("Closed session condition_order must not be empty.")

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

    for field in (
        "experiment_protocol_version",
        "functional_commit",
        "experiment_software_version",
    ):
        if not _nonempty_string(manifest.get(field)):
            errors.append(f"{field} must be a non-empty string.")

    nested_checks = {
        "device": {
            "manufacturer": _nonempty_string,
            "model": _nonempty_string,
            "android_version": _nonempty_string,
            "android_session_id": _nonempty_string,
            "api_level": _positive_integer,
        },
        "display": {
            **{field: _positive_integer for field in (
                "display_width_px",
                "display_height_px",
                "experiment_window_width_px",
                "experiment_window_height_px",
            )},
            "display_scale_factor": _positive_number,
        },
    }
    for section, pairs in EVIDENCE_FIELDS.items():
        nested_checks[section] = {
            field: check for path_field, hash_field in pairs
            for field, check in ((path_field, _evidence_path), (hash_field, _hash_string))
        }
    for section, checks in nested_checks.items():
        value = manifest.get(section)
        if not isinstance(value, dict):
            errors.append(f"{section} must be an object.")
            continue
        for field, check in checks.items():
            if not check(value.get(field)):
                errors.append(f"Missing or invalid {section}.{field}.")

    required_paths = [
        manifest[section].get(path_field)
        for section, pairs in EVIDENCE_FIELDS.items()
        if isinstance(manifest.get(section), dict)
        for path_field, _ in pairs
        if isinstance(manifest[section].get(path_field), str)
    ]
    if len(required_paths) != len(set(required_paths)):
        errors.append("Required evidence sources must reference distinct files.")

    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("files must be an array of evidence references.")
    else:
        seen_paths: set[str] = set()
        for index, entry in enumerate(files):
            if not isinstance(entry, dict):
                errors.append(f"files[{index}] must be an object.")
                continue
            for field, check in (
                ("relative_path", _evidence_path),
                ("sha256", _hash_string),
                ("role", _nonempty_string),
            ):
                if not check(entry.get(field)):
                    errors.append(f"Missing or invalid files[{index}].{field}.")
            relative_path = entry.get("relative_path")
            if isinstance(relative_path, str):
                if relative_path in seen_paths:
                    errors.append(f"Duplicate files reference: {relative_path}")
                seen_paths.add(relative_path)
    return errors
