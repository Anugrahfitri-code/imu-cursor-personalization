import copy
import json
from pathlib import Path

from pc.experiment.manifest import (
    MANIFEST_REQUIRED_FIELDS,
    validate_manifest,
)


VALID_MANIFEST = {
    "schema_version": "1.0",
    "participant_id": "P7K4M2Q8",
    "session_id": "SYNTHETIC_SESSION_001",
    "dataset_role": "synthetic",
    "session_status": "closed",
    "experiment_protocol_version": "synthetic-v1",
    "condition_order": ["P0", "P2C", "L0", "L2C"],
    "functional_commit": "synthetic",
    "experiment_software_version": "stage2.1-test",
    "device": {
        "manufacturer": "synthetic",
        "model": "SM-A175F",
        "android_version": "16",
        "api_level": 36,
        "android_session_id": "SYNTHETIC_ANDROID_001",
    },
    "display": {
        "display_width_px": 1920,
        "display_height_px": 1080,
        "experiment_window_width_px": 1920,
        "experiment_window_height_px": 1080,
        "display_scale_factor": 1.0,
    },
    "android_evidence": {
        "imu_file": "raw/imu/imu.csv",
        "imu_sha256": "0" * 64,
        "android_metadata_file": "raw/imu/meta.txt",
        "android_metadata_sha256": "0" * 64,
    },
    "clock_evidence": {
        "clock_model_file": "raw/clock/clock_model.json",
        "clock_model_sha256": "0" * 64,
        "sync_probes_file": "raw/clock/sync_probes.csv",
        "sync_probes_sha256": "0" * 64,
    },
    "files": [],
}


def test_valid_manifest_has_no_errors():
    assert validate_manifest(copy.deepcopy(VALID_MANIFEST)) == []


def test_manifest_rejects_wrong_schema_version():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["schema_version"] = "9.9"

    errors = validate_manifest(manifest)

    assert errors


def test_manifest_rejects_unknown_dataset_role():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["dataset_role"] = "unknown"

    errors = validate_manifest(manifest)

    assert errors


def test_manifest_rejects_unknown_condition():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["condition_order"] = [
        "P0",
        "P2C",
        "L0",
        "INVALID",
    ]

    errors = validate_manifest(manifest)

    assert errors


def test_manifest_rejects_duplicate_condition_order():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["condition_order"] = [
        "P0",
        "P2C",
        "L0",
        "L0",
    ]

    errors = validate_manifest(manifest)

    assert errors


def test_manifest_requires_closed_or_open_status():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["session_status"] = "invalid"

    errors = validate_manifest(manifest)

    assert errors


def test_json_schema_required_fields_match_python_contract():
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "manifest.schema.json"
    )

    schema = json.loads(
        schema_path.read_text(encoding="utf-8")
    )

    schema_required = schema["required"]

    assert len(schema_required) == len(
        MANIFEST_REQUIRED_FIELDS
    )

    assert set(schema_required) == set(
        MANIFEST_REQUIRED_FIELDS
    )
