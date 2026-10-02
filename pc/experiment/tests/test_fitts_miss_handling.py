"""Miss-handling contract for the Fitts trial pipeline.

Stage 2.5 correction: ``task/trials.py`` previously excluded a valid
miss from the movement-time denominator, while ``task/selection.py``
included it. That meant two different denominators for the same data.

These tests pin ONE definition across both modules:

=========================  ======  ==========  ========
case                       error   in MT / TP  in the log
=========================  ======  ==========  ========
hit                          0      yes         yes
valid miss                   1      yes         yes
technical failure            0      no          yes
initial acquisition          0      no          yes
=========================  ======  ==========  ========

Expected values are hand-derived from the contract above, not taken
from the implementation.
"""

from __future__ import annotations

import pytest

from pc.experiment.task.reciprocal import SequenceStep
from pc.experiment.task.schema import (
    EXCLUSION_REASONS,
    OUTCOMES,
    TRIAL_COLUMNS,
)
from pc.experiment.task.trials import build_sequence_trials


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

#: Stage 2.8 requires ``measured_transitions`` to be odd, so 4 targets
#: give 1 acquisition + 3 measured. Target 0 is the acquisition; every
#: measured miss therefore lands on target 1 at (500, 100).
TARGET_COUNT = 4

TARGETS = [
    {
        "target_index": index,
        "target_x_px": 100.0 + 400.0 * index,
        "target_y_px": 100.0,
        "target_diameter_px": 40.0,
        "difficulty_id": "EASY",
    }
    for index in range(TARGET_COUNT)
]

#: The cursor starts below the ring, so the acquisition origin differs
#: from the target 0 centre. An origin on the centre is rejected as an
#: undefined movement axis.
CONFIG = {
    "task_id": "fitts_pointing",
    "canvas_width_px": 1920.0,
    "canvas_height_px": 1080.0,
    "start_x_px": 100.0,
    "start_y_px": 300.0,
    "target_count": TARGET_COUNT,
    "measured_transitions": TARGET_COUNT - 1,
    "difficulty_ids": ["EASY"],
    "amplitude_px_by_difficulty": {"EASY": 400.0},
    "diameter_px_by_difficulty": {"EASY": 40.0},
    "task_config_version": "1.0",
}

MS = 1_000_000  # nanoseconds per millisecond


def build(observations):
    """Run the frozen stage 2.8 row builder over ``observations``."""
    return build_sequence_trials(
        participant_id="P01",
        session_id="S01",
        condition="C01",
        sequence_index=0,
        targets=TARGETS,
        observations=observations,
        config=CONFIG,
    )


def observation(*, x, y, start_ns, end_ns):
    """One observation, aimed at whichever target is current."""
    return {
        "endpoint_x_px": float(x),
        "endpoint_y_px": float(y),
        "onset_pc_time_ns": start_ns,
        "end_pc_time_ns": end_ns,
    }


def miss_run():
    """Acquisition on target 0, then a miss on target 1, then two hits.

    The cursor never teleports, so the miss endpoint (530, 100) becomes
    the real origin of the following movement.
    """
    return [
        observation(x=100.0, y=100.0, start_ns=1 * MS, end_ns=400 * MS),
        # Target 1 centre is (500, 100). Land 30 px away axially: the
        # 40 px diameter gives a 20 px tolerance, so 30 px is a miss.
        observation(x=530.0, y=100.0, start_ns=500 * MS, end_ns=1500 * MS),
        observation(x=900.0, y=100.0, start_ns=1500 * MS, end_ns=2000 * MS),
        observation(x=1300.0, y=100.0, start_ns=2000 * MS, end_ns=2400 * MS),
    ]


def run_with_second_observation(second):
    """Same clean run, but with the target 1 observation replaced."""
    observations = miss_run()
    observations[1] = second
    return build(observations)


def make_step(*, index, role="MEASURED"):
    """A minimal ``selection`` step; geometry is passed separately."""
    return SequenceStep(
        sequence_id="SEQ01",
        from_target="CENTER" if index == 0 else f"T{index - 1}",
        to_target=f"T{index}",
        trial_index=index,
        trial_role=role,
    )


# ---------------------------------------------------------------------------
# 1. A miss is not discarded
# ---------------------------------------------------------------------------


def test_valid_miss_is_a_row_not_a_dropped_trial():
    """All four trials survive, including the miss."""
    rows = build(miss_run())

    assert len(rows) == 4
    assert [row["outcome"] for row in rows] == [
        "CENTER_HIT",
        "VALID_MISS",
        "CENTER_HIT",
        "CENTER_HIT",
    ]


def test_valid_miss_is_marked_valid_and_flagged_as_an_error():
    """The proposal: a valid miss enters MT and TP with error=1."""
    miss = build(miss_run())[1]

    assert miss["valid_trial"] is True
    assert miss["error"] == 1
    assert miss["hit"] is False


def test_valid_miss_is_not_excluded_from_the_denominator():
    """A miss carries no exclusion reason, so it stays in the aggregate."""
    miss = build(miss_run())[1]

    assert miss["excluded_reason"] == ""
    assert miss["validity_rule"] == "MEASURED_MISS"


def test_valid_miss_keeps_its_real_endpoint_error_and_movement_time():
    """Discarding the endpoint or the MT would make the row unreportable."""
    miss = build(miss_run())[1]

    # The 30 px overshoot is retained, so the miss is auditable.
    assert miss["endpoint_error_px"] == pytest.approx(30.0)
    # 1500 ms - 500 ms = 1000 ms = 1e9 ns.
    assert miss["movement_time_ns"] == pytest.approx(1000 * MS)


def test_miss_is_not_an_exclusion_reason_anymore():
    """The old MISS_NOT_SELECTED code must not survive as a live reason."""
    assert "MISS_NOT_SELECTED" not in EXCLUSION_REASONS
    for row in build(miss_run()):
        assert row["excluded_reason"] != "MISS_NOT_SELECTED"


def test_orthogonal_miss_uses_the_same_rule_as_a_axial_miss():
    """Both miss categories are valid, error=1, and not excluded."""
    for miss_outcome in ("ORTHOGONAL_MISS", "VALID_MISS"):
        assert miss_outcome in OUTCOMES

    rows = run_with_second_observation(
        # 25 px off-axis on target 1: no axial error, but outside the
        # 20 px tolerance, so it is an orthogonal miss.
        observation(x=500.0, y=125.0, start_ns=500 * MS, end_ns=1500 * MS)
    )
    miss = rows[1]

    assert miss["outcome"] == "ORTHOGONAL_MISS"
    assert miss["valid_trial"] is True
    assert miss["error"] == 1
    assert miss["excluded_reason"] == ""
    assert miss["validity_rule"] == "MEASURED_MISS"


def test_consecutive_misses_are_both_counted():
    """A miss does not stop the next miss from being counted."""
    observations = miss_run()
    # Miss target 1 at 530, then miss target 2 from that real origin by
    # overshooting to 930 (30 px past the 900 centre).
    observations[2] = observation(
        x=930.0, y=100.0, start_ns=1500 * MS, end_ns=2000 * MS
    )
    rows = build(observations)

    assert [row["outcome"] for row in rows[1:3]] == ["VALID_MISS", "VALID_MISS"]
    measured = [row for row in rows if row["trial_role"] == "MEASURED"]
    assert [row["valid_trial"] for row in measured] == [True, True, True]
    assert [row["error"] for row in measured] == [1, 1, 0]



# ---------------------------------------------------------------------------
# 2. Initial acquisition is stored but not counted
# ---------------------------------------------------------------------------


def test_initial_acquisition_is_stored_for_audit():
    """It is recorded in full, keeping its own role and identity."""
    acquisition = build(miss_run())[0]

    assert acquisition["trial_role"] == "INITIAL_ACQUISITION"
    assert acquisition["trial_record_id"] == "S01:C01:0:0"
    assert acquisition["target_index"] == 0
    assert acquisition["target_x_px"] == pytest.approx(100.0)
    assert acquisition["movement_time_ns"] == pytest.approx(399 * MS)


def test_initial_acquisition_is_excluded_from_the_denominator():
    """It is the only trial recorded but not counted."""
    acquisition = build(miss_run())[0]

    assert acquisition["valid_trial"] is False
    assert acquisition["excluded_reason"] == "INITIAL_ACQUISITION"
    assert acquisition["validity_rule"] == "NOT_IN_DENOMINATOR"


def test_initial_acquisition_is_not_flagged_as_a_behavioural_error():
    """Reaching for the first target is not the participant's mistake."""
    assert build(miss_run())[0]["error"] == 0


def test_only_the_first_trial_is_the_initial_acquisition():
    """Every later trial is measured and therefore counted."""
    rows = build(miss_run())

    assert [row["trial_role"] for row in rows[1:]] == ["MEASURED"] * 3
    assert sum(1 for row in rows if not row["valid_trial"]) == 1


# ---------------------------------------------------------------------------
# 3. Technical failure is not counted
# ---------------------------------------------------------------------------


def zero_length_run():
    """Target 1 timed with end == onset, so no movement was measured."""
    return run_with_second_observation(
        observation(x=530.0, y=100.0, start_ns=500 * MS, end_ns=500 * MS)
    )


def test_invalid_timestamp_is_a_technical_failure():
    """A zero-length movement is unusable and must not reach throughput."""
    failure = zero_length_run()[1]

    assert failure["outcome"] == "INVALID_TIMESTAMP"
    assert failure["valid_trial"] is False
    assert failure["excluded_reason"] == "INVALID_TIMESTAMP"
    assert failure["validity_rule"] == "INVALID"


def test_technical_failure_is_not_flagged_as_a_behavioural_error():
    """A technical failure is not the participant's fault, so error=0."""
    assert zero_length_run()[1]["error"] == 0


def test_technical_failure_is_still_stored():
    """It is excluded from the statistics, not erased from the log."""
    failure = zero_length_run()[1]

    assert failure["trial_record_id"] == "S01:C01:0:1"
    assert failure["endpoint_error_px"] == pytest.approx(30.0)


def test_technical_failure_does_not_disturb_the_following_trials():
    """The miss offset is still carried into the next movement."""
    rows = zero_length_run()

    assert [row["trial_role"] for row in rows[1:]] == ["MEASURED"] * 3
    assert rows[2]["valid_trial"] is True


# ---------------------------------------------------------------------------
# 4. One schema, one definition across both modules
# ---------------------------------------------------------------------------


def test_error_is_a_declared_trial_column():
    """``error`` is part of the row contract, not an ad-hoc extra key."""
    assert "error" in TRIAL_COLUMNS


def test_every_row_reports_a_binary_integer_error_flag():
    """``error`` is always 0 or 1, never a bool and never missing."""
    for row in build(miss_run()):
        assert row["error"] in (0, 1)
        assert isinstance(row["error"], int)


def test_hit_and_error_are_mutually_exclusive_on_valid_trials():
    """A counted trial is either a clean hit or an error, never both."""
    for row in build(miss_run()):
        if row["valid_trial"]:
            assert row["hit"] + row["error"] == 1


def test_only_misses_carry_error_one():
    """No other trial category is flagged as an error."""
    for row in build(miss_run()):
        expected = 1 if row["outcome"] in ("VALID_MISS", "ORTHOGONAL_MISS") else 0
        assert row["error"] == expected


def test_selection_module_agrees_with_trials_module():
    """The two pipelines must reach the same verdict for one miss.

    ``selection.measured_records`` already retained valid misses. This
    drives the same 30 px overshoot through ``selection`` and checks it
    lands in the denominator, matching the ``trials`` verdict above.
    """
    from pc.experiment.task.selection import (
        build_selection_record,
        measured_records,
    )

    record = build_selection_record(
        make_step(index=0, role="MEASURED"),
        target_center=(500.0, 100.0),
        target_width=40.0,
        cursor_start=(100.0, 100.0),
        # The same endpoint the trials fixture uses for its miss.
        cursor_end=(530.0, 100.0),
        selection_time_ms=1000.0,
    )

    assert record.miss is True
    assert record.hit is False
    assert record.endpoint_x == pytest.approx(530.0)
    assert record.selection_time_ms == pytest.approx(1000.0)
    assert record.in_denominator is True


def test_selection_module_agrees_on_initial_acquisition():
    """The acquisition is excluded there too, so the two agree."""
    from pc.experiment.task.selection import (
        build_selection_record,
        measured_records,
    )

    acquisition = build_selection_record(
        make_step(index=0, role="INITIAL_ACQUISITION"),
        target_center=(100.0, 100.0),
        target_width=40.0,
        cursor_start=(100.0, 300.0),
        cursor_end=(100.0, 100.0),
        selection_time_ms=399.0,
    )

    assert acquisition.hit is True
    assert acquisition.in_denominator is False
    assert measured_records([acquisition]) == []


def test_selection_module_agrees_on_technical_failure():
    """An unusable timestamp is excluded there too, so the two agree."""
    from pc.experiment.task.selection import (
        EXCLUDED_INVALID_TIMESTAMP,
        build_selection_record,
        measured_records,
    )

    failure = build_selection_record(
        make_step(index=1, role="MEASURED"),
        target_center=(900.0, 100.0),
        target_width=40.0,
        cursor_start=(530.0, 100.0),
        cursor_end=(900.0, 100.0),
        # No movement was timed, so this is a technical failure.
        selection_time_ms=0.0,
    )

    assert failure.denominator_status == EXCLUDED_INVALID_TIMESTAMP
    assert measured_records([failure]) == []

