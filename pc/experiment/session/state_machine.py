"""Session state machine for the PC experiment (stage 2.9).

The machine never silently continues after a receiver failure or a
low-performance condition: every terminal transition must carry a
recorded stop reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .schema import (
    ACTIVE_STATES,
    CONDITION_ORDER,
    CONDITION_STATES,
    PAUSE_SOURCES,
    SESSION_MACHINE_VERSION,
    SESSION_TIME_CAP_NS,
    STATES,
    STOP_REASONS,
    TECHNICAL_STOP_REASONS,
    TERMINAL_STATES,
    TRANSITIONS,
)


MANIFEST_REQUIRED_FIELDS = (
    "session_id",
    "participant_id",
    "session_hash",
    "commit_hash",
    "condition_order",
    "difficulty_ids",
    "calibration_file_sha256",
    "p2c_config_sha256",
    "l0_config_sha256",
    "l2c_config_sha256",
    "task_config_sha256",
)


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_string(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False

    return all(
        character in "0123456789abcdefABCDEF"
        for character in value
    )


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """
    Validate the session manifest completeness contract.

    Missing provenance must fail loudly rather than default to a
    plausible-looking value.
    """
    missing = [
        name
        for name in MANIFEST_REQUIRED_FIELDS
        if name not in manifest
    ]

    if missing:
        raise ValueError(
            "session manifest missing required fields: "
            f"{missing!r}"
        )

    for name in (
        "session_id",
        "participant_id",
        "session_hash",
        "commit_hash",
    ):
        if not _non_empty_string(manifest[name]):
            raise ValueError(
                f"{name} must be a non-empty string."
            )

    for name in (
        "calibration_file_sha256",
        "p2c_config_sha256",
        "l0_config_sha256",
        "l2c_config_sha256",
        "task_config_sha256",
    ):
        if not _sha256_string(manifest[name]):
            raise ValueError(
                f"{name} must be a 64-character SHA-256 hex "
                "string."
            )

    order = manifest["condition_order"]

    if not isinstance(order, Sequence) or isinstance(
        order, (str, bytes)
    ):
        raise ValueError(
            "condition_order must be a sequence of condition codes."
        )

    conditions = [
        f"CONDITION_{code}" for code in order
    ]

    unknown = [
        code for code in conditions
        if code not in CONDITION_STATES
    ]

    if unknown:
        raise ValueError(
            f"condition_order references unknown conditions: "
            f"{unknown!r}"
        )

    if len(set(conditions)) != len(conditions):
        raise ValueError(
            "condition_order must not repeat a condition."
        )

    difficulties = manifest["difficulty_ids"]

    if not isinstance(difficulties, Sequence) or isinstance(
        difficulties, (str, bytes)
    ):
        raise ValueError("difficulty_ids must be a sequence.")

    if not difficulties:
        raise ValueError("difficulty_ids must not be empty.")

    if not all(
        _non_empty_string(value) for value in difficulties
    ):
        raise ValueError(
            "difficulty_ids entries must be non-empty strings."
        )


def validate_order_reachable(
    condition_order: Sequence[str],
) -> None:
    """
    Verify the scheduled condition order follows the frozen chain.

    The order must be a forward-only path through
    ``CONDITION_P0 -> P2C -> L0 -> L2C``. Counterbalancing may skip
    a condition but must never reorder the chain.
    """
    codes = [f"CONDITION_{code}" for code in condition_order]

    expected = CONDITION_ORDER

    unknown = [
        code for code in codes if code not in expected
    ]

    if unknown:
        raise ValueError(
            "condition_order references unknown conditions: "
            f"{unknown!r}"
        )

    positions = [expected.index(code) for code in codes]

    if positions != sorted(positions):
        raise ValueError(
            "condition_order must follow the frozen P0 -> P2C "
            "-> L0 -> L2C chain; counterbalancing may only skip "
            "conditions."
        )

    if len(set(codes)) != len(codes):
        raise ValueError(
            "condition_order must not repeat a condition."
        )


@dataclass(frozen=True)
class Transition:
    """One recorded state transition."""

    sequence: int
    from_state: str
    to_state: str
    pc_time_ns: int
    stop_reason: str


@dataclass
class SessionMachine:
    """
    Deterministic session state machine.

    Tracks elapsed time against the hard cap and refuses any
    transition that is not explicitly permitted. A session that
    reaches the time cap must stop with ``TIME_CAP_REACHED``
    rather than being truncated in the middle of a condition.
    """

    session_id: str
    participant_id: str
    condition_order: list[str]
    manifest: dict[str, Any] = field(default_factory=dict)
    time_cap_ns: int = SESSION_TIME_CAP_NS
    machine_version: str = SESSION_MACHINE_VERSION

    state: str = "READY"
    start_pc_time_ns: int = 0
    now_pc_time_ns: int = 0
    stopped: bool = False
    stop_reason: str = ""
    _transitions: list[Transition] = field(
        default_factory=list, init=False
    )
    _pause_return: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(
                f"unknown initial state: {self.state!r}"
            )

        for name in ("session_id", "participant_id"):
            if not _non_empty_string(getattr(self, name)):
                raise ValueError(
                    f"{name} must be a non-empty string."
                )

        codes = [
            f"CONDITION_{code}"
            for code in self.condition_order
        ]

        for code in codes:
            if code not in CONDITION_STATES:
                raise ValueError(
                    f"unknown condition: {code!r}"
                )

        validate_order_reachable(self.condition_order)

        if self.time_cap_ns <= 0:
            raise ValueError("time_cap_ns must be positive.")

        if self.manifest:
            validate_manifest(self.manifest)

    def _log(self, to_state: str, stop_reason: str) -> None:
        self._transitions.append(
            Transition(
                sequence=len(self._transitions) + 1,
                from_state=self.state,
                to_state=to_state,
                pc_time_ns=self.now_pc_time_ns,
                stop_reason=stop_reason,
            )
        )

        self.state = to_state

    def _guard_running(self) -> None:
        if self.stopped:
            raise RuntimeError(
                "session already stopped with reason "
                f"{self.stop_reason!r}; the machine is terminal."
            )

    def elapsed_ns(self) -> int:
        return self.now_pc_time_ns - self.start_pc_time_ns

    def remaining_ns(self) -> int:
        return self.time_cap_ns - self.elapsed_ns()

    def advance_to(self, pc_time_ns: int) -> None:
        """Move the clock forward without leaving the current state."""
        if isinstance(pc_time_ns, bool) or not isinstance(
            pc_time_ns, int
        ):
            raise TypeError("pc_time_ns must be an integer.")

        if pc_time_ns < self.now_pc_time_ns:
            raise ValueError(
                "the session clock must not move backwards."
            )

        self.now_pc_time_ns = pc_time_ns

    def can_transition(self, to_state: str) -> bool:
        if to_state not in STATES:
            return False

        if self.stopped:
            return False

        if to_state == "PAUSE":
            return self.state in PAUSE_SOURCES

        return to_state in TRANSITIONS.get(self.state, ())

    def transition(self, to_state: str) -> Transition:
        """Apply one transition, enforcing the cap and stop reasons."""
        self._guard_running()

        if to_state not in STATES:
            raise ValueError(f"unknown state: {to_state!r}")

        if to_state == "PAUSE":
            if self.state not in PAUSE_SOURCES:
                raise ValueError(
                    f"cannot pause from {self.state!r}."
                )

            self._pause_return = self.state
            self._log(to_state, "")

            return self._transitions[-1]

        if self.state == "PAUSE":
            resume = self._pause_return

            if resume == "":
                raise RuntimeError(
                    "PAUSE has no recorded return state."
                )

            if to_state != resume:
                raise ValueError(
                    "a paused session must resume into "
                    f"{resume!r}, not {to_state!r}."
                )

            self._log(to_state, "")

            return self._transitions[-1]

        if to_state not in TRANSITIONS.get(self.state, ()):
            raise ValueError(
                f"transition {self.state!r} -> {to_state!r} "
                "is not permitted."
            )

        if self.elapsed_ns() >= self.time_cap_ns:
            raise RuntimeError(
                "the session time cap has been reached; call "
                "stop_session('TIME_CAP_REACHED') instead of "
                f"transitioning to {to_state!r}."
            )

        stop_reason = ""

        if to_state in TERMINAL_STATES:
            stop_reason = "COMPLETED_SCHEDULE"

        self._log(to_state, stop_reason)

        if stop_reason:
            self.stopped = True
            self.stop_reason = stop_reason

        return self._transitions[-1]

    def next_state(self) -> str:
        """Return the next scheduled state without applying it."""
        if self.state == "PAUSE":
            return self._pause_return

        for candidate in TRANSITIONS.get(self.state, ()):
            if candidate in CONDITION_STATES:
                code = candidate[len("CONDITION_"):]

                if code in self.condition_order:
                    return candidate

            return candidate

        raise RuntimeError(
            f"no permitted successor for {self.state!r}; "
            "check condition_order."
        )

    def stop_session(self, reason: str) -> Transition:
        """
        Stop the session with an explicit reason.

        A terminal stop is always recorded so an aborted session is
        never mistaken for a completed one.
        """
        self._guard_running()

        if reason not in STOP_REASONS:
            raise ValueError(f"unknown stop reason: {reason!r}")

        self._log("COMPLETE", reason)

        self.stopped = True
        self.stop_reason = reason

        return self._transitions[-1]

    def assert_continuable(self) -> None:
        """
        Guard against resuming after a technical stop.

        Low performance is never a technical failure: callers must
        use ``PARTICIPANT_REQUEST`` or ``EXPERIMENTER_ABORT`` for a
        performance-driven early stop.
        """
        if self.stopped and self.stop_reason in TECHNICAL_STOP_REASONS:
            raise RuntimeError(
                "cannot continue after technical stop "
                f"{self.stop_reason!r}."
            )

    @property
    def transitions(self) -> list[Transition]:
        return list(self._transitions)

    def manifest_completeness(self) -> dict[str, bool]:
        """Report which provenance fields the manifest supplies."""
        return {
            name: name in self.manifest
            for name in MANIFEST_REQUIRED_FIELDS
        }