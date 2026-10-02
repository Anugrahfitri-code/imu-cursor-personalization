"""Stage 2.8 Fitts pointing task; not a participant release."""

from .outcome import classify_trial
from .schema import (
    HIT_OUTCOMES,
    INVALID_OUTCOMES,
    MISS_OUTCOMES,
    OUTCOMES,
    TARGET_COLUMNS,
    TASK_ID,
    TASK_SCHEMA_VERSION,
    TRIAL_COLUMNS,
    TRIAL_ROLES,
)
from .sequence import (
    generate_target_sequence,
    index_of_difficulty,
    task_config_sha256,
)
from .trials import build_sequence_trials

__all__ = [
    "HIT_OUTCOMES",
    "INVALID_OUTCOMES",
    "MISS_OUTCOMES",
    "OUTCOMES",
    "TARGET_COLUMNS",
    "TASK_ID",
    "TASK_SCHEMA_VERSION",
    "TRIAL_COLUMNS",
    "TRIAL_ROLES",
    "build_sequence_trials",
    "classify_trial",
    "default_task_config",
    "generate_target_sequence",
    "index_of_difficulty",
    "task_config_sha256",
]


def default_task_config() -> dict[str, object]:
    """
    Engineering candidate configuration.

    These are starter candidates for dry-run qualification only and
    are NOT declared final participant-study parameters.
    """
    return {
        "task_id": TASK_ID,
        "canvas_width_px": 1920.0,
        "canvas_height_px": 1080.0,
        "start_x_px": 960.0,
        "start_y_px": 540.0,
        "target_count": 10,
        "measured_transitions": 9,
        "difficulty_ids": ["EASY", "MEDIUM", "HARD"],
        "amplitude_px_by_difficulty": {
            "EASY": 320.0,
            "MEDIUM": 420.0,
            "HARD": 520.0,
        },
        "diameter_px_by_difficulty": {
            "EASY": 64.0,
            "MEDIUM": 40.0,
            "HARD": 24.0,
        },
        "task_config_version": "1.0",
    }