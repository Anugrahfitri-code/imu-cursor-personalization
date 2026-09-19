import csv
import json
from dataclasses import dataclass
from pathlib import Path

from pc.experiment.contracts import ALLOWED_CONDITIONS
from pc.experiment.csv_schema import (
    CSV_SCHEMAS,
    validate_header,
)
from pc.experiment.manifest import (
    EVIDENCE_FIELDS,
    load_manifest,
    validate_manifest,
)
from pc.experiment.session_hash import (
    HASH_MANIFEST_NAME,
    session_file_path,
    sha256_file,
    verify_session_hash_manifest,
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


REQUIRED_RAW_CSV_PATHS = (
    "raw/trial_events.csv",
    "raw/cursor_samples.csv",
    "raw/calibration_events.csv",
)


def _issue(
    issues: list[ValidationIssue],
    code: str,
    message: str,
) -> None:
    issues.append(
        ValidationIssue(
            code=code,
            message=message,
        )
    )


def _read_csv(
    path: Path,
    issues: list[ValidationIssue],
) -> tuple[list[str], list[dict[str, str]]] | None:
    try:
        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)

    except (OSError, csv.Error, UnicodeError) as exc:
        _issue(
            issues,
            "CSV_READ_ERROR",
            f"Could not read CSV {path}: {exc}",
        )
        return None

    return fieldnames, rows


def validate_session(
    session_dir: Path,
) -> ValidationReport:
    issues: list[ValidationIssue] = []

    # 1. Session directory exists.
    if not session_dir.exists():
        _issue(
            issues,
            "SESSION_DIR_MISSING",
            f"Session directory does not exist: {session_dir}",
        )
        return ValidationReport(tuple(issues))

    if not session_dir.is_dir():
        _issue(
            issues,
            "SESSION_PATH_NOT_DIRECTORY",
            f"Session path is not a directory: {session_dir}",
        )
        return ValidationReport(tuple(issues))

    # 2. Manifest exists and parses.
    try:
        manifest_path = session_file_path(session_dir, "manifest.json")
    except (OSError, ValueError) as exc:
        _issue(issues, "MANIFEST_PATH_INVALID", str(exc))
        return ValidationReport(tuple(issues))

    if not manifest_path.is_file():
        _issue(
            issues,
            "MANIFEST_MISSING",
            f"Manifest does not exist: {manifest_path}",
        )
        return ValidationReport(tuple(issues))

    try:
        manifest = load_manifest(manifest_path)

    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        _issue(
            issues,
            "MANIFEST_PARSE_ERROR",
            f"Manifest could not be parsed: {exc}",
        )
        return ValidationReport(tuple(issues))

    # 3. Manifest structural validation.
    manifest_errors = validate_manifest(manifest)

    for error in manifest_errors:
        _issue(
            issues,
            "MANIFEST_INVALID",
            error,
        )

    # A previously sealed session must not be silently rebaselined by finalize.
    hash_path = session_dir / HASH_MANIFEST_NAME
    if hash_path.exists() or hash_path.is_symlink():
        for error in verify_session_hash_manifest(session_dir):
            _issue(issues, "SESSION_HASH_INVALID", error)

    # Required nested evidence and supplemental declarations are content-bound.
    if not manifest_errors:
        references = []
        for section, pairs in EVIDENCE_FIELDS.items():
            for path_field, hash_field in pairs:
                references.append((manifest[section][path_field], manifest[section][hash_field]))
        references.extend((entry["relative_path"], entry["sha256"]) for entry in manifest["files"])
        for relative_path, expected_hash in references:
            try:
                path = session_file_path(session_dir, relative_path)
                if not path.is_file():
                    raise ValueError(f"Referenced evidence does not exist: {relative_path}")
                if sha256_file(path) != expected_hash.upper():
                    raise ValueError(f"SHA-256 mismatch for referenced evidence: {relative_path}")
            except (OSError, ValueError) as exc:
                _issue(issues, "EVIDENCE_INVALID", str(exc))

    # 4. Required raw CSV files exist.
    for relative_path in REQUIRED_RAW_CSV_PATHS:
        try:
            path = session_file_path(session_dir, relative_path)
        except (OSError, ValueError) as exc:
            _issue(issues, "REQUIRED_FILE_INVALID", str(exc))
            continue

        if not path.is_file():
            _issue(
                issues,
                "REQUIRED_FILE_MISSING",
                f"Required file does not exist: {relative_path}",
            )

    # Read contract CSV files that exist.
    csv_rows: dict[
        str,
        list[dict[str, str]],
    ] = {}

    for relative_path, expected_header in CSV_SCHEMAS.items():
        try:
            path = session_file_path(session_dir, relative_path)
        except (OSError, ValueError) as exc:
            _issue(issues, "CSV_PATH_INVALID", str(exc))
            continue

        if not path.is_file():
            continue

        loaded = _read_csv(path, issues)

        if loaded is None:
            continue

        actual_header, rows = loaded
        csv_rows[relative_path] = rows

        # 5. CSV headers exactly match contracts.
        header_errors = validate_header(
            actual_header,
            expected_header,
        )

        for error in header_errors:
            _issue(
                issues,
                "CSV_HEADER_MISMATCH",
                f"{relative_path}: {error}",
            )

    participant_id = manifest.get("participant_id")
    session_id = manifest.get("session_id")

    cross_file_paths = (
        "raw/trial_events.csv",
        "raw/cursor_samples.csv",
        "raw/calibration_events.csv",
    )

    # 6. participant_id consistency.
    for relative_path in cross_file_paths:
        rows = csv_rows.get(relative_path, [])

        for row_number, row in enumerate(
            rows,
            start=2,
        ):
            if row.get("participant_id") != participant_id:
                _issue(
                    issues,
                    "PARTICIPANT_ID_MISMATCH",
                    (
                        f"{relative_path}:{row_number}: "
                        "participant_id does not match manifest."
                    ),
                )

    # 7. session_id consistency.
    for relative_path in cross_file_paths:
        rows = csv_rows.get(relative_path, [])

        for row_number, row in enumerate(
            rows,
            start=2,
        ):
            if row.get("session_id") != session_id:
                _issue(
                    issues,
                    "SESSION_ID_MISMATCH",
                    (
                        f"{relative_path}:{row_number}: "
                        "session_id does not match manifest."
                    ),
                )

    # 8. Valid condition codes.
    for relative_path in cross_file_paths:
        rows = csv_rows.get(relative_path, [])

        for row_number, row in enumerate(
            rows,
            start=2,
        ):
            condition_code = row.get("condition_code")

            if condition_code not in ALLOWED_CONDITIONS:
                _issue(
                    issues,
                    "INVALID_CONDITION_CODE",
                    (
                        f"{relative_path}:{row_number}: "
                        f"invalid condition_code={condition_code!r}."
                    ),
                )
            elif isinstance(manifest.get("condition_order"), list) and condition_code not in manifest["condition_order"]:
                _issue(issues, "UNDECLARED_CONDITION", f"{relative_path}:{row_number}: condition is absent from condition_order: {condition_code}")

    trial_rows = csv_rows.get(
        "raw/trial_events.csv",
        [],
    )
    cursor_rows = csv_rows.get(
        "raw/cursor_samples.csv",
        [],
    )
    calibration_rows = csv_rows.get(
        "raw/calibration_events.csv",
        [],
    )
    if manifest.get("session_status") == "closed" and not (trial_rows or calibration_rows):
        _issue(issues, "EMPTY_SESSION", "Closed session requires trial or calibration event content.")

    # 9. Unique event_id.
    seen_event_ids: set[str] = set()

    for row_number, row in enumerate(
        trial_rows,
        start=2,
    ):
        event_id = row.get("event_id", "")

        if event_id in seen_event_ids:
            _issue(
                issues,
                "DUPLICATE_EVENT_ID",
                (
                    f"raw/trial_events.csv:{row_number}: "
                    f"duplicate event_id={event_id!r}."
                ),
            )
        else:
            seen_event_ids.add(event_id)

    # 10. Unique sample_id.
    seen_sample_ids: set[str] = set()

    for row_number, row in enumerate(
        cursor_rows,
        start=2,
    ):
        sample_id = row.get("sample_id", "")

        if sample_id in seen_sample_ids:
            _issue(
                issues,
                "DUPLICATE_SAMPLE_ID",
                (
                    f"raw/cursor_samples.csv:{row_number}: "
                    f"duplicate sample_id={sample_id!r}."
                ),
            )
        else:
            seen_sample_ids.add(sample_id)

    # 11. pc_time_ns parses as integer.
    timestamp_tables = (
        ("raw/trial_events.csv", trial_rows),
        ("raw/cursor_samples.csv", cursor_rows),
        (
            "raw/calibration_events.csv",
            calibration_rows,
        ),
    )

    parsed_cursor_times: list[
        tuple[int, int]
    ] = []

    for relative_path, rows in timestamp_tables:
        for row_number, row in enumerate(
            rows,
            start=2,
        ):
            value = row.get("pc_time_ns")

            try:
                parsed = int(value)  # type: ignore[arg-type]

            except (TypeError, ValueError):
                _issue(
                    issues,
                    "INVALID_PC_TIME_NS",
                    (
                        f"{relative_path}:{row_number}: "
                        f"pc_time_ns is not an integer: {value!r}."
                    ),
                )
                continue

            if relative_path == "raw/cursor_samples.csv":
                parsed_cursor_times.append(
                    (row_number, parsed)
                )

    # 12. Ordered cursor stream does not decrease.
    previous_time: int | None = None

    for row_number, current_time in parsed_cursor_times:
        if (
            previous_time is not None
            and current_time < previous_time
        ):
            _issue(
                issues,
                "CURSOR_TIME_DECREASE",
                (
                    f"raw/cursor_samples.csv:{row_number}: "
                    f"pc_time_ns decreased from "
                    f"{previous_time} to {current_time}."
                ),
            )

        previous_time = current_time

    # 13. Trial references resolve to known trial IDs.
    known_trial_ids = {
        row.get("trial_id", "")
        for row in trial_rows
        if row.get("trial_id", "")
    }

    for row_number, row in enumerate(
        cursor_rows,
        start=2,
    ):
        trial_id = row.get("trial_id", "")

        if trial_id not in known_trial_ids:
            _issue(
                issues,
                "UNKNOWN_TRIAL_REFERENCE",
                (
                    f"raw/cursor_samples.csv:{row_number}: "
                    f"unknown trial_id={trial_id!r}."
                ),
            )

    # 14. Finalized session must be closed.
    if manifest.get("session_status") != "closed":
        _issue(
            issues,
            "SESSION_NOT_CLOSED",
            (
                "Finalized-session validation requires "
                "session_status='closed'."
            ),
        )

    return ValidationReport(tuple(issues))
