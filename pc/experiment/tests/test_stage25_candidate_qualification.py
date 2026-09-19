import json
import re

from pc.experiment.preprocessing.candidate_qualification import (
    qualify_preprocessing_candidates,
    write_candidate_qualification_evidence,
)

from pc.experiment.tests.test_stage25_qualification import (
    UPSTREAM_SHA,
    _candidates,
    _records,
    _reference,
)


EXPECTED_REPORT_FIELDS = (
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


EXPECTED_CANDIDATE_FIELDS = (
    "configuration_id",
    "configuration_role",
    "configuration",
    "preprocessing_config_sha256",
    "build_status",
    "qualification_gates",
    "timing_coverage_diagnostics",
    "causality_result",
    "causality_evidence",
    "reproducibility_result",
    "acceptance_decision",
    "acceptance_reason",
    "common_grid_sha256",
    "preprocessing_quality_sha256",
    "preprocessing_manifest_sha256",
)


REQUIRED_COMPARED_DIMENSIONS = {
    "grid_interval_frequency",
    "causal_resampling",
    "maximum_source_gap",
    "duplicate_policy",
    "causal_filter_configuration",
    "axis_transform",
    "bias_correction",
    "active_motion_rule",
    "padding_policy",
}


def _qualify():
    return qualify_preprocessing_candidates(
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        records=_records(),
        reference_trajectory=_reference(),
        candidate_configs=_candidates(),
        upstream_stage24_provenance_sha256=(
            UPSTREAM_SHA
        ),
        upstream_clock_quality_passed=True,
        technical_errors=(),
    )


def test_report_explicitly_records_required_plan_evidence():
    bundle = _qualify()

    report = bundle[
        "qualification_report"
    ]

    assert tuple(report.keys()) == (
        EXPECTED_REPORT_FIELDS
    )

    assert report[
        "candidate_results"
    ]

    assert all(
        tuple(result.keys())
        == EXPECTED_CANDIDATE_FIELDS
        for result in report[
            "candidate_results"
        ]
    )


def test_generated_microfixtures_are_synthetic_and_caller_origin_is_unverified():
    report = _qualify()[
        "qualification_report"
    ]

    evidence = report[
        "evidence_set"
    ]

    assert (
        evidence["microfixture_dataset_role"]
        == "synthetic"
    )

    assert (
        evidence[
            "real_participant_data_used"
        ]
        is None
    )

    assert isinstance(
        evidence["fixture_id"],
        str,
    )

    assert evidence[
        "fixture_id"
    ]

    assert evidence["caller_input_origin"] == "UNVERIFIED"


def test_all_plan_candidate_dimensions_are_recorded():
    evidence = _qualify()[
        "qualification_report"
    ][
        "evidence_set"
    ]

    assert (
        set(
            evidence[
                "compared_dimensions"
            ]
        )
        == REQUIRED_COMPARED_DIMENSIONS
    )


def test_full_candidate_configuration_is_recorded():
    report = _qualify()[
        "qualification_report"
    ]

    supplied = {
        config[
            "configuration_id"
        ]:
            config
        for config in _candidates()
    }

    for result in report[
        "candidate_results"
    ]:
        configuration_id = result[
            "configuration_id"
        ]

        assert (
            result["configuration"]
            == supplied[
                configuration_id
            ]
        )


def test_pass_fail_gates_are_explicit():
    report = _qualify()[
        "qualification_report"
    ]

    required_gates = {
        "build_valid",
        "causality",
        "reproducibility",
        "supervision_available",
        "microfixtures",
    }

    for result in report[
        "candidate_results"
    ]:
        gates = result[
            "qualification_gates"
        ]

        assert (
            set(gates.keys())
            == required_gates
        )

        assert all(
            status in {
                "PASS",
                "FAIL",
            }
            for status in gates.values()
        )


def test_timing_and_coverage_diagnostics_are_explicit():
    report = _qualify()[
        "qualification_report"
    ]

    required = {
        "grid_row_count",
        "invalid_accel_row_count",
        "invalid_gyro_row_count",
        "invalid_sensor_row_count",
        "valid_supervision_count",
        "invalid_supervision_count",
        "gap_event_count",
        "max_observed_source_gap_ns",
        "active_motion_row_count",
    }

    for result in report[
        "candidate_results"
    ]:
        diagnostics = result[
            "timing_coverage_diagnostics"
        ]

        assert (
            set(diagnostics.keys())
            == required
        )


def test_causality_and_reproducibility_results_are_recorded():
    report = _qualify()[
        "qualification_report"
    ]

    for result in report[
        "candidate_results"
    ]:
        assert result[
            "causality_result"
        ] in {
            "PASS",
            "FAIL",
        }

        assert result[
            "reproducibility_result"
        ] in {
            "PASS",
            "FAIL",
        }


def test_acceptance_or_rejection_reason_is_explicit():
    report = _qualify()[
        "qualification_report"
    ]

    for result in report[
        "candidate_results"
    ]:
        assert result[
            "acceptance_decision"
        ] in {
            "ACCEPTED",
            "REJECTED",
        }

        assert isinstance(
            result[
                "acceptance_reason"
            ],
            str,
        )

        assert result[
            "acceptance_reason"
        ].strip()


def test_task15_still_does_not_rank_or_select_candidate():
    report = _qualify()[
        "qualification_report"
    ]

    serialized = json.dumps(
        report,
        sort_keys=True,
    ).lower()

    forbidden = (
        '"winner"',
        '"ranking"',
        '"rank"',
        '"selected_candidate"',
        '"selected_configuration"',
        '"score"',
    )

    for token in forbidden:
        assert token not in serialized


def test_evaluation_outcomes_are_not_written_to_report():
    report = _qualify()[
        "qualification_report"
    ]

    serialized = json.dumps(
        report,
        sort_keys=True,
    )

    assert "evaluation_score" not in serialized
    assert "condition_id" not in serialized


def test_report_digest_is_uppercase_sha256():
    bundle = _qualify()

    assert re.fullmatch(
        r"[0-9A-F]{64}",
        bundle[
            "qualification_report_sha256"
        ],
    )


def test_evidence_writer_emits_reproducible_files(
    tmp_path,
):
    bundle = _qualify()

    result = (
        write_candidate_qualification_evidence(
            qualification_bundle=bundle,
            output_directory=tmp_path,
        )
    )

    report_path = tmp_path / (
        "qualification_report.json"
    )

    digest_path = tmp_path / (
        "qualification_report.sha256"
    )

    assert report_path.exists()
    assert digest_path.exists()

    written_report = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        written_report
        == bundle[
            "qualification_report"
        ]
    )

    assert (
        digest_path.read_text(
            encoding="utf-8"
        ).strip()
        == bundle[
            "qualification_report_sha256"
        ]
    )

    assert (
        result[
            "qualification_report_sha256"
        ]
        == bundle[
            "qualification_report_sha256"
        ]
    )


EXPECTED_DIMENSION_ENTRY_FIELDS = (
    "fixture_id",
    "dataset_role",
    "alternatives",
)


EXPECTED_DIMENSION_ALTERNATIVE_FIELDS = (
    "alternative_id",
    "configuration_delta",
    "metrics",
    "qualification_status",
    "qualification_reason",
)


def _dimension_evidence():
    return _qualify()[
        "qualification_report"
    ][
        "dimension_evidence"
    ]


def test_dimension_evidence_covers_all_required_plan_dimensions():
    evidence = _dimension_evidence()

    assert (
        set(evidence.keys())
        == REQUIRED_COMPARED_DIMENSIONS
    )


def test_every_dimension_compares_at_least_two_alternatives():
    evidence = _dimension_evidence()

    for dimension, entry in evidence.items():
        assert tuple(entry.keys()) == (
            EXPECTED_DIMENSION_ENTRY_FIELDS
        )

        assert (
            entry["dataset_role"]
            == "synthetic"
        )

        assert isinstance(
            entry["fixture_id"],
            str,
        )

        assert entry[
            "fixture_id"
        ].strip()

        alternatives = entry[
            "alternatives"
        ]

        assert len(alternatives) >= 2, (
            dimension
        )

        alternative_ids = [
            alternative[
                "alternative_id"
            ]
            for alternative in alternatives
        ]

        assert (
            len(alternative_ids)
            == len(
                set(alternative_ids)
            )
        )


def test_dimension_alternatives_record_explicit_metrics_and_gate():
    evidence = _dimension_evidence()

    for dimension, entry in evidence.items():
        for alternative in entry[
            "alternatives"
        ]:
            assert tuple(
                alternative.keys()
            ) == (
                EXPECTED_DIMENSION_ALTERNATIVE_FIELDS
            )

            assert isinstance(
                alternative[
                    "configuration_delta"
                ],
                dict,
            )

            assert isinstance(
                alternative[
                    "metrics"
                ],
                dict,
            )

            assert alternative[
                "metrics"
            ], dimension

            assert (
                alternative[
                    "qualification_status"
                ]
                in {
                    "PASS",
                    "FAIL",
                    "NOT_IMPLEMENTED",
                }
            )

            assert isinstance(
                alternative[
                    "qualification_reason"
                ],
                str,
            )

            assert alternative[
                "qualification_reason"
            ].strip()


def test_resampling_dimension_contains_real_causal_comparison():
    alternatives = (
        _dimension_evidence()[
            "causal_resampling"
        ][
            "alternatives"
        ]
    )

    alternative_ids = {
        alternative[
            "alternative_id"
        ]
        for alternative in alternatives
    }

    assert (
        "previous-sample-hold"
        in alternative_ids
    )

    assert (
        "exact-only-comparison"
        in alternative_ids
    )

    offset = next(a for a in alternatives if a['alternative_id'] == 'previous-sample-hold')
    assert offset['metrics']['actual']['source_age_ns'] == 4_000_000
    assert offset['metrics']['actual']['x'] == 2.0
    assert offset['qualification_status'] == 'PASS'
    comparison = next(a for a in alternatives if a['alternative_id'] == 'exact-only-comparison')
    assert comparison['qualification_status'] == 'NOT_IMPLEMENTED'
    assert comparison['metrics']['comparison_only'] is True


def test_expanded_evidence_does_not_select_or_rank():
    evidence = _dimension_evidence()

    serialized = json.dumps(
        evidence,
        sort_keys=True,
    ).lower()

    forbidden_tokens = (
        '"winner"',
        '"ranking"',
        '"rank"',
        '"selected_candidate"',
        '"selected_configuration"',
    )

    for token in forbidden_tokens:
        assert token not in serialized


def test_expanded_dimension_evidence_is_deterministic():
    first = _dimension_evidence()
    second = _dimension_evidence()

    assert first == second
