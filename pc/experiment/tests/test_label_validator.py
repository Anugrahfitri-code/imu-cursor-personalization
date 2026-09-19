from copy import deepcopy

from pc.experiment.labels.schema import (
    NATIVE_LABEL_COLUMNS,
)
from pc.experiment.labels.validator import (
    assess_label_build,
)


def _label_row(
    *,
    label_record_id="LBL000001",
    source_row_index=1,
    pc_mapped_ts_ns=200,
    label_status="VALID",
):
    valid = label_status == "VALID"

    row = {
        "label_record_id":
            label_record_id,
        "participant_id":
            "PTEST001",
        "session_id":
            "STEST001",
        "calibration_id":
            "CAL2C001",
        "source_file":
            "raw/imu/imu.csv",
        "source_row_index":
            source_row_index,
        "phone_sensor_ts_ns":
            1_000 + source_row_index,
        "pc_mapped_ts_ns":
            pc_mapped_ts_ns,
        "alignment_lag_ns":
            100,
        "label_pc_time_ns":
            pc_mapped_ts_ns - 100,
        "sequence_id":
            "C01_D01" if valid else None,
        "direction_code":
            "RIGHT" if valid else None,
        "phase":
            "OUTBOUND" if valid else None,
        "ref_x_px":
            10.0 if valid else None,
        "ref_y_px":
            20.0 if valid else None,
        "ref_vx_px_s":
            1.0 if valid else None,
        "ref_vy_px_s":
            2.0 if valid else None,
        "label_status":
            label_status,
        "derivation_version":
            "labels-test-v1",
    }

    assert tuple(row.keys()) == (
        NATIVE_LABEL_COLUMNS
    )

    return row


def _assess(
    rows,
    *,
    clock_model_present=True,
    clock_quality_passed=True,
    source_evidence_present=True,
    provenance_present=True,
):
    return assess_label_build(
        label_rows=rows,
        clock_model_present=clock_model_present,
        clock_quality_passed=clock_quality_passed,
        source_evidence_present=(
            source_evidence_present
        ),
        provenance_present=provenance_present,
    )


def test_valid_build_passes():
    result = _assess(
        [_label_row()]
    )

    assert result["status"] == "VALID"
    assert result["mapped_record_count"] == 1
    assert result["valid_label_count"] == 1
    assert result["invalid_label_count"] == 0
    assert result["technical_errors"] == []


def test_row_level_invalid_labels_are_counted():
    rows = [
        _label_row(
            label_record_id="LBL000001",
            source_row_index=1,
            label_status="VALID",
        ),
        _label_row(
            label_record_id="LBL000002",
            source_row_index=2,
            label_status="OUTSIDE_REFERENCE",
        ),
        _label_row(
            label_record_id="LBL000003",
            source_row_index=3,
            label_status="UNRESOLVED_BOUNDARY",
        ),
    ]

    result = _assess(rows)

    assert result["status"] == "VALID"
    assert result["mapped_record_count"] == 3
    assert result["valid_label_count"] == 1
    assert result["invalid_label_count"] == 2


def test_invalid_rows_do_not_enter_valid_supervision():
    rows = [
        _label_row(
            label_record_id="LBL000001",
            label_status="VALID",
        ),
        _label_row(
            label_record_id="LBL000002",
            source_row_index=2,
            label_status="OUTSIDE_REFERENCE",
        ),
    ]

    result = _assess(rows)

    valid_ids = [
        row["label_record_id"]
        for row in result["valid_labels"]
    ]

    assert valid_ids == [
        "LBL000001"
    ]


def test_zero_valid_labels_is_technical_invalid():
    rows = [
        _label_row(
            label_status="OUTSIDE_REFERENCE"
        )
    ]

    result = _assess(rows)

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        "ZERO_VALID_LABELS"
        in result["technical_errors"]
    )


def test_missing_clock_model_is_technical_invalid():
    result = _assess(
        [_label_row()],
        clock_model_present=False,
    )

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        "MISSING_CLOCK_MODEL"
        in result["technical_errors"]
    )


def test_invalid_clock_gate_is_technical_invalid():
    result = _assess(
        [_label_row()],
        clock_quality_passed=False,
    )

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        "CLOCK_QUALITY_FAILED"
        in result["technical_errors"]
    )


def test_missing_source_evidence_is_technical_invalid():
    result = _assess(
        [_label_row()],
        source_evidence_present=False,
    )

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        "MISSING_SOURCE_EVIDENCE"
        in result["technical_errors"]
    )


def test_missing_provenance_is_technical_invalid():
    result = _assess(
        [_label_row()],
        provenance_present=False,
    )

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        "MISSING_PROVENANCE"
        in result["technical_errors"]
    )


def test_unknown_label_status_is_technical_invalid():
    row = _label_row()

    row["label_status"] = "UNKNOWN"

    result = _assess([row])

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        "INVALID_LABEL_STATUS"
        in result["technical_errors"]
    )


def test_mixed_label_identity_is_technical_invalid():
    rows = [
        _label_row(
            label_record_id="LBL000001",
        ),
        _label_row(
            label_record_id="LBL000002",
            source_row_index=2,
        ),
    ]

    rows[1]["calibration_id"] = "OTHER"

    result = _assess(rows)

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        "LABEL_IDENTITY_MISMATCH"
        in result["technical_errors"]
    )