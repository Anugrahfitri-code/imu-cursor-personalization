import csv
import json
from pathlib import Path

import pytest

from pc.experiment.tests.fixture_builder import (
    build_synthetic_session,
)
from pc.experiment.validator import validate_session


def _read_csv(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    return fieldnames, rows


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _read_manifest(
    session_dir: Path,
) -> dict[str, object]:
    return json.loads(
        (session_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )


def _write_manifest(
    session_dir: Path,
    manifest: dict[str, object],
) -> None:
    (session_dir / "manifest.json").write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_valid_synthetic_session_passes(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    report = validate_session(session_dir)

    assert report.is_valid
    assert report.issues == ()


def test_missing_required_file_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    (
        session_dir
        / "raw"
        / "trial_events.csv"
    ).unlink()

    report = validate_session(session_dir)

    assert not report.is_valid


def test_manifest_participant_mismatch_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "trial_events.csv"
    fieldnames, rows = _read_csv(path)

    rows[0]["participant_id"] = "SYNTHETIC_OTHER"

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_manifest_session_mismatch_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "cursor_samples.csv"
    fieldnames, rows = _read_csv(path)

    rows[0]["session_id"] = "SYNTHETIC_OTHER_SESSION"

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_invalid_condition_code_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "trial_events.csv"
    fieldnames, rows = _read_csv(path)

    rows[0]["condition_code"] = "INVALID"

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_duplicate_event_id_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "trial_events.csv"
    fieldnames, rows = _read_csv(path)

    rows[1]["event_id"] = rows[0]["event_id"]

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_duplicate_cursor_sample_id_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "cursor_samples.csv"
    fieldnames, rows = _read_csv(path)

    rows[1]["sample_id"] = rows[0]["sample_id"]

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_invalid_pc_time_ns_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "cursor_samples.csv"
    fieldnames, rows = _read_csv(path)

    rows[0]["pc_time_ns"] = "not-an-integer"

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_decreasing_cursor_time_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "cursor_samples.csv"
    fieldnames, rows = _read_csv(path)

    rows[1]["pc_time_ns"] = "1"

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_unknown_trial_reference_fails(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    path = session_dir / "raw" / "cursor_samples.csv"
    fieldnames, rows = _read_csv(path)

    rows[0]["trial_id"] = "UNKNOWN_TRIAL"

    _write_csv(path, fieldnames, rows)

    report = validate_session(session_dir)

    assert not report.is_valid


def test_open_session_is_not_valid_as_finalized_session(
    tmp_path,
):
    session_dir = build_synthetic_session(tmp_path)

    manifest = _read_manifest(session_dir)
    manifest["session_status"] = "open"

    _write_manifest(session_dir, manifest)

    report = validate_session(session_dir)

    assert not report.is_valid


@pytest.mark.parametrize("relative_path", [
    "raw/imu/imu.csv", "raw/imu/meta.txt",
    "raw/clock/clock_model.json", "raw/clock/sync_probes.csv",
])
@pytest.mark.parametrize("tamper", ["missing", "changed"])
def test_declared_source_evidence_must_exist_and_match_hash(tmp_path, relative_path, tamper):
    session_dir = build_synthetic_session(tmp_path)
    path = session_dir / relative_path
    if tamper == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"changed\n")
    report = validate_session(session_dir)
    assert not report.is_valid
    assert any(relative_path in issue.message for issue in report.issues)


def test_declared_supplemental_file_must_exist(tmp_path):
    session_dir = build_synthetic_session(tmp_path)
    manifest = _read_manifest(session_dir)
    manifest["files"] = [{"relative_path": "missing.bin", "sha256": "0" * 64, "role": "model"}]
    _write_manifest(session_dir, manifest)
    assert not validate_session(session_dir).is_valid


def test_source_reference_cannot_escape_through_symlink(tmp_path):
    session_dir = build_synthetic_session(tmp_path)
    evidence = session_dir / "raw/imu/imu.csv"
    outside = tmp_path / "external.csv"
    evidence.rename(outside)
    evidence.symlink_to(outside)
    assert not validate_session(session_dir).is_valid


def test_closed_session_cannot_be_only_headers(tmp_path):
    session_dir = build_synthetic_session(tmp_path)
    for relative_path in ("raw/trial_events.csv", "raw/cursor_samples.csv", "raw/calibration_events.csv"):
        path = session_dir / relative_path
        header, _ = _read_csv(path)
        _write_csv(path, header, [])
    assert not validate_session(session_dir).is_valid


def test_closed_calibration_only_development_session_is_structurally_valid(tmp_path):
    session_dir = build_synthetic_session(tmp_path)
    for relative_path in ("raw/trial_events.csv", "raw/cursor_samples.csv"):
        path = session_dir / relative_path
        header, _ = _read_csv(path)
        _write_csv(path, header, [])
    manifest = _read_manifest(session_dir)
    manifest["dataset_role"] = "development"
    manifest["condition_order"] = ["P2C", "L2C"]
    _write_manifest(session_dir, manifest)
    report = validate_session(session_dir)
    assert report.is_valid, report.issues


def test_observed_condition_must_be_declared_in_session_order(tmp_path):
    session_dir = build_synthetic_session(tmp_path)
    manifest = _read_manifest(session_dir)
    manifest["condition_order"] = ["P0"]
    _write_manifest(session_dir, manifest)
    assert not validate_session(session_dir).is_valid


def test_manifest_itself_cannot_escape_through_symlink(tmp_path):
    session_dir = build_synthetic_session(tmp_path)
    manifest = session_dir / "manifest.json"
    external = tmp_path / "external_manifest.json"
    manifest.rename(external)
    manifest.symlink_to(external)
    assert not validate_session(session_dir).is_valid
