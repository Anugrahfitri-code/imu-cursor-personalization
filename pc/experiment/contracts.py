SCHEMA_VERSION = "1.0"

ALLOWED_DATASET_ROLES = frozenset(
    {
        "development",
        "pilot",
        "evaluation",
        "synthetic",
    }
)

ALLOWED_SESSION_STATUSES = frozenset(
    {
        "open",
        "closed",
    }
)

ALLOWED_CONDITIONS = frozenset(
    {
        "P0",
        "P2C",
        "L0",
        "L2C",
    }
)

ALLOWED_EVENT_TYPES = frozenset(
    {
        "session_start",
        "session_end",
        "condition_start",
        "condition_end",
        "block_start",
        "block_end",
        "sequence_start",
        "sequence_end",
        "trial_start",
        "target_onset",
        "selection",
        "trial_complete",
        "trial_abort",
        "calibration_start",
        "calibration_end",
    }
)
