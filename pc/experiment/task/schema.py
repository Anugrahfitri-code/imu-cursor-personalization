"""Frozen schema constants for the Fitts pointing task (stage 2.8)."""

from __future__ import annotations


TASK_SCHEMA_VERSION = "1.0"


TASK_ID = "fitts_pointing"


#: Sequence-level layout. Values are engineering candidates and are
#: explicitly NOT declared final participant-study parameters.
TARGET_COLUMNS = (
    "target_index",
    "sequence_index",
    "difficulty_id",
    "target_x_px",
    "target_y_px",
    "target_diameter_px",
)


TRIAL_COLUMNS = (
    "trial_record_id",
    "participant_id",
    "session_id",
    "condition",
    "sequence_index",
    "target_index",
    "difficulty_id",
    "trial_role",
    "movement_start_x_px",
    "movement_start_y_px",
    "target_x_px",
    "target_y_px",
    "target_diameter_px",
    "origin_is_actual_endpoint",
    "amplitude_px",
    "tolerance_px",
    "onset_pc_time_ns",
    "end_pc_time_ns",
    "movement_time_ns",
    "peak_overshoot_px",
    "endpoint_error_px",
    "signed_axial_error_px",
    "orthogonal_error_px",
    "outcome",
    "valid_trial",
    "validity_rule",
    "hit",
    "excluded_reason",
    "task_config_sha256",
    "task_schema_version",
)


#: Trial roles. ``INITIAL_ACQUISITION`` is the first target of a
#: sequence and is excluded from the movement denominator.
TRIAL_ROLES = (
    "INITIAL_ACQUISITION",
    "MEASURED",
)


#: Outcome codes required by the stage 2.10 test list.
OUTCOMES = (
    "CENTER_HIT",
    "UNDERSHOOT",
    "OVERSHOOT",
    "ORTHOGONAL_MISS",
    "SERIAL_OVERSHOOT_REVERSE",
    "VALID_MISS",
    "INVALID_TIMESTAMP",
)


#: Outcomes that represent a successful selection inside tolerance.
HIT_OUTCOMES = frozenset(
    {
        "CENTER_HIT",
        "UNDERSHOOT",
        "OVERSHOOT",
        "SERIAL_OVERSHOOT_REVERSE",
    }
)


#: Outcomes that terminate a trial without a selection.
MISS_OUTCOMES = frozenset(
    {
        "ORTHOGONAL_MISS",
        "VALID_MISS",
    }
)


#: Outcomes that make a trial unusable for MT/throughput statistics.
INVALID_OUTCOMES = frozenset(
    {
        "INVALID_TIMESTAMP",
    }
)


#: Ordering used when a trial matches several rules at once.
#: More specific geometric evidence wins.
OUTCOME_PRECEDENCE = (
    "INVALID_TIMESTAMP",
    "SERIAL_OVERSHOOT_REVERSE",
    "CENTER_HIT",
    "UNDERSHOOT",
    "OVERSHOOT",
    "ORTHOGONAL_MISS",
    "VALID_MISS",
)


#: Reason codes attached to ``excluded_reason``.
EXCLUSION_REASONS = (
    "INITIAL_ACQUISITION",
    "INVALID_TIMESTAMP",
    "MISS_NOT_SELECTED",
)


VALIDITY_RULES = (
    "MEASURED_HIT",
    "MEASURED_MISS",
    "NOT_IN_DENOMINATOR",
    "INVALID",
)