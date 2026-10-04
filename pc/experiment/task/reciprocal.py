"""Reciprocal trial sequence for the circular pointing task (stage 2.11).

This module is additive. It builds on :mod:`pc.experiment.task.targets`
for geometry and does **not** import from, or modify, the frozen stage
2.8 modules.

Relationship to the frozen ring walk
------------------------------------
``sequence.generate_target_sequence`` implements a *ring walk* whose
invariant is ``target_count == measured_transitions + 1``: the walk
visits one more position than the number of transitions it makes, so
it never revisits its starting target. That invariant is correct for a
walk and is left untouched.

A *reciprocal* task differs in two decisive respects.

1. It must be able to **return to its anchor target**, which is what
   makes the sequence close on itself and makes the task "reciprocal"
   in the Fitts sense of alternating between repeated locations. For a
   ring of ``N`` unique targets this requires exactly ``N`` measured
   transitions:

       initial acquisition:  center -> target_0
       measured:             target_0 -> target_4
                             target_4 -> target_8
                             ...
                             target_5 -> target_0   (closing transition)

   So ``target_count == measured_transitions`` for this layout, *not*
   ``measured_transitions + 1``. :func:`generate_reciprocal_sequence`
   therefore validates against its own invariant and never reuses the
   frozen one.

2. Every measured movement must **span the ring**, not step to the
   neighbouring vertex. A reciprocal pointing task manipulates a
   long effective width ``We``; if consecutive movements were between
   angular neighbours the index of difficulty would be near zero and the
   throughput would say more about layout geometry than about the
   participant. Because ``N`` is odd there is no exactly-opposite
   vertex, so the walk uses the fixed stride ``(N - 1) / 2``, which
   covers every vertex exactly once and returns to the anchor. Each
   measured amplitude is then the near-opposite chord
   ``2 * radius * cos(pi / (2 * N))`` rather than the adjacent chord
   ``2 * radius * sin(pi / N)``.

   For ``N = 9`` the traversal is::

       0 -> 4 -> 8 -> 3 -> 7 -> 2 -> 6 -> 1 -> 5 -> 0

   ``gcd((N - 1) / 2, N) == 1`` for every odd ``N``, so the stride is a
   single cycle: no vertex is revisited before the anchor and the
   sequence always closes. :func:`generate_reciprocal_sequence`
   computes the order from the stride and
   :func:`~pc.experiment.task.targets.generate_circular_targets`
   assigns target ids in ascending angular order, so the geometry above
   follows from the coordinates and not from the numbering alone.

Movement origin after a miss
----------------------------
A sequence stores only the *intended* source and destination target
ids. It deliberately stores no cursor position. The origin of each
measured movement is the **actual endpoint of the previous trial**,
supplied by the caller at logging time (see :mod:`.selection`). A miss
therefore never teleports the cursor back onto a target centre: the
next movement starts wherever the previous trial physically ended.
"""

from __future__ import annotations

from dataclasses import dataclass

from .targets import Target, validate_target_count


#: Trial role for the single acquisition movement that precedes the
#: measured block. Excluded from the movement-time denominator.
INITIAL_ACQUISITION = "INITIAL_ACQUISITION"


#: Trial role for every measured transition.
MEASURED = "MEASURED"


#: Label used for the layout centre, which is not itself a target.
CENTER_LABEL = "CENTER"


@dataclass(frozen=True)
class SequenceStep:
    """One intended movement in a reciprocal sequence.

    ``from_label`` / ``to_label`` are target ids, except for the
    initial acquisition whose source is :data:`CENTER_LABEL`.
    """

    sequence_id: str
    from_target: str
    to_target: str
    trial_index: int
    trial_role: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence_id": self.sequence_id,
            "from_target": self.from_target,
            "to_target": self.to_target,
            "trial_index": self.trial_index,
            "trial_role": self.trial_role,
        }


def _label(target_id: int) -> str:
    return f"T{target_id}"


def reciprocal_traversal(target_count: int) -> list[int]:
    """Return the near-opposite vertex order for a ring of ``target_count``.

    The walk uses the fixed stride ``(N - 1) // 2`` and returns ``N + 1``
    entries: the first is the anchor, the last repeats it so the caller
    can emit a closing transition.

    For ``N = 9`` this is ``[0, 4, 8, 3, 7, 2, 6, 1, 5, 0]``. Every
    consecutive pair spans the near-opposite chord, and
    ``gcd((N - 1) // 2, N) == 1`` for odd ``N``, so the order is a single
    cycle that visits each vertex exactly once before closing.

    Raises ``ValueError`` for an even count, which has no single-cycle
    near-opposite stride, and for counts below three.
    """
    count = validate_target_count(int(target_count))
    stride = (count - 1) // 2

    return [(index * stride) % count for index in range(count + 1)]


def generate_reciprocal_sequence(
    targets: list[Target],
    *,
    sequence_id: str = "seq",
    measured_transitions: int | None = None,
) -> list[SequenceStep]:
    """Build a reciprocal sequence over a circular target layout.

    The sequence is one initial acquisition from the layout centre to
    ``targets[0]``, followed by ``measured_transitions`` measured
    transitions that walk the ring with the fixed stride
    ``(len(targets) - 1) // 2`` and close by returning to
    ``targets[0]``.

    Every measured transition therefore spans the ring along the
    near-opposite chord ``2 * radius * cos(pi / (2 * N))``. The stride
    is coprime with every odd ``N``, so the order visits each vertex
    exactly once before returning to the anchor.

    Parameters
    ----------
    targets:
        Circular layout from
        :func:`~pc.experiment.task.targets.generate_circular_targets`.
        Must be non-empty with contiguous ids starting at ``0``.
    sequence_id:
        Identifier stored on every step.
    measured_transitions:
        Number of measured transitions. Defaults to ``len(targets)``,
        which is the closed-loop count. A different value is rejected
        because it would either fail to close the loop or revisit some
        targets more than once, breaking reciprocity.

    Returns
    -------
    list[SequenceStep]
        ``1 + measured_transitions`` steps. Index ``0`` is the initial
        acquisition; indices ``1..N`` are the measured transitions.

    Raises
    ------
    ValueError
        If the target count is even, if ids are not contiguous from
        ``0``, or if ``measured_transitions`` does not match the
        target count.
    """
    if not targets:
        raise ValueError("targets must not be empty.")

    count = validate_target_count(len(targets))

    expected_ids = list(range(count))
    actual_ids = [target.target_id for target in targets]

    if actual_ids != expected_ids:
        raise ValueError(
            "targets must have contiguous ids starting at 0: "
            f"expected {expected_ids}, got {actual_ids}."
        )

    if measured_transitions is None:
        transitions = count
    else:
        transitions = int(measured_transitions)

    if transitions != count:
        raise ValueError(
            "a reciprocal ring requires measured_transitions == "
            f"target_count; got {transitions} transitions for {count} "
            "targets. A different count would not close the loop."
        )

    if not str(sequence_id):
        raise ValueError("sequence_id must be a non-empty string.")

    order = reciprocal_traversal(count)

    if order[-1] != order[0]:
        raise ValueError(
            "the traversal must close on its anchor; got order "
            f"{order}."
        )

    steps = [
        SequenceStep(
            sequence_id=sequence_id,
            from_target=CENTER_LABEL,
            to_target=_label(order[0]),
            trial_index=0,
            trial_role=INITIAL_ACQUISITION,
        )
    ]

    for offset, destination in enumerate(order[1:]):
        source = order[offset]

        steps.append(
            SequenceStep(
                sequence_id=sequence_id,
                from_target=_label(source),
                to_target=_label(destination),
                trial_index=offset + 1,
                trial_role=MEASURED,
            )
        )

    return steps


def expected_measured_pairs(
    targets: list[Target],
) -> tuple[tuple[str, str], ...]:
    """Return the measured ``(from, to)`` pairs of the planned traversal.

    This is the *trusted* expectation: it is rebuilt from the generator and
    the target layout, never from a record set. Callers hand it to
    :func:`pc.experiment.task.throughput.audit_sequence` so a block that
    chains and closes but visits a different set of targets in a different
    order is rejected instead of being pooled.
    """
    plan = generate_reciprocal_sequence(targets)

    return tuple(
        (step.from_target, step.to_target)
        for step in plan
        if step.trial_role == MEASURED
    )
