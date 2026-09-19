import math

import pytest

from pc.experiment.preprocessing.filtering import (
    filter_sensor_stream,
    one_pole_alpha,
)


def _config(
    *,
    family="ONE_POLE_IIR",
    order=1,
    cutoff_hz=10.0,
    grid_frequency_hz=100.0,
    initialization="FIRST_SAMPLE",
    reset_policy="EXPLICIT_BOUNDARIES",
):
    return {
        "family":
            family,
        "order":
            order,
        "cutoff_hz":
            cutoff_hz,
        "grid_frequency_hz":
            grid_frequency_hz,
        "initialization":
            initialization,
        "reset_policy":
            reset_policy,
    }


def _row(
    grid_pc_time_ns,
    *,
    x=0.0,
    y=0.0,
    z=0.0,
    grid_index=0,
    label_status="VALID",
):
    return {
        "grid_pc_time_ns":
            grid_pc_time_ns,
        "grid_index":
            grid_index,
        "x":
            x,
        "y":
            y,
        "z":
            z,
        "label_status":
            label_status,
    }


def _filter(
    stream,
    *,
    config=None,
    channels=("x", "y", "z"),
    reset_before_indices=(),
):
    if config is None:
        config = _config()

    return filter_sensor_stream(
        stream=stream,
        filter_config=config,
        channels=channels,
        reset_before_indices=reset_before_indices,
    )


def test_one_pole_alpha_matches_frozen_formula_mechanics():
    cutoff_hz = 10.0
    grid_frequency_hz = 100.0

    dt = 1.0 / grid_frequency_hz

    rc = (
        1.0
        / (
            2.0
            * math.pi
            * cutoff_hz
        )
    )

    expected = dt / (rc + dt)

    assert one_pole_alpha(
        cutoff_hz=cutoff_hz,
        grid_frequency_hz=grid_frequency_hz,
    ) == pytest.approx(expected)


def test_first_sample_initialization_equals_first_input():
    result = _filter(
        [
            _row(
                0,
                x=5.0,
                y=-2.0,
                z=1.0,
            ),
            _row(
                10,
                x=10.0,
                y=4.0,
                z=3.0,
            ),
        ]
    )

    assert result[0]["x"] == 5.0
    assert result[0]["y"] == -2.0
    assert result[0]["z"] == 1.0


def test_constant_input_remains_constant():
    result = _filter(
        [
            _row(
                index * 10,
                grid_index=index,
                x=3.0,
                y=-4.0,
                z=2.0,
            )
            for index in range(8)
        ]
    )

    for row in result:
        assert row["x"] == pytest.approx(3.0)
        assert row["y"] == pytest.approx(-4.0)
        assert row["z"] == pytest.approx(2.0)


def test_step_response_is_causal_and_smoothed():
    result = _filter(
        [
            _row(
                0,
                x=0.0,
            ),
            _row(
                10,
                x=1.0,
            ),
            _row(
                20,
                x=1.0,
            ),
        ],
        channels=("x",),
    )

    assert result[0]["x"] == 0.0

    assert (
        0.0
        < result[1]["x"]
        < 1.0
    )

    assert (
        result[1]["x"]
        < result[2]["x"]
        < 1.0
    )


def test_impulse_response_decays_without_future_lookahead():
    result = _filter(
        [
            _row(
                0,
                x=1.0,
            ),
            _row(
                10,
                x=0.0,
            ),
            _row(
                20,
                x=0.0,
            ),
            _row(
                30,
                x=0.0,
            ),
        ],
        channels=("x",),
    )

    values = [
        row["x"]
        for row in result
    ]

    assert values[0] == pytest.approx(1.0)

    assert (
        1.0
        > values[1]
        > values[2]
        > values[3]
        > 0.0
    )


def test_future_perturbation_cannot_change_earlier_outputs():
    first_stream = [
        _row(
            0,
            x=0.0,
        ),
        _row(
            10,
            x=1.0,
        ),
        _row(
            20,
            x=2.0,
        ),
        _row(
            30,
            x=3.0,
        ),
    ]

    second_stream = [
        dict(row)
        for row in first_stream
    ]

    second_stream[3]["x"] = 999999.0

    first = _filter(
        first_stream,
        channels=("x",),
    )

    second = _filter(
        second_stream,
        channels=("x",),
    )

    assert (
        first[:3]
        == second[:3]
    )


def test_explicit_reset_initializes_from_current_sample():
    result = _filter(
        [
            _row(
                0,
                x=0.0,
            ),
            _row(
                10,
                x=10.0,
            ),
            _row(
                20,
                x=100.0,
            ),
            _row(
                30,
                x=100.0,
            ),
        ],
        channels=("x",),
        reset_before_indices=(2,),
    )

    assert (
        result[2]["x"]
        == pytest.approx(100.0)
    )


def test_without_reset_prior_state_is_preserved():
    result = _filter(
        [
            _row(
                0,
                x=0.0,
            ),
            _row(
                10,
                x=10.0,
            ),
            _row(
                20,
                x=100.0,
            ),
        ],
        channels=("x",),
    )

    assert (
        result[2]["x"]
        < 100.0
    )


def test_filter_preserves_grid_timestamps_exactly():
    stream = [
        _row(
            100,
            grid_index=0,
            x=1.0,
        ),
        _row(
            200,
            grid_index=1,
            x=2.0,
        ),
        _row(
            300,
            grid_index=2,
            x=3.0,
        ),
    ]

    result = _filter(
        stream,
        channels=("x",),
    )

    assert [
        row["grid_pc_time_ns"]
        for row in result
    ] == [
        100,
        200,
        300,
    ]


def test_non_filtered_fields_are_preserved():
    stream = [
        _row(
            100,
            grid_index=123,
            x=1.0,
            label_status="BOUNDARY",
        ),
        _row(
            200,
            grid_index=456,
            x=2.0,
            label_status="VALID",
        ),
    ]

    result = _filter(
        stream,
        channels=("x",),
    )

    assert [
        row["grid_index"]
        for row in result
    ] == [
        123,
        456,
    ]

    assert [
        row["label_status"]
        for row in result
    ] == [
        "BOUNDARY",
        "VALID",
    ]


def test_filter_does_not_mutate_input():
    stream = [
        _row(
            0,
            x=0.0,
        ),
        _row(
            10,
            x=1.0,
        ),
    ]

    original = [
        dict(row)
        for row in stream
    ]

    _filter(
        stream,
        channels=("x",),
    )

    assert stream == original


def test_unknown_filter_family_fails_closed():
    with pytest.raises(
        ValueError,
        match="family",
    ):
        _filter(
            [
                _row(0),
                _row(10),
            ],
            config=_config(
                family="MAGIC_FILTER",
            ),
        )


def test_non_first_order_one_pole_fails_closed():
    with pytest.raises(
        ValueError,
        match="order",
    ):
        _filter(
            [
                _row(0),
                _row(10),
            ],
            config=_config(
                order=2,
            ),
        )


def test_zero_cutoff_fails_closed():
    with pytest.raises(
        ValueError,
        match="cutoff",
    ):
        _filter(
            [
                _row(0),
                _row(10),
            ],
            config=_config(
                cutoff_hz=0.0,
            ),
        )


def test_cutoff_at_or_above_nyquist_fails_closed():
    with pytest.raises(
        ValueError,
        match="cutoff",
    ):
        _filter(
            [
                _row(0),
                _row(10),
            ],
            config=_config(
                cutoff_hz=50.0,
                grid_frequency_hz=100.0,
            ),
        )


def test_non_positive_grid_frequency_fails_closed():
    with pytest.raises(
        ValueError,
        match="frequency",
    ):
        _filter(
            [
                _row(0),
                _row(10),
            ],
            config=_config(
                grid_frequency_hz=0.0,
            ),
        )


def test_non_finite_sensor_value_fails_closed():
    with pytest.raises(
        ValueError,
        match="finite",
    ):
        _filter(
            [
                _row(
                    0,
                    x=0.0,
                ),
                _row(
                    10,
                    x=float("nan"),
                ),
            ],
            channels=("x",),
        )


def test_invalid_reset_index_fails_closed():
    with pytest.raises(
        ValueError,
        match="reset",
    ):
        _filter(
            [
                _row(0),
                _row(10),
            ],
            reset_before_indices=(99,),
        )


def test_filtering_is_deterministic():
    stream = [
        _row(
            0,
            x=0.0,
            y=1.0,
            z=2.0,
        ),
        _row(
            10,
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        _row(
            20,
            x=2.0,
            y=3.0,
            z=4.0,
        ),
    ]

    first = _filter(
        stream
    )

    second = _filter(
        stream
    )

    assert first == second