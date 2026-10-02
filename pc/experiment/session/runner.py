"""End-to-end participant session runner.

The runner is the only component allowed to drive a participant through
the protocol. It composes the existing frozen contracts and adds no new
state and no new transition rule:

* :class:`~experiment.session.state_machine.SessionMachine` owns every
  state and every transition. The runner only calls
  :meth:`SessionMachine.transition`, :meth:`SessionMachine.advance_to`
  and :meth:`SessionMachine.stop_session`, so transition validation can
  never be bypassed and no state is invented here.
* :mod:`experiment.session.condition_runner` owns per-condition wiring.
* The 2C calibration is recorded exactly once, before any condition, and
  both personalised conditions must cite that one recording.

Ordering guarantees
-------------------
A clean run walks::

    READY -> INITIALIZATION -> CALIBRATION_2C -> ADAPTATION -> WARMUP
           -> CONDITION_P0 -> CONDITION_P2C -> CONDITION_L0
           -> CONDITION_L2C -> COMPLETE

A hard time cap or a technical failure may only leave the machine via
``SessionMachine.stop_session`` with a recorded reason, so an aborted
session is never indistinguishable from a completed one. Low
performance is *not* a technical failure and is never reported as one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .condition_runner import (
    ConditionExecutor,
    ConditionRun,
    require_calibration_hash,
)
from .schema import (
    CONDITION_ORDER,
    CONDITION_STATES,
    SESSION_MACHINE_VERSION,
    SESSION_TIME_CAP_NS,
    TECHNICAL_STOP_REASONS,
)
from .state_machine import (
    SessionMachine,
    validate_manifest,
    validate_order_reachable,
)

MANIFEST_SCHEMA_VERSION = "session-runner/1.0"

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "HARD_TIME_CAP_MS",
    "CONDITION_CODES",
    "DEFAULT_DIFFICULTY_ORDER",
    "PROLOGUE",
    "SESSION_STATUS_COMPLETE",
    "SESSION_STATUS_TECHNICAL_FAILURE",
    "MonotonicClock",
    "TechnicalFault",
    "ParticipantRecord",
    "ArtifactRecord",
    "SessionConfig",
    "SessionManifest",
    "SessionRun",
    "SessionRunner",
    "canonical_json",
    "sha256_of",
    "sha256_text",
    "condition_state",
    "record_calibration",
]

NS_PER_MS = 1_000_000

#: Ten-minute hard stop. Derived from the frozen schema constant so the
#: runner cannot drift away from the machine's own cap.
HARD_TIME_CAP_MS = SESSION_TIME_CAP_NS // NS_PER_MS
assert HARD_TIME_CAP_MS == 600_000

#: States walked before the first condition.
PROLOGUE = (
    "READY",
    "INITIALIZATION",
    "CALIBRATION_2C",
    "ADAPTATION",
    "WARMUP",
)

DEFAULT_DIFFICULTY_ORDER = ("EASY", "MEDIUM", "HARD")

#: Condition codes, i.e. ``CONDITION_P0`` stripped of its prefix.
CONDITION_CODES = tuple(
    state[len("CONDITION_"):] for state in CONDITION_ORDER
)
assert CONDITION_CODES == ("P0", "P2C", "L0", "L2C")

SESSION_STATUS_COMPLETE = "COMPLETE"
SESSION_STATUS_TECHNICAL_FAILURE = "STOPPED_TECHNICAL_FAILURE"


def canonical_json(value: Any) -> str:
    """Stable JSON encoding used for every hash in the manifest."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def condition_state(code: str) -> str:
    """``"P2C"`` -> ``"CONDITION_P2C"``."""
    if code not in CONDITION_CODES:
        raise ValueError(
            f"unknown condition code {code!r}; expected {list(CONDITION_CODES)}"
        )
    return f"CONDITION_{code}"


class MonotonicClock:
    """Deterministic nanosecond PC clock.

    The clock is *injected* rather than read from the wall clock so that
    a dry run is reproducible: the same inputs always produce the same
    timestamps and the same time-cap decision.
    """

    def __init__(
        self,
        start_ns: int = 0,
        step_ns: int = 1_000_000,
        epoch_unix_ns: int = 0,
    ) -> None:
        if step_ns < 0:
            raise ValueError("step_ns must not be negative")
        self._now = int(start_ns)
        self._step = int(step_ns)
        self._epoch = int(epoch_unix_ns)

    def now_ns(self) -> int:
        return self._now

    @property
    def step_ns(self) -> int:
        return self._step

    def advance(self, delta_ns: int | None = None) -> int:
        """Move the clock forward. Never accepts a negative delta."""
        delta = self._step if delta_ns is None else int(delta_ns)
        if delta < 0:
            raise ValueError("clock must not move backwards")
        self._now += delta
        return self._now

    def jump_to(self, now_ns: int) -> int:
        if now_ns < self._now:
            raise ValueError("clock must not move backwards")
        self._now = int(now_ns)
        return self._now

    def timestamp(self, now_ns: int | None = None) -> str:
        """ISO-8601 UTC timestamp derived from the deterministic clock."""
        import datetime as _datetime

        moment = self._now if now_ns is None else int(now_ns)
        seconds, remainder = divmod(
            self._epoch + moment, 1_000_000_000
        )
        base = _datetime.datetime.fromtimestamp(
            seconds, tz=_datetime.timezone.utc
        )
        return base.strftime("%Y-%m-%dT%H:%M:%S") + (
            f".{remainder:09d}Z"
        )


@dataclass(frozen=True)
class TechnicalFault:
    """A technical failure injected at a specific state.

    Only genuine technical problems may be modelled here. Low
    performance is explicitly *not* a fault: it must never stop a
    session, so it has no representation in this class.
    """

    state: str
    reason: str = "TECHNICAL_FAILURE"
    detail: str = ""

    def __post_init__(self) -> None:
        if self.reason not in TECHNICAL_STOP_REASONS:
            raise ValueError(
                f"{self.reason!r} is not a technical stop reason; "
                f"expected one of {sorted(TECHNICAL_STOP_REASONS)}"
            )
        if self.reason == "TIME_CAP_REACHED":
            raise ValueError(
                "the time cap is enforced by the runner and the machine, "
                "not injected as a fault"
            )


@dataclass(frozen=True)
class ParticipantRecord:
    """The participant half of the session inputs."""

    participant_id: str
    cohort: str
    device: str = ""


@dataclass(frozen=True)
class ArtifactRecord:
    """The artifact half of the session inputs.

    The four ``*_config_sha256`` fields and ``calibration_file_sha256``
    are 64-character hex digests, as the frozen manifest contract
    requires.
    """

    commit_hash: str
    session_hash: str
    calibration_file_sha256: str
    p2c_config_sha256: str
    l0_config_sha256: str
    l2c_config_sha256: str
    task_config_sha256: str
    l0_artifact: str = ""
    l2c_adapter_artifact: str = ""
    app_version: str = "0.0.0+unrecorded"


@dataclass(frozen=True)
class SessionConfig:
    """Protocol-level session configuration.

    ``condition_order`` holds condition *codes* (``"P0"``, ``"P2C"``,
    ...) because that is what the frozen state machine and manifest
    contract speak; the runner maps them to ``CONDITION_*`` states
    internally.
    """

    condition_order: tuple[str, ...] = CONDITION_CODES
    difficulty_order: tuple[str, ...] = DEFAULT_DIFFICULTY_ORDER
    session_id: str = ""
    time_cap_ns: int = SESSION_TIME_CAP_NS
    dry_run: bool = False
    clock_quality: str = "GOOD"
    data_policy: str = "RESEARCH"

    def __post_init__(self) -> None:
        if not self.condition_order:
            raise ValueError("a session must run at least one condition")

        for code in self.condition_order:
            if code not in CONDITION_CODES:
                raise ValueError(
                    f"unknown condition code {code!r}; expected "
                    f"{list(CONDITION_CODES)}"
                )

        # Forward-only through the frozen chain; skipping is allowed,
        # reordering is not.
        validate_order_reachable(list(self.condition_order))

        if not self.difficulty_order:
            raise ValueError("difficulty_order must not be empty")
        if self.time_cap_ns > SESSION_TIME_CAP_NS:
            raise ValueError(
                "a session may not be configured beyond the frozen "
                "ten-minute cap"
            )
        if self.dry_run and self.data_policy == "RESEARCH":
            raise ValueError(
                "a dry run must not be recorded as research data; set "
                "data_policy='DRY_RUN'"
            )

@dataclass(frozen=True)
class SessionManifest:
    """The complete session manifest.

    Every field the protocol needs is a required attribute, so an
    incomplete manifest cannot be constructed at all. The mapping the
    runner emits additionally satisfies the frozen
    ``MANIFEST_REQUIRED_FIELDS`` contract, which is why
    ``difficulty_order`` is also published under ``difficulty_ids``.
    """

    participant_id: str
    cohort: str
    session_id: str
    device: str
    app_version: str
    commit_hash: str
    session_hash: str
    model_artifact_version: str
    condition_order: tuple[str, ...]
    difficulty_order: tuple[str, ...]
    start_timestamp: str
    end_timestamp: str
    clock_quality: str
    calibration_file_sha256: str
    p2c_config_sha256: str
    l0_config_sha256: str
    l2c_config_sha256: str
    l0_artifact: str
    l2c_adapter_artifact: str
    task_config_sha256: str
    technical_status: str
    stop_reason: str
    dry_run: bool
    data_policy: str
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Flat mapping, checked against the frozen completeness contract."""
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "participant_id": self.participant_id,
            "session_id": self.session_id,
            "cohort": self.cohort,
            "device": self.device,
            "app_version": self.app_version,
            "commit_hash": self.commit_hash,
            "session_hash": self.session_hash,
            "model_artifact_version": self.model_artifact_version,
            "condition_order": list(self.condition_order),
            "difficulty_order": list(self.difficulty_order),
            "difficulty_ids": list(self.difficulty_order),
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "clock_quality": self.clock_quality,
            "calibration_file_sha256": self.calibration_file_sha256,
            "calibration_hash": self.calibration_file_sha256,
            "p2c_config_sha256": self.p2c_config_sha256,
            "l0_config_sha256": self.l0_config_sha256,
            "l2c_config_sha256": self.l2c_config_sha256,
            "l0_artifact": self.l0_artifact,
            "l2c_adapter_artifact": self.l2c_adapter_artifact,
            "task_config_sha256": self.task_config_sha256,
            "technical_status": self.technical_status,
            "stop_reason": self.stop_reason,
            "dry_run": self.dry_run,
            "data_policy": self.data_policy,
        }
        validate_manifest(payload)
        return payload


@dataclass(frozen=True)
class SessionRun:
    """Everything one session produced."""

    manifest: dict[str, Any]
    conditions: tuple[ConditionRun, ...]
    trial_records: tuple[Mapping[str, Any], ...]
    calibration: Mapping[str, Any]
    state_path: tuple[str, ...]
    stop_reason: str
    technical_status: str
    elapsed_ns: int

    def condition_result(self, code: str) -> ConditionRun:
        for run in self.conditions:
            if run.result.condition == code:
                return run
        raise KeyError(f"condition {code!r} did not run in this session")


def record_calibration(
    calibration_file_sha256: str,
    *,
    sample_count: int,
    duration_ns: int,
    recording_id: str = "",
) -> dict[str, Any]:
    """Produce the single immutable 2C calibration record for a session.

    The record is a plain immutable mapping, so once the runner holds it
    no later stage can rewrite it: every personalised condition receives
    the very same object, and the hash travels with it.
    """
    if not calibration_file_sha256:
        raise ValueError("a 2C recording must carry a file hash")
    if sample_count <= 0:
        raise ValueError("a 2C recording must contain samples")
    if duration_ns <= 0:
        raise ValueError("a 2C recording must have positive duration")

    payload = {
        "recording_id": recording_id or f"2c-{calibration_file_sha256[:12]}",
        "calibration_file_sha256": calibration_file_sha256,
        "sample_count": int(sample_count),
        "duration_ns": int(duration_ns),
        "trajectory_family": "2C",
    }
    # Freeze the record: a calibration cannot be edited after the fact.
    return MappingProxyType(payload)


class SessionRunner:
    """Drives one participant session from READY to a terminal stop."""

    def __init__(
        self,
        config: SessionConfig,
        participant: ParticipantRecord,
        artifacts: ArtifactRecord,
        clock: MonotonicClock | None = None,
        fault: TechnicalFault | None = None,
        trial_execute: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
        calibration_sample_count: int = 240,
    ) -> None:
        if not participant.participant_id:
            raise ValueError("participant_id must not be empty")
        if fault is not None and fault.state not in CONDITION_STATES | {
            "INITIALIZATION", "CALIBRATION_2C", "ADAPTATION", "WARMUP", "READY",
        }:
            raise ValueError(
                f"a fault may not be injected at {fault.state!r}"
            )

        self.config = config
        self.participant = participant
        self.artifacts = artifacts
        self.fault = fault
        self._trial_execute = trial_execute
        self._clock = clock if clock is not None else MonotonicClock()
        self._calibration_sample_count = calibration_sample_count
        self._executor: ConditionExecutor | None = None
        self._calibration: Mapping[str, Any] | None = None
        self._trial_records: list[Mapping[str, Any]] = []

    # -- helpers ---------------------------------------------------------

    @property
    def machine(self) -> SessionMachine:
        return self._machine

    @property
    def calibration(self) -> Mapping[str, Any]:
        if self._calibration is None:
            raise RuntimeError(
                "calibration is not available before CALIBRATION_2C"
            )
        return self._calibration

    def _session_id(self) -> str:
        return self.config.session_id or (
            f"{self.participant.participant_id}-s01"
        )

    def _planned_states(self) -> tuple[str, ...]:
        """The states this session will attempt, in order.

        Derived from the configured condition order, so a partial
        schedule is walked without inventing intermediate states.
        """
        if not self.config.condition_order:
            raise ValueError("a session must run at least one condition")

        conditions = tuple(
            condition_state(code) for code in self.config.condition_order
        )
        return PROLOGUE[1:] + conditions + ("COMPLETE",)

    def _record_calibration_once(self) -> None:
        if self._calibration is not None:
            raise RuntimeError(
                "a 2C calibration may only be recorded once per session; "
                "per-condition recalibration is not allowed"
            )
        self._machine.advance_to(self._clock.now_ns())
        self._calibration = record_calibration(
            self.artifacts.calibration_file_sha256,
            sample_count=self._calibration_sample_count,
            duration_ns=self._calibration_sample_count
            * self._clock.step_ns,
        )

    def _run_condition(self, state: str) -> None:
        assert self._executor is not None
        code = state[len("CONDITION_"):]
        self._machine.advance_to(self._clock.now_ns())

        run = self._executor.execute(
            code,
            difficulty_order=self.config.difficulty_order,
        )

        if self._trial_execute is not None:
            records = self._trial_execute(
                condition=code,
                calibration=self._calibration,
                difficulty_order=self.config.difficulty_order,
                clock=self._clock,
            )
            self._trial_records.extend(dict(record) for record in records)

    def run(self) -> SessionRun:
        """Execute the whole session and return its manifest and records."""
        session_id = self._session_id()
        machine = SessionMachine(
            session_id=session_id,
            participant_id=self.participant.participant_id,
            condition_order=list(self.config.condition_order),
            manifest={},
            time_cap_ns=self.config.time_cap_ns,
            machine_version=SESSION_MACHINE_VERSION,
        )
        self._machine = machine
        initial_state = machine.state
        start_ns = self._clock.now_ns()
        start_timestamp = self._clock.timestamp(start_ns)

        # The executor exists before any condition so that the
        # calibration hash it carries is the session's single recording.
        self._executor = ConditionExecutor(
            calibration_file_hash=self.artifacts.calibration_file_sha256,
            trial_execute=self._trial_execute,
        )

        for state in self._planned_states():
            if machine.stopped:
                break

            # Each state consumes a slice of the session's wall time, so
            # the machine's elapsed clock tracks the real schedule.
            self._clock.advance()
            machine.advance_to(self._clock.now_ns())

            # The cap is checked after the clock moves and before the
            # transition, which is exactly where the machine enforces
            # it: reaching the cap must abandon the schedule rather
            # than shorten it.
            if self._out_of_time():
                machine.stop_session("TIME_CAP_REACHED")
                break

            if self.fault is not None and self.fault.state == state:
                machine.stop_session(self.fault.reason)
                break

            machine.transition(state)

            if state == "CALIBRATION_2C":
                self._record_calibration_once()
            elif state in CONDITION_STATES:
                self._run_condition(state)

        # Both personalised conditions must cite one calibration, and
        # it must be this session's single recording.
        self._executor.assert_shared_calibration()
        require_calibration_hash(
            [run.result for run in self._executor.executed],
            self.artifacts.calibration_file_sha256,
        )

        return self._finalise(machine, start_timestamp, initial_state)

    def _finalise(
        self,
        machine: SessionMachine,
        start_timestamp: str,
        initial_state: str,
    ) -> SessionRun:
        """Assemble the manifest and the completed run record."""
        assert self._executor is not None

        stop_reason = machine.stop_reason or ""
        completed = stop_reason == "COMPLETED_SCHEDULE"

        if completed:
            technical_status = SESSION_STATUS_COMPLETE
        elif stop_reason in TECHNICAL_STOP_REASONS:
            technical_status = SESSION_STATUS_TECHNICAL_FAILURE
        else:
            # A participant request or an experimenter abort is not a
            # technical failure and must not be recorded as one.
            technical_status = stop_reason or SESSION_STATUS_COMPLETE

        manifest = SessionManifest(
            participant_id=self.participant.participant_id,
            cohort=self.participant.cohort,
            session_id=machine.session_id,
            device=self.participant.device,
            app_version=self.artifacts.app_version,
            commit_hash=self.artifacts.commit_hash,
            session_hash=self.artifacts.session_hash,
            model_artifact_version=(
                self.artifacts.l0_artifact
                or self.artifacts.l0_config_sha256[:12]
            ),
            condition_order=tuple(self.config.condition_order),
            difficulty_order=tuple(self.config.difficulty_order),
            start_timestamp=start_timestamp,
            end_timestamp=self._clock.timestamp(),
            clock_quality=self.config.clock_quality,
            calibration_file_sha256=(
                self.artifacts.calibration_file_sha256
            ),
            p2c_config_sha256=self.artifacts.p2c_config_sha256,
            l0_config_sha256=self.artifacts.l0_config_sha256,
            l2c_config_sha256=self.artifacts.l2c_config_sha256,
            l0_artifact=self.artifacts.l0_artifact,
            l2c_adapter_artifact=self.artifacts.l2c_adapter_artifact,
            task_config_sha256=self.artifacts.task_config_sha256,
            technical_status=technical_status,
            stop_reason=stop_reason,
            dry_run=self.config.dry_run,
            data_policy=self.config.data_policy,
        )

        state_path = (initial_state,) + tuple(
            transition.to_state for transition in machine.transitions
        )

        return SessionRun(
            manifest=manifest.to_dict(),
            conditions=self._executor.executed,
            trial_records=tuple(self._trial_records),
            calibration=self._calibration or MappingProxyType({}),
            state_path=state_path,
            stop_reason=stop_reason,
            technical_status=technical_status,
            elapsed_ns=machine.elapsed_ns(),
        )

    def _out_of_time(self) -> bool:
        return self._machine.remaining_ns() <= 0

