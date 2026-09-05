import math

import pytest

from pc.clock_sync.clock_model import (
    MAD_MULTIPLIER,
    ProbeObservation,
    fit_half_diagnostics,
    fit_robust_clock_model,
    percentile,
    select_low_delay_background,
)


def make_probe(
    *,
    seq: int,
    phase: str,
    phone_mid_ns: int,
    pc_mid_ns: int,
    delay_like_ns: int = 2_000_000,
) -> ProbeObservation:

    phone_processing_ns = 100_000

    pc_rtt_ns = (
        delay_like_ns
        + phone_processing_ns
    )

    t2 = (
        phone_mid_ns
        - phone_processing_ns // 2
    )

    t3 = (
        phone_mid_ns
        + phone_processing_ns // 2
    )

    t1 = (
        pc_mid_ns
        - pc_rtt_ns // 2
    )

    t4 = (
        pc_mid_ns
        + pc_rtt_ns // 2
    )

    return ProbeObservation(
        session_id="synthetic",
        probe_phase=phase,
        probe_seq=seq,
        t1_pc_ns=t1,
        t2_phone_ns=t2,
        t3_phone_ns=t3,
        t4_pc_ns=t4,
        response_valid=True,
        invalid_reason="",
    )


def test_derived_probe_metrics_are_correct():

    p = make_probe(
        seq=1,
        phase="background",
        phone_mid_ns=1_000_000_000,
        pc_mid_ns=2_000_000_000,
        delay_like_ns=4_000_000,
    )

    assert p.phone_mid_ns == 1_000_000_000
    assert p.pc_mid_ns == 2_000_000_000

    assert (
        p.phone_processing_ns
        == 100_000
    )

    assert (
        p.delay_like_ns
        == 4_000_000
    )

    assert (
        p.pc_rtt_ns
        == 4_100_000
    )


def test_low_delay_selection_picks_one_per_10s_block():

    base_phone = 50_000_000_000
    base_pc = 80_000_000_000

    probes = [

        make_probe(
            seq=1,
            phase="background",
            phone_mid_ns=(
                base_phone
                + 0_000_000_000
            ),
            pc_mid_ns=(
                base_pc
                + 0_000_000_000
            ),
            delay_like_ns=9_000_000,
        ),

        make_probe(
            seq=2,
            phase="background",
            phone_mid_ns=(
                base_phone
                + 2_000_000_000
            ),
            pc_mid_ns=(
                base_pc
                + 2_000_000_000
            ),
            delay_like_ns=2_000_000,
        ),

        make_probe(
            seq=3,
            phase="background",
            phone_mid_ns=(
                base_phone
                + 10_000_000_000
            ),
            pc_mid_ns=(
                base_pc
                + 10_000_000_000
            ),
            delay_like_ns=8_000_000,
        ),

        make_probe(
            seq=4,
            phase="background",
            phone_mid_ns=(
                base_phone
                + 12_000_000_000
            ),
            pc_mid_ns=(
                base_pc
                + 12_000_000_000
            ),
            delay_like_ns=3_000_000,
        ),
    ]

    selected = (
        select_low_delay_background(
            probes,
            block_ns=10_000_000_000,
        )
    )

    assert [
        p.probe_seq
        for p in selected
    ] == [
        2,
        4,
    ]


def test_exact_large_timestamp_affine_data_recovers_model():

    alpha = 1.000020
    beta = 9_000_000_000_000

    probes = []

    phone0 = 50_000_000_000_000

    for i in range(20):

        x = (
            phone0
            + i * 10_000_000_000
        )

        y = round(
            alpha * x
            + beta
        )

        probes.append(
            make_probe(
                seq=i,
                phase="background",
                phone_mid_ns=x,
                pc_mid_ns=y,
                delay_like_ns=1_000_000,
            )
        )

    result = fit_robust_clock_model(
        probes
    )

    assert result.alpha == pytest.approx(
        alpha,
        rel=0,
        abs=1e-10,
    )

    assert result.beta_ns == pytest.approx(
        beta,
        abs=20_000,
    )

    assert result.skew_ppm == pytest.approx(
        20.0,
        abs=0.001,
    )


def test_robust_fit_rejects_one_gross_midpoint_outlier():

    alpha = 0.999985
    beta = 7_000_000_000_000

    phone0 = 60_000_000_000_000

    probes = []

    for i in range(30):

        x = (
            phone0
            + i * 10_000_000_000
        )

        y = round(
            alpha * x
            + beta
        )

        if i == 15:
            y += 200_000_000

        probes.append(
            make_probe(
                seq=i,
                phase="background",
                phone_mid_ns=x,
                pc_mid_ns=y,
                delay_like_ns=1_000_000,
            )
        )

    result = fit_robust_clock_model(
        probes
    )

    assert (
        len(result.inlier_probe_seqs)
        < len(probes)
    )

    assert (
        15
        not in result.inlier_probe_seqs
    )

    assert result.alpha == pytest.approx(
        alpha,
        abs=2e-8,
    )


def test_invalid_probes_never_enter_selection_or_fit():

    good = make_probe(
        seq=1,
        phase="background",
        phone_mid_ns=10_000_000_000,
        pc_mid_ns=20_000_000_000,
    )

    bad = ProbeObservation(
        session_id="synthetic",
        probe_phase="background",
        probe_seq=2,
        t1_pc_ns=1,
        t2_phone_ns=2,
        t3_phone_ns=3,
        t4_pc_ns=4,
        response_valid=False,
        invalid_reason="timeout",
    )

    selected = (
        select_low_delay_background(
            [good, bad]
        )
    )

    assert [
        p.probe_seq
        for p in selected
    ] == [1]


def test_percentile_linear_interpolation():

    values = [
        0.0,
        10.0,
        20.0,
        30.0,
        40.0,
    ]

    assert percentile(
        values,
        0.50,
    ) == pytest.approx(
        20.0
    )

    assert percentile(
        values,
        0.95,
    ) == pytest.approx(
        38.0
    )


def test_first_half_second_half_diagnostics_are_finite():

    alpha = 1.000010
    beta = 2_000_000_000_000

    phone0 = 30_000_000_000_000

    probes = []

    for i in range(20):

        x = (
            phone0
            + i * 10_000_000_000
        )

        y = round(
            alpha * x
            + beta
        )

        probes.append(
            make_probe(
                seq=i,
                phase="background",
                phone_mid_ns=x,
                pc_mid_ns=y,
            )
        )

    first, second = (
        fit_half_diagnostics(
            probes
        )
    )

    assert math.isfinite(
        first.alpha
    )

    assert math.isfinite(
        second.alpha
    )

    assert first.alpha == pytest.approx(
        alpha,
        abs=1e-9,
    )

    assert second.alpha == pytest.approx(
        alpha,
        abs=1e-9,
    )


def test_phone_to_pc_mapping_is_monotonic_for_positive_alpha():

    alpha = 1.000010
    beta = 1_000_000_000_000

    phone0 = 20_000_000_000_000

    probes = [

        make_probe(
            seq=i,
            phase="background",
            phone_mid_ns=(
                phone0
                + i * 10_000_000_000
            ),
            pc_mid_ns=round(
                alpha
                * (
                    phone0
                    + i * 10_000_000_000
                )
                + beta
            ),
        )

        for i in range(10)
    ]

    model = fit_robust_clock_model(
        probes
    )

    mapped_a = (
        model.map_phone_to_pc_ns(
            phone0
        )
    )

    mapped_b = (
        model.map_phone_to_pc_ns(
            phone0
            + 1_000_000_000
        )
    )

    assert mapped_b > mapped_a


def test_mad_multiplier_is_frozen_at_six():
    assert MAD_MULTIPLIER == 6.0