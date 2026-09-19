import copy
import json
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("field", MANIFEST_REQUIRED_FIELDS)
def test_required_manifest_values_cannot_be_null(field):
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest[field] = None
    assert validate_manifest(manifest)


@pytest.mark.parametrize("section,field", [
    ("device", "model"), ("device", "api_level"),
    ("display", "display_width_px"), ("display", "display_scale_factor"),
    ("android_evidence", "imu_file"), ("android_evidence", "imu_sha256"),
    ("clock_evidence", "clock_model_file"), ("clock_evidence", "sync_probes_sha256"),
])
def test_nested_required_evidence_cannot_be_missing(section, field):
    manifest = copy.deepcopy(VALID_MANIFEST)
    del manifest[section][field]
    assert validate_manifest(manifest)


@pytest.mark.parametrize("section,field,value", [
    ("device", "api_level", True),
    ("display", "display_width_px", "1920"),
    ("display", "display_scale_factor", 0),
    ("display", "display_scale_factor", float("nan")),
    ("android_evidence", "imu_file", "../outside.csv"),
    ("android_evidence", "imu_file", "/outside.csv"),
    ("android_evidence", "imu_file", "C:/outside.csv"),
    ("android_evidence", "imu_file", "manifest.json"),
    ("clock_evidence", "clock_model_sha256", "not-a-hash"),
])
def test_manifest_rejects_invalid_nested_values(section, field, value):
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest[section][field] = value
    assert validate_manifest(manifest)


@pytest.mark.parametrize("files", [
    ["raw/imu/imu.csv"], [{}],
    [{"relative_path": "../outside", "sha256": "0" * 64, "role": "evidence"}],
    [{"relative_path": "raw/imu/imu.csv", "sha256": "bad", "role": "evidence"}],
    [{"relative_path": "raw/imu/imu.csv", "sha256": "0" * 64, "role": ""}],
])
def test_manifest_validates_declared_file_entries(files):
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["files"] = files
    assert validate_manifest(manifest)


def test_closed_session_requires_usable_condition_order():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["condition_order"] = []
    assert validate_manifest(manifest)
    manifest["session_status"] = "open"
    assert validate_manifest(manifest) == []


def test_distinct_required_sources_cannot_alias_one_file():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["clock_evidence"]["clock_model_file"] = manifest["android_evidence"]["imu_file"]
    assert validate_manifest(manifest)


def test_python_rejects_unknown_top_level_field_like_schema():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["unrecognized_typo"] = "value"
    assert validate_manifest(manifest)


def test_integral_json_numbers_are_accepted_for_integer_metadata():
    manifest = copy.deepcopy(VALID_MANIFEST)
    manifest["device"]["api_level"] = 36.0
    manifest["display"]["display_width_px"] = 1920.0
    assert validate_manifest(manifest) == []
