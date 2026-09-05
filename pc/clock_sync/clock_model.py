from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Iterable


MAD_MULTIPLIER = 6.0
DEFAULT_BLOCK_NS = 10_000_000_000


@dataclass(frozen=True)
class ProbeObservation:
    session_id: str
    probe_phase: str
    probe_seq: int

    t1_pc_ns: int
    t2_phone_ns: int
    t3_phone_ns: int
    t4_pc_ns: int

    response_valid: bool
    invalid_reason: str = ""

    @property
    def pc_rtt_ns(self) -> int:
        return (
            self.t4_pc_ns
            - self.t1_pc_ns
        )

    @property
    def phone_processing_ns(self) -> int:
        return (
            self.t3_phone_ns
            - self.t2_phone_ns
        )

    @property
    def delay_like_ns(self) -> int:
        return (
            self.pc_rtt_ns
            - self.phone_processing_ns
        )

    @property
    def phone_mid_ns(self) -> int:
        return (
            self.t2_phone_ns
            + self.t3_phone_ns
        ) // 2

    @property
    def pc_mid_ns(self) -> int:
        return (
            self.t1_pc_ns
            + self.t4_pc_ns
        ) // 2


@dataclass(frozen=True)
class ClockModel:
    alpha: float
    beta_ns: float
    skew_ppm: float

    selected_probe_seqs: tuple[int, ...]
    inlier_probe_seqs: tuple[int, ...]

    residual_ns_by_seq: dict[int, float]

    def map_phone_to_pc_ns(
        self,
        phone_ns: int,
    ) -> float:
        return (
            self.alpha
            * phone_ns
            + self.beta_ns
        )


def percentile(
    values: Iterable[float],
    q: float,
) -> float:

    vals = sorted(
        float(value)
        for value in values
    )

    if not vals:
        raise ValueError(
            "percentile requires values"
        )

    if not 0.0 <= q <= 1.0:
        raise ValueError(
            "q must be in [0, 1]"
        )

    if len(vals) == 1:
        return vals[0]

    position = (
        (len(vals) - 1)
        * q
    )

    lower = int(position)

    upper = min(
        lower + 1,
        len(vals) - 1,
    )

    fraction = (
        position - lower
    )

    return (
        vals[lower]
        * (1.0 - fraction)
        + vals[upper]
        * fraction
    )


def _valid_background(
    probes: Iterable[ProbeObservation],
) -> list[ProbeObservation]:

    return [
        probe
        for probe in probes
        if (
            probe.response_valid

            and probe.probe_phase
            == "background"

            and probe.t4_pc_ns
            >= probe.t1_pc_ns

            and probe.t3_phone_ns
            >= probe.t2_phone_ns

            and probe.delay_like_ns
            >= 0
        )
    ]


def select_low_delay_background(
    probes: Iterable[ProbeObservation],
    *,
    block_ns: int = DEFAULT_BLOCK_NS,
) -> list[ProbeObservation]:

    if block_ns <= 0:
        raise ValueError(
            "block_ns must be > 0"
        )

    valid = sorted(
        _valid_background(probes),
        key=lambda probe: probe.pc_mid_ns,
    )

    if not valid:
        return []

    origin = valid[0].pc_mid_ns

    blocks: dict[
        int,
        list[ProbeObservation],
    ] = {}

    for probe in valid:

        block_index = (
            probe.pc_mid_ns
            - origin
        ) // block_ns

        blocks.setdefault(
            int(block_index),
            [],
        ).append(probe)

    selected = []

    for block_index in sorted(blocks):

        best = min(
            blocks[block_index],
            key=lambda probe: (
                probe.delay_like_ns,
                probe.probe_seq,
            ),
        )

        selected.append(best)

    return selected


def _fit_xy(
    xs: list[float],
    ys: list[float],
) -> tuple[float, float]:

    if len(xs) != len(ys):
        raise ValueError(
            "x/y length mismatch"
        )

    if len(xs) < 2:
        raise ValueError(
            "at least two observations required"
        )

    # Center timestamps for numerical stability.
    x0 = median(xs)
    y0 = median(ys)

    xc = [
        x - x0
        for x in xs
    ]

    yc = [
        y - y0
        for y in ys
    ]

    denominator = sum(
        x * x
        for x in xc
    )

    if denominator == 0:
        raise ValueError(
            "phone timestamps have zero spread"
        )

    alpha = (
        sum(
            x * y
            for x, y in zip(
                xc,
                yc,
            )
        )
        / denominator
    )

    centered_intercept = (
        sum(
            y - alpha * x
            for x, y in zip(
                xc,
                yc,
            )
        )
        / len(xs)
    )

    beta = (
        y0
        + centered_intercept
        - alpha * x0
    )

    if (
        not isfinite(alpha)
        or not isfinite(beta)
    ):
        raise ValueError(
            "non-finite affine fit"
        )

    return alpha, beta


def _residuals(
    probes: list[ProbeObservation],
    alpha: float,
    beta: float,
) -> dict[int, float]:

    return {
        probe.probe_seq: (
            float(probe.pc_mid_ns)
            - (
                alpha
                * float(
                    probe.phone_mid_ns
                )
                + beta
            )
        )
        for probe in probes
    }


def fit_robust_clock_model(
    probes: Iterable[ProbeObservation],
    *,
    mad_multiplier: float = MAD_MULTIPLIER,
) -> ClockModel:

    if mad_multiplier <= 0:
        raise ValueError(
            "mad_multiplier must be > 0"
        )

    selected = (
        select_low_delay_background(
            probes
        )
    )

    if len(selected) < 2:
        raise ValueError(
            "not enough selected "
            "background probes"
        )

    xs = [
        float(probe.phone_mid_ns)
        for probe in selected
    ]

    ys = [
        float(probe.pc_mid_ns)
        for probe in selected
    ]

    # --------------------------------------------
    # INITIAL CENTERED OLS
    # --------------------------------------------

    alpha_initial, beta_initial = (
        _fit_xy(
            xs,
            ys,
        )
    )

    residual_initial = _residuals(
        selected,
        alpha_initial,
        beta_initial,
    )

    residual_values = list(
        residual_initial.values()
    )

    residual_center = median(
        residual_values
    )

    deviations = [
        abs(
            value
            - residual_center
        )
        for value in residual_values
    ]

    mad = median(
        deviations
    )

    # --------------------------------------------
    # ROBUST SCREENING
    # --------------------------------------------

    if mad == 0:

        inliers = [
            probe
            for probe in selected
            if (
                residual_initial[
                    probe.probe_seq
                ]
                == residual_center
            )
        ]

        # Floating-point residuals can differ by
        # tiny amounts even for exact synthetic
        # affine data. If exact-equality screening
        # leaves too few points, retain selected.
        if len(inliers) < 2:
            inliers = selected

    else:

        cutoff = (
            mad_multiplier
            * mad
        )

        inliers = [
            probe
            for probe in selected
            if abs(
                residual_initial[
                    probe.probe_seq
                ]
                - residual_center
            ) <= cutoff
        ]

    if len(inliers) < 2:
        raise ValueError(
            "robust screening left "
            "too few inliers"
        )

    # --------------------------------------------
    # FINAL REFIT
    # --------------------------------------------

    alpha, beta = _fit_xy(
        [
            float(
                probe.phone_mid_ns
            )
            for probe in inliers
        ],
        [
            float(
                probe.pc_mid_ns
            )
            for probe in inliers
        ],
    )

    residual_final = _residuals(
        inliers,
        alpha,
        beta,
    )

    return ClockModel(
        alpha=alpha,
        beta_ns=beta,

        skew_ppm=(
            alpha - 1.0
        ) * 1_000_000.0,

        selected_probe_seqs=tuple(
            probe.probe_seq
            for probe in selected
        ),

        inlier_probe_seqs=tuple(
            probe.probe_seq
            for probe in inliers
        ),

        residual_ns_by_seq=(
            residual_final
        ),
    )


def fit_half_diagnostics(
    probes: Iterable[ProbeObservation],
) -> tuple[
    ClockModel,
    ClockModel,
]:

    valid = sorted(
        _valid_background(probes),
        key=lambda probe: probe.pc_mid_ns,
    )

    if len(valid) < 4:
        raise ValueError(
            "at least four valid "
            "background probes required"
        )

    midpoint = (
        len(valid) // 2
    )

    first_half = valid[
        :midpoint
    ]

    second_half = valid[
        midpoint:
    ]

    first_model = (
        fit_robust_clock_model(
            first_half
        )
    )

    second_model = (
        fit_robust_clock_model(
            second_half
        )
    )

    return (
        first_model,
        second_model,
    )