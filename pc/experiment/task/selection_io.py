"""CSV export and read-back for :class:`SelectionRecord`.

The frozen stage 2.8 row schema (``schema.TRIAL_COLUMNS``) keeps the
*derived* errors ``endpoint_error_px`` and ``signed_axial_error_px`` but
**not** the raw endpoint coordinates, and it keeps no ``sequence_id``.
A record set written in that shape cannot be re-read to reconstruct
``cursor_end``, and therefore cannot be re-analysed by
:mod:`pc.experiment.task.throughput`.

This module is the export for the corrected path. Every row carries the
two target centres, the real endpoint, the timestamp, the sequence
identity, the trial role and the technical status, so
``read_selection_csv`` reconstructs a record that produces bit-identical
throughput. That equality is asserted in the tests, so the round trip
cannot silently degrade.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from .selection import SelectionRecord

#: Column order of an exported trial-selection row.
SELECTION_COLUMNS = (
    "sequence_id",
    "trial_index",
    "trial_role",
    "from_target",
    "to_target",
    "from_center_x_px",
    "from_center_y_px",
    "to_center_x_px",
    "to_center_y_px",
    "cursor_start_x_px",
    "cursor_start_y_px",
    "cursor_end_x_px",
    "cursor_end_y_px",
    "endpoint_x_px",
    "endpoint_y_px",
    "selection_time_ms",
    "hit",
    "miss",
    "denominator_status",
)


def _float(row: Mapping[str, str], field: str) -> float:
    raw = row[field]
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not a number: {raw!r}") from exc

    if not math.isfinite(value):
        raise ValueError(f"{field} is not finite: {raw!r}")

    return value


def _bool(row: Mapping[str, str], field: str) -> bool:
    raw = str(row[field]).strip().lower()

    if raw in {"true", "1"}:
        return True
    if raw in {"false", "0"}:
        return False

    raise ValueError(f"{field} is not a boolean: {row[field]!r}")
def selection_row(
    record: SelectionRecord,
    targets_by_label: Mapping[str, tuple[float, float]],
) -> dict[str, object]:
    """Return one exportable row.

    The two target centres are looked up from the layout rather than
    copied from the record, because the record deliberately stores only
    labels. A label without geometry is an error, not a silent blank.
    """
    for label in (record.from_target, record.to_target):
        if label not in targets_by_label:
            raise ValueError(f"no target geometry for label {label!r}.")

    from_center = targets_by_label[record.from_target]
    to_center = targets_by_label[record.to_target]

    return {
        "sequence_id": record.sequence_id,
        "trial_index": record.trial_index,
        "trial_role": record.trial_role,
        "from_target": record.from_target,
        "to_target": record.to_target,
        "from_center_x_px": from_center[0],
        "from_center_y_px": from_center[1],
        "to_center_x_px": to_center[0],
        "to_center_y_px": to_center[1],
        "cursor_start_x_px": record.cursor_start[0],
        "cursor_start_y_px": record.cursor_start[1],
        "cursor_end_x_px": record.cursor_end[0],
        "cursor_end_y_px": record.cursor_end[1],
        "endpoint_x_px": record.endpoint_x,
        "endpoint_y_px": record.endpoint_y,
        "selection_time_ms": (
            "" if record.selection_time_ms is None else record.selection_time_ms
        ),
        "hit": record.hit,
        "miss": record.miss,
        "denominator_status": record.denominator_status,
    }


def write_selection_csv(
    path: str | Path,
    records: Sequence[SelectionRecord],
    targets_by_label: Mapping[str, tuple[float, float]],
) -> Path:
    """Write every record, in order, with a stable header."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SELECTION_COLUMNS))
        writer.writeheader()

        for record in records:
            writer.writerow(selection_row(record, targets_by_label))

    return destination


def _verify_endpoint_pair(
    row: Mapping[str, str],
    record: SelectionRecord,
) -> None:
    """Reject an export whose two endpoint fields contradict each other.

    ``endpoint_x_px``/``endpoint_y_px`` and ``cursor_end_x_px``/
    ``cursor_end_y_px`` are written from the same value: the writer copies
    ``record.cursor_end`` into both (:func:`selection_row`), and
    :func:`~pc.experiment.task.selection.build_selection_record` derives the
    scalar pair from that same tuple. They therefore describe *one* physical
    point, and a row where they disagree is internally contradictory rather
    than a legitimate second observation.

    The estimator consumes ``cursor_end`` (see
    :func:`~pc.experiment.task.throughput.movement_geometry`), so an
    inconsistent pair is silently ignored today: the row re-analyses as if the
    unedited field were the truth. Failing here keeps the contradiction visible
    at the boundary that owns it.

    The tolerance mirrors :func:`_verify_centers` (``rel_tol=1e-12``,
    ``abs_tol=1e-9``). Both columns are serialised from the same Python float
    with ``repr()``, which round-trips exactly, so any difference beyond this is
    a genuine edit rather than decimal formatting.
    """
    end_x, end_y = record.cursor_end
    for field, endpoint_field, a, b in (
        ("cursor_end_x_px", "endpoint_x_px", end_x, record.endpoint_x),
        ("cursor_end_y_px", "endpoint_y_px", end_y, record.endpoint_y),
    ):
        if not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError(
                f"trial {record.trial_index} has contradictory endpoint "
                f"fields: {field} is {a!r} but {endpoint_field} is {b!r}. "
                f"Both are written from the same endpoint, so they must "
                f"agree; one of the two was edited after export."
            )


def _verify_centers(
    row: Mapping[str, str],
    record: SelectionRecord,
    targets_by_label: Mapping[str, tuple[float, float]],
) -> None:
    """The exported centres must match the layout we are reading into."""
    for label, fields in (
        (record.from_target, ("from_center_x_px", "from_center_y_px")),
        (record.to_target, ("to_center_x_px", "to_center_y_px")),
    ):
        if label not in targets_by_label:
            raise ValueError(f"no target geometry for label {label!r}.")

        expected = targets_by_label[label]
        actual = (_float(row, fields[0]), _float(row, fields[1]))

        if not math.isclose(actual[0], expected[0], rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError(
                f"trial {record.trial_index} was exported against a "
                f"different layout: label {label!r} was {actual} but the "
                f"layout says {expected}."
            )

        if not math.isclose(actual[1], expected[1], rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError(
                f"trial {record.trial_index} was exported against a "
                f"different layout: label {label!r} was {actual} but the "
                f"layout says {expected}."
            )


def read_selection_csv(
    path: str | Path,
    targets_by_label: Mapping[str, tuple[float, float]],
) -> list[SelectionRecord]:
    """Rebuild records from an export.

    The centres written in each row are checked against the supplied
    layout, so a row exported against a different layout is rejected
    instead of being re-analysed against geometry it was not measured
    with.
    """
    source = Path(path)

    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        return []

    if tuple(rows[0].keys()) != SELECTION_COLUMNS:
        raise ValueError(
            "selection columns do not match SELECTION_COLUMNS: "
            f"{tuple(rows[0].keys())}"
        )

    records: list[SelectionRecord] = []

    for row in rows:
        raw_time = str(row["selection_time_ms"]).strip()
        selection_time_ms = float(raw_time) if raw_time else None

        if selection_time_ms is not None and not math.isfinite(selection_time_ms):
            raise ValueError(
                f"trial {row['trial_index']} has a non-finite timestamp: "
                f"{raw_time!r}"
            )

        record = SelectionRecord(
            sequence_id=str(row["sequence_id"]),
            trial_index=int(row["trial_index"]),
            trial_role=str(row["trial_role"]),
            from_target=str(row["from_target"]),
            to_target=str(row["to_target"]),
            cursor_start=(
                _float(row, "cursor_start_x_px"),
                _float(row, "cursor_start_y_px"),
            ),
            cursor_end=(
                _float(row, "cursor_end_x_px"),
                _float(row, "cursor_end_y_px"),
            ),
            selection_time_ms=selection_time_ms,
            hit=_bool(row, "hit"),
            miss=_bool(row, "miss"),
            endpoint_x=_float(row, "endpoint_x_px"),
            endpoint_y=_float(row, "endpoint_y_px"),
            denominator_status=str(row["denominator_status"]),
        )
        _verify_endpoint_pair(row, record)
        _verify_centers(row, record, targets_by_label)
        records.append(record)

    return records
