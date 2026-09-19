import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pc.experiment.preprocessing.schema import (
    PREPROCESSING_CONFIG_REQUIRED_FIELDS,
    PREPROCESSING_SCHEMA_VERSION,
)


SUPPORTED_CONFIGURATION_ROLES = (
    "CANDIDATE",
    "FINAL",
)


EXPECTED_SENSOR_TIMESTAMP_FIELD = (
    "pc_mapped_ts_ns"
)


EXPECTED_LABEL_LAG_CONVENTION = (
    "grid_label_pc_time_ns = "
    "grid_pc_time_ns - alignment_lag_ns"
)


_SHA256_PATTERN = re.compile(
    r"^[0-9A-Fa-f]{64}$"
)


def normalize_sha256(
    value: Any,
    *,
    field_name: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{field_name} must be a SHA-256 string."
        )

    if not _SHA256_PATTERN.fullmatch(
        value
    ):
        raise ValueError(
            f"{field_name} must be a 64-character "
            "SHA-256 hexadecimal string."
        )

    return value.upper()


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
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be an integer."
        ) from exc

    return parsed


def _parse_positive_float(
    value: Any,
    *,
    field_name: str,
) -> float:
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be positive numeric."
        )

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be positive numeric."
        ) from exc

    if (
        not math.isfinite(parsed)
        or parsed <= 0.0
    ):
        raise ValueError(
            f"{field_name} must be positive numeric."
        )

    return parsed


def _validate_source_artifacts(
    *,
    source_paths: Any,
    source_hashes: Any,
) -> tuple[dict[str, str], dict[str, str]]:
    if not isinstance(
        source_paths,
        Mapping,
    ):
        raise ValueError(
            "source artifact paths must be a mapping."
        )

    if not isinstance(
        source_hashes,
        Mapping,
    ):
        raise ValueError(
            "source artifact hashes must be a mapping."
        )

    if (
        set(source_paths.keys())
        != set(source_hashes.keys())
    ):
        raise ValueError(
            "source artifact path and source artifact "
            "hash keys must match exactly."
        )

    if not source_paths:
        raise ValueError(
            "source artifact mappings must not be empty."
        )

    required_sources = {"mapped_sensor_times", "reference_trajectory", "clock_model"}
    if not required_sources.issubset(source_paths):
        raise ValueError(
            "required source artifacts are missing: "
            f"{sorted(required_sources - set(source_paths))!r}."
        )

    normalized_paths: dict[str, str] = {}
    normalized_hashes: dict[str, str] = {}

    for key in sorted(
        source_paths.keys()
    ):
        if (
            not isinstance(key, str)
            or not key
        ):
            raise ValueError(
                "source artifact keys must be "
                "non-empty strings."
            )

        normalized_paths[key] = (
            _require_nonempty_string(
                source_paths[key],
                field_name=(
                    f"source artifact path {key!r}"
                ),
            )
        )

        normalized_hashes[key] = (
            normalize_sha256(
                source_hashes[key],
                field_name=(
                    f"source artifact SHA-256 {key!r}"
                ),
            )
        )

    return (
        normalized_paths,
        normalized_hashes,
    )


def _require_mapping(
    value: Any,
    *,
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise ValueError(
            f"{field_name} must be a mapping."
        )

    return deepcopy(
        dict(value)
    )


def validate_preprocessing_config(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate and normalize a Stage 2.5 preprocessing
    configuration without mutating the caller input.

    This validates reproducibility-contract mechanics.
    Candidate scientific values remain configuration
    values until the later selection decision.
    """
    if not isinstance(
        config,
        Mapping,
    ):
        raise ValueError(
            "preprocessing config must be a mapping."
        )

    missing_fields = [
        field
        for field in PREPROCESSING_CONFIG_REQUIRED_FIELDS
        if field not in config
    ]

    if missing_fields:
        raise ValueError(
            "preprocessing config missing required "
            f"field(s): {missing_fields!r}."
        )

    extra_fields = [
        field
        for field in config
        if field not in PREPROCESSING_CONFIG_REQUIRED_FIELDS
    ]

    if extra_fields:
        raise ValueError(
            "preprocessing config contains unsupported "
            f"field(s): {extra_fields!r}."
        )

    if (
        config["schema_version"]
        != PREPROCESSING_SCHEMA_VERSION
    ):
        raise ValueError(
            "preprocessing schema version mismatch."
        )

    configuration_id = (
        _require_nonempty_string(
            config["configuration_id"],
            field_name="configuration_id",
        )
    )

    configuration_role = config[
        "configuration_role"
    ]

    if (
        configuration_role
        not in SUPPORTED_CONFIGURATION_ROLES
    ):
        raise ValueError(
            "unsupported preprocessing configuration "
            f"role: {configuration_role!r}."
        )

    grid_interval_ns = _parse_integer(
        config["grid_interval_ns"],
        field_name="grid_interval_ns",
    )

    if grid_interval_ns <= 0:
        raise ValueError(
            "grid_interval_ns must be positive."
        )

    grid_frequency_hz = (
        _parse_positive_float(
            config["grid_frequency_hz"],
            field_name="grid_frequency_hz",
        )
    )

    if not math.isclose(grid_frequency_hz, 1_000_000_000 / grid_interval_ns,
                        rel_tol=1e-9, abs_tol=0.0):
        raise ValueError("grid frequency must equal 1e9 / grid_interval_ns.")

    grid_origin_rule = (
        _require_nonempty_string(
            config["grid_origin_rule"],
            field_name="grid_origin_rule",
        )
    )

    grid_domain_rule = (
        _require_nonempty_string(
            config["grid_domain_rule"],
            field_name="grid_domain_rule",
        )
    )

    sensor_timestamp_field = config[
        "sensor_timestamp_field"
    ]

    if (
        sensor_timestamp_field
        != EXPECTED_SENSOR_TIMESTAMP_FIELD
    ):
        raise ValueError(
            "sensor timestamp field must be "
            "'pc_mapped_ts_ns'."
        )

    reorder_policy = (
        _require_nonempty_string(
            config["reorder_policy"],
            field_name="reorder_policy",
        )
    )

    duplicate_policy = (
        _require_nonempty_string(
            config["duplicate_policy"],
            field_name="duplicate_policy",
        )
    )

    gap_policy = (
        _require_nonempty_string(
            config["gap_policy"],
            field_name="gap_policy",
        )
    )

    max_source_gap_ns = _parse_integer(
        config["max_source_gap_ns"],
        field_name="max_source_gap_ns",
    )

    if max_source_gap_ns < 0:
        raise ValueError(
            "max_source_gap_ns must be "
            "non-negative."
        )

    accel_resampling_method = (
        _require_nonempty_string(
            config[
                "accel_resampling_method"
            ],
            field_name=(
                "accel_resampling_method"
            ),
        )
    )

    gyro_resampling_method = (
        _require_nonempty_string(
            config[
                "gyro_resampling_method"
            ],
            field_name=(
                "gyro_resampling_method"
            ),
        )
    )

    axis_transform = _require_mapping(
        config["axis_transform"],
        field_name="axis_transform",
    )

    bias_correction = _require_mapping(
        config["bias_correction"],
        field_name="bias_correction",
    )

    low_pass_filter = _require_mapping(
        config["low_pass_filter"],
        field_name="low_pass_filter",
    )

    filter_frequency = _parse_positive_float(
        low_pass_filter.get("grid_frequency_hz"),
        field_name="low_pass_filter.grid_frequency_hz",
    )
    if not math.isclose(filter_frequency, grid_frequency_hz,
                        rel_tol=1e-9, abs_tol=0.0):
        raise ValueError("filter frequency must match the common grid frequency.")

    filter_reset_policy = (
        _require_nonempty_string(
            config["filter_reset_policy"],
            field_name="filter_reset_policy",
        )
    )

    active_motion = _require_mapping(
        config["active_motion"],
        field_name="active_motion",
    )

    padding_policy = _require_mapping(
        config["padding_policy"],
        field_name="padding_policy",
    )

    label_lag_convention = config[
        "label_lag_convention"
    ]

    if (
        label_lag_convention
        != EXPECTED_LABEL_LAG_CONVENTION
    ):
        raise ValueError(
            "label lag convention does not match "
            "the frozen Stage 2.4 sign convention."
        )

    alignment_lag_ns = _parse_integer(
        config["alignment_lag_ns"],
        field_name="alignment_lag_ns",
    )

    (
        source_artifact_paths,
        source_artifact_hashes,
    ) = _validate_source_artifacts(
        source_paths=(
            config["source_artifact_paths"]
        ),
        source_hashes=(
            config["source_artifact_hashes"]
        ),
    )

    derivation_version = (
        _require_nonempty_string(
            config["derivation_version"],
            field_name="derivation_version",
        )
    )

    functional_commit = (
        _require_nonempty_string(
            config["functional_commit"],
            field_name="functional commit",
        )
    )

    result = {
        "schema_version":
            PREPROCESSING_SCHEMA_VERSION,
        "configuration_id":
            configuration_id,
        "configuration_role":
            configuration_role,
        "grid_interval_ns":
            grid_interval_ns,
        "grid_frequency_hz":
            grid_frequency_hz,
        "grid_origin_rule":
            grid_origin_rule,
        "grid_domain_rule":
            grid_domain_rule,
        "sensor_timestamp_field":
            sensor_timestamp_field,
        "reorder_policy":
            reorder_policy,
        "duplicate_policy":
            duplicate_policy,
        "gap_policy":
            gap_policy,
        "max_source_gap_ns":
            max_source_gap_ns,
        "accel_resampling_method":
            accel_resampling_method,
        "gyro_resampling_method":
            gyro_resampling_method,
        "axis_transform":
            axis_transform,
        "bias_correction":
            bias_correction,
        "low_pass_filter":
            low_pass_filter,
        "filter_reset_policy":
            filter_reset_policy,
        "active_motion":
            active_motion,
        "padding_policy":
            padding_policy,
        "label_lag_convention":
            label_lag_convention,
        "alignment_lag_ns":
            alignment_lag_ns,
        "source_artifact_paths":
            source_artifact_paths,
        "source_artifact_hashes":
            source_artifact_hashes,
        "derivation_version":
            derivation_version,
        "functional_commit":
            functional_commit,
    }

    if (
        tuple(result.keys())
        != PREPROCESSING_CONFIG_REQUIRED_FIELDS
    ):
        raise RuntimeError(
            "preprocessing config output does not "
            "match frozen schema order."
        )

    return result


def canonical_preprocessing_config_json(
    config: Mapping[str, Any],
) -> str:
    normalized = (
        validate_preprocessing_config(
            config
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


def preprocessing_config_sha256(
    config: Mapping[str, Any],
) -> str:
    canonical_json = (
        canonical_preprocessing_config_json(
            config
        )
    )

    return hashlib.sha256(
        canonical_json.encode(
            "utf-8"
        )
    ).hexdigest().upper()
