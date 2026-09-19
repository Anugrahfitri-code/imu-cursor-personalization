import json
import re
from copy import deepcopy

import pytest

from pc.experiment.preprocessing.config import (
    preprocessing_config_sha256,
)

from pc.experiment.preprocessing.qualification import (
    qualify_preprocessing_candidates,
)

from pc.experiment.tests.test_stage25_builder import (
    ONE_MS,
    UPSTREAM_SHA,
    _builder_config,
    _records,
    _reference,
)


EXPECTED_BUNDLE_FIELDS = (
    "qualification_report",
    "qualification_report_sha256",
)


EXPECTED_REPORT_FIELDS = (
    "qualification_version",
    "participant_id",
    "session_id",
    "calibration_id",
    "upstream_stage24_provenance_sha256",
    "candidate_count",
    "candidate_results",
)


EXPECTED_CANDIDATE_RESULT_FIELDS = (
    "configuration_id",
    "configuration_role",
    "preprocessing_config_sha256",
    "build_status",
    "grid_row_count",
    "invalid_accel_row_count",
    "invalid_gyro_row_count",
    "invalid_sensor_row_count",
    "valid_supervision_count",
    "invalid_supervision_count",
    "gap_event_count",
    "max_observed_source_gap_ns",
    "active_motion_row_count",
    "common_grid_sha256",
    "preprocessing_quality_sha256",
    "preprocessing_manifest_sha256",
)


def _candidate(
    configuration_id,
    *,
    max_source_gap_ns,
):
    config = _builder_config()

    config["configuration_id"] = (
        configuration_id
    )

    config["configuration_role"] = (
        "CANDIDATE"
    )

    config["max_source_gap_ns"] = (
        max_source_gap_ns
    )

    return config


def _candidates():
    return [
        _candidate(
            "candidate-loose-gap",
            max_source_gap_ns=(
                20 * ONE_MS
            ),
        ),
        _candidate(
            "candidate-strict-gap",
            max_source_gap_ns=(
                5 * ONE_MS
            ),
        ),
    ]


def _qualify(
    *,
    records=None,
    reference=None,
    candidates=None,
    clock_quality_passed=True,
    upstream_sha=UPSTREAM_SHA,
    technical_errors=(),
):
    if records is None:
        records = _records()

    if reference is None:
        reference = _reference()

    if candidates is None:
        candidates = _candidates()

    return qualify_preprocessing_candidates(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        records=records,
        reference_trajectory=reference,
        candidate_configs=candidates,
        upstream_stage24_provenance_sha256=(
            upstream_sha
        ),
        upstream_clock_quality_passed=(
            clock_quality_passed
        ),
        technical_errors=technical_errors,
    )


def _candidate_result(
    report,
    configuration_id,
):
    for result in report[
        "candidate_results"
    ]:
        if (
            result["configuration_id"]
            == configuration_id
        ):
            return result

    raise AssertionError(
        "candidate result not found: "
        f"{configuration_id}"
    )


def test_qualification_returns_frozen_bundle_shape():
    result = _qualify()

    assert tuple(result.keys()) == (
        EXPECTED_BUNDLE_FIELDS
    )


def test_report_contains_identity_and_candidate_count():
    report = _qualify()[
        "qualification_report"
    ]

    assert tuple(report.keys()) == (
        EXPECTED_REPORT_FIELDS
    )

    assert (
        report["participant_id"]
        == "PTEST001"
    )

    assert (
        report["session_id"]
        == "STEST001"
    )

    assert (
        report["calibration_id"]
        == "CAL2C001"
    )

    assert (
        report[
            "upstream_stage24_provenance_sha256"
        ]
        == UPSTREAM_SHA
    )

    assert report["candidate_count"] == 2


def test_candidate_result_shape_is_explicit():
    report = _qualify()[
        "qualification_report"
    ]

    assert report[
        "candidate_results"
    ]

    assert all(
        tuple(result.keys())
        == EXPECTED_CANDIDATE_RESULT_FIELDS
        for result in report[
            "candidate_results"
        ]
    )


def test_candidate_results_are_sorted_by_configuration_id():
    candidates = list(
        reversed(
            _candidates()
        )
    )

    report = _qualify(
        candidates=candidates
    )[
        "qualification_report"
    ]

    assert [
        result["configuration_id"]
        for result in report[
            "candidate_results"
        ]
    ] == [
        "candidate-loose-gap",
        "candidate-strict-gap",
    ]


def test_candidate_hashes_bind_to_exact_configs():
    candidates = _candidates()

    report = _qualify(
        candidates=candidates
    )[
        "qualification_report"
    ]

    expected = {
        config["configuration_id"]:
            preprocessing_config_sha256(
                config
            )
        for config in candidates
    }

    for result in report[
        "candidate_results"
    ]:
        assert (
            result[
                "preprocessing_config_sha256"
            ]
            == expected[
                result[
                    "configuration_id"
                ]
            ]
        )


def test_candidate_artifact_hashes_are_uppercase_sha256():
    report = _qualify()[
        "qualification_report"
    ]

    for result in report[
        "candidate_results"
    ]:
        for field in (
            "preprocessing_config_sha256",
            "common_grid_sha256",
            "preprocessing_quality_sha256",
            "preprocessing_manifest_sha256",
        ):
            assert re.fullmatch(
                r"[0-9A-F]{64}",
                result[field],
            )


def test_stricter_gap_candidate_exposes_more_invalid_sensor_rows():
    report = _qualify()[
        "qualification_report"
    ]

    loose = _candidate_result(
        report,
        "candidate-loose-gap",
    )

    strict = _candidate_result(
        report,
        "candidate-strict-gap",
    )

    assert (
        strict[
            "invalid_sensor_row_count"
        ]
        > loose[
            "invalid_sensor_row_count"
        ]
    )


def test_task15_does_not_select_or_rank_a_candidate():
    report = _qualify()[
        "qualification_report"
    ]

    forbidden = {
        "winner",
        "selected_candidate",
        "selected_configuration",
        "rank",
        "ranking",
        "score",
    }

    assert not (
        forbidden
        & set(report.keys())
    )

    for result in report[
        "candidate_results"
    ]:
        assert not (
            forbidden
            & set(result.keys())
        )


def test_report_does_not_contain_evaluation_or_condition_fields():
    report = _qualify()[
        "qualification_report"
    ]

    serialized = json.dumps(
        report,
        sort_keys=True,
    )

    assert "evaluation_score" not in serialized
    assert "condition_id" not in serialized


def test_evaluation_and_condition_metadata_cannot_change_qualification():
    first_records = _records()

    second_records = [
        dict(row)
        for row in first_records
    ]

    for index, row in enumerate(
        second_records,
        start=1,
    ):
        row["evaluation_score"] = (
            999999.0 * index
        )

        row["condition_id"] = (
            "P2C"
            if index % 2
            else "L2C"
        )

    first = _qualify(
        records=first_records
    )

    second = _qualify(
        records=second_records
    )

    assert first == second


def test_receive_timestamp_cannot_change_qualification():
    first_records = _records()

    second_records = [
        dict(row)
        for row in first_records
    ]

    for index, row in enumerate(
        second_records,
        start=1,
    ):
        row["pc_receive_ts_ns"] = (
            8_000_000_000
            + index
        )

    first = _qualify(
        records=first_records
    )

    second = _qualify(
        records=second_records
    )

    assert first == second


def test_duplicate_configuration_id_fails_closed():
    first = _candidate(
        "duplicate-id",
        max_source_gap_ns=(
            20 * ONE_MS
        ),
    )

    second = _candidate(
        "duplicate-id",
        max_source_gap_ns=(
            5 * ONE_MS
        ),
    )

    with pytest.raises(
        ValueError,
        match="configuration",
    ):
        _qualify(
            candidates=[
                first,
                second,
            ]
        )


def test_final_role_is_not_accepted_by_qualification_harness():
    candidate = _candidate(
        "not-a-candidate",
        max_source_gap_ns=(
            20 * ONE_MS
        ),
    )

    candidate[
        "configuration_role"
    ] = "FINAL"

    with pytest.raises(
        ValueError,
        match="CANDIDATE",
    ):
        _qualify(
            candidates=[
                candidate
            ]
        )


def test_invalid_upstream_clock_quality_fails_closed():
    with pytest.raises(
        ValueError,
        match="clock",
    ):
        _qualify(
            clock_quality_passed=False
        )


def test_qualification_does_not_mutate_inputs():
    records = _records()
    reference = _reference()
    candidates = _candidates()

    records_before = deepcopy(
        records
    )

    reference_before = deepcopy(
        reference
    )

    candidates_before = deepcopy(
        candidates
    )

    _qualify(
        records=records,
        reference=reference,
        candidates=candidates,
    )

    assert records == records_before
    assert reference == reference_before
    assert candidates == candidates_before


def test_qualification_is_deterministic_and_hash_is_uppercase_sha256():
    first = _qualify()
    second = _qualify()

    assert first == second

    assert re.fullmatch(
        r"[0-9A-F]{64}",
        first[
            "qualification_report_sha256"
        ],
    )


def test_report_hash_changes_when_candidate_configuration_changes():
    first = _qualify()

    candidates = _candidates()

    candidates[0] = deepcopy(
        candidates[0]
    )

    candidates[0][
        "active_motion"
    ][
        "threshold"
    ] = 999.0

    second = _qualify(
        candidates=candidates
    )

    assert (
        first[
            "qualification_report_sha256"
        ]
        != second[
            "qualification_report_sha256"
        ]
    )