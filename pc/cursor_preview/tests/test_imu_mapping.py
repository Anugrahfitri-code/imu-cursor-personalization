import pytest

from pc.cursor_preview.imu_mapping import (
    NeutralBiasEstimator,
    apply_dead_zone,
    gyro_to_velocity,
    integrate_cursor,
)


def test_zero_gyro_produces_zero_velocity():
    vx, vy = gyro_to_velocity(
        0.0,
        0.0,
        bias_x=0.0,
        bias_z=0.0,
        gain=500.0,
        x_sign=1,
        y_sign=1,
        dead_zone=0.03,
    )

    assert vx == 0.0
    assert vy == 0.0


def test_dead_zone_suppresses_small_motion():
    assert apply_dead_zone(
        0.02,
        0.03,
        True,
    ) == 0.0

    assert apply_dead_zone(
        -0.02,
        0.03,
        True,
    ) == 0.0

    assert apply_dead_zone(
        0.04,
        0.03,
        True,
    ) == pytest.approx(0.04)


def test_horizontal_gyro_z_maps_to_vx_with_sign():
    vx, vy = gyro_to_velocity(
        gx=0.0,
        gz=0.2,
        bias_x=0.0,
        bias_z=0.0,
        gain=500.0,
        x_sign=-1,
        y_sign=1,
        dead_zone=0.03,
    )

    assert vx == pytest.approx(-100.0)
    assert vy == 0.0


def test_vertical_gyro_x_maps_to_vy_with_sign():
    vx, vy = gyro_to_velocity(
        gx=0.2,
        gz=0.0,
        bias_x=0.0,
        bias_z=0.0,
        gain=500.0,
        x_sign=1,
        y_sign=-1,
        dead_zone=0.03,
    )

    assert vx == 0.0
    assert vy == pytest.approx(-100.0)


def test_double_gain_doubles_velocity():
    args = dict(
        gx=0.2,
        gz=0.3,
        bias_x=0.0,
        bias_z=0.0,
        x_sign=1,
        y_sign=1,
        dead_zone=0.03,
    )

    vx1, vy1 = gyro_to_velocity(
        gain=250.0,
        **args,
    )

    vx2, vy2 = gyro_to_velocity(
        gain=500.0,
        **args,
    )

    assert vx2 == pytest.approx(2.0 * vx1)
    assert vy2 == pytest.approx(2.0 * vy1)


def test_bias_is_subtracted_before_dead_zone():
    vx, vy = gyro_to_velocity(
        gx=0.11,
        gz=0.21,
        bias_x=0.10,
        bias_z=0.20,
        gain=500.0,
        x_sign=1,
        y_sign=1,
        dead_zone=0.03,
    )

    assert vx == 0.0
    assert vy == 0.0


def test_integrate_cursor_scales_with_dt():
    p1 = integrate_cursor(
        100.0,
        100.0,
        50.0,
        -25.0,
        0.1,
        1200,
        700,
    )

    p2 = integrate_cursor(
        100.0,
        100.0,
        50.0,
        -25.0,
        0.2,
        1200,
        700,
    )

    assert p1 == pytest.approx(
        (105.0, 97.5)
    )

    assert p2 == pytest.approx(
        (110.0, 95.0)
    )


def test_integrate_cursor_clamps_to_window_edges():
    assert integrate_cursor(
        1195.0,
        695.0,
        100.0,
        100.0,
        1.0,
        1200,
        700,
    ) == (
        1200.0,
        700.0,
    )

    assert integrate_cursor(
        5.0,
        5.0,
        -100.0,
        -100.0,
        1.0,
        1200,
        700,
    ) == (
        0.0,
        0.0,
    )


def test_neutral_bias_estimator_uses_mean_after_duration():
    est = NeutralBiasEstimator(
        duration_s=2.0
    )

    est.add_sample(
        10.0,
        0.10,
        -0.20,
        0.30,
    )

    est.add_sample(
        11.0,
        0.20,
        -0.10,
        0.40,
    )

    est.add_sample(
        12.0,
        0.30,
        0.00,
        0.50,
    )

    assert est.ready(11.99) is False
    assert est.ready(12.0) is True

    bx, by, bz = est.bias()

    assert bx == pytest.approx(0.20)
    assert by == pytest.approx(-0.10)
    assert bz == pytest.approx(0.40)


def test_neutral_bias_reset_clears_previous_samples():
    est = NeutralBiasEstimator(
        duration_s=2.0
    )

    est.add_sample(
        10.0,
        1.0,
        2.0,
        3.0,
    )

    est.reset()

    assert est.ready(20.0) is False

    with pytest.raises(
        RuntimeError,
        match="bias is not ready",
    ):
        est.bias()