"""Reproducible Subtahap 2.8 verification harness.

Run with::

    python -m pc.experiment.tests.verify_fitts_28

Prints, for one deterministic 9-target layout:

* every generator parameter and the resolved target coordinates;
* the traversal the generator actually produced;
* a nine-row measured-transition table with amplitude, selection
  endpoint, own serial offset ``dx_i``, the inherited offset
  ``dx_{i-1}`` and effective amplitude ``Ae_i``, following the frozen
  section 5.13 rule ``Ae_1 = a_1 + dx_1`` and
  ``Ae_i = a_i + dx_i + dx_{i-1}`` for ``i > 1``;
* the sequence-level result.

Nothing here writes files; it exists so the numbers quoted in review
can be regenerated on demand.
"""

from __future__ import annotations

import math

from pc.experiment.task.reciprocal import (
    MEASURED,
    expected_measured_pairs,
    generate_reciprocal_sequence,
)
from pc.experiment.task.selection import log_sequence
from pc.experiment.task.targets import generate_circular_targets
from pc.experiment.task.throughput import movement_geometry, sequence_throughput

SCREEN_W = 1920.0
SCREEN_H = 1080.0
CENTER = (960.0, 540.0)
RING_RADIUS = 260.0
TARGET_WIDTH = 64.0
TARGET_COUNT = 9
SEED = 11
JITTER_PX = 0.0

# Deliberate axial offsets along the from->to axis. Small, mixed signs,
# non-degenerate spread.
OFFSETS_PX = [2.0, -14.0, 9.0, 3.0, -5.0, 18.0, -7.0, 4.0, -11.0]
SELECTION_TIMES_MS = [0.0] + [820.0] * TARGET_COUNT
START_POINT = (400.0, 300.0)


def label_map(targets):
    centers = {f"T{t.target_id}": (t.x, t.y) for t in targets}
    widths = {f"T{t.target_id}": t.width for t in targets}
    return centers, widths


def endpoint_along(start, stop, offset_px):
    axis_x = stop[0] - start[0]
    axis_y = stop[1] - start[1]
    norm = math.hypot(axis_x, axis_y)
    unit_x, unit_y = axis_x / norm, axis_y / norm
    return (stop[0] + offset_px * unit_x, stop[1] + offset_px * unit_y)


def fmt(value, digits=3):
    return f"{value:.{digits}f}"


def to_geometry(centers, widths, label):
    center = centers[label]
    width = widths[label]
    if not (width > 0.0) or not math.isfinite(center[0]):
        raise ValueError(f"degenerate target geometry for {label}")
    return center, width
def main() -> None:
    print("=" * 78)
    print("SUBTAHAP 2.8 VERIFICATION HARNESS")
    print("=" * 78)

    print("\n[1] GENERATOR PARAMETERS")
    print(f"  screen_width   = {SCREEN_W}")
    print(f"  screen_height  = {SCREEN_H}")
    print(f"  center         = {CENTER}")
    print(f"  radius         = {RING_RADIUS}")
    print(f"  target_count   = {TARGET_COUNT}")
    print(f"  target_width   = {TARGET_WIDTH}")
    print(f"  jitter_px      = {JITTER_PX}")
    print(f"  seed           = {SEED}")

    targets = generate_circular_targets(
        screen_width=SCREEN_W,
        screen_height=SCREEN_H,
        center=CENTER,
        radius=RING_RADIUS,
        target_count=TARGET_COUNT,
        target_width=TARGET_WIDTH,
        seed=SEED,
        jitter_px=JITTER_PX,
    )
    centers, widths = label_map(targets)
    centers["CENTER"] = START_POINT
    widths["CENTER"] = TARGET_WIDTH

    print("\n[2] TARGET COORDINATES (actual values from the generator)")
    print("  id   center_x       center_y       r_from_center   angle_deg")
    for target in targets:
        dx = target.x - CENTER[0]
        dy = target.y - CENTER[1]
        angle = math.degrees(math.atan2(dy, dx)) % 360.0
        print(
            f"  T{target.target_id}   {fmt(target.x, 6):>13} "
            f"{fmt(target.y, 6):>13}   {fmt(math.hypot(dx, dy), 6):>13}"
            f"   {fmt(angle, 4):>9}"
        )

    adjacent = 2.0 * RING_RADIUS * math.sin(math.pi / TARGET_COUNT)
    opposed = 2.0 * RING_RADIUS * math.cos(math.pi / (2.0 * TARGET_COUNT))
    print(f"\n  adjacent chord 2R sin(pi/N)  = {fmt(adjacent, 9)} px")
    print(f"  opposed  chord 2R cos(pi/N) = {fmt(opposed, 9)} px")

    steps = generate_reciprocal_sequence(targets, sequence_id="s1")

    print("\n[3] GENERATED TRAVERSAL (as emitted, before any measurement)")
    print("  trial  role            from  ->  to")
    for step in steps:
        print(
            f"  {step.trial_index:>5}  {step.trial_role:<14} "
            f"{step.from_target:>4} -> {step.to_target:>4}"
        )

    measured_steps = [s for s in steps if s.trial_role == "MEASURED"]
    if len(measured_steps) != len(OFFSETS_PX):
        raise AssertionError("offset list must match the measured block.")

    cursor_ends = [endpoint_along(START_POINT, centers[steps[0].to_target], 4.0)]
    for step, offset in zip(measured_steps, OFFSETS_PX):
        start = centers[step.from_target]
        stop = centers[step.to_target]
        cursor_ends.append(endpoint_along(start, stop, offset))

    records = log_sequence(
        steps,
        centers,
        widths,
        origin=START_POINT,
        cursor_ends=cursor_ends,
        selection_times_ms=SELECTION_TIMES_MS,
    )

    measured_transitions = len(
        [step for step in steps if step.trial_role == MEASURED]
    )
    # The reference count comes from the trusted plan, not from the number
    # of rows that happen to be logged: that is the whole point of the guard.
    assert measured_transitions == TARGET_COUNT, (
        f"plan declares {measured_transitions} measured transitions; "
        f"this harness verifies {TARGET_COUNT}."
    )

    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=measured_transitions,
        expected_pairs=expected_measured_pairs(targets),
    )
    ae_by_trial = {t.trial_index: t.effective_amplitude_px for t in result.terms}

    print("\n[4] MEASURED TRANSITION TABLE")
    header = (
        f"{'trial':>5} {'from':>4} {'from_center':>21} "
        f"{'to':>4} {'to_center':>21} {'a_i':>13} "
        f"{'endpoint':>21} {'dx_i':>8} {'dx_i-1':>8} {'Ae_i':>13}"
    )
    print(header)
    print("-" * len(header))
    previous_offset = 0.0
    for record in records:
        if record.trial_role != "MEASURED":
            continue
        from_xy = centers[record.from_target]
        to_xy = centers[record.to_target]
        from_center = f"({fmt(from_xy[0], 3)},{fmt(from_xy[1], 3)})"
        to_center = f"({fmt(to_xy[0], 3)},{fmt(to_xy[1], 3)})"
        endpoint = f"({fmt(record.endpoint_x, 3)},{fmt(record.endpoint_y, 3)})"
        nominal, offset = movement_geometry(record, from_xy, to_xy)
        print(
            f"{record.trial_index:>5} {record.from_target:>4} {from_center:>21} "
            f"{record.to_target:>4} {to_center:>21} {fmt(nominal, 6):>12} "
            f"{endpoint:>21} {offset:>8.3f} {previous_offset:>8.3f} "
            f"{fmt(ae_by_trial[record.trial_index], 6):>13}"
        )
        previous_offset = offset

    print("\n[5] SEQUENCE RESULT")
    print("  rule           = Ae_1 = a_1 + dx_1 ; "
          "Ae_i = a_i + dx_i + dx_{i-1} for i > 1 (dx_0 = 0)")
    print(f"  mean Ae_i       = {fmt(result.mean_effective_amplitude_px, 6)} px")
    print(f"  SDx            = {fmt(result.endpoint_offset_sd_px, 6)} px")
    print(f"  We             = {fmt(result.effective_width_px, 6)} px")
    print(f"  ID_e           = {fmt(result.index_of_difficulty_bits, 6)} bits")
    print(f"  mean MT        = {fmt(result.mean_movement_time_ms, 6)} ms")
    print(f"  TP             = {fmt(result.throughput_bits_per_second, 6)} bits/s")
    print(f"  measured / miss= {result.measured_count} / {result.miss_count}")
    print("=" * 78)


if __name__ == "__main__":
    main()