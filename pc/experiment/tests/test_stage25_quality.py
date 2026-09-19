from copy import deepcopy

import pytest

from pc.experiment.preprocessing.quality import (
    assess_preprocessing_quality,
)

from pc.experiment.preprocessing.schema import (
    PREPROCESSING_QUALITY_REQUIRED_FIELDS,
)


def _source_row(
    pc_mapped_ts_ns,
    *,
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
):
    return {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
    }


def _source_streams():
    return {
        "ACCEL": [
            _source_row(100),
            _source_row(110),
            _source_row(140),
        ],
        "GYRO": [
            _source_row(105),
            _source_row(115),
            _source_row(125),
        ],
    }


def _diagnostics():
    return {
        "source_counts": {
            "ACCEL": 5,
            "GYRO": 4,
        },
        "reorder_count":
            2,
        "duplicate_count":
            3,
        "invalid_timestamp_count":
            1,
    }


def _gap_events():
    return {
        "ACCEL": [
            {
                "event_type":
                    "BOUNDED_GAP",
                "observed_gap_ns":
                    30,
            },
        ],
        "GYRO": [
            {
                "event_type":
                    "BOUNDED_GAP",
                "observed_gap_ns":
                    20,
            },
        ],
    }


def _grid_row(
    *,
    grid_index,
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    accel_status="VALID",
    gyro_status="VALID",
    sensor_status="VALID",
    label_status="VALID",
):
    return {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "grid_index":
            grid_index,
        "accel_status":
            accel_status,
        "gyro_status":
            gyro_status,
        "sensor_status":
            sensor_status,
        "label_status":
            label_status,
    }


def _grid_rows():
    return [
        _grid_row(
            grid_index=0,
        ),
        _grid_row(
            grid_index=1,
            accel_status="GAP_EXCEEDED",
            sensor_status="INVALID_ACCEL",
            label_status="OUTSIDE_REFERENCE",
        ),
        _grid_row(
            grid_index=2,
            gyro_status="INVALID_SOURCE",
            sensor_status="INVALID_GYRO",
            label_status="UNRESOLVED_BOUNDARY",
        ),
        _grid_row(
            grid_index=3,
            accel_status="NO_SOURCE",
            gyro_status="NO_SOURCE",
            sensor_status="INVALID_BOTH",
            label_status="VALID",
        ),
    ]


def _assess(
    *,
    source_streams=None,
    source_diagnostics=None,
    gap_events=None,
    common_grid_rows=None,
    technical_errors=(),
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    derivation_version="stage2.5-test-v1",
):
    if source_streams is None:
        source_streams = _source_streams()

    if source_diagnostics is None:
        source_diagnostics = _diagnostics()

    if gap_events is None:
        gap_events = _gap_events()

    if common_grid_rows is None:
        common_grid_rows = _grid_rows()

    return assess_preprocessing_quality(
        participant_id=participant_id,
        session_id=session_id,
        calibration_id=calibration_id,
        source_streams=source_streams,
        source_diagnostics=source_diagnostics,
        gap_events=gap_events,
        common_grid_rows=common_grid_rows,
        technical_errors=technical_errors,
        derivation_version=derivation_version,
    )


def test_quality_output_matches_frozen_schema_order():
    result = _assess()

    assert tuple(result.keys()) == (
        PREPROCESSING_QUALITY_REQUIRED_FIELDS
    )


def test_source_diagnostic_counts_are_aggregated():
    result = _assess()

    assert result["accel_source_count"] == 5
    assert result["gyro_source_count"] == 4
    assert result["reorder_count"] == 2
    assert result["duplicate_count"] == 3

    assert (
        result["invalid_timestamp_count"]
        == 1
    )


def test_mapped_coverage_spans_both_sensor_families():
    result = _assess()

    assert (
        result["first_mapped_pc_time_ns"]
        == 100
    )

    assert (
        result["last_mapped_pc_time_ns"]
        == 140
    )


def test_max_observed_source_gap_comes_from_native_streams():
    result = _assess()

    assert (
        result["max_observed_source_gap_ns"]
        == 30
    )


def test_gap_event_count_aggregates_sensor_families():
    result = _assess()

    assert result["gap_event_count"] == 2


def test_invalid_grid_row_counts_are_separate():
    result = _assess()

    assert result["grid_row_count"] == 4

    assert (
        result["invalid_accel_row_count"]
        == 2
    )

    assert (
        result["invalid_gyro_row_count"]
        == 2
    )

    assert (
        result["invalid_sensor_row_count"]
        == 3
    )


def test_supervision_counts_are_independent_of_sensor_validity():
    result = _assess()

    assert (
        result["valid_supervision_count"]
        == 2
    )

    assert (
        result["invalid_supervision_count"]
        == 2
    )


def test_row_invalidity_does_not_make_build_technical_invalid():
    result = _assess(
        technical_errors=(),
    )

    assert result["invalid_sensor_row_count"] == 3

    assert result["status"] == "VALID"
    assert result["technical_errors"] == []


def test_technical_errors_make_build_technical_invalid():
    result = _assess(
        technical_errors=(
            "clock provenance mismatch",
            "common-grid artifact incomplete",
        ),
    )

    assert result["status"] == "TECHNICAL_INVALID"

    assert result["technical_errors"] == [
        "clock provenance mismatch",
        "common-grid artifact incomplete",
    ]


def test_empty_artifacts_can_still_emit_technical_invalid_quality():
    result = _assess(
        source_streams={
            "ACCEL": [],
            "GYRO": [],
        },
        source_diagnostics={
            "source_counts": {
                "ACCEL": 0,
                "GYRO": 0,
            },
            "reorder_count":
                0,
            "duplicate_count":
                0,
            "invalid_timestamp_count":
                0,
        },
        gap_events={
            "ACCEL": [],
            "GYRO": [],
        },
        common_grid_rows=[],
        technical_errors=(
            "upstream build failed",
        ),
    )

    assert result["status"] == "TECHNICAL_INVALID"

    assert (
        result["first_mapped_pc_time_ns"]
        is None
    )

    assert (
        result["last_mapped_pc_time_ns"]
        is None
    )

    assert (
        result["max_observed_source_gap_ns"]
        == 0
    )

    assert result["grid_row_count"] == 0
    assert result["gap_event_count"] == 0


def test_mixed_common_grid_participant_fails_closed():
    rows = _grid_rows()

    rows[1] = dict(
        rows[1]
    )

    rows[1]["participant_id"] = "OTHER"

    with pytest.raises(
        ValueError,
        match="participant",
    ):
        _assess(
            common_grid_rows=rows,
        )


def test_source_identity_mismatch_fails_closed():
    streams = _source_streams()

    streams = {
        family: [
            dict(row)
            for row in rows
        ]
        for family, rows in streams.items()
    }

    streams["GYRO"][0]["calibration_id"] = "OTHER"

    with pytest.raises(
        ValueError,
        match="calibration",
    ):
        _assess(
            source_streams=streams,
        )


def test_unknown_sensor_coverage_status_fails_closed():
    rows = _grid_rows()

    rows[0] = dict(
        rows[0]
    )

    rows[0]["accel_status"] = "BROKEN"

    with pytest.raises(
        ValueError,
        match="accel",
    ):
        _assess(
            common_grid_rows=rows,
        )


def test_unknown_combined_sensor_status_fails_closed():
    rows = _grid_rows()

    rows[0] = dict(
        rows[0]
    )

    rows[0]["sensor_status"] = "BROKEN"

    with pytest.raises(
        ValueError,
        match="sensor",
    ):
        _assess(
            common_grid_rows=rows,
        )


def test_unknown_label_status_fails_closed():
    rows = _grid_rows()

    rows[0] = dict(
        rows[0]
    )

    rows[0]["label_status"] = "BROKEN"

    with pytest.raises(
        ValueError,
        match="label",
    ):
        _assess(
            common_grid_rows=rows,
        )


def test_negative_diagnostic_count_fails_closed():
    diagnostics = _diagnostics()

    diagnostics["reorder_count"] = -1

    with pytest.raises(
        ValueError,
        match="count",
    ):
        _assess(
            source_diagnostics=diagnostics,
        )


def test_quality_assessment_does_not_mutate_inputs():
    streams = _source_streams()
    diagnostics = _diagnostics()
    gaps = _gap_events()
    rows = _grid_rows()

    streams_before = deepcopy(
        streams
    )

    diagnostics_before = deepcopy(
        diagnostics
    )

    gaps_before = deepcopy(
        gaps
    )

    rows_before = deepcopy(
        rows
    )

    _assess(
        source_streams=streams,
        source_diagnostics=diagnostics,
        gap_events=gaps,
        common_grid_rows=rows,
    )

    assert streams == streams_before
    assert diagnostics == diagnostics_before
    assert gaps == gaps_before
    assert rows == rows_before


def test_quality_assessment_is_deterministic():
    first = _assess()
    second = _assess()

    assert first == second