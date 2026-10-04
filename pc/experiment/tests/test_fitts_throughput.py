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
``radius = 260`` around ``(960, 540)``, walked with the reciprocal
near-opposite stride, so every measured movement spans the chord
``2 * 260 * cos(pi / 18) ~= 512.10px``. The adjacent chord
``2 * 260 * sin(pi / 9) ~= 177.85px`` is what a naive ascending-id walk
would produce and is asserted *not* to be used. A miss is anything
landing further than the 32px tolerance from the centre.
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

#: Chord between angularly adjacent vertices. This is the amplitude a
#: naive ascending-id walk would produce and must never be measured.
ADJACENT_CHORD = 2 * RADIUS * math.sin(math.pi / 9)

#: Chord spanned by the reciprocal near-opposite stride. This is the
#: amplitude every measured transition must actually have.
TRAVERSAL_CHORD = 2 * RADIUS * math.cos(math.pi / (2 * TARGET_COUNT))


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

    step = steps[1]
    origin = centers[step.from_target]
    destination = centers[step.to_target]

    record = build_selection_record(
        step,
        target_center=destination,
        target_width=TARGET_WIDTH,
        cursor_start=origin,
        cursor_end=destination,
        selection_time_ms=1000.0,
    )

    assert record.hit is True
    assert record.miss is False
    assert record.denominator_status == IN_DENOMINATOR

    amplitude, offset = movement_geometry(record, origin, destination)

    # Hand check: the measured step of a reciprocal sequence runs from
    # T0 to T4, so the movement amplitude is the near-opposite chord of a
    # regular 9-gon of radius 260: 2 * 260 * cos(pi / 18).
    expected_amplitude = TRAVERSAL_CHORD

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

    _, offset = movement_geometry(record, start, center)

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

    _, offset = movement_geometry(record, start, center)

    assert offset == pytest.approx(15.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. orthogonal miss
# ---------------------------------------------------------------------------


def test_orthogonal_miss_is_miss_with_near_zero_offset():
    """A sideways miss lands off-target but not along the movement axis."""
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    step = steps[1]
    start = centers[step.from_target]
    center = centers[step.to_target]
    axis = (center[0] - start[0], center[1] - start[1])
    length = math.hypot(*axis)
    unit = (axis[0] / length, axis[1] / length)

    # Perpendicular unit vector: rotate the axis by 90 degrees.
    normal = (-unit[1], unit[0])
    endpoint = (center[0] + 50.0 * normal[0], center[1] + 50.0 * normal[1])

    record = build_selection_record(
        step,
        target_center=center,
        target_width=TARGET_WIDTH,
        cursor_start=start,
        cursor_end=endpoint,
        selection_time_ms=1000.0,
    )

    amplitude, offset = movement_geometry(record, start, center)

    assert record.hit is False
    assert record.miss is True
    # A miss is still a real observation: it stays in the denominator.
    assert record.denominator_status == IN_DENOMINATOR
    # Purely lateral, so the signed axial offset is zero.
    assert offset == pytest.approx(0.0, abs=1e-9)

    # The amplitude stays the nominal chord. Section 5.13 forbids the
    # 2-D path length, so the 50px lateral deviation must NOT be folded
    # into the amplitude; it only shows up as a miss flag.
    chord = TRAVERSAL_CHORD

    assert amplitude == pytest.approx(chord, rel=1e-9)
    assert amplitude != pytest.approx(math.hypot(chord, 50.0), rel=1e-3)



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
        endpoint = axis_step(centers[step.from_target], center, 12.0)

        record = build_selection_record(
            step,
            target_center=center,
            target_width=TARGET_WIDTH,
            cursor_start=previous,
            cursor_end=endpoint,
            selection_time_ms=1000.0,
        )

        _, offset = movement_geometry(record, centers[step.from_target], center)
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
        endpoint = axis_step(centers[step.from_target], center, -12.0)

        record = build_selection_record(
            step,
            target_center=center,
            target_width=TARGET_WIDTH,
            cursor_start=previous,
            cursor_end=endpoint,
            selection_time_ms=1000.0,
        )

        _, offset = movement_geometry(record, centers[step.from_target], center)
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

    measured_labels = [s.to_target for s in steps if s.trial_role == MEASURED]

    for offset_value, label in zip(
        [-6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0],
        measured_labels,
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

    result = sequence_throughput(
        records, centers, sequence_id="s1",
        expected_measured_transitions=TARGET_COUNT,
    )

    # Hand check 1: the effective width.
    assert result.endpoint_offset_sd_px == pytest.approx(3.0, rel=1e-9)
    assert result.effective_width_px == pytest.approx(12.399, rel=1e-9)

    # Hand check 2: the acquisition is absent, and every measured move
    # took exactly 1000 ms.
    assert result.measured_count == 9
    assert result.mean_movement_time_ms == pytest.approx(1000.0, rel=1e-12)

    # Hand check 3: the serial correction of proposal section 5.13.
    # Every movement has the same nominal amplitude a (the near-opposite
    # chord of a regular 9-gon of radius 260), and the offsets are
    # [-6, 0, 0, 0, 0, 0, 0, 0, 6], so:
    #
    #   Ae_1 = a + dx_1            = a - 6
    #   Ae_2 = a + dx_2 + dx_1     = a - 6
    #   Ae_i = a + dx_i + dx_{i-1} = a      for i = 3..8
    #   Ae_9 = a + dx_9 + dx_8     = a + 6
    #
    # The two -6 corrections are not cancelled by the single +6, so
    # the mean effective amplitude is the chord less 6/9.
    chord = TRAVERSAL_CHORD
    first = result.terms[0]
    second = result.terms[1]

    assert first.nominal_amplitude_px == pytest.approx(chord, rel=1e-12)
    assert first.endpoint_offset_px == pytest.approx(-6.0, abs=1e-6)
    assert first.effective_amplitude_px == pytest.approx(
        chord - 6.0, rel=1e-9
    )
    assert second.effective_amplitude_px == pytest.approx(
        chord - 6.0, rel=1e-9
    )
    assert result.terms[8].effective_amplitude_px == pytest.approx(
        chord + 6.0, rel=1e-9
    )
    assert result.mean_effective_amplitude_px == pytest.approx(
        chord - 6.0 / 9.0, rel=1e-9
    )

    # Hand check 4: ID_e is defined once per sequence from the mean
    # effective amplitude, and TP = ID_e / mean(MT) with MT in seconds.
    expected_id = math.log2((chord - 6.0 / 9.0) / 12.399 + 1.0)

    assert result.index_of_difficulty_bits == pytest.approx(
        expected_id, rel=1e-9
    )
    assert result.throughput_bits_per_second == pytest.approx(
        expected_id / 1.0, rel=1e-9
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
    # Every measured step advances by the near-opposite stride, not by one
    # angular neighbour.
    assert [s.to_target for s in steps[1:]] == [
        "T4", "T8", "T3", "T7", "T2", "T6", "T1", "T5", "T0",
    ]
    assert [(s.from_target, s.to_target) for s in steps[1:]] == [
        ("T0", "T4"), ("T4", "T8"), ("T8", "T3"), ("T3", "T7"),
        ("T7", "T2"), ("T2", "T6"), ("T6", "T1"), ("T1", "T5"),
        ("T5", "T0"),
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
            acquisition_only,
            centers,
            sequence_id="s1",
            expected_measured_transitions=TARGET_COUNT,
        )

# ---------------------------------------------------------------------------
# 12. throughput audit regressions
#
# These lock the mathematical decisions recorded in
# ``docs/decisions/throughput-audit.md``. They are deliberately written
# against literals derived by hand, not against the implementation.
# ---------------------------------------------------------------------------


def test_effective_width_uses_sample_standard_deviation():
    """We = 4.133 * SDx with SDx the *sample* SD (n-1), not the population SD.

    For offsets [+30, -30] the two candidates differ by sqrt(2):

    * sample SD      = sqrt(1800 / (2 - 1)) = 42.42640...
    * population SD  = sqrt(1800 / 2)     = 30

    We must equal 4.133 * 42.42640 = 175.34834, not 4.133 * 30 = 123.99.
    """

    width = effective_width([30.0, -30.0])

    # mean = 0, sum of squares = 1800, sample variance = 1800 / (2 - 1)
    assert standard_deviation([30.0, -30.0]) == pytest.approx(
        math.sqrt(1800.0), abs=1e-9
    )
    assert width == pytest.approx(4.133 * math.sqrt(1800.0), abs=1e-9)
    assert width == pytest.approx(175.34834, abs=1e-5)

    # The population-SD reading is the regression we are guarding against:
    # it would divide by N instead of N-1 and understate We by sqrt(2).
    population = 4.133 * 30.0
    assert width != pytest.approx(population, abs=1e-6)
    assert width / population == pytest.approx(math.sqrt(2.0), abs=1e-9)


def test_movement_geometry_amplitude_is_nominal_not_path_length():
    """The amplitude is the nominal centre-to-centre distance a_i.

    Proposal section 5.13 defines a_i as the distance from the
    from-target centre to the to-target centre and states that the
    serial correction "is not a measure of two-dimensional cursor path
    length". The measured step runs T0 -> T4, so the targets are one
    near-opposite chord apart, 2*260*cos(pi/18) = 512.10003px, so a 40px
    overshoot must not change
    the amplitude, and the amplitude is certainly not the 32px
    tolerance radius.
    """

    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    step = steps[1]
    start = centers[step.from_target]
    center = centers[step.to_target]
    on_centre = axis_step(start, center, 0.0)
    overshoot = axis_step(start, center, 40.0)

    clean = build_selection_record(
        step,
        target_center=center,
        target_width=TARGET_WIDTH,
        cursor_start=start,
        cursor_end=on_centre,
        selection_time_ms=1000.0,
    )

    long = build_selection_record(
        step,
        target_center=center,
        target_width=TARGET_WIDTH,
        cursor_start=start,
        cursor_end=overshoot,
        selection_time_ms=1000.0,
    )

    clean_amplitude, clean_offset = movement_geometry(clean, start, center)
    long_amplitude, long_offset = movement_geometry(long, start, center)

    nominal = math.dist(start, center)

    assert clean_amplitude == pytest.approx(nominal, abs=1e-9)
    assert clean_amplitude == pytest.approx(TRAVERSAL_CHORD, abs=1e-5)
    assert clean_offset == pytest.approx(0.0, abs=1e-9)

    # The overshoot changes the offset only, never the amplitude.
    assert long_amplitude == pytest.approx(clean_amplitude, abs=1e-9)
    assert long_amplitude != pytest.approx(clean_amplitude + 40.0, abs=1e-6)
    assert long_amplitude != pytest.approx(TARGET_WIDTH / 2, abs=1e-6)
    assert long_offset == pytest.approx(40.0, abs=1e-6)


def test_orthogonal_miss_leaves_amplitude_nominal_and_offset_zero():
    """A sideways miss is recorded, but changes neither a_i nor dx_i.

    The endpoint is 50px off to the side of the target centre, which is
    past the 32px tolerance and therefore a miss. The travelled path is
    the hypotenuse sqrt(a^2 + 50^2) = 514.53695px, but section 5.13
    forbids using a 2-D path length here, so the amplitude stays at the
    nominal chord while the axial projection is 0. The miss is still
    counted and still contributes its movement time.
    """

    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    step = steps[1]
    start = centers[step.from_target]
    center = centers[step.to_target]
    axis = (center[0] - start[0], center[1] - start[1])
    unit = (axis[0] / math.hypot(*axis), axis[1] / math.hypot(*axis))
    perpendicular = (-unit[1], unit[0])
    endpoint = (center[0] + 50.0 * perpendicular[0], center[1] + 50.0 * perpendicular[1])

    record = build_selection_record(
        step,
        target_center=center,
        target_width=TARGET_WIDTH,
        cursor_start=start,
        cursor_end=endpoint,
        selection_time_ms=1000.0,
    )

    nominal = math.dist(start, center)
    amplitude, offset = movement_geometry(record, start, center)

    assert record.hit is False
    assert record.miss is True
    assert record.denominator_status == IN_DENOMINATOR

    # The amplitude is the chord, explicitly not the 2-D path length.
    assert amplitude == pytest.approx(nominal, abs=1e-9)
    assert amplitude != pytest.approx(math.hypot(nominal, 50.0), abs=1e-3)
    assert offset == pytest.approx(0.0, abs=1e-6)

    # A purely orthogonal endpoint contributes no spread, so a set built
    # only from orthogonal misses has SDx = 0 and must be rejected rather
    # than reported as We = 0 (which would imply infinite throughput).
    with pytest.raises(ValueError, match="effective width must be positive"):
        effective_width([offset, offset])

    # A single orthogonal endpoint cannot be spread-estimated at all.
    with pytest.raises(ValueError, match="at least two movements"):
        effective_width([offset])


def test_overshoot_and_undershoot_keep_their_sign():
    """Serial reciprocal movement preserves the sign of the axial offset.

    Overshoot, undershoot, overshoot-reverse and undershoot-reverse are
    all recorded as signed deviations. Taking the absolute value would
    inflate SDx for a symmetric spread and hide a directional bias.
    """

    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    start = centers["T0"]
    center = centers["T1"]

    expected = {
        "overshoot": 40.0,
        "undershoot": -25.0,
        "overshoot-reverse": 12.0,
        "undershoot-reverse": -8.0,
    }

    nominal = math.dist(start, center)

    for name, deviation in expected.items():
        endpoint = axis_step(start, center, deviation)
        record = build_selection_record(
            steps[1],
            target_center=center,
            target_width=TARGET_WIDTH,
            cursor_start=start,
            cursor_end=endpoint,
            selection_time_ms=1000.0,
        )
        amplitude, offset = movement_geometry(record, start, center)
        assert offset == pytest.approx(deviation, abs=1e-6), name

        # The sign test is what matters here; a_i stays nominal
        # regardless of the deviation, as section 5.13 requires.
        assert amplitude == pytest.approx(nominal, abs=1e-9), name


def test_effective_width_depends_on_spread_not_directional_bias():
    """We tracks endpoint spread and ignores a constant offset.

    A participant who consistently overshoots by the same amount has a
    high mean error but a small SDx. We must reflect the SDx alone, so a
    zero-spread set of biased endpoints is rejected instead of yielding
    an inflated width.
    """

    symmetric = effective_width([30.0, -30.0])

    assert symmetric == pytest.approx(4.133 * math.sqrt(1800.0), abs=1e-9)
    assert symmetric == pytest.approx(175.34834, abs=1e-5)

    with pytest.raises(ValueError, match="effective width must be positive"):
        effective_width([30.0, 30.0])


def build_partial_sequence(measured_endpoints):
    """Log only the first ``len(measured_endpoints)`` measured movements.

    ``log_sequence`` always logs a full ten-step sequence, so the tail
    is padded with target centres and then truncated. The truncation is
    safe because every record already carries its own observed
    ``cursor_start`` and ``cursor_end``.
    """
    targets = make_targets()
    centers, _ = label_map(targets)
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    # Derive the padding from the generator's own traversal rather than a
    # hard-coded ring, so this helper cannot silently drift away from the
    # sequence shape it is supposed to truncate.
    measured_labels = [step.to_target for step in steps if step.trial_role == MEASURED]
    padding = [centers[label] for label in measured_labels[len(measured_endpoints) :]]

    records, centers = build_sequence(list(measured_endpoints) + padding)
    return records[: 1 + len(measured_endpoints)], centers


# ---------------------------------------------------------------------------
# 9. Serial correction of section 5.13
#
# Movement ``i`` of a reciprocal sequence runs from the centre of
# ``order[i]`` to the centre of ``order[i + 1]``, where ``order`` is the
# near-opposite traversal ``[0, 4, 8, 3, 7, 2, 6, 1, 5, 0]``. The endpoint
# of movement 1 therefore sits on the axis ``T0 -> T4``, not ``T4 -> T8``.
# Every fixture below is built from that layout axis so the signed offset
# is exact rather than approximate.
# ---------------------------------------------------------------------------

CHORD = TRAVERSAL_CHORD


def test_serial_correction_carries_offset_into_next_movement():
    """Ae_i = a_i + dx_i + dx_{i-1}, so one overshoot widens the next move.

    Proposal section 5.13 fixes Ae_1 = a_1 + dx_1 and
    Ae_i = a_i + dx_i + dx_{i-1}. A single +30px overshoot on movement 1
    must therefore lengthen movement 1 by 30px and leave movement 2
    lengthened by the inherited +30px, while movement 3 inherits the
    zero offset of movement 2 and only carries its own -10px.
    """

    targets = make_targets()
    centers, _ = label_map(targets)

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == MEASURED]

    endpoints = [
        axis_step(
            centers[measured_steps[i].from_target],
            centers[measured_steps[i].to_target],
            offset_value,
        )
        for i, offset_value in enumerate([30.0, 0.0, -10.0])
    ]
    records, centers = build_partial_sequence(endpoints)

    # This fixture is a whole 3-transition sequence, so the trusted
    # reference count has to say so; without it the block cannot be shown
    # to be anything but a fragment.
    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=len(endpoints),
    )

    assert [t.nominal_amplitude_px for t in result.terms] == pytest.approx(
        [CHORD] * 3, rel=1e-9
    )
    assert [t.endpoint_offset_px for t in result.terms] == pytest.approx(
        [30.0, 0.0, -10.0], abs=1e-6
    )

    # Ae_1 = a + dx_1, Ae_2 = a + dx_2 + dx_1, Ae_3 = a + dx_3 + dx_2.
    assert result.terms[0].effective_amplitude_px == pytest.approx(
        CHORD + 30.0, rel=1e-9
    )
    assert result.terms[1].effective_amplitude_px == pytest.approx(
        CHORD + 30.0, rel=1e-9
    )
    assert result.terms[2].effective_amplitude_px == pytest.approx(
        CHORD - 10.0, rel=1e-9
    )

    # The mean of the three terms is the chord plus 50/3 px.
    assert result.mean_effective_amplitude_px == pytest.approx(
        CHORD + 50.0 / 3.0, rel=1e-9
    )


def test_serial_correction_sums_own_and_inherited_offsets():
    """Section 5.13 adds dx_i and dx_{i-1} for every i > 1.

    The frozen equation is Ae_i = a_i + dx_i + dx_{i-1}, so a later
    movement carries both its own endpoint offset and the inherited one.
    Movement 2 overshoots by +30 after a centred movement 1, so its own
    offset and the inherited zero are each visible: the amplitude is the
    chord plus 30, never the chord and never the chord minus 30.
    """

    targets = make_targets()
    centers, _ = label_map(targets)

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == MEASURED]

    endpoints = [
        axis_step(
            centers[measured_steps[i].from_target],
            centers[measured_steps[i].to_target],
            offset_value,
        )
        for i, offset_value in enumerate([0.0, 30.0])
    ]
    records, centers = build_partial_sequence(endpoints)

    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=len(endpoints),
    )

    assert result.terms[1].endpoint_offset_px == pytest.approx(
        30.0, abs=1e-6
    )
    assert result.terms[1].effective_amplitude_px == pytest.approx(
        CHORD + 30.0, rel=1e-9
    )
    # The superseded shortcut that ignored dx_i would report the bare
    # chord here, and the older subtractive form would report chord-30.
    assert result.terms[1].effective_amplitude_px != pytest.approx(
        CHORD, rel=1e-6
    )
    assert result.terms[1].effective_amplitude_px != pytest.approx(
        CHORD - 30.0, rel=1e-6
    )



def test_serial_correction_never_inherits_the_acquisition_offset():
    """dx_0 is zero, because the acquisition is not a measured movement.

    Section 5.13 indexes the serial correction over measured movements
    only, so the endpoint of the initial acquisition must never become
    the inherited offset of movement 1. Movement 1 is centred here, so
    any leakage would show up as ``Ae_1 = a + dx_0`` instead of ``a``.
    """

    targets = make_targets()
    centers, widths = label_map(targets)

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == MEASURED]

    spread = [0.0, 12.0, -8.0, 4.0, -4.0, 0.0, 9.0, -9.0, 3.0]
    cursor_ends = [
        axis_step(
            centers[step.from_target],
            centers[step.to_target],
            spread[i],
        )
        for i, step in enumerate(measured_steps)
    ]
    # The acquisition stops 5px short of the first centre: a real hit
    # that is logged, but is not a measured transition.
    cursor_ends.insert(0, axis_step(CENTER, centers["T0"], 5.0))

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=CENTER,
        cursor_ends=cursor_ends,
        selection_times_ms=[500.0] + [1000.0] * len(measured_steps),
    )

    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=len(measured_steps),
    )

    assert result.terms[0].endpoint_offset_px == pytest.approx(0.0, abs=1e-6)
    assert result.terms[0].effective_amplitude_px == pytest.approx(
        CHORD, rel=1e-9
    )
    # dx_0 must not leak in as a shifted Ae_1 for every later movement.
    assert [t.effective_amplitude_px for t in result.terms[1:]] == pytest.approx(
        [
            CHORD + 12.0 + 0.0,
            CHORD - 8.0 + 12.0,
            CHORD + 4.0 - 8.0,
            CHORD - 4.0 + 4.0,
            CHORD + 0.0 - 4.0,
            CHORD + 9.0 + 0.0,
            CHORD - 9.0 + 9.0,
            CHORD + 3.0 - 9.0,
        ],
        rel=1e-9,
    )


def test_difficulty_is_sequence_level_not_mean_of_movements():
    """ID_e = log2(mean(Ae)/We + 1), not mean(log2(Ae_i/We + 1)).

    log2 is concave, so averaging per-movement difficulties biases the
    result whenever the effective amplitudes vary. Section 5.13 defines
    difficulty once per sequence, and the two definitions must not
    coincide on a deliberately uneven sequence.
    """

    targets = make_targets()
    centers, _ = label_map(targets)

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == MEASURED]

    offsets = [0.0, 40.0, -40.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    endpoints = [
        axis_step(
            centers[measured_steps[i].from_target],
            centers[measured_steps[i].to_target],
            offsets[i],
        )
        for i in range(9)
    ]
    records, centers = build_sequence(endpoints)

    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=TARGET_COUNT,
    )

    expected_id = math.log2(
        result.mean_effective_amplitude_px / result.effective_width_px + 1.0
    )

    assert result.index_of_difficulty_bits == pytest.approx(
        expected_id, rel=1e-12
    )

    per_movement_mean = sum(
        math.log2(
            term.effective_amplitude_px / result.effective_width_px + 1.0
        )
        for term in result.terms
    ) / len(result.terms)

    assert result.index_of_difficulty_bits != pytest.approx(
        per_movement_mean, rel=1e-6
    )
    # Concavity makes the per-movement mean the smaller of the two.
    assert per_movement_mean < result.index_of_difficulty_bits


def test_zero_effective_width_is_rejected_not_substituted():
    """We = 0 must flag the sequence, never fabricate a fallback width.

    Section 5.13 forbids substituting an ad hoc value when We = 0 or the
    movement time is invalid; the sequence is flagged for audit instead.
    A constant +20px overshoot on every movement gives SDx = 0, so the
    call must raise rather than invent a width from the nominal radius.
    """

    targets = make_targets()
    centers, _ = label_map(targets)

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == MEASURED]
    endpoints = [
        axis_step(
            centers[step.from_target], centers[step.to_target], 20.0
        )
        for step in measured_steps
    ]
    records, centers = build_sequence(endpoints)
    assert find_sequence_breaks(records) == []

    with pytest.raises(ValueError, match="effective width must be positive"):
        sequence_throughput(
            records,
            centers,
            sequence_id="s1",
            expected_measured_transitions=TARGET_COUNT,
        )


def test_incomplete_sequence_is_refused_before_pooling():
    """A gap in the measured run must stop the computation.

    Section 5.13 treats a sequence broken by a technical failure as
    incomplete, to be handled by the frozen missing/repeat rule. The
    movements either side of the gap are separate blocks, so pooling
    them would corrupt both the effective width and the mean movement
    time. The entry point must refuse rather than rely on every caller
    remembering to run ``find_sequence_breaks`` first.
    """

    targets = make_targets()
    centers, _ = label_map(targets)

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == MEASURED]

    spread = [0.0, 12.0, -8.0, 4.0, -4.0, 0.0, 9.0, -9.0, 3.0]
    full, centers = build_sequence(
        [
            axis_step(
                centers[step.from_target],
                centers[step.to_target],
                spread[i],
            )
            for i, step in enumerate(measured_steps)
        ]
    )

    assert is_contiguous_sequence(full) is True

    # Trial 3 never reached the participant, so the measured run splits
    # into two independent blocks at trial 4.
    gapped = [record for record in full if record.trial_index != 3]

    assert find_sequence_breaks(gapped) == [4]
    assert is_contiguous_sequence(gapped) is False

    with pytest.raises(ValueError, match="INTERNAL_GAP"):
        sequence_throughput(
            gapped,
            centers,
            sequence_id="s1",
            expected_measured_transitions=TARGET_COUNT,
        )

    # The intact sequence still computes, so the guard is specific.
    assert (
        sequence_throughput(
            full,
            centers,
            sequence_id="s1",
            expected_measured_transitions=TARGET_COUNT,
        ).measured_count
        == 9
    )


def test_miss_endpoint_still_corrects_the_following_movement():
    """A miss keeps its endpoint, and that endpoint feeds Ae_{i+1}.

    Section 5.13 and the frozen task design both require that a miss is
    recorded and that the cursor is not teleported afterwards, so the
    overshoot that produced the miss must still be visible in the next
    movement's effective amplitude.
    """

    targets = make_targets()
    centers, _ = label_map(targets)

    # A 50px overshoot is past the 32px tolerance, so this is a miss.
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == MEASURED]

    endpoints = [
        axis_step(
            centers[measured_steps[i].from_target],
            centers[measured_steps[i].to_target],
            offset_value,
        )
        for i, offset_value in enumerate([50.0, 0.0])
    ]
    records, centers = build_partial_sequence(endpoints)

    assert records[1].miss is True
    assert records[1].denominator_status == IN_DENOMINATOR
    assert records[1].selection_time_ms == pytest.approx(1000.0)

    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=len(endpoints),
    )

    assert result.miss_count == 1
    assert result.measured_count == 2
    assert result.terms[1].effective_amplitude_px == pytest.approx(
        CHORD + 50.0, rel=1e-9
    )
    # The miss is retained in the time denominator, not dropped.
    assert result.mean_movement_time_ms == pytest.approx(1000.0, rel=1e-12)


