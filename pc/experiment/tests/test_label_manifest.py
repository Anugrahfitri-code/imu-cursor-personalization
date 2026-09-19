import pytest

from pc.experiment.labels.schema import (
    LABEL_MANIFEST_REQUIRED_FIELDS,
    NATIVE_LABEL_COLUMNS,
)
from pc.experiment.labels.validator import (
    assess_label_build,
)
from pc.experiment.labels.manifest import (
    build_label_manifest,
)


RAW_IMU_SHA256 = "A" * 64
REFERENCE_SHA256 = "B" * 64
CLOCK_MODEL_SHA256 = "C" * 64
LABEL_CONFIG_SHA256 = "D" * 64


def _label_row(
    *,
    label_record_id,
    source_row_index,
    pc_mapped_ts_ns,
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


def _rows():
    return [
        _label_row(
            label_record_id="LBL000001",
            source_row_index=1,
            pc_mapped_ts_ns=200,
            label_status="VALID",
        ),
        _label_row(
            label_record_id="LBL000002",
            source_row_index=2,
            pc_mapped_ts_ns=300,
            label_status="OUTSIDE_REFERENCE",
        ),
        _label_row(
            label_record_id="LBL000003",
            source_row_index=3,
            pc_mapped_ts_ns=400,
            label_status="VALID",
        ),
    ]


def _assessment(rows):
    return assess_label_build(
        label_rows=rows,
        clock_model_present=True,
        clock_quality_passed=True,
        source_evidence_present=True,
        provenance_present=True,
    )


def _manifest(
    *,
    rows=None,
    raw_imu_sha256=RAW_IMU_SHA256,
):
    if rows is None:
        rows = _rows()

    assessment = _assessment(rows)

    return build_label_manifest(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        label_rows=rows,
        assessment=assessment,
        raw_imu_sha256=raw_imu_sha256,
        reference_trajectory_sha256=(
            REFERENCE_SHA256
        ),
        clock_model_sha256=(
            CLOCK_MODEL_SHA256
        ),
        label_config_sha256=(
            LABEL_CONFIG_SHA256
        ),
        derivation_version="labels-test-v1",
        functional_commit="TESTCOMMIT",
    )


def test_manifest_fields_are_exact():
    manifest = _manifest()

    assert tuple(manifest.keys()) == (
        LABEL_MANIFEST_REQUIRED_FIELDS
    )


def test_manifest_counts_match_label_rows():
    manifest = _manifest()

    assert manifest["mapped_record_count"] == 3
    assert manifest["valid_label_count"] == 2
    assert manifest["invalid_label_count"] == 1


def test_manifest_status_matches_assessment():
    manifest = _manifest()

    assert manifest["status"] == "VALID"


def test_manifest_hashes_are_preserved():
    manifest = _manifest()

    assert (
        manifest["raw_imu_sha256"]
        == RAW_IMU_SHA256
    )

    assert (
        manifest["reference_trajectory_sha256"]
        == REFERENCE_SHA256
    )

    assert (
        manifest["clock_model_sha256"]
        == CLOCK_MODEL_SHA256
    )

    assert (
        manifest["label_config_sha256"]
        == LABEL_CONFIG_SHA256
    )


def test_manifest_mapped_time_range_is_exact():
    manifest = _manifest()

    assert (
        manifest["first_mapped_pc_time_ns"]
        == 200
    )

    assert (
        manifest["last_mapped_pc_time_ns"]
        == 400
    )


def test_manifest_is_deterministic():
    first = _manifest()
    second = _manifest()

    assert first == second


def test_invalid_sha256_is_rejected():
    with pytest.raises(ValueError):
        _manifest(
            raw_imu_sha256="BAD"
        )


def test_manifest_identity_must_match_rows():
    rows = _rows()

    rows[0]["participant_id"] = "OTHER"

    with pytest.raises(ValueError):
        _manifest(rows=rows)