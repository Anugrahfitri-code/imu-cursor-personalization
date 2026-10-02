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

A *reciprocal* task differs in one decisive respect: it must be able to
**return to its anchor target**, which is what makes the sequence
close on itself and makes the task "reciprocal" in the Fitts sense of
alternating between repeated locations. For a ring of ``N`` unique
targets this requires exactly ``N`` measured transitions:

    initial acquisition:  center -> target_0
    measured:             target_0 -> target_1
                          ...
                          target_8 -> target_0   (closing transition)

So ``target_count == measured_transitions`` for this layout, *not*
``measured_transitions + 1``. Because ``N`` must be odd, both the
anchor and the closing transition behave symmetrically around the
reference axis. :func:`generate_reciprocal_sequence` therefore
validates against its own invariant and never reuses the frozen one.

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


def generate_reciprocal_sequence(
    targets: list[Target],
    *,
    sequence_id: str = "seq",
    measured_transitions: int | None = None,
) -> list[SequenceStep]:
    """Build a reciprocal sequence over a circular target layout.

    The sequence is one initial acquisition from the layout centre to
    ``targets[0]``, followed by ``measured_transitions`` measured
    transitions that walk the ring in ascending target id and close by
    returning to ``targets[0]``.

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

    steps = [
        SequenceStep(
            sequence_id=sequence_id,
            from_target=CENTER_LABEL,
            to_target=_label(0),
            trial_index=0,
            trial_role=INITIAL_ACQUISITION,
        )
    ]

    for offset in range(transitions):
        source = offset % count
        destination = (offset + 1) % count

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
