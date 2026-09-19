import pytest

from pc.experiment.calibration.schema import (
    CALIBRATION_MANIFEST_REQUIRED_FIELDS,
)
from pc.experiment.calibration.provenance import (
    build_calibration_manifest,
    calibration_provenance_sha256,
)


RAW_IMU_SHA256 = "A" * 64
CLOCK_MODEL_SHA256 = "B" * 64
TRAJECTORY_CONFIG_SHA256 = "C" * 64


def _source_selection():
    return {
        "source_file": "raw/imu/imu.csv",
        "source_file_sha256": RAW_IMU_SHA256,
        "source_first_row": 10,
        "source_last_row": 250,
        "source_first_sequence": 100,
        "source_last_sequence": 340,
        "calibration_start_pc_ns":
            1_000_000_000_000,
        "calibration_end_pc_ns":
            1_040_000_000_000,
        "calibration_id": "CAL2C001",
    }


def _build_manifest(
    *,
    raw_imu_sha256=RAW_IMU_SHA256,
    clock_model_sha256=CLOCK_MODEL_SHA256,
    calibration_start_pc_ns=
        1_000_000_000_000,
    calibration_end_pc_ns=
        1_040_000_000_000,
    source_selection=None,
):
    if source_selection is None:
        source_selection = _source_selection()

    return build_calibration_manifest(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        calibration_start_pc_ns=
            calibration_start_pc_ns,
        calibration_end_pc_ns=
            calibration_end_pc_ns,
        cycle_count=2,
        reference_trajectory_file=(
            "raw/calibration/"
            "reference_trajectory.csv"
        ),
        trajectory_version="stage2.3-test-v1",
        trajectory_config_sha256=(
            TRAJECTORY_CONFIG_SHA256
        ),
        raw_imu_sha256=raw_imu_sha256,
        clock_model_sha256=(
            clock_model_sha256
        ),
        source_selection=source_selection,
    )


def test_calibration_manifest_contains_required_fields():
    manifest = _build_manifest()

    for field in (
        CALIBRATION_MANIFEST_REQUIRED_FIELDS
    ):
        assert field in manifest


def test_source_hashes_are_preserved():
    manifest = _build_manifest()

    assert manifest["raw_imu_sha256"] == (
        RAW_IMU_SHA256
    )

    assert manifest["clock_model_sha256"] == (
        CLOCK_MODEL_SHA256
    )

    assert (
        manifest["trajectory_config_sha256"]
        == TRAJECTORY_CONFIG_SHA256
    )


def test_source_selection_descriptor_is_recorded():
    selection = _source_selection()

    manifest = _build_manifest(
        source_selection=selection
    )

    assert manifest["source_selection"] == selection


def test_source_selection_records_exact_window():
    manifest = _build_manifest()

    selection = manifest["source_selection"]

    assert selection["source_first_row"] == 10
    assert selection["source_last_row"] == 250

    assert (
        selection["source_first_sequence"]
        == 100
    )

    assert (
        selection["source_last_sequence"]
        == 340
    )

    assert (
        selection["calibration_start_pc_ns"]
        == 1_000_000_000_000
    )

    assert (
        selection["calibration_end_pc_ns"]
        == 1_040_000_000_000
    )

    assert (
        selection["calibration_id"]
        == "CAL2C001"
    )


def test_same_inputs_produce_same_manifest():
    first = _build_manifest()
    second = _build_manifest()

    assert first == second


def test_same_inputs_produce_same_provenance_hash():
    first = calibration_provenance_sha256(
        _build_manifest()
    )

    second = calibration_provenance_sha256(
        _build_manifest()
    )

    assert first == second

    assert len(first) == 64

    int(first, 16)


def test_changed_raw_hash_changes_provenance():
    first = calibration_provenance_sha256(
        _build_manifest()
    )

    changed_selection = _source_selection()

    changed_selection[
        "source_file_sha256"
    ] = "D" * 64

    changed = calibration_provenance_sha256(
        _build_manifest(
            raw_imu_sha256="D" * 64,
            source_selection=changed_selection,
        )
    )

    assert first != changed


def test_changed_clock_hash_changes_provenance():
    first = calibration_provenance_sha256(
        _build_manifest()
    )

    changed = calibration_provenance_sha256(
        _build_manifest(
            clock_model_sha256="E" * 64
        )
    )

    assert first != changed


def test_changed_source_window_changes_provenance():
    first_selection = _source_selection()

    changed_selection = dict(
        first_selection
    )

    changed_selection[
        "source_last_row"
    ] = 249

    first = calibration_provenance_sha256(
        _build_manifest(
            source_selection=first_selection
        )
    )

    changed = calibration_provenance_sha256(
        _build_manifest(
            source_selection=changed_selection
        )
    )

    assert first != changed


def test_changed_calibration_window_changes_provenance():
    first_selection = _source_selection()

    changed_selection = dict(
        first_selection
    )

    changed_end_pc_ns = (
        1_040_000_000_000 - 1
    )

    changed_selection[
        "calibration_end_pc_ns"
    ] = changed_end_pc_ns

    first = calibration_provenance_sha256(
        _build_manifest(
            source_selection=first_selection
        )
    )

    changed = calibration_provenance_sha256(
        _build_manifest(
            calibration_end_pc_ns=(
                changed_end_pc_ns
            ),
            source_selection=changed_selection,
        )
    )

    assert first != changed


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_imu_sha256", ""),
        ("clock_model_sha256", ""),
    ],
)
def test_missing_required_source_hash_fails(
    field,
    value,
):
    kwargs = {
        "raw_imu_sha256": RAW_IMU_SHA256,
        "clock_model_sha256":
            CLOCK_MODEL_SHA256,
    }

    kwargs[field] = value

    with pytest.raises(ValueError):
        _build_manifest(**kwargs)


def test_invalid_sha256_length_fails():
    with pytest.raises(ValueError):
        _build_manifest(
            raw_imu_sha256="ABC123"
        )


def test_source_selection_hash_must_match_raw_hash():
    selection = _source_selection()

    selection["source_file_sha256"] = (
        "F" * 64
    )

    with pytest.raises(ValueError):
        _build_manifest(
            source_selection=selection
        )

def test_source_selection_calibration_id_must_match_manifest():
    selection = _source_selection()

    selection["calibration_id"] = "OTHER"

    with pytest.raises(ValueError):
        _build_manifest(
            source_selection=selection
        )


def test_source_selection_window_must_match_manifest():
    selection = _source_selection()

    selection[
        "calibration_end_pc_ns"
    ] -= 1

    with pytest.raises(ValueError):
        _build_manifest(
            source_selection=selection
        )
