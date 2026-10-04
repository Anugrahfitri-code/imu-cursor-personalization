"""Numeric audit of ``SPREAD_TOLERANCE`` and effective width.

``SPREAD_TOLERANCE`` is a *roundoff* guard, not a scientific threshold.
It exists to catch a constant overshoot, whose endpoints differ only in
the last float bits, and to keep a zero effective width from producing
an infinite index of difficulty. It must never discard a spread that is
small but numerically real, must never be silently substituted by an
epsilon, and must be invariant to where the layout sits on screen and
to the spatial unit used.

Every expected number below is written out longhand so the arithmetic
can be checked by hand against the values quoted in review.
"""

from __future__ import annotations

import math

import pytest

from pc.experiment.task.reciprocal import generate_reciprocal_sequence
from pc.experiment.task.selection import log_sequence
from pc.experiment.task.targets import generate_circular_targets
from pc.experiment.task.throughput import (
    EFFECTIVE_WIDTH_FACTOR,
    SPREAD_TOLERANCE,
    SequenceThroughput,
    effective_width,
    movement_geometry,
    sequence_throughput,
    standard_deviation,
)


def build_sequence(origin, factor=1.0, seed=11):
    """A complete, non-degenerate 9-trial sequence at ``origin``.

    ``factor`` scales every spatial quantity, including the screen, so
    the layout stays valid and the result must be unit-invariant.
    """
    origin = (origin[0] * factor, origin[1] * factor)
    targets = generate_circular_targets(
        screen_width=4000.0 * factor,
        screen_height=4000.0 * factor,
        center=origin,
        radius=260.0 * factor,
        target_count=9,
        target_width=64.0 * factor,
        seed=seed,
        jitter_px=0.0,
    )
    centers = {f"T{t.target_id}": (t.x, t.y) for t in targets}
    widths = {f"T{t.target_id}": t.width for t in targets}
    centers["CENTER"] = origin
    widths["CENTER"] = 64.0 * factor

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    offsets = [2.0, -14.0, 9.0, 3.0, -5.0, 18.0, -7.0, 4.0, -11.0]

    def on_axis(a, b, d):
        axis = (b[0] - a[0], b[1] - a[1])
        length = math.hypot(*axis)
        return (b[0] + d * axis[0] / length, b[1] + d * axis[1] / length)

    ends = [on_axis(origin, centers[steps[0].to_target], 4.0 * factor)]
    previous = centers[steps[0].to_target]
    for step, d in zip(steps[1:], offsets):
        stop = centers[step.to_target]
        ends.append(on_axis(previous, stop, d * factor))
        previous = stop

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=origin,
        cursor_ends=ends,
        selection_times_ms=[0.0] + [820.0] * 9,
    )
    return records, centers, factor


# ---------------------------------------------------------------------------
# 1. The constant and the branch that uses it
# ---------------------------------------------------------------------------


def test_the_constant_is_a_relative_floor_not_an_absolute_one():
    """The branch is ``sd <= SPREAD_TOLERANCE * scale``, i.e. scale-free."""
    assert SPREAD_TOLERANCE == 1e-9

    offsets = [3.0, 3.0, 3.0, 3.0]
    sd = standard_deviation(offsets)
    scale = max(abs(value) for value in offsets)

    assert scale == 3.0
    assert sd <= SPREAD_TOLERANCE * scale
    assert SPREAD_TOLERANCE * scale == pytest.approx(3e-9, rel=1e-12)


def test_the_tolerance_is_far_below_any_participant_visible_spread():
    """1e-9 is nine orders below a 1px spread: it cannot hide behaviour."""
    assert 1e-9 < 1.0 / 1e6


# ---------------------------------------------------------------------------
# 2. Identical offsets give a clear numerical-degeneracy status
# ---------------------------------------------------------------------------


def test_identical_offsets_are_refused_with_an_explicit_reason():
    with pytest.raises(ValueError) as excinfo:
        effective_width([12.0, 12.0, 12.0, 12.0])

    message = str(excinfo.value)

    assert "effective width must be positive" in message
    # The message reports the numbers, not a vague "bad data".
    assert "offset_sd" in message
    assert "scale" in message


def test_zero_offsets_are_refused_too():
    with pytest.raises(ValueError, match="effective width must be positive"):
        effective_width([0.0, 0.0, 0.0])


def test_constant_overshoot_differs_only_in_the_last_float_bits():
    """The physical case the tolerance exists for.

    A *constant* overshoot is computed as ``(nominal + 0.1) - nominal``
    for nine different nominals. In binary floating point each of those
    loses a different amount in the last bits, so the offsets are equal
    in intent but not in representation. The resulting spread is real
    but numerically meaningless, and must not become a tiny ``We``.
    """
    nominals = [100.0 * (index + 1) for index in range(9)]
    offsets = [(nominal + 0.1) - nominal for nominal in nominals]

    sd = standard_deviation(offsets)
    scale = max(abs(value) for value in offsets)

    assert len(set(offsets)) > 1        # not bit-identical ...
    assert sd < 1e-12                  # ... but far below 1px
    assert sd <= SPREAD_TOLERANCE * scale

    with pytest.raises(ValueError, match="effective width must be positive"):
        effective_width(offsets)
# ---------------------------------------------------------------------------
# 3. We is never replaced by an epsilon
# ---------------------------------------------------------------------------


def test_we_is_computed_from_sd_and_never_from_epsilon():
    """The only place a width is produced is ``FACTOR * SDx``."""
    offsets = [-6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0]

    # Hand check: sum = 0, sum of squares = 36 + 36 = 72.
    # Sample variance = 72 / (9 - 1) = 9; SDx = 3 exactly.
    assert standard_deviation(offsets) == pytest.approx(3.0, rel=1e-12)

    width = effective_width(offsets)

    assert width == pytest.approx(EFFECTIVE_WIDTH_FACTOR * 3.0, rel=1e-12)
    assert width == pytest.approx(12.399, rel=1e-12)
    # Not the tolerance, not an epsilon, not the target width.
    assert width != pytest.approx(SPREAD_TOLERANCE)
    assert width != pytest.approx(1e-9)
    assert width != pytest.approx(64.0)


def test_shrinking_a_real_spread_shrinks_we_proportionally():
    """``We`` tracks ``SDx``; no floor is quietly applied underneath."""
    wide = effective_width([-60.0, 60.0])
    narrow = effective_width([-6.0, 6.0])

    # Two samples: sample variance = (3600 + 3600) / 1 = 7200.
    assert wide == pytest.approx(4.133 * math.sqrt(7200.0), rel=1e-12)
    assert narrow == pytest.approx(4.133 * math.sqrt(72.0), rel=1e-12)
    assert wide == pytest.approx(10 * narrow, rel=1e-12)


# ---------------------------------------------------------------------------
# 4. Small but real variation is not silently discarded
# ---------------------------------------------------------------------------


def test_a_millipixel_spread_still_produces_a_real_width():
    """0.001px is six orders above the tolerance and must survive."""
    offsets = [-0.001, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.001]

    # Sum of squares = 2e-6; sample variance = 2e-6 / 8 = 2.5e-7;
    # SDx = sqrt(2.5e-7) = 0.0005 exactly.
    sd = standard_deviation(offsets)
    assert sd == pytest.approx(5.0e-4, rel=1e-6)

    width = effective_width(offsets)
    assert width == pytest.approx(4.133 * 5.0e-4, rel=1e-6)
    assert width == pytest.approx(2.0665e-3, rel=1e-6)


def test_spread_just_above_the_guard_passes_and_just_below_is_refused():
    base = 1000.0
    tiny = SPREAD_TOLERANCE * base

    with pytest.raises(ValueError, match="effective width must be positive"):
        effective_width([base, base + tiny * 0.5])

    assert effective_width([base, base + tiny * 4.0]) > 0.0


# ---------------------------------------------------------------------------
# 5. Translation invariance
# ---------------------------------------------------------------------------


class _Geometry:
    """Minimal stand-in for a record; ``movement_geometry`` needs only
    ``trial_index`` and ``cursor_end``."""

    __slots__ = ("trial_index", "cursor_end")

    def __init__(self, x, y):
        self.trial_index = 1
        self.cursor_end = (x, y)


def test_translating_the_layout_does_not_change_the_offsets():
    """Offsets are differences, so absolute coordinate size is irrelevant."""
    centers_a = ((960.0, 540.0), (1472.1, 540.0))
    centers_b = ((9600.0, 5400.0), (10112.1, 5400.0))

    # The same physical endpoint, expressed in each layout's coordinates.
    _, offset_a = movement_geometry(_Geometry(1479.1, 540.0), *centers_a)
    _, offset_b = movement_geometry(_Geometry(10119.1, 5400.0), *centers_b)

    assert offset_a == pytest.approx(offset_b, rel=1e-12)
    assert offset_a == pytest.approx(7.0, rel=1e-9)


def test_translating_the_layout_far_away_does_not_change_the_verdict():
    """A translated but non-degenerate sequence still pools, identically."""
    small_records, small_centers, _ = build_sequence((960.0, 540.0))
    big_records, big_centers, _ = build_sequence((3600.0, 3600.0))

    small = sequence_throughput(
        small_records, small_centers, sequence_id="s1",
        expected_measured_transitions=9,
    )
    big = sequence_throughput(
        big_records, big_centers, sequence_id="s1",
        expected_measured_transitions=9,
    )

    assert big.endpoint_offset_sd_px == pytest.approx(
        small.endpoint_offset_sd_px, rel=1e-9
    )
    assert big.effective_width_px == pytest.approx(
        small.effective_width_px, rel=1e-9
    )
    assert big.throughput_bits_per_second == pytest.approx(
        small.throughput_bits_per_second, rel=1e-9
    )


# ---------------------------------------------------------------------------
# 6. Consistent spatial unit change preserves TP
# ---------------------------------------------------------------------------


def test_scaling_the_layout_scales_ae_and_we_alike_and_preserves_tp():
    """TP is a ratio: a consistent change of spatial unit cancels out."""
    offsets = [-6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0]
    factor = 4.0

    width = effective_width(offsets)
    width_scaled = effective_width([v * factor for v in offsets])

    amplitude = 512.100031566
    index = math.log2(amplitude / width + 1.0)
    index_scaled = math.log2((amplitude * factor) / width_scaled + 1.0)

    assert width_scaled == pytest.approx(factor * width, rel=1e-12)
    assert index_scaled == pytest.approx(index, rel=1e-12)

    # Throughput is per second, so it is untouched by the unit change.
    mean_ms = 820.0
    assert index_scaled / (mean_ms / 1000.0) == pytest.approx(
        index / (mean_ms / 1000.0), rel=1e-12
    )


def test_end_to_end_unit_change_preserves_the_reported_tp():
    """The same check through the real generator, logger and estimator."""
    small_records, small_centers, _ = build_sequence((960.0, 540.0))
    big_records, big_centers, _ = build_sequence((960.0, 540.0), factor=4.0)

    small = sequence_throughput(
        small_records, small_centers, sequence_id="s1",
        expected_measured_transitions=9,
    )
    big = sequence_throughput(
        big_records, big_centers, sequence_id="s1",
        expected_measured_transitions=9,
    )

    assert big.effective_width_px == pytest.approx(
        4.0 * small.effective_width_px, rel=1e-9
    )
    assert big.mean_effective_amplitude_px == pytest.approx(
        4.0 * small.mean_effective_amplitude_px, rel=1e-9
    )
    assert big.index_of_difficulty_bits == pytest.approx(
        small.index_of_difficulty_bits, rel=1e-9
    )
    assert big.throughput_bits_per_second == pytest.approx(
        small.throughput_bits_per_second, rel=1e-9
    )


# ---------------------------------------------------------------------------
# 7. Full worked numbers for a reported throughput
# ---------------------------------------------------------------------------


def worked_example(offsets, amplitude, mean_time_ms):
    """Assemble a SequenceThroughput from explicit numbers."""
    sd = standard_deviation(offsets)
    width = effective_width(offsets)
    index = math.log2(amplitude / width + 1.0)

    return SequenceThroughput(
        sequence_id="worked-example",
        effective_width_px=width,
        endpoint_offset_sd_px=sd,
        mean_effective_amplitude_px=amplitude,
        index_of_difficulty_bits=index,
        mean_movement_time_ms=mean_time_ms,
        throughput_bits_per_second=index / (mean_time_ms / 1000.0),
        measured_count=len(offsets),
        miss_count=0,
        terms=[],
    )


def test_worked_example_full_numbers():
    """The numbers behind a reported throughput, written out longhand.

    Offsets ``[-6, 0, 0, 0, 0, 0, 0, 0, 6]`` give, with ``Ae_i = a_i +
    dx_i + dx_{i-1}`` and the near-opposite chord ``a = 512.100032``:

        SDx  = sqrt(72 / 8)                    = 3.000000 px
        We   = 4.133 * 3.0                     = 12.399000 px
        Ae_1 = a - 6, Ae_2 = a - 6, Ae_9 = a + 6, the rest a
        Ae   = mean(Ae_i) = a - 6/9            = 511.433365 px
        ID_e = log2(511.433365 / 12.399 + 1)   = 5.400810 bits
        MT   = 820 ms
        TP   = 5.400810 / 0.820                = 6.586353 bits/s

    TP here is single-digit bits per second. No physically achievable
    Fitts dataset produces "tens of thousands of bits/s": at this index
    of difficulty that would need movement times far below one
    millisecond, which is not humanly possible.
    """
    result = worked_example(
        [-6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0],
        511.433364900,
        820.0,
    )

    assert result.endpoint_offset_sd_px == pytest.approx(3.0, rel=1e-12)
    assert result.effective_width_px == pytest.approx(12.399, rel=1e-12)
    assert result.mean_effective_amplitude_px == pytest.approx(
        511.433364900, rel=1e-12
    )
    assert result.index_of_difficulty_bits == pytest.approx(5.400810, abs=1e-6)
    assert result.mean_movement_time_ms == pytest.approx(820.0, rel=1e-12)
    assert result.throughput_bits_per_second == pytest.approx(6.586353, abs=1e-5)


def test_verification_fixture_full_numbers():
    """The harness fixture, quoted exactly.

    Offsets ``[2, -14, 9, 3, -5, 18, -7, 4, -11]``:

        sum    = -1
        sum sq = 4+196+81+9+25+324+49+16+121 = 825
        var    = (825 - (-1)^2/9) / 8 = (825 - 1/9) / 8 = 103.111111
        SDx    = sqrt(103.111111)           = 10.154364 px
        We     = 4.133 * 10.154364          = 41.967987 px
        sum dx_i     = -1        (i = 1..9)
        sum dx_{i-1} = 10        (dx_1 .. dx_8)
        Ae     = a + (-1 + 10)/9             = 513.100032 px
        ID_e   = log2(513.100032/41.967987 + 1) = 3.725303 bits
        TP     = 3.725303 / 0.820            = 4.543053 bits/s
    """
    result = worked_example(
        [2.0, -14.0, 9.0, 3.0, -5.0, 18.0, -7.0, 4.0, -11.0],
        513.100031566,
        820.0,
    )

    assert result.endpoint_offset_sd_px == pytest.approx(10.154364, abs=1e-6)
    assert result.effective_width_px == pytest.approx(
        EFFECTIVE_WIDTH_FACTOR * 10.154364, abs=1e-6
    )
    assert result.mean_effective_amplitude_px == pytest.approx(
        513.100032, abs=1e-6
    )
    assert result.index_of_difficulty_bits == pytest.approx(3.725303, abs=1e-6)
    assert result.throughput_bits_per_second == pytest.approx(4.543053, abs=1e-6)
