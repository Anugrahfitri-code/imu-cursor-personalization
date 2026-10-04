"""Sequence-level throughput for the reciprocal pointing task.

'This module is additive: it does not import from, or modify, the
'frozen stage 2.8 modules. It implements the Shannon formulation of
'Fitts' law using the *effective width* estimator rather than the
'nominal target diameter.

Formulation
-----------
Implements the operational definition of throughput in proposal
section 5.13 ("Definisi Operasional Throughput"), which follows
effective throughput at the sequence level (Soukoreff and MacKenzie,
2004; MacKenzie, 2015).

For a sequence of measured movements:

1. **Nominal amplitude** ``a_i`` is the distance from the from-target
   centre to the to-target centre.

2. **Endpoint offset** ``dx_i`` is the signed offset of the endpoint
   against the to-target centre, projected on the from-to movement
   axis. Positive is an overshoot, negative an undershoot, and zero
   means the endpoint projects exactly onto the target centre.

3. **Effective amplitude** follows the frozen serial convention of
   proposal section 5.13: ``Ae_1 = a_1 + dx_1`` and
   ``Ae_i = a_i + dx_i + dx_{i-1}`` for ``i > 1``, with the inherited
   term taken as zero for the first measured movement. The
   correction is stated in section 5.13 to apply consistently for the
   reciprocal serial task "and is not a measure of two-dimensional
   cursor path length", so no measured path distance is substituted
   for the corrected amplitude.

4. **Effective width** ``We = 4.133 * SDx``, with ``SDx`` the sample
   standard deviation of the ``dx_i`` over one sequence, including
   valid misses.

5. **Effective difficulty** is defined once per sequence, not per
   movement: ``Ae = mean(Ae_i)`` and ``ID_e = log2(Ae / We + 1)``.

6. **Throughput** ``TP = ID_e / mean(MT)`` in bits per second. The
   initial acquisition is excluded from ``mean(MT)``.

Guard rails
-----------
* A zero effective width raises and the sequence is flagged for
  audit. Section 5.13 forbids substituting an ad hoc value, so no
  fallback width is fabricated.
* An invalid movement time raises instead of being dropped.
* A gap in the measured ``trial_index`` run is reported as a broken
  sequence instead of being silently pooled.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .selection import SelectionRecord, initial_acquisition, measured_records


#: Frozen effective-width factor, ``We = 4.133 * SDx``.
EFFECTIVE_WIDTH_FACTOR = 4.133

#: Relative floor on the endpoint spread. Below ``SDx / max(|dx|)``
#: this value the sequence is treated as having no measurable spread and
#: is flagged for audit rather than reported with a near-zero ``We``.
SPREAD_TOLERANCE = 1e-9


#: Nanoseconds per second, for unit conversion.
NS_PER_SECOND = 1_000_000_000.0

@dataclass(frozen=True)
class MovementTerm:
    """Per-movement quantities feeding the sequence aggregate.

    ``nominal_amplitude_px`` is ``a_i``, ``endpoint_offset_px`` is
    ``dx_i``, and ``effective_amplitude_px`` is ``Ae_i`` after the
    serial correction of proposal section 5.13. The per-movement
    difficulty is deliberately absent: section 5.13 defines
    difficulty once per sequence.
    """

    trial_index: int
    nominal_amplitude_px: float
    endpoint_offset_px: float
    effective_amplitude_px: float
    movement_time_ms: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "trial_index": self.trial_index,
            "nominal_amplitude_px": self.nominal_amplitude_px,
            "endpoint_offset_px": self.endpoint_offset_px,
            "effective_amplitude_px": self.effective_amplitude_px,
            "movement_time_ms": self.movement_time_ms,
        }


@dataclass(frozen=True)
class SequenceThroughput:
    """Sequence-level index of performance.

    ``index_of_difficulty_bits`` is ``ID_e`` and
    ``throughput_bits_per_second`` is ``TP``, both defined once per
    sequence exactly as in proposal section 5.13.
    """

    sequence_id: str
    effective_width_px: float
    endpoint_offset_sd_px: float
    mean_effective_amplitude_px: float
    index_of_difficulty_bits: float
    mean_movement_time_ms: float
    throughput_bits_per_second: float
    measured_count: int
    miss_count: int
    terms: list[MovementTerm]

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence_id": self.sequence_id,
            "effective_width_px": self.effective_width_px,
            "endpoint_offset_sd_px": self.endpoint_offset_sd_px,
            "mean_effective_amplitude_px": self.mean_effective_amplitude_px,
            "index_of_difficulty_bits": self.index_of_difficulty_bits,
            "mean_movement_time_ms": self.mean_movement_time_ms,
            "throughput_bits_per_second": self.throughput_bits_per_second,
            "measured_count": self.measured_count,
            "miss_count": self.miss_count,
            "terms": [term.as_dict() for term in self.terms],
        }


def standard_deviation(values: list[float]) -> float:
    """Sample standard deviation (``n - 1`` denominator).

    Raises ``ValueError`` for fewer than two samples, because a
    single observation carries no evidence of endpoint spread and
    would make the effective width meaningless.
    """
    count = len(values)

    if count < 2:
        raise ValueError(
            "at least two movements are required to estimate the "
            f"endpoint spread; got {count}."
        )

    mean = sum(values) / count
    variance = sum((value - mean) ** 2 for value in values) / (count - 1)

    return math.sqrt(variance)


def effective_width(endpoint_offsets_px: list[float]) -> float:
    """Return ``We = 4.133 * SDx`` for a sequence of signed offsets.

    Raises
    ------
    ValueError
        If fewer than two offsets are supplied, or if the offsets carry
        no measurable spread. The latter means ``SDx ~ 0``, which
        would make the effective width zero and the difficulty
        infinite. A zero effective width is not a meaningful
        measurement, and proposal section 5.13 forbids substituting an
        ad hoc value for it, so the sequence is flagged for audit
        instead. A *constant* overshoot is the physical form of this
        case and is detected through ``SPREAD_TOLERANCE``, because the
        endpoints still differ in the last float bits.
    """
    sd = standard_deviation(endpoint_offsets_px)
    width = EFFECTIVE_WIDTH_FACTOR * sd

    # A constant overshoot is the physical case where SDx is exactly
    # zero, but the endpoints still differ in the last float bits, so a
    # bare ``width <= 0.0`` test would let a numerically negligible
    # spread through and report a wildly inflated throughput. The
    # relative guard below flags that sequence for audit instead.
    scale = max(abs(value) for value in endpoint_offsets_px)

    if (
        not math.isfinite(width)
        or width <= 0.0
        or sd <= SPREAD_TOLERANCE * scale
    ):
        raise ValueError(
            "effective width must be positive; identical endpoints "
            f"give SDx=0 and We=0 (offset_sd={sd!r}, scale={scale!r})."
        )

    return width


def movement_geometry(
    record: SelectionRecord,
    from_center: tuple[float, float],
    to_center: tuple[float, float],
) -> tuple[float, float]:
    """Return ``(nominal_amplitude_px, endpoint_offset_px)`` for a record.

    Proposal section 5.13 defines, for movement ``i``:

    * ``a_i`` -- the distance from the from-target centre to the
      to-target centre. This is a layout quantity and does not depend
      on where the cursor actually started.
    * ``d_i`` -- the signed offset of the endpoint against the
      to-target centre, projected onto the from-to movement axis.
      Positive is an overshoot, negative an undershoot, and zero means
      the endpoint projects exactly onto the target centre.

    Section 5.13 states the correction is applied consistently for the
    reciprocal serial task "and is not a measure of two-dimensional
    cursor path length", so the returned amplitude is the
    centre-to-centre distance and never ``dist(start, end)``.
    """
    from_x, from_y = from_center
    center_x, center_y = to_center
    end_x, end_y = record.cursor_end

    delta_x = center_x - from_x
    delta_y = center_y - from_y
    nominal = math.hypot(delta_x, delta_y)

    if nominal <= 0.0:
        raise ValueError(
            f"trial {record.trial_index} has zero amplitude: the "
            "movement axis is undefined when the from-target and "
            "to-target centres coincide."
        )

    unit_x = delta_x / nominal
    unit_y = delta_y / nominal

    offset = (end_x - center_x) * unit_x + (end_y - center_y) * unit_y

    return (nominal, offset)


def measured_records_in_order(
    records: list[SelectionRecord],
) -> list[SelectionRecord]:
    """Return the measured records in ascending ``trial_index`` order.

    The serial correction of section 5.13 pairs movement ``i`` with the
    endpoint offset of movement ``i-1``, so every consumer of the
    denominator must walk the trials in trial order. Relying on the order
    the rows happen to arrive in lets a shuffled log silently change the
    estimator, so both :func:`audit_sequence` and :func:`sequence_throughput`
    take their order from ``trial_index`` instead of from the list.
    """
    return sorted(measured_records(records), key=lambda record: record.trial_index)


def sequence_throughput(
    records: list[SelectionRecord],
    targets_by_label: dict[str, tuple[float, float]],
    *,
    sequence_id: str,
    selection_time_unit_ms: bool = True,
    expected_measured_transitions: int | None = None,
    expected_pairs: Sequence[tuple[str, str]] | None = None,
    technical_failure: bool = False,
) -> SequenceThroughput:
    """Compute the sequence-level throughput.

    Implements the operational definition of throughput frozen in
    proposal section 5.13, including the serial correction of the
    amplitude, the sequence-level difficulty, and the exclusion of the
    initial acquisition from the movement-time denominator.

    Parameters
    ----------
    records:
        All records for the sequence, including the initial
        acquisition. Only the denominator is used, so the acquisition
        cannot leak into the result.
    targets_by_label:
        Mapping of target label to ``(x, y)`` centre, used to derive
        the movement axis and the signed endpoint offset.
    sequence_id:
        Identifier stored on the result.
    selection_time_unit_ms:
        Kept for explicitness about units. Movement times are recorded
        in milliseconds and the aggregate throughput is reported in
        bits per second.

    Raises
    ------
    ValueError
        If no measured movement survives, if the effective width is
        zero, or if a movement has zero amplitude.
    """
    del selection_time_unit_ms

    measured = measured_records_in_order(records)

    if not measured:
        raise ValueError(
            "no measured movement survived denominator selection; an "
            "index of performance cannot be computed."
        )

    integrity = audit_sequence(
        records,
        expected_measured_transitions=expected_measured_transitions,
        expected_sequence_id=sequence_id,
        expected_pairs=expected_pairs,
        technical_failure=technical_failure,
    )

    if not integrity.is_complete:
        raise ValueError(
            f"sequence {sequence_id!r} is incomplete "
            f"(status {integrity.status}): "
            + " ".join(integrity.reasons)
            + " It must be recorded as incomplete and handled by the "
            "frozen missing/repeat rule rather than pooled."
        )

    amplitudes: list[float] = []
    offsets: list[float] = []
    times: list[float] = []
    terms: list[MovementTerm] = []

    previous_offset = 0.0

    for record in measured:
        label = record.to_target
        from_label = record.from_target

        if label not in targets_by_label:
            raise ValueError(f"no target geometry for label {label!r}.")

        if from_label not in targets_by_label:
            raise ValueError(
                f"no target geometry for label {from_label!r}."
            )

        nominal, offset = movement_geometry(
            record, targets_by_label[from_label], targets_by_label[label]
        )

        duration = record.selection_time_ms

        if duration is None or not math.isfinite(duration) or duration <= 0.0:
            raise ValueError(
                f"trial {record.trial_index} has an invalid movement "
                f"time: {duration!r}"
            )

        # Frozen serial convention of proposal section 5.13:
        #
        #     Ae_1 = a_1 + dx_1
        #     Ae_i = a_i + dx_i + dx_{i-1}   for i > 1
        #
        # ``previous_offset`` is zero for the first measured movement,
        # so both cases collapse into one expression, and the
        # inherited term never reaches back to the initial
        # acquisition, which is not a measured transition. The
        # correction is applied for every movement, valid miss
        # included, because a miss still moves and still consumes a
        # target.
        effective_amplitude = nominal + offset + previous_offset

        previous_offset = offset

        amplitudes.append(effective_amplitude)
        offsets.append(offset)
        times.append(duration)

        terms.append(
            MovementTerm(
                trial_index=record.trial_index,
                nominal_amplitude_px=nominal,
                endpoint_offset_px=offset,
                effective_amplitude_px=effective_amplitude,
                movement_time_ms=duration,
            )
        )

    if min(amplitudes) <= 0.0:
        raise ValueError(
            "the serial correction produced a non-positive effective "
            "amplitude; the sequence is not analysable and must be "
            "flagged for audit."
        )

    width_px = effective_width(offsets)
    offset_sd = standard_deviation(offsets)

    mean_amplitude = sum(amplitudes) / len(amplitudes)
    mean_time_ms = sum(times) / len(times)

    if mean_time_ms <= 0.0:
        raise ValueError("mean movement time must be positive.")

    # Difficulty is defined once per sequence in section 5.13, from the
    # mean effective amplitude rather than by averaging per-movement
    # difficulties.
    index_of_difficulty = math.log2(mean_amplitude / width_px + 1.0)

    return SequenceThroughput(
        sequence_id=sequence_id,
        effective_width_px=width_px,
        endpoint_offset_sd_px=offset_sd,
        mean_effective_amplitude_px=mean_amplitude,
        index_of_difficulty_bits=index_of_difficulty,
        mean_movement_time_ms=mean_time_ms,
        throughput_bits_per_second=index_of_difficulty
        / (mean_time_ms / 1000.0),
        measured_count=len(terms),
        miss_count=sum(1 for record in measured if record.miss),
        terms=terms,
    )



#: Sequence-integrity statuses. Only :data:`SEQUENCE_COMPLETE` may be
#: pooled into an index of performance; every other status names a
#: specific way the measured block failed to be the whole sequence.
SEQUENCE_COMPLETE = "COMPLETE"
SEQUENCE_TRUNCATED_HEAD = "TRUNCATED_HEAD"
SEQUENCE_TRUNCATED_TAIL = "TRUNCATED_TAIL"
SEQUENCE_INTERNAL_GAP = "INTERNAL_GAP"
SEQUENCE_DUPLICATE_TRIAL = "DUPLICATE_TRIAL"
SEQUENCE_SURPLUS_TRIALS = "SURPLUS_TRIALS"
SEQUENCE_BROKEN_CONTINUITY = "BROKEN_CONTINUITY"
SEQUENCE_PLAN_MISMATCH = "PLAN_MISMATCH"
SEQUENCE_MIXED_IDENTITY = "MIXED_SEQUENCE_IDENTITY"
SEQUENCE_TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
SEQUENCE_UNVERIFIED_COUNT = "UNVERIFIED_COUNT"

#: Ordered most severe first. A sequence can fail several ways at once;
#: the first match is the reported status and every match is reported in
#: the reason list.
#:
#: :data:`SEQUENCE_UNVERIFIED_COUNT` is last because it is an absence of
#: evidence rather than a positive finding: it only decides the verdict
#: when nothing else is wrong, and it must still outrank ``COMPLETE``.
SEQUENCE_FAILURE_PRECEDENCE = (
    SEQUENCE_MIXED_IDENTITY,
    SEQUENCE_DUPLICATE_TRIAL,
    SEQUENCE_SURPLUS_TRIALS,
    SEQUENCE_BROKEN_CONTINUITY,
    SEQUENCE_TRUNCATED_HEAD,
    SEQUENCE_TRUNCATED_TAIL,
    SEQUENCE_INTERNAL_GAP,
    SEQUENCE_TECHNICAL_FAILURE,
    SEQUENCE_UNVERIFIED_COUNT,
)


@dataclass(frozen=True)
class SequenceIntegrity:
    """Verdict on whether a record set is one whole reciprocal sequence.

    ``expected_measured_transitions`` is what makes head and tail
    truncation detectable. A contiguous run of trials 5..8 is internally
    consistent, so without knowing that nine transitions were intended
    it cannot be told apart from a complete sequence that simply
    happened to start at trial 5.
    """

    status: str
    expected_measured_transitions: int | None
    observed_measured_count: int
    observed_trial_indices: tuple[int, ...]
    duplicated_trial_indices: tuple[int, ...]
    surplus_trial_indices: tuple[int, ...]
    foreign_sequence_ids: tuple[str, ...]
    mismatched_plan_positions: tuple[int, ...]
    reasons: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return self.status == SEQUENCE_COMPLETE
def audit_sequence(
    records: list[SelectionRecord],
    *,
    expected_measured_transitions: int | None = None,
    expected_sequence_id: str | None = None,
    expected_pairs: Sequence[tuple[str, str]] | None = None,
    technical_failure: bool = False,
) -> SequenceIntegrity:
    """Classify a measured block without raising.

    Covers every way a reciprocal sequence can fail to be complete:

    * a missing **first** trial (head truncation);
    * a missing **last** trial (tail truncation), including a sequence
      cut short by an unmeasurable movement duration or a technical
      failure;
    * a missing **interior** trial;
    * a duplicated trial index;
    * records belonging to more than one sequence;
    * a technical failure flagged by the caller.

    A **valid miss** is not a failure. A miss is a real observation
    about the participant and stays in the denominator; low
    performance is never reported as a technical failure.
    """
    if expected_measured_transitions is not None:
        expected = int(expected_measured_transitions)
        if expected < 1:
            raise ValueError(
                "expected_measured_transitions must be positive: "
                f"{expected}"
            )
    else:
        expected = None

    measured = measured_records_in_order(records)
    indices = tuple(sorted(record.trial_index for record in measured))

    seen: dict[int, int] = {}
    for record in measured:
        seen[record.trial_index] = seen.get(record.trial_index, 0) + 1
    duplicates = tuple(sorted(k for k, v in seen.items() if v > 1))

    observed_ids = tuple(sorted({record.sequence_id for record in measured}))
    blank_ids = tuple(i for i in observed_ids if not i.strip())

    if expected_sequence_id is not None:
        foreign = tuple(i for i in observed_ids if i != expected_sequence_id)
    elif len(observed_ids) > 1:
        # No expectation was supplied, so which id is the intruder cannot be
        # named. Heterogeneity is still disqualifying on its own: rows that
        # were logged under different sequence identities cannot be pooled
        # as one whole sequence. Keep the lexicographically first id and
        # report the remainder so the field stays deterministic.
        foreign = observed_ids[1:]
    else:
        foreign = ()

    if blank_ids:
        foreign = tuple(sorted({*foreign, *blank_ids}))

    missing: set[int] = set()
    if expected is not None:
        missing = set(range(1, expected + 1)) - set(indices)
        # A transition whose index falls outside the exact range ``1..N``
        # means the block is not this sequence at all: either a repeat was
        # logged under the same identity, a second run was merged in, or a
        # row carries an out-of-range trial index (0 or negative). Testing
        # only ``index > expected or index < 1`` would let any index below 1 through as
        # COMPLETE, so the range is enforced on both ends. Either way the
        # block must not be pooled.
        surplus = tuple(
            index for index in indices if index > expected or index < 1
        )
    else:
        surplus = ()

    # Interior gaps are detectable from the observed run alone and are
    # therefore always a failure. Head and tail truncation can only be
    # told apart from a complete sequence by knowing how many
    # transitions were intended, so they need ``expected``.
    interior_gaps = [
        current
        for previous, current in zip(indices, indices[1:])
        if current != previous + 1
    ]

    head_missing = 1 in missing
    tail_missing = any(index >= expected for index in missing) if expected else False

    # A reciprocal movement starts where the previous one landed. A block
    # whose ``from_target``/``to_target`` pairs do not chain is not a single
    # continuous walk of the targets, so its per-movement amplitudes are not
    # the amplitudes of one sequence.
    #
    # Only rows that are genuinely adjacent in trial order are compared.
    # A block that already lost a trial cannot chain across the hole, and
    # reporting that as a separate fault would double-count the truncation
    # that ``expected_measured_transitions`` already names.
    broken_continuity: list[int] = []
    for previous, current in zip(measured, measured[1:]):
        if current.trial_index == previous.trial_index + 1 and (
            current.from_target != previous.to_target
        ):
            broken_continuity.append(current.trial_index)

    acquisition = initial_acquisition(records)
    if (
        acquisition is not None
        and measured
        and measured[0].trial_index == 1
        and measured[0].from_target != acquisition.to_target
    ):
        broken_continuity.insert(0, 1)

    # Chaining and closure are necessary but not sufficient. An adjacent
    # ring walk (``T0->T1->T2 ... T8->T0``) chains perfectly and closes on
    # its anchor, yet visits a different sequence of targets than the
    # configured reciprocal plan, so its per-movement amplitudes are not
    # the planned movements and must not be pooled. The caller supplies the
    # expected pairs from the trusted generator/config; they are never
    # derived from the records being validated, so a wrong block cannot
    # define its own expectation.
    plan_mismatch: tuple[int, ...] = ()
    if expected_pairs is not None:
        observed_pairs = tuple(
            (record.from_target, record.to_target) for record in measured
        )
        wanted = tuple((str(pair[0]), str(pair[1])) for pair in expected_pairs)
        if observed_pairs != wanted:
            first_bad = next(
                (
                    position
                    for position, (seen, plan) in enumerate(
                        zip(observed_pairs, wanted), start=1
                    )
                    if seen != plan
                ),
                min(len(observed_pairs), len(wanted)) + 1,
            )
            plan_mismatch = (first_bad,)

    reasons: list[str] = []

    if blank_ids:
        reasons.append(
            f"measured records carry a blank sequence id: {list(blank_ids)}."
        )
    elif foreign and expected_sequence_id is not None:
        reasons.append(
            f"measured records span sequence ids {list(foreign)}; "
            f"expected {expected_sequence_id!r}."
        )
    elif foreign:
        reasons.append(
            f"measured records span more than one sequence id: "
            f"{list(observed_ids)}."
        )

    if duplicates:
        reasons.append(
            f"trial indices appear more than once: {list(duplicates)}."
        )

    if surplus:
        reasons.append(
            f"measured trial indices fall outside the exact range 1..{expected}: "
            f"{list(surplus)}; the block is not the whole sequence."
        )

    if broken_continuity:
        reasons.append(
            "the logged target pairs do not chain into one reciprocal walk; "
            f"these movements do not start where the previous one ended: "
            f"{broken_continuity}."
        )

    if plan_mismatch:
        reasons.append(
            "the logged target pairs do not match the configured reciprocal "
            "plan; the first differing measured movement is position "
            f"{plan_mismatch[0]} of {len(measured)}. The block is a different "
            "traversal of the targets and must not be pooled."
        )

    if head_missing:
        reasons.append(
            "the first measured transition is absent; the sequence was "
            "truncated before it started."
        )
    if tail_missing:
        reasons.append(
            "the last measured transition(s) "
            f"{sorted(i for i in missing if i >= expected)} are absent; "
            "the sequence stopped early."
        )
    if interior_gaps:
        reasons.append(
            f"the measured run is not contiguous; trial indices "
            f"{interior_gaps} break it into separate blocks."
        )

    if technical_failure:
        reasons.append(
            "the caller reported a technical failure before the sequence "
            "was complete."
        )

    if expected is None:
        reasons.append(
            "no trusted reference count was supplied, so the observed "
            f"{len(indices)} transition(s) cannot be shown to be the whole "
            "sequence; pass expected_measured_transitions from the "
            "configured plan."
        )

    status = SEQUENCE_COMPLETE

    if foreign:
        status = SEQUENCE_MIXED_IDENTITY
    elif duplicates:
        status = SEQUENCE_DUPLICATE_TRIAL
    elif surplus:
        status = SEQUENCE_SURPLUS_TRIALS
    elif head_missing:
        status = SEQUENCE_TRUNCATED_HEAD
    elif tail_missing:
        status = SEQUENCE_TRUNCATED_TAIL
    elif interior_gaps:
        status = SEQUENCE_INTERNAL_GAP
    elif broken_continuity:
        status = SEQUENCE_BROKEN_CONTINUITY
    elif plan_mismatch:
        status = SEQUENCE_PLAN_MISMATCH
    elif technical_failure:
        status = SEQUENCE_TECHNICAL_FAILURE
    elif expected is None:
        status = SEQUENCE_UNVERIFIED_COUNT

    return SequenceIntegrity(
        status=status,
        expected_measured_transitions=expected,
        observed_measured_count=len(indices),
        observed_trial_indices=indices,
        duplicated_trial_indices=duplicates,
        surplus_trial_indices=surplus,
        mismatched_plan_positions=plan_mismatch,
        foreign_sequence_ids=foreign,
        reasons=tuple(reasons),
    )


def find_sequence_breaks(records: list[SelectionRecord]) -> list[int]:
    """Return the trial indices at which a measured sequence breaks.

    A break is any gap in the contiguous ``trial_index`` run of the
    denominator records. A missing trial means the movements after the
    gap are a separate block: pooling them would average movement times
    across two independent contexts and misstate the effective width.
    """
    indices = sorted(
        record.trial_index for record in measured_records(records)
    )
    breaks: list[int] = []

    for previous, current in zip(indices, indices[1:]):
        if current != previous + 1:
            breaks.append(current)

    return breaks


def is_contiguous_sequence(records: list[SelectionRecord]) -> bool:
    """Return ``True`` when the measured block has no missing trial."""
    return not find_sequence_breaks(records)
