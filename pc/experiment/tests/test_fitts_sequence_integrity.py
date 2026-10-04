"""Completeness guards for a reciprocal sequence.

Every way the measured block can fail to be *the whole sequence* gets
its own test, because each one previously slipped through a guard that
only looked for an interior gap:

* the first trial missing (head truncation);
* the last trial missing (tail truncation);
* an interior trial missing;
* a duplicated trial;
* records from two different sequences mixed together;
* an invalid timestamp;
* a missing or non-finite endpoint;
* a technical failure before the sequence finished.

A valid miss is a participant behaviour and stays in the denominator;
it is never reported as a technical failure.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from pc.experiment.task.reciprocal import (
    expected_measured_pairs,
    generate_reciprocal_sequence,
)
from pc.experiment.task.selection import (
    EXCLUDED_INVALID_TIMESTAMP,
    IN_DENOMINATOR,
    build_selection_record,
    log_sequence,
    measured_records,
)
from pc.experiment.task.selection_io import (
    read_selection_csv,
    write_selection_csv,
)
from pc.experiment.task.targets import generate_circular_targets
from pc.experiment.task.throughput import (
    SEQUENCE_BROKEN_CONTINUITY,
    SEQUENCE_COMPLETE,
    SEQUENCE_DUPLICATE_TRIAL,
    SEQUENCE_INTERNAL_GAP,
    SEQUENCE_MIXED_IDENTITY,
    SEQUENCE_PLAN_MISMATCH,
    SEQUENCE_SURPLUS_TRIALS,
    SEQUENCE_TECHNICAL_FAILURE,
    SEQUENCE_TRUNCATED_HEAD,
    SEQUENCE_TRUNCATED_TAIL,
    SEQUENCE_UNVERIFIED_COUNT,
    SequenceIntegrity,
    audit_sequence,
    measured_records_in_order,
    sequence_throughput,
)

SCREEN_W = 1920.0
SCREEN_H = 1080.0
CENTER = (960.0, 540.0)
RADIUS = 260.0
WIDTH = 64.0
SEED = 11
EXPECTED = 9

TARGETS = generate_circular_targets(
    screen_width=SCREEN_W,
    screen_height=SCREEN_H,
    center=CENTER,
    radius=RADIUS,
    target_count=EXPECTED,
    target_width=WIDTH,
    seed=SEED,
    jitter_px=0.0,
)
CENTERS = {f"T{t.target_id}": (t.x, t.y) for t in TARGETS}
WIDTHS = {f"T{t.target_id}": t.width for t in TARGETS}
STEPS = generate_reciprocal_sequence(TARGETS, sequence_id="s1")
CENTERS["CENTER"] = CENTER
WIDTHS["CENTER"] = WIDTH


#: Mixed-sign axial offsets, all well inside the 32px hit tolerance, so
#: the fixture is a complete sequence of hits with a non-degenerate
#: endpoint spread (SDx > 0). Identical endpoints would be rejected by
#: ``effective_width``, which is correct but would not exercise the
#: completeness guards.
OFFSETS_PX = [2.0, -14.0, 9.0, 3.0, -5.0, 18.0, -7.0, 4.0, -11.0]


def on_axis(start, stop, distance):
    axis = (stop[0] - start[0], stop[1] - start[1])
    length = math.hypot(*axis)
    unit = (axis[0] / length, axis[1] / length)
    return (stop[0] + distance * unit[0], stop[1] + distance * unit[1])


def default_endpoints():
    """A hit endpoint for every step, with a real spread of offsets."""
    ends = [on_axis(CENTER, CENTERS[STEPS[0].to_target], 4.0)]
    previous = CENTERS[STEPS[0].to_target]

    for step, offset in zip(STEPS[1:], OFFSETS_PX):
        stop = CENTERS[step.to_target]
        ends.append(on_axis(previous, stop, offset))
        previous = stop

    return ends


def ring_endpoints(steps):
    """Hit endpoints chaining along an arbitrary walk of the ring."""
    ends = [on_axis(CENTER, CENTERS[steps[0].to_target], 4.0)]
    previous = CENTERS[steps[0].to_target]

    for step, offset in zip(steps[1:], OFFSETS_PX):
        stop = CENTERS[step.to_target]
        ends.append(on_axis(previous, stop, offset))
        previous = stop

    return ends


def complete_records():
    """A whole sequence: acquisition plus nine measured trials, all hits."""
    return log_sequence(
        STEPS,
        CENTERS,
        WIDTHS,
        origin=CENTER,
        cursor_ends=default_endpoints(),
        selection_times_ms=[0.0] + [820.0] * EXPECTED,
    )


def audit(records, **kwargs):
    return audit_sequence(
        records,
        expected_measured_transitions=EXPECTED,
        expected_sequence_id="s1",
        **kwargs,
    )


def test_a_whole_sequence_is_complete():
    verdict = audit(complete_records())

    assert isinstance(verdict, SequenceIntegrity)
    assert verdict.status == SEQUENCE_COMPLETE
    assert verdict.is_complete is True
# ---------------------------------------------------------------------------
# 1. Head truncation
# ---------------------------------------------------------------------------


def test_missing_first_trial_is_head_truncation():
    """Trials 2..9 are internally contiguous but are not the sequence."""
    records = [r for r in complete_records() if r.trial_index != 1]

    verdict = audit(records)

    assert verdict.status == SEQUENCE_TRUNCATED_HEAD
    assert verdict.observed_measured_count == EXPECTED - 1
    assert "truncated before it started" in verdict.reasons[0]


def test_missing_first_two_trials_is_still_head_truncation():
    records = [r for r in complete_records() if r.trial_index > 2]

    assert audit(records).status == SEQUENCE_TRUNCATED_HEAD


# ---------------------------------------------------------------------------
# 2. Tail truncation
# ---------------------------------------------------------------------------


def test_missing_last_trial_is_tail_truncation():
    """Trials 1..8 are contiguous; only the expected count reveals this."""
    records = [r for r in complete_records() if r.trial_index != EXPECTED]

    verdict = audit(records)

    assert verdict.status == SEQUENCE_TRUNCATED_TAIL
    assert "stopped early" in " ".join(verdict.reasons)


def test_missing_last_three_trials_is_tail_truncation():
    records = [r for r in complete_records() if r.trial_index <= EXPECTED - 3]

    assert audit(records).status == SEQUENCE_TRUNCATED_TAIL


def test_without_an_expected_count_truncation_is_invisible():
    """This is exactly why the expected count is required.

# ---------------------------------------------------------------------------
# 3. Interior gap
# ---------------------------------------------------------------------------


def test_missing_interior_trial_is_an_internal_gap():
    records = [r for r in complete_records() if r.trial_index != 5]

    verdict = audit(records)

    assert verdict.status == SEQUENCE_INTERNAL_GAP
    assert "not contiguous" in " ".join(verdict.reasons)


def test_interior_gap_is_detected_even_without_an_expected_count():
    records = [r for r in complete_records() if r.trial_index != 5]

    assert (
        audit_sequence(records, expected_sequence_id="s1").status
        == SEQUENCE_INTERNAL_GAP
    )


# ---------------------------------------------------------------------------
# 4. Duplicate trial
# ---------------------------------------------------------------------------


def test_duplicated_trial_is_rejected():
    records = list(complete_records())

    # Re-log trial 4 under the same index.
    trial_four = next(s for s in STEPS if s.trial_index == 4)
    records.append(
        build_selection_record(
            trial_four,
            target_center=CENTERS[trial_four.to_target],
            target_width=WIDTH,
            cursor_start=CENTERS[trial_four.from_target],
            cursor_end=CENTERS[trial_four.to_target],
            selection_time_ms=820.0,
        )
    )

    verdict = audit(records)

    assert verdict.status == SEQUENCE_DUPLICATE_TRIAL
    assert verdict.duplicated_trial_indices == (4,)


# ---------------------------------------------------------------------------
# 5. Mixed sequence identity
# ---------------------------------------------------------------------------


def test_two_sequences_pooled_together_are_mixed_identity():
    other = generate_reciprocal_sequence(TARGETS, sequence_id="s2")
    intruder_step = next(s for s in other if s.trial_index == 1)

    records = list(complete_records())
    records.append(
        build_selection_record(
            intruder_step,
            target_center=CENTERS[intruder_step.to_target],
            target_width=WIDTH,
            cursor_start=CENTER,
            cursor_end=CENTERS[intruder_step.to_target],
            selection_time_ms=900.0,
        )
    )

    verdict = audit(records)

    assert verdict.status == SEQUENCE_MIXED_IDENTITY
    assert verdict.foreign_sequence_ids == ("s2",)
    An interior-gap scan reports no break for trials 1..8, so the guard
    must be told how many transitions were intended.
    """
# ---------------------------------------------------------------------------
# 6. Invalid timestamp
# ---------------------------------------------------------------------------


def test_invalid_timestamp_excludes_the_trial_and_shortens_the_sequence():
    times = [0.0] + [820.0] * EXPECTED
    times[4] = float("nan")

    records = log_sequence(
        STEPS,
        CENTERS,
        WIDTHS,
        origin=CENTER,
        cursor_ends=[CENTERS[s.to_target] for s in STEPS],
        selection_times_ms=times,
    )

    excluded = next(r for r in records if r.trial_index == 4)
    assert excluded.denominator_status == EXCLUDED_INVALID_TIMESTAMP
    assert excluded.in_denominator is False

    # The trial is dropped from the measured run, leaving an interior gap
    # that the audit names rather than silently re-indexing around.
    assert len(measured_records(records)) == EXPECTED - 1
    assert audit(records).status == SEQUENCE_INTERNAL_GAP


def test_invalid_timestamp_on_the_last_trial_looks_like_tail_truncation():
    times = [0.0] + [820.0] * EXPECTED
    times[EXPECTED] = -1.0

    records = log_sequence(
        STEPS,
        CENTERS,
        WIDTHS,
        origin=CENTER,
        cursor_ends=[CENTERS[s.to_target] for s in STEPS],
        selection_times_ms=times,
    )

    assert audit(records).status == SEQUENCE_TRUNCATED_TAIL


# ---------------------------------------------------------------------------
# 7. Missing or non-finite endpoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_endpoint_is_refused_at_the_logger(bad):
    step = next(s for s in STEPS if s.trial_index == 3)

    with pytest.raises(ValueError, match="finite"):
        build_selection_record(
            step,
            target_center=CENTERS[step.to_target],
            target_width=WIDTH,
            cursor_start=CENTERS[step.from_target],
            cursor_end=(bad, 540.0),
            selection_time_ms=820.0,
        )


def test_a_short_endpoint_list_does_not_shift_every_later_endpoint():
    """A dropped endpoint must not be silently absorbed.

    ``zip`` would stop at the shorter iterable and quietly return a
    five-trial log; the logger must instead refuse the mismatch.
    """
    ends = [CENTERS[s.to_target] for s in STEPS][:-2]

    with pytest.raises((ValueError, TypeError)):
        log_sequence(
            STEPS,
            CENTERS,
            WIDTHS,
            origin=CENTER,
            cursor_ends=ends,
            selection_times_ms=[0.0] + [820.0] * EXPECTED,
        )


# ---------------------------------------------------------------------------
# 8. Technical failure before the sequence finished
# ---------------------------------------------------------------------------


def test_technical_failure_on_a_whole_sequence_is_still_reported():
    verdict = audit(complete_records(), technical_failure=True)

    assert verdict.status == SEQUENCE_TECHNICAL_FAILURE
    assert "technical failure" in " ".join(verdict.reasons)


def test_technical_failure_after_truncation_reports_the_truncation_first():
    records = [r for r in complete_records() if r.trial_index <= 4]

    verdict = audit(records, technical_failure=True)

    assert verdict.status == SEQUENCE_TRUNCATED_TAIL
    # The failure is still recorded, not dropped.
    assert "technical failure" in " ".join(verdict.reasons)


# ---------------------------------------------------------------------------
# A valid miss is not a failure
# ---------------------------------------------------------------------------


def test_a_valid_miss_stays_in_the_denominator_and_is_not_a_failure():
    # Land 50px past each centre: past the 32px tolerance, so a miss.
    ends = [(CENTERS[s.to_target][0] + 50.0, CENTERS[s.to_target][1]) for s in STEPS]

    records = log_sequence(
        STEPS,
        CENTERS,
        WIDTHS,
        origin=CENTER,
        cursor_ends=ends,
        selection_times_ms=[0.0] + [1400.0] * EXPECTED,
    )

    measured = measured_records(records)
    misses = [r for r in measured if r.miss]
    assert len(measured) == EXPECTED
    assert len(misses) == EXPECTED
    assert all(r.denominator_status == IN_DENOMINATOR for r in misses)

    assert audit(records).status == SEQUENCE_COMPLETE
# ---------------------------------------------------------------------------
# The caller records the incomplete status and its reason
# ---------------------------------------------------------------------------


def test_caller_can_persist_incomplete_status_with_reason():
    """An exception alone is not evidence; the status must be recordable."""
    records = [r for r in complete_records() if r.trial_index != EXPECTED]
    verdict = audit(records)

    logged = {
        "sequence_id": "s1",
        "status": verdict.status,
        "expected_measured_transitions": verdict.expected_measured_transitions,
        "observed_measured_count": verdict.observed_measured_count,
        "reasons": " ".join(verdict.reasons),
    }

    assert logged["status"] == SEQUENCE_TRUNCATED_TAIL
    assert logged["expected_measured_transitions"] == EXPECTED
    assert logged["observed_measured_count"] == EXPECTED - 1
    assert "stopped early" in logged["reasons"]


def test_sequence_throughput_names_the_status_in_its_error():
    records = [r for r in complete_records() if r.trial_index != EXPECTED]

    with pytest.raises(ValueError, match=SEQUENCE_TRUNCATED_TAIL):
        sequence_throughput(
            records,
            CENTERS,
            sequence_id="s1",
            expected_measured_transitions=EXPECTED,
        )


def test_expected_count_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        audit_sequence(complete_records(), expected_measured_transitions=0)


def test_a_complete_sequence_still_pools():
    result = sequence_throughput(
        complete_records(),
        CENTERS,
        sequence_id="s1",
        expected_measured_transitions=EXPECTED,
    )

    assert result.measured_count == EXPECTED
    assert math.isfinite(result.throughput_bits_per_second)
    assert math.isfinite(result.throughput_bits_per_second)


# ---------------------------------------------------------------------------
# 12. Trusted reference count
#
# Truncation is only visible when the intended number of transitions is
# known. Without it a fragment is indistinguishable from a whole sequence,
# so the audit must refuse to certify and the estimator must refuse to score.
# ---------------------------------------------------------------------------


def test_no_reference_count_cannot_certify_completeness():
    """Eight contiguous trials may be a fragment; that is not decidable here."""
    records = [r for r in complete_records() if r.trial_index != 1]

    verdict = audit_sequence(records, expected_measured_transitions=None)

    assert verdict.status == SEQUENCE_UNVERIFIED_COUNT
    assert verdict.is_complete is False
    assert any("reference count" in reason for reason in verdict.reasons)


def test_no_reference_count_is_refused_by_the_estimator():
    records = [r for r in complete_records() if r.trial_index != 1]

    with pytest.raises(ValueError, match=SEQUENCE_UNVERIFIED_COUNT):
        sequence_throughput(records, CENTERS, sequence_id="s1")


def test_missing_reference_count_does_not_mask_a_detectable_break():
    """An interior gap is decidable without the count and still wins."""
    records = [r for r in complete_records() if r.trial_index != 4]

    verdict = audit_sequence(records, expected_measured_transitions=None)

    assert verdict.status == SEQUENCE_INTERNAL_GAP


def test_missing_reference_count_does_not_mask_a_duplicate():
    base = complete_records()
    records = base + [base[-1]]

    verdict = audit_sequence(records, expected_measured_transitions=None)

    assert verdict.status == SEQUENCE_DUPLICATE_TRIAL


# ---------------------------------------------------------------------------
# 13. Surplus transitions
# ---------------------------------------------------------------------------


def test_more_transitions_than_planned_is_not_the_sequence():
    """A tenth logged movement means the block is not this sequence."""
    base = complete_records()
    records = base + [dataclasses.replace(base[-1], trial_index=EXPECTED + 1)]

    verdict = audit(records)

    assert verdict.status == SEQUENCE_SURPLUS_TRIALS
    assert verdict.is_complete is False
    assert verdict.surplus_trial_indices == (EXPECTED + 1,)


def test_surplus_transitions_are_refused_by_the_estimator():
    base = complete_records()
    records = base + [dataclasses.replace(base[-1], trial_index=EXPECTED + 1)]

    with pytest.raises(ValueError, match=SEQUENCE_SURPLUS_TRIALS):
        sequence_throughput(
            records,
            CENTERS,
            sequence_id="s1",
            expected_measured_transitions=EXPECTED,
        )


def test_extra_measured_row_with_index_zero_is_not_complete():
    """An index below 1 must fail the exact range, not slip past the count.

    The surplus check used to test only ``index > expected``, so a tenth
    measured row numbered 0 was neither surplus nor missing and the block
    was accepted as COMPLETE with ten measured trials.
    """
    base = complete_records()
    records = base + [dataclasses.replace(base[-1], trial_index=0)]

    verdict = audit(records)

    assert verdict.status == SEQUENCE_SURPLUS_TRIALS
    assert verdict.is_complete is False
    assert 0 in verdict.surplus_trial_indices
    assert verdict.observed_measured_count == EXPECTED + 1

    with pytest.raises(ValueError, match=SEQUENCE_SURPLUS_TRIALS):
        sequence_throughput(
            records,
            CENTERS,
            sequence_id="s1",
            expected_measured_transitions=EXPECTED,
        )


def test_extra_measured_row_survives_no_csv_round_trip(tmp_path):
    """The same out-of-range row is rejected through the public CSV path."""
    base = complete_records()
    records = base + [dataclasses.replace(base[-1], trial_index=0)]
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)

    loaded = read_selection_csv(path, CENTERS)
    verdict = audit_sequence(
        loaded,
        expected_measured_transitions=EXPECTED,
        expected_sequence_id="s1",
    )

    assert verdict.status == SEQUENCE_SURPLUS_TRIALS
    assert 0 in verdict.surplus_trial_indices


def test_continuous_but_unplanned_ring_walk_is_refused():
    """A chained, closed walk of the wrong plan must not be pooled.

    ``T0 -> T1 -> ... -> T8 -> T0`` chains perfectly and closes on its
    anchor, so every structural guard passes. It is nonetheless a different
    traversal than the configured reciprocal plan, so the measured
    movements are not the planned ones.
    """
    ring_order = [*range(EXPECTED), 0]
    ring_steps = [
        dataclasses.replace(
            STEPS[0],
            to_target=f"T{ring_order[0]}",
        ),
        *[
            dataclasses.replace(
                STEPS[offset],
                from_target=f"T{source}",
                to_target=f"T{destination}",
            )
            for offset, (source, destination) in enumerate(
                zip(ring_order, ring_order[1:]), start=1
            )
        ],
    ]
    records = log_sequence(
        ring_steps,
        CENTERS,
        WIDTHS,
        origin=CENTER,
        cursor_ends=ring_endpoints(ring_steps),
        selection_times_ms=[0.0] + [820.0] * EXPECTED,
    )

    # Structurally sound: contiguous, chained and closed.
    unguarded = audit(records)
    assert unguarded.status == SEQUENCE_COMPLETE

    verdict = audit(records, expected_pairs=expected_measured_pairs(TARGETS))

    assert verdict.status == SEQUENCE_PLAN_MISMATCH
    assert verdict.is_complete is False
    assert verdict.mismatched_plan_positions == (1,)

    with pytest.raises(ValueError, match=SEQUENCE_PLAN_MISMATCH):
        sequence_throughput(
            records,
            CENTERS,
            sequence_id="s1",
            expected_measured_transitions=EXPECTED,
            expected_pairs=expected_measured_pairs(TARGETS),
        )


def test_a_block_matching_the_planned_plan_is_still_complete():
    """Supplying the trusted plan must not reject the genuine sequence."""
    verdict = audit(
        complete_records(), expected_pairs=expected_measured_pairs(TARGETS)
    )

    assert verdict.status == SEQUENCE_COMPLETE
    assert verdict.is_complete is True
    assert verdict.mismatched_plan_positions == ()


# ---------------------------------------------------------------------------
# 14. Identity without an expectation
#
# The audit and the estimator must not disagree. The estimator always knows
# the expected id, so an audit that omits it has to detect mixed identity
# from the observed rows alone.
# ---------------------------------------------------------------------------


def test_mixed_identity_is_detected_without_an_expected_id():
    records = list(complete_records())
    records[3] = dataclasses.replace(records[3], sequence_id="s2")

    verdict = audit_sequence(records, expected_measured_transitions=EXPECTED)

    assert verdict.status == SEQUENCE_MIXED_IDENTITY
    assert "s2" in verdict.foreign_sequence_ids


def test_blank_identity_is_rejected():
    records = list(complete_records())
    records[2] = dataclasses.replace(records[2], sequence_id="")

    verdict = audit(records)

    assert verdict.status == SEQUENCE_MIXED_IDENTITY
    assert verdict.is_complete is False


def test_a_uniform_identity_without_an_expectation_is_complete():
    """One id throughout is legitimate; only mixing is not."""
    verdict = audit_sequence(
        complete_records(), expected_measured_transitions=EXPECTED
    )

    assert verdict.status == SEQUENCE_COMPLETE
    assert verdict.foreign_sequence_ids == ()


# ---------------------------------------------------------------------------
# 15. Target continuity
#
# Contiguous indices are not enough: the logged pairs must form one
# reciprocal walk, or the per-movement amplitudes belong to no sequence.
# ---------------------------------------------------------------------------


def test_target_pairs_must_chain_into_one_walk():
    records = list(complete_records())
    records[3] = dataclasses.replace(
        records[3], from_target="T0", to_target="T8"
    )

    verdict = audit(records)

    assert verdict.status == SEQUENCE_BROKEN_CONTINUITY
    assert verdict.is_complete is False
    assert "4" in " ".join(verdict.reasons)


def test_broken_continuity_is_refused_by_the_estimator():
    records = list(complete_records())
    records[3] = dataclasses.replace(
        records[3], from_target="T0", to_target="T8"
    )

    with pytest.raises(ValueError, match=SEQUENCE_BROKEN_CONTINUITY):
        sequence_throughput(
            records,
            CENTERS,
            sequence_id="s1",
            expected_measured_transitions=EXPECTED,
        )


def test_truncation_is_not_double_counted_as_broken_continuity():
    """Losing a trial cannot chain across the hole; that is the truncation."""
    records = [r for r in complete_records() if r.trial_index != 1]

    verdict = audit(records)

    assert verdict.status == SEQUENCE_TRUNCATED_HEAD


# ---------------------------------------------------------------------------
# 16. Order independence
#
# The serial correction pairs movement i with the endpoint of i-1, so the
# audit and the estimator must agree on trial order instead of inheriting
# whatever order the rows happen to arrive in.
# ---------------------------------------------------------------------------


def test_shuffled_rows_give_the_same_result_as_ordered_rows():
    base = complete_records()

    ordered_result = sequence_throughput(
        base, CENTERS, sequence_id="s1", expected_measured_transitions=EXPECTED
    )
    shuffled_result = sequence_throughput(
        list(reversed(base)),
        CENTERS,
        sequence_id="s1",
        expected_measured_transitions=EXPECTED,
    )

    assert shuffled_result.throughput_bits_per_second == pytest.approx(
        ordered_result.throughput_bits_per_second, rel=1e-12
    )
    assert [
        term.effective_amplitude_px for term in shuffled_result.terms
    ] == [term.effective_amplitude_px for term in ordered_result.terms]


def test_measured_records_in_order_sorts_by_trial_index():
    shuffled = list(reversed(complete_records()))

    ordered = measured_records_in_order(shuffled)

    assert [record.trial_index for record in ordered] == list(
        range(1, EXPECTED + 1)
    )
