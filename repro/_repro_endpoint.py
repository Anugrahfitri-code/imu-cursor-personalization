"""Evidence for stage 2.8 endpoint + export review.

Run:  python _repro_endpoint.py
Sections A..E map to the review questions. Kept so evidence is reproducible.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import math
import tempfile
from pathlib import Path

from pc.experiment.task.reciprocal import MEASURED, generate_reciprocal_sequence
from pc.experiment.task.selection import log_sequence
from pc.experiment.task.selection_io import read_selection_csv, write_selection_csv
from pc.experiment.task.targets import generate_circular_targets
from pc.experiment.task.throughput import audit_sequence, sequence_throughput

from pc.experiment.tests.verify_fitts_28 import JITTER_PX, SEED

TARGET_COUNT = 9
RING_RADIUS = 260.0
TARGET_WIDTH = 64.0
OFFSETS_PX = [2.0, -14.0, 9.0, 3.0, -5.0, 18.0, -7.0, 4.0, -11.0]
SELECTION_TIMES_MS = [0.0] + [820.0] * TARGET_COUNT
START_POINT = (400.0, 300.0)


def endpoint_along(start, stop, offset_px):
    axis_x, axis_y = stop[0] - start[0], stop[1] - start[1]
    norm = math.hypot(axis_x, axis_y)
    return (stop[0] + offset_px * axis_x / norm, stop[1] + offset_px * axis_y / norm)


def header(title: str) -> None:
    print("\n" + "=" * 74)
    print(f"  {title}")
    print("=" * 74)


def build():
    targets = generate_circular_targets(
        screen_width=1920.0,
        screen_height=1080.0,
        center=(960.0, 540.0),
        radius=RING_RADIUS,
        target_count=TARGET_COUNT,
        target_width=TARGET_WIDTH,
        seed=SEED,
        jitter_px=JITTER_PX,
    )
    centers = {f"T{t.target_id}": (t.x, t.y) for t in targets}
    centers["CENTER"] = (960.0, 540.0)
    widths = {f"T{t.target_id}": t.width for t in targets}
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    measured = [s for s in steps if s.trial_role == MEASURED]
    ends = [endpoint_along(START_POINT, centers[steps[0].to_target], 4.0)]
    for step, offset in zip(measured, OFFSETS_PX):
        ends.append(
            endpoint_along(centers[step.from_target], centers[step.to_target], offset)
        )
    records = log_sequence(
        steps,
        centers,
        widths,
        origin=START_POINT,
        cursor_ends=ends,
        selection_times_ms=SELECTION_TIMES_MS,
    )
    return records, steps, centers


def to_csv_text(records, centers) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.csv"
        write_selection_csv(path, records, centers)
        return path.read_text(encoding="utf-8")


def rewrite(rows) -> str:
    header_line = ",".join(rows[0].keys())
    body = "\n".join(",".join(str(r[c]) for c in rows[0].keys()) for r in rows)
    return header_line + "\n" + body + "\n"


# --- A. reference count provenance -----------------------------------------
def section_a():
    header("A. reference count provenance")
    records, steps, centers = build()
    plan_measured = len([s for s in steps if s.trial_role == "MEASURED"])
    print(f"  plan MEASURED steps            : {plan_measured}")
    print(f"  records actually logged        : {len(records)}")
    print(
        "  audit(expected=plan count)     : "
        f"{audit_sequence(records, expected_measured_transitions=plan_measured).status}"
    )
    partial = records[:TARGET_COUNT]
    v_plan = audit_sequence(partial, expected_measured_transitions=plan_measured)
    v_rows = audit_sequence(partial, expected_measured_transitions=len(partial) - 1)
    print(f"  tail dropped, audit(=plan)     : {v_plan.status}")
    print(f"  tail dropped, audit(=rows)     : {v_rows.status}")
    print(f"    -> rows-derived count certifies "
          f"{len(partial) - 1} of {plan_measured} transitions")
    for r in v_plan.reasons:
        print(f"    reason: {r}")


# --- B. plan conformance vs continuity -------------------------------------
def section_b():
    header("B. plan conformance vs mere continuity")
    records, _, centers = build()
    # Relabel T4 <-> T8 (labels AND coordinates). It is an automorphism of the
    # ring, so every leg keeps its real length and the walk stays perfectly
    # chained -- yet it is no longer the plan that was issued.
    permuted = dict(centers)
    permuted["T4"], permuted["T8"] = centers["T8"], centers["T4"]
    flip = {"T4": "T8", "T8": "T4"}

    wrong = []
    for record in records:
        new_from = flip.get(record.from_target, record.from_target)
        new_to = flip.get(record.to_target, record.to_target)
        offset = record.endpoint_offset_px if hasattr(record, "endpoint_offset_px") else None
        wrong.append(
            dataclasses.replace(
                record,
                from_target=new_from,
                to_target=new_to,
                cursor_start=permuted[new_from] if record.trial_index > 1 else record.cursor_start,
                cursor_end=permuted[new_to],
                endpoint_x=permuted[new_to][0],
                endpoint_y=permuted[new_to][1],
                selection_time_ms=record.selection_time_ms,
            )
        )

    # Re-apply the planned endpoint offsets so We is not degenerate.
    measured_wrong = [r for r in wrong if r.trial_role == MEASURED]
    fixed = []
    for record in wrong:
        if record.trial_role != MEASURED:
            fixed.append(record)
            continue
        idx = measured_wrong.index(record)
        if idx == 0:
            fixed.append(record)
            continue
        previous = measured_wrong[idx - 1]
        offset = OFFSETS_PX[idx]
        start_p = previous.cursor_end
        stop_p = permuted[record.to_target]
        end_p = endpoint_along(start_p, stop_p, offset)
        fixed.append(
            dataclasses.replace(
                record,
                cursor_start=start_p,
                cursor_end=end_p,
                endpoint_x=end_p[0],
                endpoint_y=end_p[1],
            )
        )
    wrong = fixed

    v = audit_sequence(wrong, expected_measured_transitions=TARGET_COUNT)
    changed = next(
        i for i, (a, b) in enumerate(zip(records, wrong))
        if (a.from_target, a.to_target) != (b.from_target, b.to_target)
    )
    print(f"  planned leg {changed}   : "
          f"{records[changed].from_target}->{records[changed].to_target}")
    print(f"  logged   leg {changed}   : "
          f"{wrong[changed].from_target}->{wrong[changed].to_target}")
    print(f"  chained+complete audit      : {v.status}")
    print(f"  is_complete                 : {v.is_complete}")
    print("  TP still produced?          : ", end="")
    try:
        r = sequence_throughput(
            wrong, permuted, sequence_id="s1",
            expected_measured_transitions=TARGET_COUNT,
        )
        print(f"YES  {r.throughput_bits_per_second:.6f} bit/s  <-- divergence invisible")
    except ValueError as exc:
        print(f"NO   {exc}")


# --- C. technical failure / empty denominator ------------------------------
def section_c():
    header("C. technical failure flag (not an empty denominator)")
    records, steps, centers = build()

    # NOTE: dataclasses.replace only rewrites the field it is given. It does
    # NOT recompute denominator_status, so these rows still say
    # IN_DENOMINATOR even though selection_time_ms is now None. This case
    # therefore exercises the caller-supplied technical_failure flag on an
    # otherwise structurally sound block; it is *not* evidence of an empty
    # denominator. See section C2 for a genuine empty denominator.
    partial = [
        dataclasses.replace(r, selection_time_ms=None) for r in records
    ]
    statuses = sorted({r.denominator_status for r in partial})
    print(f"  rows retained                  : {len(partial)} of {len(records)}")
    print(f"  denominator_status values      : {statuses}")
    print("  (unchanged by replace -> these rows are still in the denominator)")
    v = audit_sequence(
        partial, expected_measured_transitions=TARGET_COUNT,
        technical_failure=True,
    )
    print(f"  audit                          : {v.status}")
    for r in v.reasons:
        print(f"    reason: {r}")
    try:
        sequence_throughput(
            partial, centers, sequence_id="s1",
            expected_measured_transitions=TARGET_COUNT,
            technical_failure=True,
        )
        print("  estimator: produced a number  <-- expected refusal")
    except ValueError as exc:
        print(f"  estimator refused: {exc}")


def section_c2():
    """A genuine empty denominator, produced through the real logger."""
    header("C2. genuine empty denominator via the logger (duration None)")
    records, steps, centers = build()
    targets = generate_circular_targets(
        screen_width=1920.0,
        screen_height=1080.0,
        center=(960.0, 540.0),
        radius=RING_RADIUS,
        target_count=TARGET_COUNT,
        target_width=TARGET_WIDTH,
        seed=SEED,
        jitter_px=JITTER_PX,
    )
    centers = {f"T{t.target_id}": (t.x, t.y) for t in targets}
    centers["CENTER"] = (960.0, 540.0)
    widths = {f"T{t.target_id}": t.width for t in targets}
    measured = [s for s in steps if s.trial_role == MEASURED]
    ends = [endpoint_along(START_POINT, centers[steps[0].to_target], 4.0)]
    for step, offset in zip(measured, OFFSETS_PX):
        ends.append(
            endpoint_along(centers[step.from_target], centers[step.to_target], offset)
        )
    # Pass every duration as None through log_sequence itself, so the
    # denominator_status is derived by the production rule rather than
    # patched afterwards.
    no_times = log_sequence(
        steps,
        centers,
        widths,
        origin=START_POINT,
        cursor_ends=ends,
        selection_times_ms=[None] * (TARGET_COUNT + 1),
    )
    statuses = sorted({r.denominator_status for r in no_times})
    in_denominator = sum(1 for r in no_times if r.in_denominator)
    print(f"  rows written                   : {len(no_times)}")
    print(f"  denominator_status values      : {statuses}")
    print(f"  rows in denominator            : {in_denominator}")
    v = audit_sequence(
        no_times, expected_measured_transitions=TARGET_COUNT,
        technical_failure=True,
    )
    print(f"  audit                          : {v.status}")
    for r in v.reasons:
        print(f"    reason: {r}")
    try:
        sequence_throughput(
            no_times, centers, sequence_id="s1",
            expected_measured_transitions=TARGET_COUNT,
            technical_failure=True,
        )
        print("  estimator: produced a number  <-- expected refusal")
    except ValueError as exc:
        print(f"  estimator refused: {exc}")


# --- D. conflicting endpoint pair -----------------------------------------
def section_d():
    header("D. endpoint_x shifted 100 px, cursor_end untouched")
    records, _, centers = build()
    text = to_csv_text(records, centers)
    rows = list(csv.DictReader(io.StringIO(text)))
    original = rows[3]["endpoint_x_px"]
    rows[3]["endpoint_x_px"] = str(float(original) + 100.0)
    print(f"  trial 4 endpoint_x_px          : {original} -> {rows[3]['endpoint_x_px']}")
    print(f"  trial 4 cursor_end_x_px        : {rows[3]['cursor_end_x_px']} (unchanged)")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "conflict.csv"
        path.write_text(rewrite(rows), encoding="utf-8")
        print("  reader verdict                 : ", end="")
        try:
            read_selection_csv(path, centers)
            print("ACCEPTED  <-- contradiction silently passed")
        except ValueError as exc:
            print(f"REJECTED  {exc}")
        print("  then TP from the conflicting row: ", end="")
        try:
            loaded = read_selection_csv(path, centers)
        except ValueError:
            loaded = None
        if loaded is None:
            print("n/a (reader already refused)")
        else:
            try:
                res = sequence_throughput(
                    loaded, centers, sequence_id="s1",
                    expected_measured_transitions=TARGET_COUNT,
                )
                print(f"{res.throughput_bits_per_second:.6f} bit/s")
            except ValueError as exc:
                print(f"refused: {exc}")


# --- E. non-finite / missing ----------------------------------------------
def section_e():
    header("E. missing, NaN and infinity coordinates")
    records, _, centers = build()
    lines = to_csv_text(records, centers).strip().splitlines()
    head = lines[0]
    col = head.split(",")
    xi, yi, ci = (col.index("endpoint_x_px"), col.index("endpoint_y_px"),
                  col.index("cursor_end_x_px"))

    def attempt(label, index, value):
        rows = [r.split(",") for r in lines[1:]]
        rows[index][xi if "endpoint_x" in label else (yi if "endpoint_y" in label else ci)] = value
        payload = head + "\n" + "\n".join(",".join(r) for r in rows) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.csv"
            p.write_text(payload, encoding="utf-8")
            try:
                read_selection_csv(p, centers)
                print(f"  {label:<26}: ACCEPTED  <-- not caught")
            except ValueError as exc:
                print(f"  {label:<26}: REJECTED  {exc}")

    attempt("endpoint_x = nan", 3, "nan")
    attempt("endpoint_y = inf", 3, "inf")
    attempt("endpoint_x = -inf", 3, "-inf")
    attempt("cursor_end_x = nan", 3, "nan")
    attempt("endpoint_x = ''", 3, "")


def main():
    section_a()
    section_b()
    section_c()
    section_c2()
    section_d()
    section_e()
    print("\nDone.\n")


if __name__ == "__main__":
    main()
