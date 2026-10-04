"""Export the substage 2.8 evidence artefacts from one execution.

Writes, all derived from the *same* deterministic sequence that
``verify_fitts_28`` prints, so the nine-trial table, the CSV, the JSON and
the summary cannot drift apart:

* ``data/fitts_per_trial.csv``  -- per-trial table
* ``data/fitts_summary.json``   -- sequence aggregates
* ``data/fitts_sequence.csv``   -- the round-tripped selection export
* ``logs/per_trial_table.txt``  -- the printed table

Run with::

    python _repro_export_evidence.py

Exit code 0 means every artefact was written.
"""

from __future__ import annotations

import csv
import json
import os
import sys

from pc.experiment.task.selection_io import (
    SELECTION_COLUMNS,
    selection_row,
    write_selection_csv,
)
from pc.experiment.task.throughput import sequence_throughput
from pc.experiment.tests import verify_fitts_28 as harness

PACKAGE = os.environ.get("FITTS_PACKAGE_DIR", "review_package_substage_28_v2")


def build() -> tuple[object, list[dict]]:
    targets = harness.generate_circular_targets(
        screen_width=harness.SCREEN_W,
        screen_height=harness.SCREEN_H,
        center=harness.CENTER,
        radius=harness.RING_RADIUS,
        target_count=harness.TARGET_COUNT,
        target_width=harness.TARGET_WIDTH,
        # Forward the harness seed/jitter explicitly so the exported CSV is
        # built from the same layout as the harness fixture, instead of
        # silently falling back to the generator default (seed 0).
        seed=harness.SEED,
        jitter_px=harness.JITTER_PX,
    )
    centers, widths = harness.label_map(targets)
    centers["CENTER"] = harness.START_POINT
    widths["CENTER"] = harness.TARGET_WIDTH

    steps = harness.generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == harness.MEASURED]

    cursor_ends = [
        harness.endpoint_along(harness.START_POINT, centers[steps[0].to_target], 4.0)
    ]
    for step, offset in zip(measured_steps, harness.OFFSETS_PX):
        cursor_ends.append(
            harness.endpoint_along(centers[step.from_target],
                                   centers[step.to_target], offset)
        )

    records = harness.log_sequence(
        steps,
        centers,
        widths,
        origin=harness.START_POINT,
        cursor_ends=cursor_ends,
        selection_times_ms=harness.SELECTION_TIMES_MS,
    )
    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=len(measured_steps),
    )
    rows = [
        selection_row(r, targets_by_label=centers)
        for r in records
    ]
    return result, rows


def measured_labels(rows):
    """Return ``(from_target, to_target, hit)`` for each measured row."""
    return [
        (r["from_target"], r["to_target"], r["hit"])
        for r in rows
        if r["trial_role"] == harness.MEASURED
    ]


def main() -> int:
    result, rows = build()
    labels = measured_labels(rows)
    data_dir = os.path.join(PACKAGE, "data")
    log_dir = os.path.join(PACKAGE, "logs")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    # --- per-trial table -------------------------------------------------
    table_path = os.path.join(data_dir, "fitts_per_trial.csv")
    fields = [
        "trial_index", "from_target", "to_target",
        "nominal_amplitude_px", "endpoint_offset_px",
        "inherited_offset_px", "effective_amplitude_px",
        "movement_time_ms", "hit",
    ]
    lines = [",".join(fields)]
    text_lines = [
        f"{'trial':>5} {'from':>5} {'to':>5} {'a_i':>12} {'dx_i':>8} "
        f"{'dx_i-1':>8} {'Ae_i':>12} {'MT_ms':>8}"
    ]
    previous = 0.0
    for term, (from_label, to_label, hit) in zip(result.terms, labels):
        inherited = previous
        lines.append(
            f"{term.trial_index},{from_label},{to_label},"
            f"{term.nominal_amplitude_px!r},{term.endpoint_offset_px!r},"
            f"{inherited!r},{term.effective_amplitude_px!r},"
            f"{term.movement_time_ms!r},{hit!r}"
        )
        text_lines.append(
            f"{term.trial_index:>5} {from_label:>5} {to_label:>5} "
            f"{term.nominal_amplitude_px:>12.6f} {term.endpoint_offset_px:>8.3f} "
            f"{inherited:>8.3f} {term.effective_amplitude_px:>12.6f} "
            f"{term.movement_time_ms:>8.1f}"
        )
        previous = term.endpoint_offset_px

    with open(table_path, "w", newline="", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(log_dir, "per_trial_table.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(text_lines) + "\n")

    # --- summary ---------------------------------------------------------
    summary = {
        "sequence_id": result.sequence_id,
        "measured_count": result.measured_count,
        "miss_count": result.miss_count,
        "endpoint_offset_sd_px": result.endpoint_offset_sd_px,
        "effective_width_px": result.effective_width_px,
        "mean_effective_amplitude_px": result.mean_effective_amplitude_px,
        "index_of_difficulty_bits": result.index_of_difficulty_bits,
        "mean_movement_time_ms": result.mean_movement_time_ms,
        "throughput_bits_per_second": result.throughput_bits_per_second,
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
    with open(os.path.join(data_dir, "fitts_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")

    # --- sequence export --------------------------------------------------
    seq_path = os.path.join(data_dir, "fitts_sequence.csv")
    with open(seq_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(SELECTION_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)

    print("\n".join(text_lines))
    print()
    print(f"mean Ae = {result.mean_effective_amplitude_px!r}")
    print(f"TP      = {result.throughput_bits_per_second!r}")
    print(f"artefacts written under {PACKAGE}/data and {PACKAGE}/logs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
