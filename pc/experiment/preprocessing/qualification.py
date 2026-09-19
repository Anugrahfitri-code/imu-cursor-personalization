import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pc.experiment.preprocessing.builder import (
    build_stage25_preprocessing,
)

from pc.experiment.preprocessing.config import (
    validate_preprocessing_config,
)


QUALIFICATION_VERSION = (
    "stage2.5-candidate-qualification-v1"
)


_REPORT_FIELDS = (
    "qualification_version",
    "participant_id",
    "session_id",
    "calibration_id",
    "upstream_stage24_provenance_sha256",
    "candidate_count",
    "candidate_results",
)


_CANDIDATE_RESULT_FIELDS = (
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


_BUNDLE_FIELDS = (
    "qualification_report",
    "qualification_report_sha256",
)


def _canonical_sha256(
    value: Any,
) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode(
            "utf-8"
        )
    ).hexdigest().upper()


def _validate_candidate_configs(
    candidate_configs: Sequence[
        Mapping[str, Any]
    ],
) -> list[dict[str, Any]]:
    if isinstance(
        candidate_configs,
        (str, bytes),
    ):
        raise ValueError(
            "candidate configurations must be "
            "a sequence."
        )

    if not candidate_configs:
        raise ValueError(
            "candidate configurations must not "
            "be empty."
        )

    normalized: list[
        dict[str, Any]
    ] = []

    seen_configuration_ids: set[str] = set()

    for candidate_index, candidate in enumerate(
        candidate_configs,
        start=1,
    ):
        if not isinstance(
            candidate,
            Mapping,
        ):
            raise ValueError(
                "candidate configuration "
                f"{candidate_index} must be a mapping."
            )

        validated = (
            validate_preprocessing_config(
                candidate
            )
        )

        if (
            validated[
                "configuration_role"
            ]
            != "CANDIDATE"
        ):
            raise ValueError(
                "qualification harness accepts only "
                "CANDIDATE configurations."
            )

        configuration_id = validated[
            "configuration_id"
        ]

        if (
            configuration_id
            in seen_configuration_ids
        ):
            raise ValueError(
                "duplicate preprocessing "
                "configuration_id: "
                f"{configuration_id!r}."
            )

        seen_configuration_ids.add(
            configuration_id
        )

        normalized.append(
            validated
        )

    normalized.sort(
        key=lambda config: (
            config[
                "configuration_id"
            ]
        )
    )

    return normalized


def _count_active_motion_rows(
    common_grid_rows: Sequence[
        Mapping[str, Any]
    ],
) -> int:
    return sum(
        1
        for row in common_grid_rows
        if row.get(
            "active_motion_flag"
        ) is True
    )


def _candidate_result(
    *,
    config: Mapping[str, Any],
    build_result: Mapping[str, Any],
) -> dict[str, Any]:
    quality = build_result[
        "preprocessing_quality"
    ]

    common_grid_rows = build_result[
        "common_grid_rows"
    ]

    result = {
        "configuration_id":
            config[
                "configuration_id"
            ],
        "configuration_role":
            config[
                "configuration_role"
            ],
        "preprocessing_config_sha256":
            build_result[
                "preprocessing_config_sha256"
            ],
        "build_status":
            quality[
                "status"
            ],
        "grid_row_count":
            quality[
                "grid_row_count"
            ],
        "invalid_accel_row_count":
            quality[
                "invalid_accel_row_count"
            ],
        "invalid_gyro_row_count":
            quality[
                "invalid_gyro_row_count"
            ],
        "invalid_sensor_row_count":
            quality[
                "invalid_sensor_row_count"
            ],
        "valid_supervision_count":
            quality[
                "valid_supervision_count"
            ],
        "invalid_supervision_count":
            quality[
                "invalid_supervision_count"
            ],
        "gap_event_count":
            quality[
                "gap_event_count"
            ],
        "max_observed_source_gap_ns":
            quality[
                "max_observed_source_gap_ns"
            ],
        "active_motion_row_count":
            _count_active_motion_rows(
                common_grid_rows
            ),
        "common_grid_sha256":
            build_result[
                "common_grid_sha256"
            ],
        "preprocessing_quality_sha256":
            build_result[
                "preprocessing_quality_sha256"
            ],
        "preprocessing_manifest_sha256":
            build_result[
                "preprocessing_manifest_sha256"
            ],
    }

    if (
        tuple(result.keys())
        != _CANDIDATE_RESULT_FIELDS
    ):
        raise RuntimeError(
            "candidate qualification result does "
            "not match frozen field order."
        )

    return result


def qualify_preprocessing_candidates(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    records: Sequence[Mapping[str, Any]],
    reference_trajectory: Sequence[
        Mapping[str, Any]
    ],
    candidate_configs: Sequence[
        Mapping[str, Any]
    ],
    upstream_stage24_provenance_sha256: str,
    upstream_clock_quality_passed: bool,
    technical_errors: Sequence[Any] = (),
) -> dict[str, Any]:
    """
    Build deterministic engineering evidence for Stage 2.5
    preprocessing candidates.

    This function intentionally does not select, rank,
    score, or name a winner. Candidate selection belongs
    to the later explicit selection-decision stage.

    Evaluation outcomes and experiment condition metadata
    are not inputs to candidate qualification logic.
    """
    if upstream_clock_quality_passed is not True:
        raise ValueError(
            "upstream clock quality gate did not pass."
        )

    normalized_candidates = (
        _validate_candidate_configs(
            candidate_configs
        )
    )

    candidate_results: list[
        dict[str, Any]
    ] = []

    for config in normalized_candidates:
        build_result = (
            build_stage25_preprocessing(
                participant_id=participant_id,
                session_id=session_id,
                calibration_id=calibration_id,
                records=records,
                reference_trajectory=(
                    reference_trajectory
                ),
                preprocessing_config=config,
                upstream_stage24_provenance_sha256=(
                    upstream_stage24_provenance_sha256
                ),
                upstream_clock_quality_passed=True,
                technical_errors=(
                    technical_errors
                ),
            )
        )

        candidate_results.append(
            _candidate_result(
                config=config,
                build_result=build_result,
            )
        )

    report = {
        "qualification_version":
            QUALIFICATION_VERSION,
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "upstream_stage24_provenance_sha256":
            upstream_stage24_provenance_sha256,
        "candidate_count":
            len(candidate_results),
        "candidate_results":
            candidate_results,
    }

    if (
        tuple(report.keys())
        != _REPORT_FIELDS
    ):
        raise RuntimeError(
            "qualification report does not match "
            "frozen field order."
        )

    report_sha256 = (
        _canonical_sha256(
            report
        )
    )

    result = {
        "qualification_report":
            deepcopy(
                report
            ),
        "qualification_report_sha256":
            report_sha256,
    }

    if (
        tuple(result.keys())
        != _BUNDLE_FIELDS
    ):
        raise RuntimeError(
            "qualification bundle does not match "
            "frozen field order."
        )

    return result