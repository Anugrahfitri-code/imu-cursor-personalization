import re
from copy import deepcopy

import pytest

from pc.experiment.preprocessing.config import (
    canonical_preprocessing_config_json,
    preprocessing_config_sha256,
    validate_preprocessing_config,
)

from pc.experiment.preprocessing.schema import (
    PREPROCESSING_CONFIG_REQUIRED_FIELDS,
    PREPROCESSING_SCHEMA_VERSION,
)


HASH_A = "A" * 64
HASH_B = "B" * 64
HASH_C = "C" * 64


def _axis_family():
    return {
        "x": {
            "source_axis": "x",
            "sign": 1,
        },
        "y": {
            "source_axis": "y",
            "sign": 1,
        },
        "z": {
            "source_axis": "z",
            "sign": 1,
        },
    }


def _config(
    *,
    configuration_role="CANDIDATE",
):
    return {
        "schema_version":
            PREPROCESSING_SCHEMA_VERSION,
        "configuration_id":
            "stage25-test-candidate",
        "configuration_role":
            configuration_role,
        "grid_interval_ns":
            10_000_000,
        "grid_frequency_hz":
            100.0,
        "grid_origin_rule":
            "ALIGN_TO_ORIGIN",
        "grid_domain_rule":
            "INTERSECTION",
        "sensor_timestamp_field":
            "pc_mapped_ts_ns",
        "reorder_policy":
            "SORT_AND_REPORT",
        "duplicate_policy":
            "KEEP_FIRST",
        "gap_policy":
            "EXPLICIT_STATUS",
        "max_source_gap_ns":
            30_000_000,
        "accel_resampling_method":
            "PREVIOUS_SAMPLE_HOLD",
        "gyro_resampling_method":
            "PREVIOUS_SAMPLE_HOLD",
        "axis_transform": {
            "ACCEL":
                _axis_family(),
            "GYRO":
                _axis_family(),
        },
        "bias_correction": {
            "method":
                "MEAN_PC_WINDOW",
            "channels": [
                "x",
                "y",
                "z",
            ],
            "window_start_pc_ns":
                0,
            "window_end_pc_ns":
                20_000_000,
            "minimum_samples":
                2,
        },
        "low_pass_filter": {
            "family":
                "ONE_POLE_IIR",
            "order":
                1,
            "cutoff_hz":
                10.0,
            "grid_frequency_hz":
                100.0,
            "initialization":
                "FIRST_SAMPLE",
            "reset_policy":
                "EXPLICIT_BOUNDARIES",
        },
        "filter_reset_policy":
            "EXPLICIT_BOUNDARIES",
        "active_motion": {
            "method":
                "L2_NORM_THRESHOLD",
            "channels": [
                "x",
                "y",
            ],
            "threshold":
                5.0,
            "comparison":
                "GREATER_EQUAL",
        },
        "padding_policy": {
            "method":
                "REPEAT_FIRST",
            "padding_value":
                0.0,
        },
        "label_lag_convention":
            (
                "grid_label_pc_time_ns = "
                "grid_pc_time_ns - alignment_lag_ns"
            ),
        "alignment_lag_ns":
            5_000_000,
        "source_artifact_paths": {
            "mapped_sensor_times":
                "derived/calibration/mapped_sensor_times.csv",
            "reference_trajectory":
                "raw/calibration/reference_trajectory.csv",
            "clock_model":
                "artifacts/clock/clock_model.json",
        },
        "source_artifact_hashes": {
            "mapped_sensor_times":
                HASH_A,
            "reference_trajectory":
                HASH_B,
            "clock_model":
                HASH_C,
        },
        "derivation_version":
            "stage2.5-test-v1",
        "functional_commit":
            "TESTCOMMIT",
    }


def test_validated_config_matches_frozen_schema_order():
    result = validate_preprocessing_config(
        _config()
    )

    assert tuple(result.keys()) == (
        PREPROCESSING_CONFIG_REQUIRED_FIELDS
    )


def test_canonical_config_json_is_dictionary_order_independent():
    first = _config()

    second = dict(
        reversed(
            list(first.items())
        )
    )

    second[
        "source_artifact_hashes"
    ] = dict(
        reversed(
            list(
                first[
                    "source_artifact_hashes"
                ].items()
            )
        )
    )

    assert (
        canonical_preprocessing_config_json(first)
        == canonical_preprocessing_config_json(second)
    )


def test_config_sha256_is_deterministic_uppercase_hex():
    config = _config()

    first = preprocessing_config_sha256(
        config
    )

    second = preprocessing_config_sha256(
        config
    )

    assert first == second

    assert re.fullmatch(
        r"[0-9A-F]{64}",
        first,
    )


def test_config_hash_changes_when_configuration_changes():
    first = _config()
    second = _config()

    second["grid_interval_ns"] = (
        first["grid_interval_ns"]
        + 1
    )

    assert (
        preprocessing_config_sha256(first)
        != preprocessing_config_sha256(second)
    )


def test_schema_version_mismatch_fails_closed():
    config = _config()

    config["schema_version"] = "999.0"

    with pytest.raises(
        ValueError,
        match="schema",
    ):
        validate_preprocessing_config(
            config
        )


@pytest.mark.parametrize(
    "role",
    [
        "CANDIDATE",
        "FINAL",
    ],
)
def test_candidate_and_final_roles_are_supported(
    role,
):
    config = _config(
        configuration_role=role,
    )

    result = validate_preprocessing_config(
        config
    )

    assert (
        result["configuration_role"]
        == role
    )


def test_unknown_configuration_role_fails_closed():
    config = _config(
        configuration_role="MAGIC",
    )

    with pytest.raises(
        ValueError,
        match="role",
    ):
        validate_preprocessing_config(
            config
        )


def test_sensor_timestamp_field_must_use_mapped_pc_time():
    config = _config()

    config["sensor_timestamp_field"] = (
        "pc_receive_ts_ns"
    )

    with pytest.raises(
        ValueError,
        match="timestamp",
    ):
        validate_preprocessing_config(
            config
        )


def test_missing_required_field_fails_closed():
    config = _config()

    del config["grid_interval_ns"]

    with pytest.raises(
        ValueError,
        match="field",
    ):
        validate_preprocessing_config(
            config
        )


def test_source_path_and_hash_keys_must_match():
    config = _config()

    del config[
        "source_artifact_hashes"
    ]["clock_model"]

    with pytest.raises(
        ValueError,
        match="source",
    ):
        validate_preprocessing_config(
            config
        )


def test_invalid_source_artifact_sha256_fails_closed():
    config = _config()

    config[
        "source_artifact_hashes"
    ][
        "clock_model"
    ] = "NOT-A-SHA256"

    with pytest.raises(
        ValueError,
        match="SHA",
    ):
        validate_preprocessing_config(
            config
        )


def test_lowercase_source_hashes_are_normalized_without_mutating_input():
    config = _config()

    config[
        "source_artifact_hashes"
    ][
        "mapped_sensor_times"
    ] = HASH_A.lower()

    original = deepcopy(
        config
    )

    result = validate_preprocessing_config(
        config
    )

    assert (
        result[
            "source_artifact_hashes"
        ][
            "mapped_sensor_times"
        ]
        == HASH_A
    )

    assert config == original


def test_empty_functional_commit_fails_closed():
    config = _config()

    config["functional_commit"] = "   "

    with pytest.raises(
        ValueError,
        match="functional",
    ):
        validate_preprocessing_config(
            config
        )


def test_validation_is_deterministic():
    config = _config()

    first = validate_preprocessing_config(
        config
    )

    second = validate_preprocessing_config(
        config
    )

    assert first == second