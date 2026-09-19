from collections.abc import Mapping, Sequence
from typing import Any

from pc.experiment.labels.schema import (
    LABEL_STATUSES,
    NATIVE_LABEL_COLUMNS,
)


def assess_label_build(
    *,
    label_rows: Sequence[Mapping[str, Any]],
    clock_model_present: bool,
    clock_quality_passed: bool,
    source_evidence_present: bool,
    provenance_present: bool,
) -> dict[str, object]:
    """
    Assess whether a label build is technically usable.

    Row-level label invalidity is distinct from build-level
    technical invalidity.

    OUTSIDE_REFERENCE and UNRESOLVED_BOUNDARY are legitimate
    row-level statuses and are excluded from valid
    supervision. They do not, by themselves, invalidate the
    whole build as long as at least one VALID label remains.
    """
    technical_errors: list[str] = []

    if not clock_model_present:
        technical_errors.append(
            "MISSING_CLOCK_MODEL"
        )

    if not clock_quality_passed:
        technical_errors.append(
            "CLOCK_QUALITY_FAILED"
        )

    if not source_evidence_present:
        technical_errors.append(
            "MISSING_SOURCE_EVIDENCE"
        )

    if not provenance_present:
        technical_errors.append(
            "MISSING_PROVENANCE"
        )

    valid_labels: list[Mapping[str, Any]] = []

    expected_identity: tuple[
        Any,
        Any,
        Any,
    ] | None = None

    identity_mismatch = False
    invalid_status_found = False
    schema_problem_found = False

    for row in label_rows:
        if (
            tuple(row.keys())
            != NATIVE_LABEL_COLUMNS
        ):
            schema_problem_found = True

        participant_id = row.get(
            "participant_id"
        )

        session_id = row.get(
            "session_id"
        )

        calibration_id = row.get(
            "calibration_id"
        )

        identity = (
            participant_id,
            session_id,
            calibration_id,
        )

        if expected_identity is None:
            expected_identity = identity
        elif identity != expected_identity:
            identity_mismatch = True

        label_status = row.get(
            "label_status"
        )

        if label_status not in LABEL_STATUSES:
            invalid_status_found = True
            continue

        if label_status == "VALID":
            valid_labels.append(row)

    if schema_problem_found:
        technical_errors.append(
            "INVALID_LABEL_SCHEMA"
        )

    if invalid_status_found:
        technical_errors.append(
            "INVALID_LABEL_STATUS"
        )

    if identity_mismatch:
        technical_errors.append(
            "LABEL_IDENTITY_MISMATCH"
        )

    mapped_record_count = len(label_rows)

    valid_label_count = len(
        valid_labels
    )

    invalid_label_count = (
        mapped_record_count
        - valid_label_count
    )

    if valid_label_count == 0:
        technical_errors.append(
            "ZERO_VALID_LABELS"
        )

    status = (
        "VALID"
        if not technical_errors
        else "TECHNICAL_INVALID"
    )

    return {
        "status":
            status,
        "mapped_record_count":
            mapped_record_count,
        "valid_label_count":
            valid_label_count,
        "invalid_label_count":
            invalid_label_count,
        "valid_labels":
            list(valid_labels),
        "technical_errors":
            technical_errors,
    }