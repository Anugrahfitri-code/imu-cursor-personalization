from pc.experiment.contracts import (
    ALLOWED_CONDITIONS,
    ALLOWED_DATASET_ROLES,
    ALLOWED_EVENT_TYPES,
    ALLOWED_SESSION_STATUSES,
    SCHEMA_VERSION,
)


def test_schema_version_is_1_0():
    assert SCHEMA_VERSION == "1.0"


def test_allowed_conditions_are_frozen():
    assert ALLOWED_CONDITIONS == frozenset(
        {"P0", "P2C", "L0", "L2C"}
    )


def test_dataset_roles_are_frozen():
    assert ALLOWED_DATASET_ROLES == frozenset(
        {"development", "pilot", "evaluation", "synthetic"}
    )


def test_session_statuses_are_frozen():
    assert ALLOWED_SESSION_STATUSES == frozenset(
        {"open", "closed"}
    )


def test_event_vocabulary_is_frozen():
    assert ALLOWED_EVENT_TYPES == frozenset(
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
