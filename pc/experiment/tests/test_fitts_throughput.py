"""Unit tests for the reciprocal Fitts task and sequence throughput.

Every expected value in this file is derived by hand from the
formulation documented in ``docs/decisions/fitts-task-design.md`` and
written as an explicit literal, so a regression in the implementation
shows up as a mismatch against an independently computed number rather
than against a value produced by the code under test.

Manual derivations
------------------
Effective width uses ``We = 4.133 * SDx`` with the *sample* standard
deviation (``n - 1`` denominator). Difficulty is ``log2(Ae/We + 1)``
and throughput is ``mean(IDe) / mean(MT)`` with movement time in
milliseconds, giving bits per second.

The canonical fixture is a 9-target ring of ``width = 64`` at
``radius = 260`` around ``(960, 540)``. Adjacent vertices are separated
by the chord ``2 * 260 * sin(pi / 9) ~= 177.78px``, and a miss is
anything landing further than the 32px tolerance from the centre.
"""

from __future__ import annotations

import math

import pytest

from pc.experiment.task.reciprocal import (
    INITIAL_ACQUISITION,
    MEASURED,
    generate_reciprocal_sequence,
)
from pc.experiment.task.selection import (
    EXCLUDED_INITIAL_ACQUISITION,
    EXCLUDED_INVALID_TIMESTAMP,
    IN_DENOMINATOR,
    build_selection_record,
    log_sequence,
    measured_records,
)
from pc.experiment.task.targets import generate_circular_targets
from pc.experiment.task.throughput import (
    EFFECTIVE_WIDTH_FACTOR,
    effective_width,
    find_sequence_breaks,
    is_contiguous_sequence,
    movement_geometry,
    sequence_throughput,
    standard_deviation,
)




SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
CENTER = (960.0, 540.0)
RADIUS = 260.0
TARGET_COUNT = 9
TARGET_WIDTH = 64.0


def make_targets(**overrides):
    params = {
        "screen_width": SCREEN_WIDTH,
        "screen_height": SCREEN_HEIGHT,
        "center": CENTER,
        "radius": RADIUS,
        "target_count": TARGET_COUNT,
        "target_width": TARGET_WIDTH,
    }
    params.update(overrides)

    return generate_circular_targets(**params)


def label_map(targets):
    centers = {f"T{t.target_id}": t.center for t in targets}
    widths = {f"T{t.target_id}": t.width for t in targets}

    return (centers, widths)


def build_sequence(measured_endpoints, times=None, origin=CENTER):
    """Log a full reciprocal sequence with explicit measured endpoints.

    ``measured_endpoints`` supplies the real endpoint of each measured
    trial. When ``times`` is omitted every measured trial takes 1000 ms.
    """
    targets = make_targets()
    centers, widths = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    if times is None:
        times = [500.0] + [1000.0] * len(measured_endpoints)

    # The initial acquisition ends on target 0, so the first measured
    # movement starts from target 0's centre.
    cursor_ends = [centers["T0"]] + list(measured_endpoints)

    return (
        log_sequence(
            steps,
            centers,
            widths,
            origin=origin,
            cursor_ends=cursor_ends,
            selection_times_ms=times,
        ),
        centers,
    )


# ---------------------------------------------------------------------------
# 1. center hit
# ---------------------------------------------------------------------------


def test_center_hit():
    """An endpoint on the target centre is a hit with zero offset."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    record = build_selection_record(
        steps[1],
        target_center=centers["T1"],
        target_width=TARGET_WIDTH,
        cursor_start=centers["T0"],
        cursor_end=centers["T1"],
        selection_time_ms=1000.0,
    )

    assert record.hit is True
    assert record.miss is False
    assert record.denominator_status == IN_DENOMINATOR

    amplitude, offset = movement_geometry(record, centers["T1"])

    # Hand check: T0 and T1 are adjacent vertices, so the movement
    # amplitude is the chord of one step of a regular 9-gon of radius
    # 260: 2 * 260 * sin(pi / 9).
    expected_amplitude = 2 * RADIUS * math.sin(math.pi / 9)

    assert amplitude == pytest.approx(expected_amplitude, rel=1e-9)
    assert offset == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 2. undershoot
# ---------------------------------------------------------------------------


def test_undershoot_has_negative_offset():
    """Stopping short of the centre yields a negative signed offset."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    start = centers["T0"]
    center = centers["T1"]
    axis = (center[0] - start[0], center[1] - start[1])
    length = math.hypot(*axis)
    unit = (axis[0] / length, axis[1] / length)

    # 20px short of the centre along the movement axis.
    endpoint = (center[0] - 20.0 * unit[0], center[1] - 20.0 * unit[1])

    record = build_selection_record(
        steps[1],
        target_center=center,
        target_width=TARGET_WIDTH,
        cursor_start=start,
        cursor_end=endpoint,
        selection_time_ms=1000.0,
    )

    _, offset = movement_geometry(record, center)

    assert offset == pytest.approx(-20.0, abs=1e-9)
    assert record.hit is True  # 20px < 32px tolerance


# ---------------------------------------------------------------------------
# 3. overshoot
# ---------------------------------------------------------------------------


def test_overshoot_has_positive_offset():
    """Passing the centre yields a positive signed offset."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    start = centers["T0"]
    center = centers["T1"]
    axis = (center[0] - start[0], center[1] - start[1])
    length = math.hypot(*axis)
    unit = (axis[0] / length, axis[1] / length)

    endpoint = (center[0] + 15.0 * unit[0], center[1] + 15.0 * unit[1])

    record = build_selection_record(
        steps[1],
        target_center=center,
        target_width=TARGET_WIDTH,
        cursor_start=start,
        cursor_end=endpoint,
        selection_time_ms=1000.0,
    )

    _, offset = movement_geometry(record, center)

    assert offset == pytest.approx(15.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. orthogonal miss
# ---------------------------------------------------------------------------


def test_orthogonal_miss_is_miss_with_near_zero_offset():
    """A sideways miss lands off-target but not along the movement axis."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    start = centers["T0"]
    center = centers["T1"]
    axis = (center[0] - start[0], center[1] - start[1])
    length = math.hypot(*axis)
    unit = (axis[0] / length, axis[1] / length)

    # Perpendicular unit vector: rotate the axis by 90 degrees.
    normal = (-unit[1], unit[0])
    endpoint = (center[0] + 50.0 * normal[0], center[1] + 50.0 * normal[1])

    record = build_selection_record(
        steps[1],
        target_center=center,
        target_width=TARGET_WIDTH,
        cursor_start=start,
        cursor_end=endpoint,
        selection_time_ms=1000.0,
    )

    amplitude, offset = movement_geometry(record, center)

    assert record.hit is False
    assert record.miss is True
    # A miss is still a real observation: it stays in the denominator.
    assert record.denominator_status == IN_DENOMINATOR
    # Purely lateral, so the signed axial offset is zero.
    assert offset == pytest.approx(0.0, abs=1e-9)

    # The amplitude is the total path length travelled: the chord to
    # the centre (2 * R * sin(pi / 9)) plus the 50px lateral deviation,
    # combined at right angles by the Pythagorean theorem.
    chord = 2 * RADIUS * math.sin(math.pi / 9)

    assert amplitude == pytest.approx(math.hypot(chord, 50.0), rel=1e-9)



# ---------------------------------------------------------------------------
# 5. serial overshoot reverse
# ---------------------------------------------------------------------------


def axis_step(start, center, distance):
    """Move ``distance`` px from ``center`` along the start->center axis."""
    axis = (center[0] - start[0], center[1] - start[1])
    length = math.hypot(*axis)
    unit = (axis[0] / length, axis[1] / length)

    return (center[0] + distance * unit[0], center[1] + distance * unit[1])


def test_serial_overshoot_reverse_keeps_offsets_positive():
    """Every endpoint past the centre gives a positive signed offset."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    previous = centers["T0"]
    offsets = []

    for step in steps[1:]:
        label = step.to_target
        center = centers[label]
        endpoint = axis_step(previous, center, 12.0)

        record = build_selection_record(
            step,
            target_center=center,
            target_width=TARGET_WIDTH,
            cursor_start=previous,
            cursor_end=endpoint,
            selection_time_ms=1000.0,
        )

        _, offset = movement_geometry(record, center)
        offsets.append(offset)
        previous = endpoint

    assert all(offset == pytest.approx(12.0, abs=1e-6) for offset in offsets)


# ---------------------------------------------------------------------------
# 6. serial undershoot reverse
# ---------------------------------------------------------------------------


def test_serial_undershoot_reverse_keeps_offsets_negative():
    """Every endpoint short of the centre gives a negative offset."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    previous = centers["T0"]
    offsets = []

    for step in steps[1:]:
        label = step.to_target
        center = centers[label]
        endpoint = axis_step(previous, center, -12.0)

        record = build_selection_record(
            step,
            target_center=center,
            target_width=TARGET_WIDTH,
            cursor_start=previous,
            cursor_end=endpoint,
            selection_time_ms=1000.0,
        )

        _, offset = movement_geometry(record, center)
        offsets.append(offset)
        previous = endpoint

    assert all(offset == pytest.approx(-12.0, abs=1e-6) for offset in offsets)



# ---------------------------------------------------------------------------
# 7. valid miss
# ---------------------------------------------------------------------------


def test_valid_miss_is_retained_in_denominator():
    """A miss stays in the denominator and still carries an endpoint."""
    targets = make_targets()
    centers, widths = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    # Overshoot well beyond the 32px tolerance on the first measured move,
    # then land exactly on centres for the remaining measured moves so
    # that the sequence is otherwise well formed.
    miss_endpoint = axis_step(centers["T0"], centers["T1"], 80.0)
    rest = [centers[label] for label in ("T2", "T3", "T4", "T5", "T6", "T7", "T8", "T0")]

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=CENTER,
        cursor_ends=[centers["T0"], miss_endpoint] + rest,
        selection_times_ms=[500.0] + [1000.0] * 9,
    )

    measured = measured_records(records)

    assert len(measured) == 9
    assert measured[0].miss is True
    assert measured[0].hit is False
    # The miss is not discarded: it is a real observation.
    assert measured[0].denominator_status == IN_DENOMINATOR
    assert measured[0].endpoint_x == pytest.approx(miss_endpoint[0])
    assert measured[0].endpoint_y == pytest.approx(miss_endpoint[1])


def test_miss_does_not_teleport_the_next_movement():
    """After a miss the next movement starts at the miss endpoint."""
    targets = make_targets()
    centers, widths = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    miss_endpoint = axis_step(centers["T0"], centers["T1"], 80.0)
    rest = [centers[label] for label in ("T2", "T3", "T4", "T5", "T6", "T7", "T8", "T0")]

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=CENTER,
        cursor_ends=[centers["T0"], miss_endpoint, centers["T2"]] + rest[1:],
        selection_times_ms=[500.0] + [1000.0] * 9,
    )

    assert records[1].cursor_end == pytest.approx(miss_endpoint)
    # The crucial assertion: the next trial begins where the miss ended,
    # NOT on target 0 or target 1.
    assert records[2].cursor_start == pytest.approx(miss_endpoint)
    assert records[2].cursor_start != pytest.approx(centers["T1"])
    assert records[2].cursor_start != pytest.approx(centers["T0"])


# ---------------------------------------------------------------------------
# 8. invalid timestamp
# ---------------------------------------------------------------------------


def test_invalid_timestamp_is_excluded_from_denominator():
    """A non-positive movement time cannot contribute to throughput."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    record = build_selection_record(
        steps[1],
        target_center=centers["T1"],
        target_width=TARGET_WIDTH,
        cursor_start=centers["T0"],
        cursor_end=centers["T1"],
        selection_time_ms=0.0,
    )

    assert record.denominator_status == EXCLUDED_INVALID_TIMESTAMP
    assert record.in_denominator is False


def test_missing_timestamp_is_excluded_from_denominator():
    """A ``None`` movement time is also excluded."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    record = build_selection_record(
        steps[1],
        target_center=centers["T1"],
        target_width=TARGET_WIDTH,
        cursor_start=centers["T0"],
        cursor_end=centers["T1"],
        selection_time_ms=None,
    )

    assert record.denominator_status == EXCLUDED_INVALID_TIMESTAMP


def test_initial_acquisition_is_recorded_but_excluded():
    """The acquisition is logged in full, yet stays out of MT."""
    targets = make_targets()
    centers, widths = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=CENTER,
        cursor_ends=[centers["T0"]] * len(steps),
        selection_times_ms=[500.0] * len(steps),
    )

    acquisition = records[0]

    # Recorded in full ...
    assert acquisition.trial_role == INITIAL_ACQUISITION
    assert acquisition.hit is True
    assert acquisition.selection_time_ms == 500.0
    assert acquisition.endpoint_x == pytest.approx(centers["T0"][0])

    # ... but not in the denominator.
    assert acquisition.denominator_status == EXCLUDED_INITIAL_ACQUISITION
    assert acquisition not in measured_records(records)
    assert len(measured_records(records)) == len(steps) - 1



# ---------------------------------------------------------------------------
# 9. missing trial breaks the sequence
# ---------------------------------------------------------------------------


def test_missing_trial_breaks_the_sequence():
    """A gap in trial_index must be reported, not silently pooled."""
    targets = make_targets()
    centers, widths = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    # Build a full, contiguous sequence, then drop the trial at index 5.
    # Nine measured destinations follow the initial acquisition.
    labels = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T0")
    rest = [centers[label] for label in labels]

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=CENTER,
        cursor_ends=[centers["T0"]] + rest,
        selection_times_ms=[500.0] + [1000.0] * 9,
    )

    assert is_contiguous_sequence(records) is True
    assert find_sequence_breaks(records) == []

    holed = [record for record in records if record.trial_index != 5]
    indices = sorted(
        record.trial_index for record in measured_records(holed)
    )

    # Index 5 is gone, so index 6 starts a new block.
    assert 5 not in indices
    assert is_contiguous_sequence(holed) is False
    assert find_sequence_breaks(holed) == [6]


# ---------------------------------------------------------------------------
# 10. We must never be zero
# ---------------------------------------------------------------------------


def test_effective_width_matches_hand_computation():
    """``We = 4.133 * SDx`` with a hand-computed sample SDx."""
    offsets = [-6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0]

    # Hand check: mean is 0, sum of squares is 36 + 36 = 72, and the
    # sample variance divides by n - 1 = 8, giving 9 and SDx = 3.
    assert standard_deviation(offsets) == pytest.approx(3.0, rel=1e-12)
    assert effective_width(offsets) == pytest.approx(12.399, rel=1e-12)
    assert EFFECTIVE_WIDTH_FACTOR == 4.133


def test_zero_effective_width_is_rejected():
    """Identical endpoints give SDx = 0, so We = 0 is refused."""
    offsets = [5.0] * 9

    assert standard_deviation(offsets) == pytest.approx(0.0, abs=1e-12)

    with pytest.raises(ValueError, match="effective width must be positive"):
        effective_width(offsets)


def test_effective_width_requires_two_samples():
    """One observation carries no spread information."""
    with pytest.raises(ValueError, match="at least two movements"):
        effective_width([4.0])


# ---------------------------------------------------------------------------
# Throughput aggregate
# ---------------------------------------------------------------------------


def test_sequence_throughput_uses_hand_computed_values():
    """Full aggregate: We, IDe, mean(MT) and TP, all hand-derived."""
    targets = make_targets()
    centers, widths = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    # Nine measured moves with signed offsets of -6 and +6 at the ends
    # and 0 elsewhere, giving a sample SDx of exactly 3.
    ends = [centers["T0"]]
    previous = centers["T0"]

    for offset_value, label in zip(
        [-6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0],
        ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T0"],
    ):
        center = centers[label]
        ends.append(axis_step(previous, center, offset_value))
        previous = ends[-1]

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=CENTER,
        cursor_ends=ends,
        selection_times_ms=[500.0] + [1000.0] * 9,
    )

    result = sequence_throughput(records, centers, sequence_id="s1")

    # Hand check 1: the effective width.
    assert result.endpoint_offset_sd_px == pytest.approx(3.0, rel=1e-9)
    assert result.effective_width_px == pytest.approx(12.399, rel=1e-9)

    # Hand check 2: the acquisition is absent, and every measured move
    # took exactly 1000 ms.
    assert result.measured_count == 9
    assert result.mean_movement_time_ms == pytest.approx(1000.0, rel=1e-12)

    # Hand check 3: IDe = log2(Ae / We + 1) for the first movement, whose
    # amplitude is the one-step chord plus a 6px undershoot.
    chord = 2 * RADIUS * math.sin(math.pi / 9)
    first = result.terms[0]

    assert first.actual_amplitude_px == pytest.approx(chord - 6.0, rel=1e-9)
    assert first.endpoint_offset_px == pytest.approx(-6.0, abs=1e-6)
    assert first.effective_id_bits == pytest.approx(
        math.log2(first.actual_amplitude_px / 12.399 + 1.0), rel=1e-12
    )

    # Hand check 4: TP = mean(IDe) / mean(MT) with MT in seconds.
    expected_mean_id = sum(
        term.effective_id_bits for term in result.terms
    ) / 9

    assert result.mean_effective_id_bits == pytest.approx(
        expected_mean_id, rel=1e-12
    )
    assert result.throughput_bits_per_second == pytest.approx(
        expected_mean_id / 1.0, rel=1e-9
        )


# ---------------------------------------------------------------------------
# Target generation: odd count and determinism
# ---------------------------------------------------------------------------


def test_odd_target_count_is_accepted():
    """9 is odd, so the layout is built and has the requested size."""
    targets = make_targets(target_count=9)

    assert len(targets) == 9
    assert [t.target_id for t in targets] == list(range(9))
    assert all(t.width == TARGET_WIDTH for t in targets)


def test_even_target_count_is_rejected():
    """An even ring has no single anchor target, so it is refused."""
    with pytest.raises(ValueError, match="target_count must be odd"):
        make_targets(target_count=10)


def test_same_seed_produces_identical_layout():
    """A seed fully determines the layout, so it can be replayed."""
    first = make_targets(seed=7)
    second = make_targets(seed=7)

    assert [t.as_dict() for t in first] == [t.as_dict() for t in second]


def test_different_seed_changes_the_layout():
    """A different seed rotates the layout, giving a distinct instance."""
    first = make_targets(seed=0)
    second = make_targets(seed=11)

    assert [t.as_dict() for t in first] != [t.as_dict() for t in second]


def test_targets_lie_on_the_circle():
    """Every target is exactly ``radius`` away from the layout centre."""
    for target in make_targets():
        assert math.dist(target.center, CENTER) == pytest.approx(
            RADIUS, rel=1e-9
        )


def test_ring_too_tight_is_rejected():
    """Targets that would touch or overlap make hits ambiguous."""
    with pytest.raises(ValueError, match="overlap"):
        make_targets(radius=20.0)


def test_ring_outside_screen_is_rejected():
    """A ring that does not fit the display is refused."""
    with pytest.raises(ValueError, match="display"):
        make_targets(radius=900.0)


# ---------------------------------------------------------------------------
# Reciprocal sequence shape
# ---------------------------------------------------------------------------


def test_sequence_has_one_acquisition_and_nine_measured():
    """1 initial acquisition + 9 measured transitions, as specified."""
    steps = generate_reciprocal_sequence(make_targets(), sequence_id="s1")

    assert len(steps) == 10
    assert steps[0].trial_role == INITIAL_ACQUISITION
    assert steps[0].from_target == "CENTER"
    assert steps[0].to_target == "T0"
    assert sum(1 for s in steps if s.trial_role == MEASURED) == 9


def test_sequence_closes_back_onto_the_anchor():
    """The final measured transition returns to target 0."""
    steps = generate_reciprocal_sequence(make_targets(), sequence_id="s1")

    assert steps[-1].to_target == "T0"
    assert steps[-1].trial_role == MEASURED
    # Every intermediate step advances by one ring position.
    assert [s.to_target for s in steps[1:]] == [
        "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T0",
    ]


def test_sequence_rejects_transition_count_mismatch():
    """A count that cannot close the loop is not reciprocal."""
    targets = make_targets()

    with pytest.raises(ValueError, match="measured_transitions == target_count"):
        generate_reciprocal_sequence(targets, measured_transitions=8)


def test_sequence_throughput_requires_measured_movement():
    """A sequence with nothing in the denominator cannot be scored."""
    targets = make_targets()
    centers, widths = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=CENTER,
        cursor_ends=[centers["T0"]] * len(steps),
        selection_times_ms=[500.0] * len(steps),
    )

    acquisition_only = [records[0]]

    with pytest.raises(ValueError, match="no measured movement"):
        sequence_throughput(
            acquisition_only, centers, sequence_id="s1"
        )

