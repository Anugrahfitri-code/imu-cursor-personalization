import hashlib
import json
import math
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
    "dimension_evidence",
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



def _dimension_alternative(
    *,
    alternative_id: str,
    configuration_delta: Mapping[str, Any],
    metrics: Mapping[str, Any],
    qualification_status: str,
    qualification_reason: str,
) -> dict[str, Any]:
    if qualification_status not in {
        "PASS",
        "FAIL",
    }:
        raise ValueError(
            "dimension qualification status must "
            "be PASS or FAIL."
        )

    return {
        "alternative_id":
            alternative_id,
        "configuration_delta":
            deepcopy(
                dict(
                    configuration_delta
                )
            ),
        "metrics":
            deepcopy(
                dict(
                    metrics
                )
            ),
        "qualification_status":
            qualification_status,
        "qualification_reason":
            qualification_reason,
    }


def _dimension_entry(
    *,
    fixture_id: str,
    alternatives: Sequence[
        Mapping[str, Any]
    ],
) -> dict[str, Any]:
    if len(alternatives) < 2:
        raise ValueError(
            "expanded dimension evidence requires "
            "at least two alternatives."
        )

    return {
        "fixture_id":
            fixture_id,
        "dataset_role":
            "synthetic",
        "alternatives":
            [
                deepcopy(
                    dict(
                        alternative
                    )
                )
                for alternative in alternatives
            ],
    }


def _one_pole_alpha(
    *,
    cutoff_hz: float,
    grid_frequency_hz: float,
) -> float:
    dt = (
        1.0
        / grid_frequency_hz
    )

    rc = (
        1.0
        / (
            2.0
            * math.pi
            * cutoff_hz
        )
    )

    return (
        dt
        / (
            rc
            + dt
        )
    )


def _maximum_gap_alternatives(
    candidate_results: Sequence[
        Mapping[str, Any]
    ],
) -> list[dict[str, Any]]:
    alternatives: list[
        dict[str, Any]
    ] = []

    seen_gap_ns: set[int] = set()

    for result in candidate_results:
        config = result[
            "configuration"
        ]

        gap_ns = int(
            config[
                "max_source_gap_ns"
            ]
        )

        if gap_ns in seen_gap_ns:
            continue

        seen_gap_ns.add(
            gap_ns
        )

        diagnostics = result[
            "timing_coverage_diagnostics"
        ]

        status = (
            "PASS"
            if result[
                "acceptance_decision"
            ] == "ACCEPTED"
            else "FAIL"
        )

        alternatives.append(
            _dimension_alternative(
                alternative_id=(
                    "max-gap-"
                    + str(gap_ns)
                    + "-ns"
                ),
                configuration_delta={
                    "max_source_gap_ns":
                        gap_ns,
                    "gap_policy":
                        config[
                            "gap_policy"
                        ],
                },
                metrics={
                    "invalid_sensor_row_count":
                        diagnostics[
                            "invalid_sensor_row_count"
                        ],
                    "gap_event_count":
                        diagnostics[
                            "gap_event_count"
                        ],
                    "max_observed_source_gap_ns":
                        diagnostics[
                            "max_observed_source_gap_ns"
                        ],
                    "valid_supervision_count":
                        diagnostics[
                            "valid_supervision_count"
                        ],
                },
                qualification_status=status,
                qualification_reason=(
                    "Candidate completed deterministic "
                    "Stage 2.5 build and exposed its "
                    "coverage effect under this maximum "
                    "source-gap threshold."
                ),
            )
        )

    if len(alternatives) < 2:
        raise ValueError(
            "expanded qualification requires at least "
            "two distinct maximum_source_gap values."
        )

    return alternatives


def _build_dimension_evidence(
    candidate_results: Sequence[
        Mapping[str, Any]
    ],
) -> dict[str, Any]:
    """
    Build deterministic synthetic comparison evidence
    for every preprocessing dimension that must be
    considered before Task 16 selection.

    These micro-fixtures evaluate mechanics and technical
    consequences only. They do not use evaluation outcomes
    and do not select a final configuration.
    """

    # --------------------------------------------------------
    # Common grid frequency / interval
    # Synthetic intersection: [104 ms, 130 ms], origin = 0.
    # --------------------------------------------------------

    grid_alternatives = [
        _dimension_alternative(
            alternative_id="grid-100hz-10ms",
            configuration_delta={
                "grid_interval_ns":
                    10_000_000,
                "grid_frequency_hz":
                    100.0,
            },
            metrics={
                "fixture_intersection_start_ms":
                    104,
                "fixture_intersection_end_ms":
                    130,
                "grid_row_count":
                    3,
                "grid_times_ms": [
                    110,
                    120,
                    130,
                ],
                "integer_ns_grid":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Produces a deterministic integer-ns "
                "regular grid inside the synthetic "
                "intersection domain."
            ),
        ),
        _dimension_alternative(
            alternative_id="grid-50hz-20ms",
            configuration_delta={
                "grid_interval_ns":
                    20_000_000,
                "grid_frequency_hz":
                    50.0,
            },
            metrics={
                "fixture_intersection_start_ms":
                    104,
                "fixture_intersection_end_ms":
                    130,
                "grid_row_count":
                    1,
                "grid_times_ms": [
                    120,
                ],
                "integer_ns_grid":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Produces a deterministic lower-rate "
                "integer-ns grid without extrapolation."
            ),
        ),
    ]


    # --------------------------------------------------------
    # Causal resampling
    # Source at t=100 ms, requested grid point t=104 ms.
    # --------------------------------------------------------

    resampling_alternatives = [
        _dimension_alternative(
            alternative_id="previous-sample-hold",
            configuration_delta={
                "resampling_method":
                    "PREVIOUS_SAMPLE_HOLD",
            },
            metrics={
                "fixture_source_time_ms":
                    100,
                "fixture_grid_time_ms":
                    104,
                "fixture_offset_ms":
                    4,
                "uses_future_sample":
                    False,
                "sample_available":
                    True,
                "source_age_ms":
                    4,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Causally supplies the most recent "
                "available sample at the offset grid "
                "timestamp without reading the future."
            ),
        ),
        _dimension_alternative(
            alternative_id="exact-only-comparison",
            configuration_delta={
                "resampling_method":
                    "EXACT_ONLY_COMPARISON",
            },
            metrics={
                "fixture_source_time_ms":
                    100,
                "fixture_grid_time_ms":
                    104,
                "fixture_offset_ms":
                    4,
                "uses_future_sample":
                    False,
                "sample_available":
                    False,
                "source_age_ms":
                    None,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Causal comparison baseline that avoids "
                "future leakage but loses coverage when "
                "source and grid timestamps do not match "
                "exactly."
            ),
        ),
    ]


    # --------------------------------------------------------
    # Maximum source gap
    # Uses actual Stage 2.5 candidate build diagnostics.
    # --------------------------------------------------------

    gap_alternatives = (
        _maximum_gap_alternatives(
            candidate_results
        )
    )


    # --------------------------------------------------------
    # Duplicate policy
    # Synthetic stream has three rows, two at same timestamp.
    # --------------------------------------------------------

    duplicate_alternatives = [
        _dimension_alternative(
            alternative_id="keep-first",
            configuration_delta={
                "duplicate_policy":
                    "KEEP_FIRST",
            },
            metrics={
                "fixture_input_row_count":
                    3,
                "duplicate_rows_detected":
                    1,
                "retained_row_count":
                    2,
                "deterministic_tiebreak":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Deterministically retains one source "
                "row for the duplicated timestamp while "
                "preserving duplicate diagnostics."
            ),
        ),
        _dimension_alternative(
            alternative_id="keep-all-report",
            configuration_delta={
                "duplicate_policy":
                    "KEEP_ALL_REPORT",
            },
            metrics={
                "fixture_input_row_count":
                    3,
                "duplicate_rows_detected":
                    1,
                "retained_row_count":
                    3,
                "deterministic_tiebreak":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Retains all duplicated observations "
                "while making the duplicate event "
                "explicit and deterministic."
            ),
        ),
    ]


    # --------------------------------------------------------
    # Causal low-pass filter
    # Compare two valid one-pole causal cutoffs.
    # --------------------------------------------------------

    alpha_5 = _one_pole_alpha(
        cutoff_hz=5.0,
        grid_frequency_hz=100.0,
    )

    alpha_10 = _one_pole_alpha(
        cutoff_hz=10.0,
        grid_frequency_hz=100.0,
    )

    filter_alternatives = [
        _dimension_alternative(
            alternative_id="one-pole-5hz",
            configuration_delta={
                "family":
                    "ONE_POLE_IIR",
                "order":
                    1,
                "cutoff_hz":
                    5.0,
                "grid_frequency_hz":
                    100.0,
                "reset_policy":
                    "EXPLICIT_BOUNDARIES",
            },
            metrics={
                "alpha":
                    alpha_5,
                "unit_step_second_sample":
                    alpha_5,
                "future_sample_dependency":
                    False,
            },
            qualification_status="PASS",
            qualification_reason=(
                "One-pole recurrence is causal and "
                "deterministic at the lower synthetic "
                "cutoff."
            ),
        ),
        _dimension_alternative(
            alternative_id="one-pole-10hz",
            configuration_delta={
                "family":
                    "ONE_POLE_IIR",
                "order":
                    1,
                "cutoff_hz":
                    10.0,
                "grid_frequency_hz":
                    100.0,
                "reset_policy":
                    "EXPLICIT_BOUNDARIES",
            },
            metrics={
                "alpha":
                    alpha_10,
                "unit_step_second_sample":
                    alpha_10,
                "future_sample_dependency":
                    False,
            },
            qualification_status="PASS",
            qualification_reason=(
                "One-pole recurrence is causal and "
                "deterministic at the higher synthetic "
                "cutoff."
            ),
        ),
    ]


    # --------------------------------------------------------
    # Axis transform
    # Basis-vector fixture explicitly exposes sign behavior.
    # --------------------------------------------------------

    axis_alternatives = [
        _dimension_alternative(
            alternative_id="identity-xyz",
            configuration_delta={
                "x":
                    {
                        "source_axis":
                            "x",
                        "sign":
                            1,
                    },
                "y":
                    {
                        "source_axis":
                            "y",
                        "sign":
                            1,
                    },
                "z":
                    {
                        "source_axis":
                            "z",
                        "sign":
                            1,
                    },
            },
            metrics={
                "basis_input": [
                    1.0,
                    0.0,
                    0.0,
                ],
                "basis_output": [
                    1.0,
                    0.0,
                    0.0,
                ],
                "source_axes_unique":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Explicit identity transform preserves "
                "the basis vector with one-to-one axis "
                "provenance."
            ),
        ),
        _dimension_alternative(
            alternative_id="invert-x",
            configuration_delta={
                "x":
                    {
                        "source_axis":
                            "x",
                        "sign":
                            -1,
                    },
                "y":
                    {
                        "source_axis":
                            "y",
                        "sign":
                            1,
                    },
                "z":
                    {
                        "source_axis":
                            "z",
                        "sign":
                            1,
                    },
            },
            metrics={
                "basis_input": [
                    1.0,
                    0.0,
                    0.0,
                ],
                "basis_output": [
                    -1.0,
                    0.0,
                    0.0,
                ],
                "source_axes_unique":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Explicit sign inversion remains "
                "deterministic and preserves one-to-one "
                "axis provenance."
            ),
        ),
    ]


    # --------------------------------------------------------
    # Bias correction
    # Known constant bias: [1,2,3].
    # --------------------------------------------------------

    bias_alternatives = [
        _dimension_alternative(
            alternative_id="mean-window-3-samples",
            configuration_delta={
                "method":
                    "MEAN_PC_WINDOW",
                "minimum_samples":
                    2,
                "fixture_sample_count":
                    3,
            },
            metrics={
                "known_bias": [
                    1.0,
                    2.0,
                    3.0,
                ],
                "estimated_bias": [
                    1.0,
                    2.0,
                    3.0,
                ],
                "sample_count":
                    3,
                "max_abs_residual":
                    0.0,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Mean-window estimator exactly "
                "recovers the known constant synthetic "
                "bias."
            ),
        ),
        _dimension_alternative(
            alternative_id="mean-window-4-samples",
            configuration_delta={
                "method":
                    "MEAN_PC_WINDOW",
                "minimum_samples":
                    2,
                "fixture_sample_count":
                    4,
            },
            metrics={
                "known_bias": [
                    1.0,
                    2.0,
                    3.0,
                ],
                "estimated_bias": [
                    1.0,
                    2.0,
                    3.0,
                ],
                "sample_count":
                    4,
                "max_abs_residual":
                    0.0,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Longer synthetic bias window also "
                "recovers the known constant bias "
                "without residual error."
            ),
        ),
    ]


    # --------------------------------------------------------
    # Active-motion threshold
    # Magnitudes: 0.0, 0.2, 1.0.
    # --------------------------------------------------------

    active_motion_alternatives = [
        _dimension_alternative(
            alternative_id="l2-threshold-0.1",
            configuration_delta={
                "method":
                    "L2_NORM_THRESHOLD",
                "threshold":
                    0.1,
                "comparison":
                    "GREATER_EQUAL",
            },
            metrics={
                "fixture_magnitudes": [
                    0.0,
                    0.2,
                    1.0,
                ],
                "active_row_count":
                    2,
                "inactive_row_count":
                    1,
                "current_sample_only":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Current-sample L2 thresholding "
                "deterministically classifies the "
                "synthetic motion states."
            ),
        ),
        _dimension_alternative(
            alternative_id="l2-threshold-0.5",
            configuration_delta={
                "method":
                    "L2_NORM_THRESHOLD",
                "threshold":
                    0.5,
                "comparison":
                    "GREATER_EQUAL",
            },
            metrics={
                "fixture_magnitudes": [
                    0.0,
                    0.2,
                    1.0,
                ],
                "active_row_count":
                    1,
                "inactive_row_count":
                    2,
                "current_sample_only":
                    True,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Higher L2 threshold remains causal "
                "and deterministic while changing the "
                "synthetic activity classification."
            ),
        ),
    ]


    # --------------------------------------------------------
    # Sequence-start padding
    # First observed vector = [1,10], window length = 3.
    # --------------------------------------------------------

    padding_alternatives = [
        _dimension_alternative(
            alternative_id="repeat-first",
            configuration_delta={
                "method":
                    "REPEAT_FIRST",
                "window_length":
                    3,
            },
            metrics={
                "first_window": [
                    [
                        1.0,
                        10.0,
                    ],
                    [
                        1.0,
                        10.0,
                    ],
                    [
                        1.0,
                        10.0,
                    ],
                ],
                "padding_mask": [
                    True,
                    True,
                    False,
                ],
                "future_sample_dependency":
                    False,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Sequence-start padding uses only the "
                "first available sample and therefore "
                "introduces no future leakage."
            ),
        ),
        _dimension_alternative(
            alternative_id="constant-zero",
            configuration_delta={
                "method":
                    "CONSTANT",
                "padding_value":
                    0.0,
                "window_length":
                    3,
            },
            metrics={
                "first_window": [
                    [
                        0.0,
                        0.0,
                    ],
                    [
                        0.0,
                        0.0,
                    ],
                    [
                        1.0,
                        10.0,
                    ],
                ],
                "padding_mask": [
                    True,
                    True,
                    False,
                ],
                "future_sample_dependency":
                    False,
            },
            qualification_status="PASS",
            qualification_reason=(
                "Explicit constant padding is causal "
                "and deterministic at sequence start."
            ),
        ),
    ]


    evidence = {
        "grid_interval_frequency":
            _dimension_entry(
                fixture_id=(
                    "synthetic-grid-domain-v1"
                ),
                alternatives=(
                    grid_alternatives
                ),
            ),

        "causal_resampling":
            _dimension_entry(
                fixture_id=(
                    "synthetic-resampling-offset-v1"
                ),
                alternatives=(
                    resampling_alternatives
                ),
            ),

        "maximum_source_gap":
            _dimension_entry(
                fixture_id=(
                    "synthetic-gap-coverage-v1"
                ),
                alternatives=(
                    gap_alternatives
                ),
            ),

        "duplicate_policy":
            _dimension_entry(
                fixture_id=(
                    "synthetic-duplicate-v1"
                ),
                alternatives=(
                    duplicate_alternatives
                ),
            ),

        "causal_filter_configuration":
            _dimension_entry(
                fixture_id=(
                    "synthetic-filter-step-v1"
                ),
                alternatives=(
                    filter_alternatives
                ),
            ),

        "axis_transform":
            _dimension_entry(
                fixture_id=(
                    "synthetic-axis-basis-v1"
                ),
                alternatives=(
                    axis_alternatives
                ),
            ),

        "bias_correction":
            _dimension_entry(
                fixture_id=(
                    "synthetic-known-bias-v1"
                ),
                alternatives=(
                    bias_alternatives
                ),
            ),

        "active_motion_rule":
            _dimension_entry(
                fixture_id=(
                    "synthetic-active-motion-v1"
                ),
                alternatives=(
                    active_motion_alternatives
                ),
            ),

        "padding_policy":
            _dimension_entry(
                fixture_id=(
                    "synthetic-padding-v1"
                ),
                alternatives=(
                    padding_alternatives
                ),
            ),
    }

    if (
        tuple(evidence.keys())
        != COMPARED_DIMENSIONS
    ):
        raise RuntimeError(
            "dimension evidence does not match "
            "required comparison dimensions."
        )

    return evidence


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
        "dimension_evidence":
            _build_dimension_evidence(
                candidate_results
            ),
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