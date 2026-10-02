"""Sequence-level throughput for the reciprocal pointing task.

'This module is additive: it does not import from, or modify, the
'frozen stage 2.8 modules. It implements the Shannon formulation of
'Fitts' law using the *effective width* estimator rather than the
'nominal target diameter.

Formulation
-----------
For a sequence of measured movements:

1. **Actual amplitude** ``Ae_i`` is the distance the cursor actually
   travelled, ``dist(start_i, end_i)``. Because ``start_i`` is the
   previous trial's real endpoint, a miss genuinely lengthens the
   following movement. Nominal centre-to-centre distance is not used.

2. **Endpoint offset** ``dx_i`` is the signed projection of the endpoint
   error onto the unit movement axis. Positive is an overshoot. An
   orthogonal miss has ``dx_i ~= 0`` but a non-zero amplitude.

3. **Effective width** ``We = 4.133 * SDx``, with ``SDx`` the sample
   standard deviation of the signed offsets over the sequence.

4. **Effective difficulty** ``IDe = log2(Ae / We + 1)`` per movement.

5. **Throughput** ``TP = mean(IDe) / mean(MT)`` in bits per second.

Guard rails
-----------
* A zero effective width is rejected, never reported as an
  infinite throughput.
* A movement with zero amplitude raises rather than dividing by
  zero.
* A gap in the measured ``trial_index`` run is reported as a broken
  sequence instead of being silently pooled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .selection import SelectionRecord, measured_records


#: Frozen effective-width factor, ``We = 4.133 * SDx``.
EFFECTIVE_WIDTH_FACTOR = 4.133


#: Nanoseconds per second, for unit conversion.
NS_PER_SECOND = 1_000_000_000.0

@dataclass(frozen=True)
class MovementTerm:
    """Per-movement quantities feeding the sequence aggregate."""

    trial_index: int
    actual_amplitude_px: float
    endpoint_offset_px: float
    movement_time_ms: float
    effective_id_bits: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "trial_index": self.trial_index,
            "actual_amplitude_px": self.actual_amplitude_px,
            "endpoint_offset_px": self.endpoint_offset_px,
            "movement_time_ms": self.movement_time_ms,
            "effective_id_bits": self.effective_id_bits,
        }


@dataclass(frozen=True)
class SequenceThroughput:
    """Sequence-level index of performance."""

    sequence_id: str
    effective_width_px: float
    endpoint_offset_sd_px: float
    mean_effective_id_bits: float
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
            "mean_effective_id_bits": self.mean_effective_id_bits,
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
        If fewer than two offsets are supplied, or if the offsets are
        all identical. The latter means ``SDx == 0``, which would
        make the effective width zero and the difficulty infinite; a
        zero effective width is not a meaningful measurement, so it is
        rejected rather than reported as infinite throughput.
    """
    sd = standard_deviation(endpoint_offsets_px)
    width = EFFECTIVE_WIDTH_FACTOR * sd

    if width <= 0.0 or not math.isfinite(width):
        raise ValueError(
            "effective width must be positive; identical endpoints "
            f"give SDx=0 and We=0 (offset_sd={sd!r})."
        )

    return width


def movement_geometry(
    record: SelectionRecord,
    target_center: tuple[float, float],
) -> tuple[float, float]:
    """Return ``(actual_amplitude_px, endpoint_offset_px)`` for a record.

    The amplitude is the distance the cursor actually travelled. The
    offset is the signed projection of the endpoint error onto the
    movement axis, positive for an overshoot.
    """
    start_x, start_y = record.cursor_start
    end_x, end_y = record.cursor_end
    center_x, center_y = target_center

    delta_x = center_x - start_x
    delta_y = center_y - start_y
    nominal = math.hypot(delta_x, delta_y)

    if nominal <= 0.0:
        raise ValueError(
            f"trial {record.trial_index} has zero amplitude: the "
            "movement axis is undefined when the cursor starts on the "
            "target centre."
        )

    unit_x = delta_x / nominal
    unit_y = delta_y / nominal

    actual_amplitude = math.hypot(end_x - start_x, end_y - start_y)

    offset = (end_x - center_x) * unit_x + (end_y - center_y) * unit_y

    return (actual_amplitude, offset)


def sequence_throughput(
    records: list[SelectionRecord],
    targets_by_label: dict[str, tuple[float, float]],
    *,
    sequence_id: str,
    selection_time_unit_ms: bool = True,
) -> SequenceThroughput:
    """Compute the sequence-level throughput.

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

    measured = measured_records(records)

    if not measured:
        raise ValueError(
            "no measured movement survived denominator selection; an "
            "index of performance cannot be computed."
        )

    amplitudes: list[float] = []
    offsets: list[float] = []
    times: list[float] = []

    for record in measured:
        label = record.to_target

        if label not in targets_by_label:
            raise ValueError(f"no target geometry for label {label!r}.")

        amplitude, offset = movement_geometry(
            record, targets_by_label[label]
        )

        duration = record.selection_time_ms

        if duration is None or not math.isfinite(duration) or duration <= 0.0:
            raise ValueError(
                f"trial {record.trial_index} has an invalid movement "
                f"time: {duration!r}"
            )

        amplitudes.append(amplitude)
        offsets.append(offset)
        times.append(duration)

    width_px = effective_width(offsets)
    offset_sd = standard_deviation(offsets)

    terms = [
        MovementTerm(
            trial_index=record.trial_index,
            actual_amplitude_px=amplitude,
            endpoint_offset_px=offset,
            movement_time_ms=duration,
            effective_id_bits=math.log2(amplitude / width_px + 1.0),
        )
        for record, amplitude, offset, duration in zip(
            measured, amplitudes, offsets, times
        )
    ]

    mean_id = sum(term.effective_id_bits for term in terms) / len(terms)
    mean_time_ms = sum(times) / len(times)

    if mean_time_ms <= 0.0:
        raise ValueError("mean movement time must be positive.")

    return SequenceThroughput(
        sequence_id=sequence_id,
        effective_width_px=width_px,
        endpoint_offset_sd_px=offset_sd,
        mean_effective_id_bits=mean_id,
        mean_movement_time_ms=mean_time_ms,
        throughput_bits_per_second=mean_id / (mean_time_ms / 1000.0),
        measured_count=len(terms),
        miss_count=sum(1 for record in measured if record.miss),
        terms=terms,
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
