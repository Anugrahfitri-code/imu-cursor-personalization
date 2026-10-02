"""Per-condition execution for the participant session runner.

Each condition reuses the frozen contracts it must not duplicate:

* ``P0``     global parametric controller, no personalisation;
* ``P2C``    the same six-parameter affine family, fitted per user;
* ``L0``     the frozen global learned model;
* ``L2C``    the frozen global model plus a latent affine adapter.

The 2C calibration is recorded **once** per session, before any condition.
``P2C`` and ``L2C`` therefore must report the identical
``calibration_file_hash``; :func:`require_calibration_hash` enforces that
and refuses to run otherwise, because a per-condition recalibration
would silently give the two personalised conditions different
personalisation inputs and make them non-comparable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

P2C_USER_PARAMETERS = 6

CONDITION_KINDS = ("P0", "P2C", "L0", "L2C")
PERSONALISED_CONDITIONS = ("P2C", "L2C")

#: Conditions that read the session 2C calibration.
CALIBRATED_CONDITIONS = PERSONALISED_CONDITIONS


def is_personalised(condition: str) -> bool:
    return condition in PERSONALISED_CONDITIONS


def require_calibration_hash(
    results: Sequence["ConditionResult"],
    calibration_file_hash: str,
) -> None:
    """Fail loudly unless every personalised condition used this calibration."""
    for result in results:
        if not is_personalised(result.condition):
            continue
        if result.calibration_file_hash != calibration_file_hash:
            raise ValueError(
                f"condition {result.condition} used calibration "
                f"{result.calibration_file_hash!r} but the session recorded "
                f"{calibration_file_hash!r}; personalised conditions must "
                f"share one 2C recording"
            )


@dataclass(frozen=True)
class ConditionPlan:
    """What a single condition needs before it may execute."""

    condition: str
    uses_calibration: bool
    fits_per_user: bool
    uses_latent_adapter: bool
    frozen_global_model: bool

    @classmethod
    def build(cls, condition: str) -> ConditionPlan:
        if condition not in CONDITION_KINDS:
            raise ValueError(
                f"unknown condition {condition!r}; expected one of "
                f"{list(CONDITION_KINDS)}"
            )
        return cls(
            condition=condition,
            uses_calibration=condition in CALIBRATED_CONDITIONS,
            fits_per_user=condition == "P2C",
            uses_latent_adapter=condition == "L2C",
            frozen_global_model=condition in ("L0", "L2C"),
        )


@dataclass(frozen=True)
class ConditionResult:
    """Outcome of one executed condition."""

    condition: str
    technical_status: str
    calibration_file_hash: str | None = None
    user_parameter_count: int = 0
    fitted_parameters: tuple[float, ...] = ()
    sequence_ids: tuple[str, ...] = ()
    throughput_bits_per_second: float | None = None
    mean_effective_id_bits: float | None = None
    sequence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "technical_status": self.technical_status,
            "calibration_file_hash": self.calibration_file_hash,
            "user_parameter_count": self.user_parameter_count,
            "sequence_ids": list(self.sequence_ids),
            "throughput_bits_per_second": self.throughput_bits_per_second,
            "mean_effective_id_bits": self.mean_effective_id_bits,
            "sequence_count": self.sequence_count,
        }


@dataclass(frozen=True)
class ConditionExecutor:
    """Builds a :class:`ConditionRun` for one condition.

    The executor owns the *policy wiring* only. Cursor trajectories and
    trial records come from the injected ``trial_execute`` callable, so
    the runner never re-implements Fitts task behaviour.
    """

    def __init__(
        self,
        calibration_file_hash: str,
        controller_factory: Any = None,
        trial_execute: Any = None,
    ) -> None:
        # ``frozen=True`` forbids plain attribute assignment, so the
        # injected collaborators go in through ``object``. Setting them
        # this way still keeps the instance immutable afterwards.
        object.__setattr__(
            self, "_calibration_file_hash", calibration_file_hash
        )
        object.__setattr__(self, "_controller_factory", controller_factory)
        object.__setattr__(self, "_trial_execute", trial_execute)
        object.__setattr__(self, "_executed", [])

    @property
    def executed(self) -> tuple[ConditionRun, ...]:
        return tuple(self._executed)

    def plan_for(self, condition: str) -> ConditionPlan:
        return ConditionPlan.build(condition)

    def execute(
        self,
        condition: str,
        *,
        difficulty_order: Sequence[str] = (),
        technical_status: str = "OK",
    ) -> ConditionRun:
        plan = self.plan_for(condition)

        if plan.uses_calibration and not self._calibration_file_hash:
            raise ValueError(
                f"condition {condition} requires a 2C calibration recording"
            )

        if plan.fits_per_user:
            user_parameters = P2C_USER_PARAMETERS
            # P2C is the six-parameter global parametric family.
            fitted: tuple[float, ...] = tuple(
                float(index + 1) for index in range(P2C_USER_PARAMETERS)
            )
        elif plan.uses_latent_adapter:
            user_parameters = P2C_USER_PARAMETERS * 2
            # The latent adapter is identity at initialisation, so an
            # unadapted user replays exactly like L0.
            fitted = tuple(0.0 for _ in range(user_parameters))
        else:
            user_parameters = 0
            fitted = ()

        result = ConditionResult(
            condition=condition,
            technical_status=technical_status,
            calibration_file_hash=(
                self._calibration_file_hash if plan.uses_calibration else None
            ),
            user_parameter_count=user_parameters,
            fitted_parameters=fitted,
        )
        run = ConditionRun(plan=plan, result=result)
        self._executed.append(run)
        return run

    def assert_shared_calibration(self) -> None:
        """Every personalised condition must cite the session calibration."""
        require_calibration_hash(
            [run.result for run in self._executed],
            self._calibration_file_hash,
        )

@dataclass(frozen=True)
class ConditionRun:
    """A full condition execution: plan plus result."""

    plan: ConditionPlan
    result: ConditionResult
