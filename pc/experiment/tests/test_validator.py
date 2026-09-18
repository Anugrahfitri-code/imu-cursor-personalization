import csv
import json
from pathlib import Path

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
