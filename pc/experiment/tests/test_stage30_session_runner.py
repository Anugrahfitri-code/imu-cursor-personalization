"""End-to-end session runner: ordering, provenance and termination.

The runner composes frozen contracts rather than owning state, so these
tests pin the guarantees the protocol depends on: calibration is
recorded once and shared by both personalised conditions, a technical
stop is never mistaken for a completed session, and a time cap
abandons the schedule instead of quietly shortening it.
"""

import pytest

from pc.experiment.session import SESSION_TIME_CAP_NS
from pc.experiment.session.runner import (
    CONDITION_CODES,
    DEFAULT_DIFFICULTY_ORDER,
    HARD_TIME_CAP_MS,
    PROLOGUE,
    SESSION_STATUS_COMPLETE,
    SESSION_STATUS_TECHNICAL_FAILURE,
    ArtifactRecord,
    MonotonicClock,
    ParticipantRecord,
    SessionConfig,
    SessionRunner,
    TechnicalFault,
    condition_state,
    record_calibration,
    sha256_text,
)

HAPPY_PATH = PROLOGUE + tuple(
    condition_state(code) for code in CONDITION_CODES
) + ("COMPLETE",)


def _participant(**overrides):
    params = {
        "participant_id": "P-TEST",
        "cohort": "A",
        "device": "mouse-n95",
    }
    params.update(overrides)
    return ParticipantRecord(**params)


def _artifacts(**overrides):
    params = {
        "commit_hash": "a" * 40,
        "session_hash": sha256_text("session"),
        "calibration_file_sha256": sha256_text("calibration"),
        "p2c_config_sha256": sha256_text("p2c-config"),
        "l0_config_sha256": sha256_text("l0-config"),
        "l2c_config_sha256": sha256_text("l2c-config"),
        "task_config_sha256": sha256_text("task-config"),
        "l0_artifact": "l0-v1.2.3",
        "l2c_adapter_artifact": "adapter-a9",
        "app_version": "0.1.0",
    }
    params.update(overrides)
    return ArtifactRecord(**params)


def _config(**overrides):
    params = {"dry_run": True, "data_policy": "DRY_RUN"}
    params.update(overrides)
    return SessionConfig(**params)


def _run(**overrides):
    params = {
        "config": _config(),
        "participant": _participant(),
        "artifacts": _artifacts(),
        "clock": MonotonicClock(step_ns=1_000_000),
    }
    params.update(overrides)
    return SessionRunner(**params).run()


# -- ordering ----------------------------------------------------------


def test_clean_session_walks_the_frozen_path():
    run = _run()

    assert run.state_path == HAPPY_PATH
    assert run.stop_reason == "COMPLETED_SCHEDULE"
    assert run.technical_status == SESSION_STATUS_COMPLETE


def test_every_condition_runs_once_in_chain_order():
    run = _run()

    assert [c.result.condition for c in run.conditions] == [
        "P0", "P2C", "L0", "L2C",
    ]


def test_runner_invents_no_state_outside_the_frozen_chain():
    run = _run()

    assert set(run.state_path) <= set(HAPPY_PATH)
    # No state repeats, so the walk is a genuine forward progression.
    assert len(set(run.state_path)) == len(run.state_path)


def test_condition_codes_map_to_frozen_states():
    assert CONDITION_CODES == ("P0", "P2C", "L0", "L2C")
    assert condition_state("P2C") == "CONDITION_P2C"
    with pytest.raises(ValueError):
        condition_state("NOPE")


def test_hard_time_cap_matches_the_frozen_schema_constant():
    assert HARD_TIME_CAP_MS == 600_000
    assert SESSION_TIME_CAP_NS == HARD_TIME_CAP_MS * 1_000_000


# -- calibration -------------------------------------------------------


def test_calibration_is_recorded_exactly_once():
    run = _run()

    assert run.calibration["trajectory_family"] == "2C"
    assert run.calibration["sample_count"] > 0


def test_personalised_conditions_share_one_calibration():
    run = _run()

    p2c = run.condition_result("P2C").result.calibration_file_hash
    l2c = run.condition_result("L2C").result.calibration_file_hash

    assert p2c == l2c == _artifacts().calibration_file_sha256


def test_unpersonalised_conditions_carry_no_calibration():
    run = _run()

    assert run.condition_result("P0").result.calibration_file_hash is None
    assert run.condition_result("L0").result.calibration_file_hash is None


def test_the_two_personalised_conditions_differ_by_adaptation_mode():
    run = _run()

    p2c = run.condition_result("P2C").plan
    l2c = run.condition_result("L2C").plan

    # P2C fits a fresh policy per user...
    assert p2c.fits_per_user
    assert p2c.uses_calibration
    # ...whereas L2C adapts a *frozen* global model through a latent
    # adapter, so the shared weights must not be refitted.
    assert l2c.frozen_global_model
    assert l2c.uses_latent_adapter
    assert not l2c.fits_per_user
    assert l2c.uses_calibration


def test_baseline_conditions_are_neither_calibrated_nor_fitted():
    run = _run()

    for code in ("P0", "L0"):
        plan = run.condition_result(code).plan
        assert not plan.uses_calibration
        assert not plan.fits_per_user


def test_calibration_record_cannot_be_edited_after_recording():
    record = record_calibration(
        sha256_text("c"), sample_count=10, duration_ns=1_000
    )

    with pytest.raises(TypeError):
        record["sample_count"] = 999


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_count": 0},
        {"duration_ns": 0},
    ],
)
def test_empty_calibration_recording_is_rejected(kwargs):
    params = {
        "sample_count": 10,
        "duration_ns": 1_000,
    }
    params.update(kwargs)

    with pytest.raises(ValueError):
        record_calibration(sha256_text("c"), **params)


def test_calibration_is_unavailable_before_its_state():
    runner = SessionRunner(_config(), _participant(), _artifacts())

    with pytest.raises(RuntimeError):
        _ = runner.calibration


# -- termination -------------------------------------------------------


def test_technical_fault_stops_and_is_not_reported_as_complete():
    run = _run(fault=TechnicalFault(state="CONDITION_L0"))

    assert run.stop_reason == "TECHNICAL_FAILURE"
    assert run.technical_status == SESSION_STATUS_TECHNICAL_FAILURE
    # The schedule is abandoned, not shortened into a "complete" run.
    assert [c.result.condition for c in run.conditions] == ["P0", "P2C"]


def test_time_cap_stops_the_session():
    # Every state burns a full slice of the cap, so the very first
    # transition is already too late.
    run = _run(clock=MonotonicClock(step_ns=SESSION_TIME_CAP_NS))

    assert run.stop_reason == "TIME_CAP_REACHED"
    assert run.technical_status == SESSION_STATUS_TECHNICAL_FAILURE
    assert run.conditions == ()


def test_shortened_schedule_still_completes():
    # Counterbalancing may skip a condition but never reorder the chain.
    run = _run(config=_config(condition_order=("P0", "L0", "L2C")))

    assert [c.result.condition for c in run.conditions] == [
        "P0", "L0", "L2C",
    ]
    assert run.technical_status == SESSION_STATUS_COMPLETE


def test_low_performance_is_never_a_technical_stop():
    # The contract reserves technical reasons for genuine faults.
    with pytest.raises(ValueError):
        TechnicalFault(
            state="CONDITION_L0", reason="PARTICIPANT_REQUEST"
        )


def test_time_cap_cannot_be_injected_as_a_fault():
    with pytest.raises(ValueError):
        TechnicalFault(state="CONDITION_L0", reason="TIME_CAP_REACHED")


def test_runner_rejects_a_session_longer_than_the_cap():
    with pytest.raises(ValueError):
        _config(time_cap_ns=SESSION_TIME_CAP_NS * 2)


# -- configuration guards ---------------------------------------------


def test_condition_chain_cannot_be_reordered():
    with pytest.raises(ValueError):
        _config(condition_order=("L2C", "P0"))


def test_unknown_condition_is_rejected():
    with pytest.raises(ValueError):
        _config(condition_order=("P0", "NOPE"))


def test_empty_condition_order_is_rejected():
    with pytest.raises(ValueError):
        _config(condition_order=())


def test_empty_difficulty_order_is_rejected():
    with pytest.raises(ValueError):
        _config(difficulty_order=())


def test_dry_run_may_not_be_recorded_as_research_data():
    with pytest.raises(ValueError):
        SessionConfig(dry_run=True, data_policy="RESEARCH")


def test_participant_must_be_identified():
    with pytest.raises(ValueError):
        SessionRunner(
            _config(), _participant(participant_id=""), _artifacts()
        )

        record_calibration(sha256_text("c"), **params)


def test_calibration_is_unavailable_before_its_state():
    runner = SessionRunner(_config(), _participant(), _artifacts())

    with pytest.raises(RuntimeError):
        _ = runner.calibration


# -- manifest ----------------------------------------------------------


def test_manifest_satisfies_the_frozen_completeness_contract():
    from pc.experiment.session import validate_manifest

    manifest = _run().manifest

    # ``validate_manifest`` raises when a required field is missing or
    # a hash is malformed, so a clean return is the assertion.
    validate_manifest(manifest)
    assert manifest["participant_id"] == "P-TEST"
    assert manifest["session_id"] == "P-TEST-s01"
    assert manifest["cohort"] == "A"
    assert manifest["device"] == "mouse-n95"
    assert manifest["app_version"] == "0.1.0"
    assert manifest["commit_hash"] == "a" * 40
    assert manifest["l0_artifact"] == "l0-v1.2.3"
    assert manifest["l2c_adapter_artifact"] == "adapter-a9"


def test_manifest_records_both_orderings_consistently():
    manifest = _run().manifest

    assert manifest["condition_order"] == list(CONDITION_CODES)
    assert manifest["difficulty_order"] == list(DEFAULT_DIFFICULTY_ORDER)
    assert manifest["difficulty_ids"] == manifest["difficulty_order"]


def test_manifest_records_timestamps_and_stop_outcome():
    manifest = _run().manifest

    assert manifest["start_timestamp"] < manifest["end_timestamp"]
    assert manifest["technical_status"] == SESSION_STATUS_COMPLETE
    assert manifest["stop_reason"] == "COMPLETED_SCHEDULE"
    assert manifest["dry_run"] is True
    assert manifest["data_policy"] == "DRY_RUN"


def test_manifest_marks_a_technical_failure():
    manifest = _run(fault=TechnicalFault(state="CONDITION_P2C")).manifest

    assert manifest["technical_status"] == SESSION_STATUS_TECHNICAL_FAILURE
    assert manifest["stop_reason"] == "TECHNICAL_FAILURE"


# -- trials and determinism -------------------------------------------


def test_trials_cover_every_condition_and_difficulty():
    seen = []

    def trial_execute(**kwargs):
        for difficulty in kwargs["difficulty_order"]:
            seen.append((kwargs["condition"], difficulty))
        return [
            {"condition": kwargs["condition"], "difficulty": d}
            for d in kwargs["difficulty_order"]
        ]

    run = _run(trial_execute=trial_execute)

    assert len(run.trial_records) == len(CONDITION_CODES) * len(
        DEFAULT_DIFFICULTY_ORDER
    )
    assert [c for c, _ in seen[:3]] == ["P0", "P0", "P0"]


def test_trial_hook_receives_the_session_calibration():
    captured = {}

    def trial_execute(**kwargs):
        captured["calibration"] = kwargs["calibration"]
        return []

    run = _run(trial_execute=trial_execute)

    assert captured["calibration"] is run.calibration


def test_session_is_reproducible_under_the_injected_clock():
    first = _run()
    second = _run()

    assert first.manifest == second.manifest
    assert first.state_path == second.state_path
    assert first.elapsed_ns == second.elapsed_ns


def test_elapsed_time_advances_with_the_schedule():
    run = _run()

    assert run.elapsed_ns > 0
    # One clock slice per planned state after READY.
    assert run.elapsed_ns == (len(HAPPY_PATH) - 1) * 1_000_000


def test_condition_result_lookup_rejects_a_condition_that_never_ran():
    run = _run(fault=TechnicalFault(state="CONDITION_P0"))

    with pytest.raises(KeyError):
        run.condition_result("L2C")


def test_clock_never_moves_backwards():
    clock = MonotonicClock(step_ns=1_000)

    clock.advance(5_000)
    with pytest.raises(ValueError):
        clock.advance(-1)
    with pytest.raises(ValueError):
        clock.jump_to(0)

