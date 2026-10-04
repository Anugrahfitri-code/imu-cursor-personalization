"""Round-trip proof for the trial-selection export.

The claim under test is narrow and checkable: a sequence logged by the
corrected path, exported to CSV and read back, yields the *same*
effective widths, serial-corrected amplitudes and throughput as the
in-memory records. If the export dropped the endpoint, the timestamp or
the target identity, the numbers would move.
"""

from __future__ import annotations

import math

import pytest

from pc.experiment.task.reciprocal import generate_reciprocal_sequence
from pc.experiment.task.selection import (
    EXCLUDED_INVALID_TIMESTAMP,
    log_sequence,
)
from pc.experiment.task.selection_io import (
    SELECTION_COLUMNS,
    read_selection_csv,
    selection_row,
    write_selection_csv,
)
from pc.experiment.task.targets import generate_circular_targets
from pc.experiment.task.throughput import audit_sequence, sequence_throughput

CENTER = (960.0, 540.0)
EXPECTED = 9

TARGETS = generate_circular_targets(
    screen_width=1920.0,
    screen_height=1080.0,
    center=CENTER,
    radius=260.0,
    target_count=EXPECTED,
    target_width=64.0,
    seed=11,
    jitter_px=0.0,
)
CENTERS = {f"T{t.target_id}": (t.x, t.y) for t in TARGETS}
WIDTHS = {f"T{t.target_id}": t.width for t in TARGETS}
CENTERS["CENTER"] = CENTER
WIDTHS["CENTER"] = 64.0
STEPS = generate_reciprocal_sequence(TARGETS, sequence_id="s1")

OFFSETS_PX = [2.0, -14.0, 9.0, 3.0, -5.0, 18.0, -7.0, 4.0, -11.0]


def on_axis(start, stop, distance):
    axis = (stop[0] - start[0], stop[1] - start[1])
    length = math.hypot(*axis)
    return (stop[0] + distance * axis[0] / length, stop[1] + distance * axis[1] / length)


def build_records(offsets=OFFSETS_PX, times=None):
    ends = [on_axis(CENTER, CENTERS[STEPS[0].to_target], 4.0)]
    previous = CENTERS[STEPS[0].to_target]

    for step, offset in zip(STEPS[1:], offsets):
        stop = CENTERS[step.to_target]
        ends.append(on_axis(previous, stop, offset))
        previous = stop

    if times is None:
        times = [0.0] + [820.0] * EXPECTED

    return log_sequence(
        STEPS,
        CENTERS,
        WIDTHS,
        origin=CENTER,
        cursor_ends=ends,
        selection_times_ms=times,
    )


def score(records):
    return sequence_throughput(
        records,
        CENTERS,
        sequence_id="s1",
        expected_measured_transitions=EXPECTED,
    )
def test_export_keeps_both_centres_the_endpoint_and_the_identity():
    record = build_records()[1]
    row = selection_row(record, CENTERS)

    assert tuple(row.keys()) == SELECTION_COLUMNS

    assert row["sequence_id"] == "s1"
    assert row["trial_index"] == 1
    assert row["trial_role"] == "MEASURED"
    assert row["from_target"] == "T0"
    assert row["to_target"] == "T4"

    # Both target centres survive.
    assert row["from_center_x_px"] == CENTERS["T0"][0]
    assert row["from_center_y_px"] == CENTERS["T0"][1]
    assert row["to_center_x_px"] == CENTERS["T4"][0]
    assert row["to_center_y_px"] == CENTERS["T4"][1]

    # The real endpoint, not a derived error.
    assert row["endpoint_x_px"] == pytest.approx(record.endpoint_x, rel=1e-12)
    assert row["endpoint_y_px"] == pytest.approx(record.endpoint_y, rel=1e-12)
    assert row["cursor_end_x_px"] == pytest.approx(record.cursor_end[0], rel=1e-12)
    assert row["cursor_end_y_px"] == pytest.approx(record.cursor_end[1], rel=1e-12)

    assert row["selection_time_ms"] == pytest.approx(820.0, rel=1e-12)
    assert row["denominator_status"] == "IN_DENOMINATOR"
    assert row["hit"] is True
    assert row["miss"] is False


def test_round_trip_reproduces_the_throughput_exactly(tmp_path):
    records = build_records()
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    assert len(restored) == len(records)

    original = score(records)
    replayed = score(restored)

    assert replayed.effective_width_px == original.effective_width_px
    assert replayed.endpoint_offset_sd_px == original.endpoint_offset_sd_px
    assert replayed.mean_effective_amplitude_px == original.mean_effective_amplitude_px
    assert replayed.index_of_difficulty_bits == original.index_of_difficulty_bits
    assert replayed.throughput_bits_per_second == original.throughput_bits_per_second
    assert replayed.miss_count == original.miss_count


def test_round_trip_preserves_every_field(tmp_path):
    records = build_records()
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    for before, after in zip(records, restored):
        assert after == before


def test_round_trip_preserves_a_miss_and_its_overshoot(tmp_path):
    """A miss keeps its endpoint, so the next Ae still sees the overshoot."""
    records = build_records(
        offsets=[50.0, 0.0, -10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    assert any(record.miss for record in records)

    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    original = score(records)
    replayed = score(restored)

    assert replayed.miss_count == original.miss_count
    assert replayed.endpoint_offset_sd_px == original.endpoint_offset_sd_px
    assert replayed.mean_effective_amplitude_px == original.mean_effective_amplitude_px


def test_round_trip_preserves_an_invalid_timestamp_marker(tmp_path):
    times = [0.0] + [820.0] * EXPECTED
    times[4] = None

    records = build_records(times=times)
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    excluded = next(r for r in restored if r.trial_index == 4)

    assert excluded.selection_time_ms is None
    assert excluded.denominator_status == "EXCLUDED_INVALID_TIMESTAMP"

    # ... and the truncation is still visible to the completeness audit.
    assert (
        audit_sequence(
            restored,
            expected_measured_transitions=EXPECTED,
            expected_sequence_id="s1",
        ).status
        == "INTERNAL_GAP"
    )


def test_reading_against_a_different_layout_is_refused(tmp_path):
    """A row exported against one layout cannot be replayed on another."""
    records = build_records()
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)

    moved = {label: (x + 5.0, y + 5.0) for label, (x, y) in CENTERS.items()}

    with pytest.raises(ValueError, match="different layout"):
        read_selection_csv(path, moved)


# ---------------------------------------------------------------------------
# Contradictory endpoint pairs must not survive the reader
# ---------------------------------------------------------------------------


def rewrite_one_field(tmp_path, records, field, value, row_index=3):
    """Re-export, then edit one cell of one row in place.

    Everything else -- layout, target identity, column order -- is untouched,
    so a reader that accepts the result is accepting a contradiction rather
    than a differently-parameterised layout.
    """
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header = lines[0].split(",")
    cells = lines[row_index + 1].split(",")
    cells[header.index(field)] = str(value)
    lines[row_index + 1] = ",".join(cells)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_endpoint_fields_are_the_same_point_by_construction():
    """The scalar pair and the tuple are written from one source.

    ``selection_row`` copies ``record.cursor_end`` into both pairs, so the
    two encodings cannot legitimately disagree.
    """
    for record in build_records():
        assert (record.endpoint_x, record.endpoint_y) == record.cursor_end


def test_shifted_endpoint_x_is_rejected(tmp_path):
    """The audit finding: only ``endpoint_x_px`` moved, by 100 px.

    ``cursor_end_x_px`` -- the field the estimator actually consumes -- was
    left alone, so before this guard the row re-analysed as if nothing had
    been edited.
    """
    records = build_records()
    path = rewrite_one_field(
        tmp_path, records, "endpoint_x_px", records[3].endpoint_x + 100.0
    )

    with pytest.raises(ValueError, match="contradictory endpoint fields"):
        read_selection_csv(path, CENTERS)


def test_shifted_endpoint_y_is_rejected(tmp_path):
    records = build_records()
    path = rewrite_one_field(
        tmp_path, records, "endpoint_y_px", records[3].endpoint_y - 100.0
    )

    with pytest.raises(ValueError, match="contradictory endpoint fields"):
        read_selection_csv(path, CENTERS)


def test_contradiction_is_reported_before_the_layout_check(tmp_path):
    """Both the endpoint pair and the layout are wrong; the pair is named.

    The message must identify the specific contradiction rather than only
    reporting whichever check happens to run first.
    """
    records = build_records()
    path = rewrite_one_field(
        tmp_path, records, "endpoint_x_px", records[3].endpoint_x + 100.0
    )

    with pytest.raises(ValueError) as info:
        read_selection_csv(path, CENTERS)

    message = str(info.value)
    assert "endpoint_x_px" in message
    assert "cursor_end_x_px" in message
    assert str(int(records[3].trial_index)) in message


def test_a_conflicting_row_cannot_reach_the_estimator(tmp_path):
    """End to end: the contradiction is refused before any throughput."""
    records = build_records()
    path = rewrite_one_field(
        tmp_path, records, "endpoint_x_px", records[3].endpoint_x + 100.0
    )

    with pytest.raises(ValueError, match="contradictory endpoint fields"):
        restored = read_selection_csv(path, CENTERS)
        score(restored)


def test_a_one_ulp_difference_is_still_accepted(tmp_path):
    """The guard uses a numeric tolerance, not exact string equality.

    ``repr`` round-trips a float exactly, so the tolerance only has to absorb
    a full-precision rewrite of the same number -- it must not reject it.
    """
    records = build_records()
    nudged = math.nextafter(records[2].endpoint_x, math.inf)
    assert nudged != records[2].endpoint_x
    path = rewrite_one_field(tmp_path, records, "endpoint_x_px", nudged, row_index=2)

    restored = read_selection_csv(path, CENTERS)
    assert restored[2].endpoint_x == nudged


def test_clean_round_trip_is_unaffected(tmp_path):
    """The guard must not cost the baseline a single bit per second."""
    records = build_records()
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    assert score(restored).throughput_bits_per_second == (
        score(records).throughput_bits_per_second
    )


def test_full_path_reproduces_the_published_baseline(tmp_path):
    """log -> export -> read -> validate -> throughput, exact figures.

    Pins the two numbers quoted in the stage 2.8 report so that a change to
    the reader, the guard, or the estimator cannot move them silently.

    The report rounds ``mean Ae`` to ``513.1000315663482`` and prints TP as
    ``4.543053``; the unrounded quotient is ``4.543052927725114``, i.e. the
    quoted ``4.54305292772511`` to 14 significant digits. Both the exact float
    and the quoted value are asserted, so a real change fails while ordinary
    last-digit float formatting cannot.
    """
    records = build_records()
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)
    result = score(restored)

    assert result.mean_effective_amplitude_px == 513.1000315663482
    assert result.throughput_bits_per_second == 4.543052927725114
    assert result.throughput_bits_per_second == pytest.approx(
        4.54305292772511, rel=1e-14
    )
    assert round(result.throughput_bits_per_second, 6) == 4.543053


def test_full_path_stays_complete_after_round_trip(tmp_path):
    """Validation is not weakened by the round trip either."""
    records = build_records()
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    audit = audit_sequence(
        restored, expected_measured_transitions=EXPECTED
    )
    assert audit.status == audit_sequence(
        records, expected_measured_transitions=EXPECTED
    ).status


def test_miss_rows_survive_the_round_trip(tmp_path):
    """A miss keeps its real endpoint; it is never snapped to a centre.

    ``hit`` is derived from the endpoint distance to the target centre, so the
    miss is produced by logging a genuinely off-target endpoint through
    :func:`log_sequence`. Editing the flag afterwards would be circular: the
    exporter would just write back whatever flag was set.
    """
    ends = [on_axis(CENTER, CENTERS[STEPS[0].to_target], 4.0)]
    outside = (120.0, 80.0)
    ends.append(outside)  # trial 1 lands nowhere near a target
    previous = CENTERS[STEPS[1].to_target]
    for step in STEPS[2:]:
        ends.append(on_axis(previous, CENTERS[step.to_target], 3.0))
        previous = CENTERS[step.to_target]

    records = log_sequence(
        STEPS,
        CENTERS,
        WIDTHS,
        origin=CENTER,
        cursor_ends=ends,
        selection_times_ms=[0.0] + [820.0] * EXPECTED,
    )
    assert records[1].miss is True  # the miss is real before export

    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    assert restored[1].miss is True
    assert restored[1].hit is False
    assert restored[1].cursor_end == outside
    assert (restored[1].endpoint_x, restored[1].endpoint_y) == outside
    # the next trial starts where the miss really ended
    assert restored[2].cursor_start == outside
    # and every other row is still a hit
    assert [r.miss for r in restored] == [r.miss for r in records]


def test_a_miss_excluded_row_keeps_its_reason(tmp_path):
    """Excluded rows are not deleted; the reason survives the round trip."""
    records = build_records(times=[None] * (EXPECTED + 1))
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)
    restored = read_selection_csv(path, CENTERS)

    failed = [r for r in restored if r.selection_time_ms is None]
    assert len(failed) == EXPECTED + 1  # nothing was dropped
    # Each row keeps its own reason: the acquisition row is excluded for its
    # role, the measured rows for the unusable duration. Neither is silently
    # folded into a generic "missing" bucket.
    assert {r.denominator_status for r in failed} == {
        "EXCLUDED_INITIAL_ACQUISITION",
        EXCLUDED_INVALID_TIMESTAMP,
    }


# ---------------------------------------------------------------------------
# The legacy stage 2.8 row schema, for contrast
# ---------------------------------------------------------------------------


def test_frozen_28_schema_still_cannot_carry_the_endpoint():
    """Why the corrected path needed its own export.

    ``TRIAL_COLUMNS`` keeps the *derived* errors but never the raw
    endpoint, so a frozen-schema row cannot be turned back into a
    ``SelectionRecord`` and cannot be re-analysed by the throughput
    estimator.
    """
    from pc.experiment.task.schema import TRIAL_COLUMNS

    assert "endpoint_x_px" not in TRIAL_COLUMNS
    assert "endpoint_y_px" not in TRIAL_COLUMNS
    assert "sequence_id" not in TRIAL_COLUMNS

    # It does keep the derived axial error, which is not the same thing:
    # it loses the perpendicular component and the endpoint itself.
    assert "signed_axial_error_px" in TRIAL_COLUMNS
    assert "orthogonal_error_px" in TRIAL_COLUMNS

    # The corrected export carries both.
    assert "endpoint_x_px" in SELECTION_COLUMNS
    assert "endpoint_y_px" in SELECTION_COLUMNS
    assert "sequence_id" in SELECTION_COLUMNS


def test_non_finite_endpoint_in_the_file_is_refused(tmp_path):
    records = build_records()
    path = write_selection_csv(tmp_path / "s1.csv", records, CENTERS)

    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    column = header.index("endpoint_x_px")
    fields = lines[1].split(",")
    fields[column] = "nan"
    lines[1] = ",".join(fields)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not finite"):
        read_selection_csv(path, CENTERS)