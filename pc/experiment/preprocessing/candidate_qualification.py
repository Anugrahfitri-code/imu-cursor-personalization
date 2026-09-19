import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from pc.experiment.preprocessing.builder import (
    build_stage25_preprocessing,
)

from pc.experiment.preprocessing.config import (
    normalize_sha256,
    validate_preprocessing_config,
)


QUALIFICATION_VERSION = (
    "stage2.5-candidate-qualification-v1.0"
)


SYNTHETIC_FIXTURE_ID = (
    "stage2.5-synthetic-preprocessing-qualification-v1"
)


COMPARED_DIMENSIONS = (
    "grid_interval_frequency",
    "causal_resampling",
    "maximum_source_gap",
    "duplicate_policy",
    "causal_filter_configuration",
    "axis_transform",
    "bias_correction",
    "active_motion_rule",
    "padding_policy",
)


_REPORT_FIELDS = (
    "qualification_version",
    "participant_id",
    "session_id",
    "calibration_id",
    "upstream_stage24_provenance_sha256",
    "evidence_set",
    "candidate_count",
    "candidate_results",
)


_CANDIDATE_FIELDS = (
    "configuration_id",
    "configuration_role",
    "configuration",
    "preprocessing_config_sha256",
    "build_status",
    "qualification_gates",
    "timing_coverage_diagnostics",
    "causality_result",
    "reproducibility_result",
    "acceptance_decision",
    "acceptance_reason",
    "common_grid_sha256",
    "preprocessing_quality_sha256",
    "preprocessing_manifest_sha256",
)


_BUNDLE_FIELDS = (
    "qualification_report",
    "qualification_report_sha256",
)


def _canonical_json(
    value: Any,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )


def _canonical_sha256(
    value: Any,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            value
        ).encode(
            "utf-8"
        )
    ).hexdigest().upper()


def _validate_candidates(
    candidate_configs: Sequence[
        Mapping[str, Any]
    ],
) -> list[
    tuple[
        dict[str, Any],
        dict[str, Any],
    ]
]:
    if isinstance(
        candidate_configs,
        (str, bytes),
    ):
        raise ValueError(
            "candidate configurations must be a sequence."
        )

    if not candidate_configs:
        raise ValueError(
            "candidate configurations must not be empty."
        )

    validated_candidates: list[
        tuple[
            dict[str, Any],
            dict[str, Any],
        ]
    ] = []

    seen_ids: set[str] = set()

    for index, supplied in enumerate(
        candidate_configs,
        start=1,
    ):
        if not isinstance(
            supplied,
            Mapping,
        ):
            raise ValueError(
                "candidate configuration "
                f"{index} must be a mapping."
            )

        normalized = (
            validate_preprocessing_config(
                supplied
            )
        )

        if (
            normalized[
                "configuration_role"
            ]
            != "CANDIDATE"
        ):
            raise ValueError(
                "candidate qualification accepts "
                "only CANDIDATE configurations."
            )

        configuration_id = (
            normalized[
                "configuration_id"
            ]
        )

        if configuration_id in seen_ids:
            raise ValueError(
                "duplicate preprocessing "
                "configuration_id: "
                f"{configuration_id!r}."
            )

        seen_ids.add(
            configuration_id
        )

        validated_candidates.append(
            (
                deepcopy(
                    dict(supplied)
                ),
                normalized,
            )
        )

    validated_candidates.sort(
        key=lambda item: (
            item[1][
                "configuration_id"
            ]
        )
    )

    return validated_candidates


def _active_motion_count(
    rows: Sequence[
        Mapping[str, Any]
    ],
) -> int:
    return sum(
        1
        for row in rows
        if row.get(
            "active_motion_flag"
        ) is True
    )


def _causality_result(
    config: Mapping[str, Any],
) -> str:
    causal = (
        config[
            "sensor_timestamp_field"
        ]
        == "pc_mapped_ts_ns"
        and config[
            "accel_resampling_method"
        ]
        == "PREVIOUS_SAMPLE_HOLD"
        and config[
            "gyro_resampling_method"
        ]
        == "PREVIOUS_SAMPLE_HOLD"
        and config[
            "low_pass_filter"
        ].get(
            "family"
        )
        == "ONE_POLE_IIR"
        and config[
            "filter_reset_policy"
        ]
        == config[
            "low_pass_filter"
        ].get(
            "reset_policy"
        )
    )

    return (
        "PASS"
        if causal
        else "FAIL"
    )


def _reproducibility_result(
    first_build: Mapping[str, Any],
    second_build: Mapping[str, Any],
) -> str:
    return (
        "PASS"
        if first_build == second_build
        else "FAIL"
    )


def _qualification_gates(
    *,
    quality: Mapping[str, Any],
    causality_result: str,
    reproducibility_result: str,
) -> dict[str, str]:
    return {
        "build_valid":
            (
                "PASS"
                if quality[
                    "status"
                ] == "VALID"
                else "FAIL"
            ),
        "causality":
            causality_result,
        "reproducibility":
            reproducibility_result,
        "supervision_available":
            (
                "PASS"
                if quality[
                    "valid_supervision_count"
                ] > 0
                else "FAIL"
            ),
    }


def _acceptance(
    gates: Mapping[str, str],
) -> tuple[str, str]:
    failed = [
        gate
        for gate, status in gates.items()
        if status != "PASS"
    ]

    if not failed:
        return (
            "ACCEPTED",
            (
                "All technical qualification gates "
                "passed on the synthetic engineering "
                "evidence set."
            ),
        )

    return (
        "REJECTED",
        (
            "Failed technical qualification gate(s): "
            + ", ".join(
                failed
            )
            + "."
        ),
    )


def _build_candidate_result(
    *,
    supplied_config: Mapping[str, Any],
    normalized_config: Mapping[str, Any],
    first_build: Mapping[str, Any],
    second_build: Mapping[str, Any],
) -> dict[str, Any]:
    quality = first_build[
        "preprocessing_quality"
    ]

    grid_rows = first_build[
        "common_grid_rows"
    ]

    causality = (
        _causality_result(
            normalized_config
        )
    )

    reproducibility = (
        _reproducibility_result(
            first_build,
            second_build,
        )
    )

    gates = _qualification_gates(
        quality=quality,
        causality_result=causality,
        reproducibility_result=(
            reproducibility
        ),
    )

    (
        acceptance_decision,
        acceptance_reason,
    ) = _acceptance(
        gates
    )

    diagnostics = {
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
            _active_motion_count(
                grid_rows
            ),
    }

    result = {
        "configuration_id":
            normalized_config[
                "configuration_id"
            ],
        "configuration_role":
            normalized_config[
                "configuration_role"
            ],
        "configuration":
            deepcopy(
                dict(
                    supplied_config
                )
            ),
        "preprocessing_config_sha256":
            first_build[
                "preprocessing_config_sha256"
            ],
        "build_status":
            quality[
                "status"
            ],
        "qualification_gates":
            gates,
        "timing_coverage_diagnostics":
            diagnostics,
        "causality_result":
            causality,
        "reproducibility_result":
            reproducibility,
        "acceptance_decision":
            acceptance_decision,
        "acceptance_reason":
            acceptance_reason,
        "common_grid_sha256":
            first_build[
                "common_grid_sha256"
            ],
        "preprocessing_quality_sha256":
            first_build[
                "preprocessing_quality_sha256"
            ],
        "preprocessing_manifest_sha256":
            first_build[
                "preprocessing_manifest_sha256"
            ],
    }

    if (
        tuple(result.keys())
        != _CANDIDATE_FIELDS
    ):
        raise RuntimeError(
            "candidate qualification result does not "
            "match canonical field order."
        )

    return result


def qualify_preprocessing_candidates(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    records: Sequence[
        Mapping[str, Any]
    ],
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
    Produce Stage 2.5 candidate qualification evidence.

    This stage evaluates technical admissibility only.
    It deliberately does not rank candidates or select a
    final preprocessing configuration.
    """
    if upstream_clock_quality_passed is not True:
        raise ValueError(
            "upstream clock quality gate did not pass."
        )

    upstream_sha = normalize_sha256(
        upstream_stage24_provenance_sha256,
        field_name=(
            "upstream Stage 2.4 provenance SHA-256"
        ),
    )

    candidates = _validate_candidates(
        candidate_configs
    )

    candidate_results: list[
        dict[str, Any]
    ] = []

    for (
        supplied_config,
        normalized_config,
    ) in candidates:
        first_build = (
            build_stage25_preprocessing(
                participant_id=participant_id,
                session_id=session_id,
                calibration_id=calibration_id,
                records=records,
                reference_trajectory=(
                    reference_trajectory
                ),
                preprocessing_config=(
                    normalized_config
                ),
                upstream_stage24_provenance_sha256=(
                    upstream_sha
                ),
                upstream_clock_quality_passed=True,
                technical_errors=(
                    technical_errors
                ),
            )
        )

        second_build = (
            build_stage25_preprocessing(
                participant_id=participant_id,
                session_id=session_id,
                calibration_id=calibration_id,
                records=records,
                reference_trajectory=(
                    reference_trajectory
                ),
                preprocessing_config=(
                    normalized_config
                ),
                upstream_stage24_provenance_sha256=(
                    upstream_sha
                ),
                upstream_clock_quality_passed=True,
                technical_errors=(
                    technical_errors
                ),
            )
        )

        candidate_results.append(
            _build_candidate_result(
                supplied_config=(
                    supplied_config
                ),
                normalized_config=(
                    normalized_config
                ),
                first_build=(
                    first_build
                ),
                second_build=(
                    second_build
                ),
            )
        )

    evidence_set = {
        "dataset_role":
            "synthetic",
        "real_participant_data_used":
            False,
        "fixture_id":
            SYNTHETIC_FIXTURE_ID,
        "compared_dimensions":
            list(
                COMPARED_DIMENSIONS
            ),
    }

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
            upstream_sha,
        "evidence_set":
            evidence_set,
        "candidate_count":
            len(
                candidate_results
            ),
        "candidate_results":
            candidate_results,
    }

    if (
        tuple(report.keys())
        != _REPORT_FIELDS
    ):
        raise RuntimeError(
            "candidate qualification report does not "
            "match canonical field order."
        )

    result = {
        "qualification_report":
            deepcopy(
                report
            ),
        "qualification_report_sha256":
            _canonical_sha256(
                report
            ),
    }

    if (
        tuple(result.keys())
        != _BUNDLE_FIELDS
    ):
        raise RuntimeError(
            "candidate qualification bundle does not "
            "match canonical field order."
        )

    return result


def write_candidate_qualification_evidence(
    *,
    qualification_bundle: Mapping[str, Any],
    output_directory: str | Path,
) -> dict[str, Any]:
    """
    Write deterministic candidate qualification evidence.

    Evidence files belong under ignored bench_data rather
    than the tracked source tree.
    """
    if not isinstance(
        qualification_bundle,
        Mapping,
    ):
        raise ValueError(
            "qualification bundle must be a mapping."
        )

    if (
        tuple(
            qualification_bundle.keys()
        )
        != _BUNDLE_FIELDS
    ):
        raise ValueError(
            "qualification bundle has unexpected fields."
        )

    report = qualification_bundle[
        "qualification_report"
    ]

    supplied_digest = normalize_sha256(
        qualification_bundle[
            "qualification_report_sha256"
        ],
        field_name=(
            "qualification report SHA-256"
        ),
    )

    actual_digest = _canonical_sha256(
        report
    )

    if supplied_digest != actual_digest:
        raise ValueError(
            "qualification report SHA-256 does not "
            "match report content."
        )

    output_path = Path(
        output_directory
    )

    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = (
        output_path
        / "qualification_report.json"
    )

    digest_path = (
        output_path
        / "qualification_report.sha256"
    )

    report_path.write_text(
        json.dumps(
            report,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    digest_path.write_text(
        actual_digest
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "qualification_report_path":
            str(
                report_path
            ),
        "qualification_digest_path":
            str(
                digest_path
            ),
        "qualification_report_sha256":
            actual_digest,
    }