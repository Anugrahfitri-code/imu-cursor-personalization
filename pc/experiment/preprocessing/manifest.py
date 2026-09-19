import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pc.experiment.preprocessing.config import (
    normalize_sha256,
    preprocessing_config_sha256,
    validate_preprocessing_config,
)

from pc.experiment.preprocessing.schema import (
    PREPROCESSING_BUILD_STATUSES,
    PREPROCESSING_MANIFEST_REQUIRED_FIELDS,
)


_IDENTITY_FIELDS = (
    "participant_id",
    "session_id",
    "calibration_id",
)


def _identity_name(
    field: str,
) -> str:
    return (
        field
        .replace("_id", "")
        .replace("_", " ")
    )


def _require_nonempty_string(
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

    return value


def _parse_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be an integer."
        )

    if isinstance(value, float):
        if (
            not math.isfinite(value)
            or not value.is_integer()
        ):
            raise ValueError(
                f"{field_name} must be an integer."
            )

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be an integer."
        ) from exc


def _normalize_hash_mapping(
    value: Any,
    *,
    field_name: str,
) -> dict[str, str]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise ValueError(
            f"{field_name} must be a mapping."
        )

    normalized: dict[str, str] = {}

    for key in sorted(
        value.keys()
    ):
        if (
            not isinstance(key, str)
            or not key
        ):
            raise ValueError(
                f"{field_name} keys must be "
                "non-empty strings."
            )

        normalized[key] = (
            normalize_sha256(
                value[key],
                field_name=(
                    f"{field_name} SHA-256 "
                    f"{key!r}"
                ),
            )
        )

    return normalized


def _validate_identity(
    *,
    row: Mapping[str, Any],
    expected_identity: Mapping[str, Any],
    context: str,
) -> None:
    for field in _IDENTITY_FIELDS:
        if field not in row:
            raise ValueError(
                f"{context} missing "
                f"{_identity_name(field)} identity."
            )

        if (
            row[field]
            != expected_identity[field]
        ):
            raise ValueError(
                f"{context} "
                f"{_identity_name(field)} identity "
                "does not match manifest identity."
            )


def _validate_common_grid_rows(
    *,
    rows: Sequence[Mapping[str, Any]],
    expected_identity: Mapping[str, Any],
    expected_config_sha256: str,
) -> tuple[
    int | None,
    int | None,
    int,
]:
    timestamps: list[int] = []

    for row_index, row in enumerate(
        rows,
        start=1,
    ):
        if not isinstance(
            row,
            Mapping,
        ):
            raise ValueError(
                "common grid row "
                f"{row_index} must be a mapping."
            )

        _validate_identity(
            row=row,
            expected_identity=expected_identity,
            context=(
                f"common grid row {row_index}"
            ),
        )

        if "grid_pc_time_ns" not in row:
            raise ValueError(
                "common grid row "
                f"{row_index} missing "
                "grid_pc_time_ns."
            )

        if (
            "preprocessing_config_sha256"
            not in row
        ):
            raise ValueError(
                "common grid row "
                f"{row_index} missing config hash."
            )

        row_config_sha = (
            normalize_sha256(
                row[
                    "preprocessing_config_sha256"
                ],
                field_name=(
                    "common grid config SHA-256"
                ),
            )
        )

        if (
            row_config_sha
            != expected_config_sha256
        ):
            raise ValueError(
                "common grid config hash does not "
                "match preprocessing config."
            )

        timestamps.append(
            _parse_integer(
                row["grid_pc_time_ns"],
                field_name=(
                    "common grid grid_pc_time_ns"
                ),
            )
        )

    if timestamps:
        first_time = min(
            timestamps
        )

        last_time = max(
            timestamps
        )
    else:
        first_time = None
        last_time = None

    return (
        first_time,
        last_time,
        len(rows),
    )


def _validate_quality(
    *,
    preprocessing_quality: Mapping[str, Any],
    expected_identity: Mapping[str, Any],
    expected_grid_row_count: int,
) -> str:
    if not isinstance(
        preprocessing_quality,
        Mapping,
    ):
        raise ValueError(
            "preprocessing quality must be a mapping."
        )

    _validate_identity(
        row=preprocessing_quality,
        expected_identity=expected_identity,
        context="preprocessing quality",
    )

    if "status" not in preprocessing_quality:
        raise ValueError(
            "preprocessing quality missing status."
        )

    status = preprocessing_quality[
        "status"
    ]

    if (
        status
        not in PREPROCESSING_BUILD_STATUSES
    ):
        raise ValueError(
            "preprocessing quality status is invalid."
        )

    if (
        "grid_row_count"
        not in preprocessing_quality
    ):
        raise ValueError(
            "preprocessing quality missing "
            "grid row count."
        )

    quality_count = _parse_integer(
        preprocessing_quality[
            "grid_row_count"
        ],
        field_name=(
            "preprocessing quality grid row count"
        ),
    )

    if quality_count < 0:
        raise ValueError(
            "preprocessing quality grid row count "
            "must be non-negative."
        )

    if (
        quality_count
        != expected_grid_row_count
    ):
        raise ValueError(
            "preprocessing quality grid row count "
            "does not match common-grid row count."
        )

    return status


def build_preprocessing_manifest(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    preprocessing_config: Mapping[str, Any],
    preprocessing_config_sha256: str,
    source_artifact_hashes: Mapping[str, Any],
    upstream_stage24_provenance_sha256: str,
    common_grid_rows: Sequence[
        Mapping[str, Any]
    ],
    common_grid_sha256: str,
    preprocessing_quality: Mapping[str, Any],
    preprocessing_quality_sha256: str,
    derivation_version: str,
    functional_commit: str,
) -> dict[str, Any]:
    """
    Build the Stage 2.5 preprocessing manifest while
    checking all provenance links.

    The manifest cannot silently point to a config,
    source bundle, grid, or quality artifact whose hash
    disagrees with the supplied build inputs.
    """
    expected_identity = {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
    }

    normalized_config = (
        validate_preprocessing_config(
            preprocessing_config
        )
    )

    actual_config_sha = (
        globals()[
            "preprocessing_config_sha256"
        ](
            normalized_config
        )
    )

    provided_config_sha = (
        normalize_sha256(
            preprocessing_config_sha256,
            field_name=(
                "preprocessing config SHA-256"
            ),
        )
    )

    if (
        provided_config_sha
        != actual_config_sha
    ):
        raise ValueError(
            "preprocessing config hash does not "
            "match canonical config content."
        )

    normalized_source_hashes = (
        _normalize_hash_mapping(
            source_artifact_hashes,
            field_name=(
                "source artifact hashes"
            ),
        )
    )

    config_source_hashes = (
        normalized_config[
            "source_artifact_hashes"
        ]
    )

    if (
        normalized_source_hashes
        != config_source_hashes
    ):
        raise ValueError(
            "source artifact hashes do not match "
            "the preprocessing config."
        )

    upstream_sha = normalize_sha256(
        upstream_stage24_provenance_sha256,
        field_name=(
            "upstream Stage 2.4 provenance SHA-256"
        ),
    )

    grid_sha = normalize_sha256(
        common_grid_sha256,
        field_name="common-grid SHA-256",
    )

    quality_sha = normalize_sha256(
        preprocessing_quality_sha256,
        field_name=(
            "preprocessing quality SHA-256"
        ),
    )

    (
        first_grid_pc_time_ns,
        last_grid_pc_time_ns,
        grid_row_count,
    ) = _validate_common_grid_rows(
        rows=common_grid_rows,
        expected_identity=expected_identity,
        expected_config_sha256=(
            actual_config_sha
        ),
    )

    status = _validate_quality(
        preprocessing_quality=(
            preprocessing_quality
        ),
        expected_identity=expected_identity,
        expected_grid_row_count=(
            grid_row_count
        ),
    )

    normalized_derivation_version = (
        _require_nonempty_string(
            derivation_version,
            field_name="derivation_version",
        )
    )

    normalized_functional_commit = (
        _require_nonempty_string(
            functional_commit,
            field_name="functional commit",
        )
    )

    if (
        normalized_derivation_version
        != normalized_config[
            "derivation_version"
        ]
    ):
        raise ValueError(
            "manifest derivation version does not "
            "match preprocessing config."
        )

    if (
        normalized_functional_commit
        != normalized_config[
            "functional_commit"
        ]
    ):
        raise ValueError(
            "manifest functional commit does not "
            "match preprocessing config."
        )

    result = {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "status":
            status,
        "source_artifact_hashes":
            deepcopy(
                normalized_source_hashes
            ),
        "upstream_stage24_provenance_sha256":
            upstream_sha,
        "preprocessing_config_sha256":
            actual_config_sha,
        "common_grid_sha256":
            grid_sha,
        "preprocessing_quality_sha256":
            quality_sha,
        "first_grid_pc_time_ns":
            first_grid_pc_time_ns,
        "last_grid_pc_time_ns":
            last_grid_pc_time_ns,
        "grid_row_count":
            grid_row_count,
        "derivation_version":
            normalized_derivation_version,
        "functional_commit":
            normalized_functional_commit,
    }

    if (
        tuple(result.keys())
        != PREPROCESSING_MANIFEST_REQUIRED_FIELDS
    ):
        raise RuntimeError(
            "preprocessing manifest output does not "
            "match frozen schema order."
        )

    return result


def canonical_preprocessing_manifest_json(
    manifest: Mapping[str, Any],
) -> str:
    if not isinstance(
        manifest,
        Mapping,
    ):
        raise ValueError(
            "preprocessing manifest must be a mapping."
        )

    return json.dumps(
        deepcopy(
            dict(manifest)
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )


def preprocessing_manifest_sha256(
    manifest: Mapping[str, Any],
) -> str:
    canonical_json = (
        canonical_preprocessing_manifest_json(
            manifest
        )
    )

    return hashlib.sha256(
        canonical_json.encode(
            "utf-8"
        )
    ).hexdigest().upper()