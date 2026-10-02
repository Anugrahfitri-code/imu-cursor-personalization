"""Frozen state constants for the session machine (stage 2.9)."""

from __future__ import annotations


SESSION_MACHINE_VERSION = "1.0"


#: Session states in their required order.
STATES = (
    "READY",
    "INITIALIZATION",
    "CALIBRATION_2C",
    "ADAPTATION",
    "WARMUP",
    "CONDITION_P0",
    "CONDITION_P2C",
    "CONDITION_L0",
    "CONDITION_L2C",
    "PAUSE",
    "COMPLETE",
)


#: States in which a condition block is running.
CONDITION_STATES = frozenset(
    {
        "CONDITION_P0",
        "CONDITION_P2C",
        "CONDITION_L0",
        "CONDITION_L2C",
    }
)


#: The frozen condition chain, in canonical order.
#:
#: ``CONDITION_STATES`` is a frozenset and therefore cannot express an
#: order. This tuple is the single source of truth for that order:
#: counterbalancing may skip a condition but must never reorder the
#: chain.
CONDITION_ORDER = (
    "CONDITION_P0",
    "CONDITION_P2C",
    "CONDITION_L0",
    "CONDITION_L2C",
)

assert set(CONDITION_ORDER) == set(CONDITION_STATES)


#: States from which the session may still advance.
ACTIVE_STATES = frozenset(STATES) - frozenset(
    {"COMPLETE"}
)


#: Allowed transitions. ``PAUSE`` is reachable from any active state
#: and, after a pause, the session resumes into the state it left.
PAUSE_SOURCES = frozenset(
    {
        "READY",
        "INITIALIZATION",
        "CALIBRATION_2C",
        "ADAPTATION",
        "WARMUP",
        "CONDITION_P0",
        "CONDITION_P2C",
        "CONDITION_L0",
        "CONDITION_L2C",
    }
)


TRANSITIONS: dict[str, tuple[str, ...]] = {
    "READY": ("INITIALIZATION",),
    "INITIALIZATION": ("CALIBRATION_2C",),
    "CALIBRATION_2C": ("ADAPTATION",),
    "ADAPTATION": ("WARMUP",),
    "WARMUP": ("CONDITION_P0", "CONDITION_P2C",
               "CONDITION_L0", "CONDITION_L2C"),
    "CONDITION_P0": ("CONDITION_P2C", "CONDITION_L0",
                     "CONDITION_L2C"),
    "CONDITION_P2C": ("CONDITION_L0", "CONDITION_L2C"),
    "CONDITION_L0": ("CONDITION_L2C",),
    "CONDITION_L2C": ("COMPLETE",),
    "PAUSE": (
        "READY",
        "INITIALIZATION",
        "CALIBRATION_2C",
        "ADAPTATION",
        "WARMUP",
        "CONDITION_P0",
        "CONDITION_P2C",
        "CONDITION_L0",
        "CONDITION_L2C",
    ),
    "COMPLETE": (),
}


#: Terminal states. Reaching one freezes the session.
TERMINAL_STATES = frozenset({"COMPLETE"})


#: Recorded stop reasons. A stop reason is mandatory for every
#: terminal transition so an aborted session is never
#: indistinguishable from a completed one.
STOP_REASONS = (
    "COMPLETED_SCHEDULE",
    "TIME_CAP_REACHED",
    "TECHNICAL_FAILURE",
    "PARTICIPANT_REQUEST",
    "EXPERIMENTER_ABORT",
)


#: Stop reasons that indicate a technical rather than a performance
#: outcome. Low performance must NOT be recorded as a technical
#: failure.
TECHNICAL_STOP_REASONS = frozenset(
    {
        "TECHNICAL_FAILURE",
        "TIME_CAP_REACHED",
    }
)


#: Ten-minute hard cap on a single session, in nanoseconds.
SESSION_TIME_CAP_NS = 600 * 1_000_000_000