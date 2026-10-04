"""Trial event logging for the reciprocal pointing task (stage 2.11).

This module is additive: it does not import from, or modify, the
frozen stage 2.8 modules. It records what physically happened during a
trial so that :mod:`~pc.experiment.task.throughput` can compute a
sequence-level index of performance.

No-teleport invariant
---------------------
The single most important rule enforced here is that a sequence's
*intended* structure and its *observed* endpoints are kept strictly
separate.

* :class:`~pc.experiment.task.reciprocal.SequenceStep` says which
  target the protocol asked the participant to move to.
* :class:`SelectionRecord` says where the cursor physically was and
  physically ended.

Nothing in the logger ever rewrites a record's ``cursor_start`` to a
target centre. :func:`log_sequence` threads the previous trial's real
endpoint into the next trial's origin, so after a miss the next
movement begins at the miss endpoint. A "repair" function such as
``_reset_to_target()`` deliberately does not exist.

Denominator separation
----------------------
The initial acquisition is recorded with the same fidelity as any
other trial but is tagged
:data:`~pc.experiment.task.reciprocal.INITIAL_ACQUISITION`.
:func:`measured_records` is the only supported way to obtain the
denominator for an index of performance, which keeps the
acquisition out of movement time by construction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .reciprocal import (
    CENTER_LABEL,
    INITIAL_ACQUISITION,
    MEASURED,
    SequenceStep,
)


#: Denominator membership codes. ``MEASURED`` is the only code that
#: contributes to an index of performance.
IN_DENOMINATOR = "IN_DENOMINATOR"


#: Applied to the initial acquisition, which is recorded but excluded.
EXCLUDED_INITIAL_ACQUISITION = "EXCLUDED_INITIAL_ACQUISITION"


#: Applied when the movement duration is not positive or not finite. The name
#: says "timestamp" for schema stability only: the field it describes is a
#: duration, not a clock reading.
EXCLUDED_INVALID_TIMESTAMP = "EXCLUDED_INVALID_TIMESTAMP"


@dataclass(frozen=True)
class SelectionRecord:
    """One observed trial.

    Attributes
    ----------
    sequence_id, trial_index, trial_role:
        Identity taken verbatim from the :class:`SequenceStep`.
    from_target, to_target:
        Intended target labels. These are the protocol's intent and are
        never used to derive a cursor position.
    cursor_start, cursor_end:
        Real observed positions in pixels. ``cursor_start`` equals the
        previous trial's ``cursor_end`` within a sequence.
    selection_time_ms:
        Duration of the movement in milliseconds -- an elapsed interval
        measured from trial onset to selection, not a clock reading and not
        an absolute timestamp. May be absent or non-finite when the run
        failed before a duration could be measured; the constant name
        :data:`EXCLUDED_INVALID_TIMESTAMP` is retained for schema
        compatibility with already-written exports.
    hit, miss:
        Outcome of the selection against ``to_target``.
    endpoint_x, endpoint_y:
        Real endpoint in pixels; equal to ``cursor_end``. Stored
        explicitly because it is the quantity the throughput analysis
        consumes, and keeping it named makes that dependency obvious.
    denominator_status:
        One of :data:`IN_DENOMINATOR`,
        :data:`EXCLUDED_INITIAL_ACQUISITION`, or
        :data:`EXCLUDED_INVALID_TIMESTAMP`.
    """

    sequence_id: str
    trial_index: int
    trial_role: str
    from_target: str
    to_target: str
    cursor_start: tuple[float, float]
    cursor_end: tuple[float, float]
    selection_time_ms: float | None
    hit: bool
    miss: bool
    endpoint_x: float
    endpoint_y: float
    denominator_status: str

    @property
    def in_denominator(self) -> bool:
        return self.denominator_status == IN_DENOMINATOR


def _point(value: tuple[float, float], name: str) -> tuple[float, float]:
    try:
        x, y = value
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an (x, y) pair.") from exc

    x = float(x)
    y = float(y)

    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"{name} must be finite: {value!r}")

    return (x, y)


def _tolerance(target_width: float) -> float:
    width = float(target_width)

    if not math.isfinite(width) or width <= 0.0:
        raise ValueError(
            f"target_width must be a positive finite number: {target_width!r}"
        )

    return width / 2.0


def build_selection_record(
    step: SequenceStep,
    *,
    target_center: tuple[float, float],
    target_width: float,
    cursor_start: tuple[float, float],
    cursor_end: tuple[float, float],
    selection_time_ms: float | None,
) -> SelectionRecord:
    """Build one :class:`SelectionRecord` from an observation.

    ``cursor_start`` is supplied by the caller, not derived from
    ``step.from_target``. This is what prevents a teleport after a
    miss: the caller passes the previous trial's real endpoint.

    ``hit`` is decided with the stage 2.8 tolerance rule,
    ``distance(cursor_end, target_center) <= target_width / 2``, so this
    module agrees with the frozen classifier on what a hit is.
    """
    start = _point(cursor_start, "cursor_start")
    end = _point(cursor_end, "cursor_end")
    center = _point(target_center, "target_center")
    tolerance = _tolerance(target_width)

    hit = math.dist(end, center) <= tolerance

    if step.trial_role == INITIAL_ACQUISITION:
        status = EXCLUDED_INITIAL_ACQUISITION
    elif selection_time_ms is None or not math.isfinite(
        float(selection_time_ms)
    ):
        status = EXCLUDED_INVALID_TIMESTAMP
    elif float(selection_time_ms) <= 0.0:
        status = EXCLUDED_INVALID_TIMESTAMP
    else:
        status = IN_DENOMINATOR

    return SelectionRecord(
        sequence_id=step.sequence_id,
        trial_index=step.trial_index,
        trial_role=step.trial_role,
        from_target=step.from_target,
        to_target=step.to_target,
        cursor_start=start,
        cursor_end=end,
        selection_time_ms=None if selection_time_ms is None else float(
            selection_time_ms
        ),
        hit=hit,
        miss=not hit,
        endpoint_x=end[0],
        endpoint_y=end[1],
        denominator_status=status,
    )


def measured_records(records: list[SelectionRecord]) -> list[SelectionRecord]:
    """Return only the records that belong in the denominator.

    This is the single supported way to build a denominator. It drops
    the initial acquisition and any invalid-timestamp trial, and it
    **retains valid misses**, because a miss is a real observation
    about the participant and dropping it would bias the analysis.
    """
    return [record for record in records if record.in_denominator]


def initial_acquisition(records: list[SelectionRecord]) -> SelectionRecord | None:
    """Return the initial-acquisition record, if present."""
    for record in records:
        if record.trial_role == INITIAL_ACQUISITION:
            return record

    return None


def log_sequence(
    steps: list[SequenceStep],
    targets_by_label: dict[str, tuple[float, float]],
    target_widths: dict[str, float],
    *,
    origin: tuple[float, float],
    cursor_ends: list[tuple[float, float]],
    selection_times_ms: list[float | None],
) -> list[SelectionRecord]:
    """Log a whole sequence, threading real endpoints forward.

    Parameters
    ----------
    steps:
        The intended sequence from
        :func:`~pc.experiment.task.reciprocal.generate_reciprocal_sequence`.
    targets_by_label:
        Mapping of target label (``"T0"``, ``"T1"``, ...) to
        ``(x, y)`` centre.
    target_widths:
        Mapping of target label to width in pixels.
    origin:
        Real cursor position at the start of the sequence. Used only
        for the first step.
    cursor_ends:
        Real observed endpoint for each step, in order.
    selection_times_ms:
        Movement time for each step, in order. ``None`` marks a trial
        with an invalid timestamp.

    Returns
    -------
    list[SelectionRecord]
        One record per step.

    Notes
    -----
    Step ``i > 0`` takes its ``cursor_start`` from step ``i - 1``'s
    **observed endpoint**, never from the intended source target. That
    is the whole point of the no-teleport rule: after a miss the
    participant starts from where they actually stopped.
    """
    if len(cursor_ends) != len(steps):
        raise ValueError(
            "cursor_ends must have one entry per step: "
            f"{len(cursor_ends)} != {len(steps)}"
        )

    if len(selection_times_ms) != len(steps):
        raise ValueError(
            "selection_times_ms must have one entry per step: "
            f"{len(selection_times_ms)} != {len(steps)}"
        )

    records: list[SelectionRecord] = []
    current = _point(origin, "origin")

    for step, end, duration in zip(steps, cursor_ends, selection_times_ms):
        label = step.to_target

        if label not in targets_by_label:
            raise ValueError(f"no target geometry for label {label!r}.")

        if label not in target_widths:
            raise ValueError(f"no target width for label {label!r}.")

        record = build_selection_record(
            step,
            target_center=targets_by_label[label],
            target_width=target_widths[label],
            cursor_start=current,
            cursor_end=end,
            selection_time_ms=duration,
        )

        records.append(record)

        # The next movement starts from the real endpoint, which for a
        # miss is outside the target. Never reassign it to a target
        # centre.
        current = record.cursor_end

    return records

