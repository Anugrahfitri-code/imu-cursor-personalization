import re
from copy import deepcopy

import pytest

from pc.experiment.preprocessing.builder import (
    build_stage25_preprocessing,
)

from pc.experiment.preprocessing.schema import (
    COMMON_GRID_COLUMNS,
    PREPROCESSING_SCHEMA_VERSION,
)


ONE_MS = 1_000_000

HASH_A = "A" * 64
HASH_B = "B" * 64
HASH_C = "C" * 64
UPSTREAM_SHA = "D" * 64


EXPECTED_RESULT_FIELDS = (
    "preprocessing_config",
    "preprocessing_config_sha256",
    "common_grid_rows",
    "preprocessing_quality",
    "preprocessing_manifest",
    "common_grid_sha256",
    "preprocessing_quality_sha256",
    "preprocessing_manifest_sha256",
    "source_diagnostics",
    "gap_events",
)


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


def _mapped_row(
    *,
    sensor_family,
    source_row_index,
    time_ms,
    x,
    y,
    z,
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    pc_receive_ts_ns=None,
    evaluation_score=None,
    condition_id=None,
):
    mapped_time = (
        time_ms
        * ONE_MS
    )

    if pc_receive_ts_ns is None:
        pc_receive_ts_ns = (
            mapped_time
            + 50_000
        )

    return {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "sensor_family":
            sensor_family,
        "source_file":
            "raw/imu/synthetic.csv",
        "source_row_index":
            source_row_index,
        "sensor_sequence":
            source_row_index,
        "phone_sensor_ts_ns":
            mapped_time - 1_000,
        "pc_mapped_ts_ns":
            mapped_time,
        "pc_receive_ts_ns":
            pc_receive_ts_ns,
        "mapping_status":
            "MAPPED",
        "x":
            x,
        "y":
            y,
        "z":
            z,
        "evaluation_score":
            evaluation_score,
        "condition_id":
            condition_id,
    }


def _records():
    return [
        _mapped_row(
            sensor_family="ACCEL",
            source_row_index=1,
            time_ms=100,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _mapped_row(
            sensor_family="GYRO",
            source_row_index=2,
            time_ms=104,
            x=4.0,
            y=5.0,
            z=6.0,
        ),
        _mapped_row(
            sensor_family="ACCEL",
            source_row_index=3,
            time_ms=110,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _mapped_row(
            sensor_family="GYRO",
            source_row_index=4,
            time_ms=114,
            x=4.0,
            y=5.0,
            z=6.0,
        ),
        _mapped_row(
            sensor_family="ACCEL",
            source_row_index=5,
            time_ms=120,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _mapped_row(
            sensor_family="GYRO",
            source_row_index=6,
            time_ms=124,
            x=4.0,
            y=5.0,
            z=6.0,
        ),
        _mapped_row(
            sensor_family="ACCEL",
            source_row_index=7,
            time_ms=130,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _mapped_row(
            sensor_family="GYRO",
            source_row_index=8,
            time_ms=134,
            x=4.0,
            y=5.0,
            z=6.0,
        ),
    ]


def _reference_row(
    *,
    reference_sample_id,
    time_ms,
    relative_time_ns,
    ref_x_px,
    ref_y_px,
    ref_vx_px_s,
    ref_vy_px_s,
):
    return {
        "reference_sample_id":
            reference_sample_id,
        "participant_id":
            "PTEST001",
        "session_id":
            "STEST001",
        "calibration_id":
            "CAL2C001",
        "cycle_index":
            0,
        "sequence_id":
            "SEQ001",
        "segment_index":
            0,
        "direction_code":
            "RIGHT",
        "phase":
            "OUTBOUND",
        "pc_time_ns":
            time_ms * ONE_MS,
        "relative_time_ns":
            relative_time_ns,
        "ref_x_px":
            ref_x_px,
        "ref_y_px":
            ref_y_px,
        "ref_vx_px_s":
            ref_vx_px_s,
        "ref_vy_px_s":
            ref_vy_px_s,
        "speed_profile_code":
            "SYNTHETIC_LINEAR_TEST",
        "pause_flag":
            0,
        "trajectory_version":
            "stage2.5-builder-test-v1",
    }


def _reference():
    return [
        _reference_row(
            reference_sample_id="REF001",
            time_ms=100,
            relative_time_ns=0,
            ref_x_px=0.0,
            ref_y_px=10.0,
            ref_vx_px_s=20.0,
            ref_vy_px_s=30.0,
        ),
        _reference_row(
            reference_sample_id="REF002",
            time_ms=140,
            relative_time_ns=40 * ONE_MS,
            ref_x_px=40.0,
            ref_y_px=50.0,
            ref_vx_px_s=20.0,
            ref_vy_px_s=30.0,
        ),
    ]


def _builder_config():
    return {
        "schema_version":
            PREPROCESSING_SCHEMA_VERSION,
        "configuration_id":
            "stage25-builder-test",
        "configuration_role":
            "CANDIDATE",
        "grid_interval_ns":
            10 * ONE_MS,
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
            20 * ONE_MS,
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
                100 * ONE_MS,
            "window_end_pc_ns":
                114 * ONE_MS,
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
                0.1,
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
            0,
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
            "stage2.5-builder-test-v1",
        "functional_commit":
            "TESTCOMMIT",
    }


def _build(
    *,
    records=None,
    reference=None,
    config=None,
    clock_quality_passed=True,
    upstream_sha=UPSTREAM_SHA,
    technical_errors=(),
):
    if records is None:
        records = _records()

    if reference is None:
        reference = _reference()

    if config is None:
        config = _builder_config()

    return build_stage25_preprocessing(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        records=records,
        reference_trajectory=reference,
        preprocessing_config=config,
        upstream_stage24_provenance_sha256=(
            upstream_sha
        ),
        upstream_clock_quality_passed=(
            clock_quality_passed
        ),
        technical_errors=technical_errors,
    )


def test_builder_returns_complete_artifact_bundle():
    result = _build()

    assert tuple(result.keys()) == (
        EXPECTED_RESULT_FIELDS
    )


def test_common_grid_rows_match_frozen_schema_and_config_hash():
    result = _build()

    rows = result[
        "common_grid_rows"
    ]

    assert rows

    assert all(
        tuple(row.keys())
        == COMMON_GRID_COLUMNS
        for row in rows
    )

    expected_hash = result[
        "preprocessing_config_sha256"
    ]

    assert all(
        row[
            "preprocessing_config_sha256"
        ]
        == expected_hash
        for row in rows
    )


def test_integrated_grid_uses_post_bias_timestamp_intersection():
    result = _build()

    rows = result[
        "common_grid_rows"
    ]

    assert [
        row["grid_pc_time_ns"]
        for row in rows
    ] == [
        120 * ONE_MS,
        130 * ONE_MS,
    ]

    assert [
        row["grid_index"]
        for row in rows
    ] == [
        0,
        1,
    ]


def test_integrated_reference_labels_are_valid():
    result = _build()

    rows = result[
        "common_grid_rows"
    ]

    assert all(
        row["label_status"] == "VALID"
        for row in rows
    )

    assert all(
        row["sequence_id"] == "SEQ001"
        for row in rows
    )

    assert all(
        row["direction_code"] == "RIGHT"
        for row in rows
    )

    assert all(
        row["phase"] == "OUTBOUND"
        for row in rows
    )


def test_quality_and_manifest_are_provenance_bound():
    result = _build()

    quality = result[
        "preprocessing_quality"
    ]

    manifest = result[
        "preprocessing_manifest"
    ]

    assert quality["status"] == "VALID"

    assert (
        quality["grid_row_count"]
        == len(
            result["common_grid_rows"]
        )
    )

    assert manifest["status"] == "VALID"

    assert (
        manifest[
            "preprocessing_config_sha256"
        ]
        == result[
            "preprocessing_config_sha256"
        ]
    )

    assert (
        manifest["common_grid_sha256"]
        == result["common_grid_sha256"]
    )

    assert (
        manifest[
            "preprocessing_quality_sha256"
        ]
        == result[
            "preprocessing_quality_sha256"
        ]
    )

    assert (
        manifest[
            "upstream_stage24_provenance_sha256"
        ]
        == UPSTREAM_SHA
    )


def test_all_artifact_hashes_are_uppercase_sha256():
    result = _build()

    for field in (
        "preprocessing_config_sha256",
        "common_grid_sha256",
        "preprocessing_quality_sha256",
        "preprocessing_manifest_sha256",
    ):
        assert re.fullmatch(
            r"[0-9A-F]{64}",
            result[field],
        )


def test_same_source_and_config_rebuild_identically():
    first = _build()
    second = _build()

    assert first == second


def test_receive_timestamp_cannot_change_builder_output():
    first_records = _records()

    second_records = [
        dict(row)
        for row in first_records
    ]

    for index, row in enumerate(
        second_records,
        start=1,
    ):
        row["pc_receive_ts_ns"] = (
            9_000_000_000
            + index
        )

    first = _build(
        records=first_records
    )

    second = _build(
        records=second_records
    )

    assert first == second


def test_condition_and_evaluation_metadata_cannot_change_builder_output():
    first_records = _records()

    second_records = [
        dict(row)
        for row in first_records
    ]

    for index, row in enumerate(
        second_records,
        start=1,
    ):
        row["condition_id"] = (
            "P2C"
            if index % 2
            else "L2C"
        )

        row["evaluation_score"] = (
            999999.0 * index
        )

    first = _build(
        records=first_records
    )

    second = _build(
        records=second_records
    )

    assert first == second


def test_mixed_source_identity_fails_closed():
    records = [
        dict(row)
        for row in _records()
    ]

    records[3]["participant_id"] = "OTHER"

    with pytest.raises(
        ValueError,
        match="participant",
    ):
        _build(
            records=records
        )


def test_invalid_upstream_clock_quality_fails_closed():
    with pytest.raises(
        ValueError,
        match="clock",
    ):
        _build(
            clock_quality_passed=False
        )


def test_builder_does_not_mutate_inputs():
    records = _records()
    reference = _reference()
    config = _builder_config()

    records_before = deepcopy(
        records
    )

    reference_before = deepcopy(
        reference
    )

    config_before = deepcopy(
        config
    )

    _build(
        records=records,
        reference=reference,
        config=config,
    )

    assert records == records_before
    assert reference == reference_before
    assert config == config_before
