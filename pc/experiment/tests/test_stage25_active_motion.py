import math

import pytest

from pc.experiment.preprocessing.active_motion import (
    annotate_active_motion_stream,
    classify_active_motion_sample,
)


def _config(
    *,
    method="L2_NORM_THRESHOLD",
    channels=("x", "y"),
    threshold=5.0,
    comparison="GREATER_EQUAL",
):
    return {
        "method":
            method,
        "channels":
            channels,
        "threshold":
            threshold,
        "comparison":
            comparison,
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


def test_below_threshold_is_inactive():
    result = classify_active_motion_sample(
        sample=_row(
            0,
            x=3.0,
            y=3.0,
        ),
        active_motion_config=_config(
            threshold=5.0,
        ),
    )

    assert result is False


def test_exact_threshold_is_active():
    result = classify_active_motion_sample(
        sample=_row(
            0,
            x=3.0,
            y=4.0,
        ),
        active_motion_config=_config(
            threshold=5.0,
        ),
    )

    assert result is True


def test_above_threshold_is_active():
    result = classify_active_motion_sample(
        sample=_row(
            0,
            x=6.0,
            y=8.0,
        ),
        active_motion_config=_config(
            threshold=5.0,
        ),
    )

    assert result is True


def test_l2_norm_uses_only_configured_channels():
    config = _config(
        channels=("x", "y"),
        threshold=5.0,
    )

    first = classify_active_motion_sample(
        sample=_row(
            0,
            x=3.0,
            y=4.0,
            z=0.0,
        ),
        active_motion_config=config,
    )

    second = classify_active_motion_sample(
        sample=_row(
            0,
            x=3.0,
            y=4.0,
            z=999999.0,
        ),
        active_motion_config=config,
    )

    assert first is True
    assert second is True
    assert first == second


def test_l2_norm_is_sign_invariant():
    positive = classify_active_motion_sample(
        sample=_row(
            0,
            x=3.0,
            y=4.0,
        ),
        active_motion_config=_config(),
    )

    negative = classify_active_motion_sample(
        sample=_row(
            0,
            x=-3.0,
            y=-4.0,
        ),
        active_motion_config=_config(),
    )

    assert positive is True
    assert negative is True


def test_stream_annotation_adds_boolean_flag():
    result = annotate_active_motion_stream(
        stream=[
            _row(
                0,
                x=1.0,
                y=1.0,
            ),
            _row(
                10,
                x=3.0,
                y=4.0,
            ),
            _row(
                20,
                x=10.0,
                y=0.0,
            ),
        ],
        active_motion_config=_config(
            threshold=5.0,
        ),
    )

    assert [
        row["active_motion_flag"]
        for row in result
    ] == [
        False,
        True,
        True,
    ]

    assert all(
        isinstance(
            row["active_motion_flag"],
            bool,
        )
        for row in result
    )


def test_future_perturbation_cannot_change_earlier_flags():
    first_stream = [
        _row(
            0,
            x=1.0,
            y=1.0,
        ),
        _row(
            10,
            x=2.0,
            y=2.0,
        ),
        _row(
            20,
            x=3.0,
            y=4.0,
        ),
    ]

    second_stream = [
        dict(row)
        for row in first_stream
    ]

    second_stream[2]["x"] = 999999.0
    second_stream[2]["y"] = 999999.0

    first = annotate_active_motion_stream(
        stream=first_stream,
        active_motion_config=_config(),
    )

    second = annotate_active_motion_stream(
        stream=second_stream,
        active_motion_config=_config(),
    )

    assert (
        first[:2]
        == second[:2]
    )


def test_annotation_preserves_non_motion_fields():
    result = annotate_active_motion_stream(
        stream=[
            _row(
                100,
                grid_index=123,
                x=3.0,
                y=4.0,
                label_status="BOUNDARY",
            )
        ],
        active_motion_config=_config(),
    )

    assert (
        result[0]["grid_pc_time_ns"]
        == 100
    )

    assert (
        result[0]["grid_index"]
        == 123
    )

    assert (
        result[0]["label_status"]
        == "BOUNDARY"
    )


def test_annotation_does_not_mutate_input():
    stream = [
        _row(
            0,
            x=1.0,
            y=2.0,
        ),
        _row(
            10,
            x=3.0,
            y=4.0,
        ),
    ]

    original = [
        dict(row)
        for row in stream
    ]

    annotate_active_motion_stream(
        stream=stream,
        active_motion_config=_config(),
    )

    assert stream == original


def test_unknown_method_fails_closed():
    with pytest.raises(
        ValueError,
        match="method",
    ):
        classify_active_motion_sample(
            sample=_row(
                0,
                x=3.0,
                y=4.0,
            ),
            active_motion_config=_config(
                method="MAGIC_ACTIVITY",
            ),
        )


def test_unknown_comparison_fails_closed():
    with pytest.raises(
        ValueError,
        match="comparison",
    ):
        classify_active_motion_sample(
            sample=_row(
                0,
                x=3.0,
                y=4.0,
            ),
            active_motion_config=_config(
                comparison="MAYBE",
            ),
        )


def test_negative_threshold_fails_closed():
    with pytest.raises(
        ValueError,
        match="threshold",
    ):
        classify_active_motion_sample(
            sample=_row(0),
            active_motion_config=_config(
                threshold=-1.0,
            ),
        )


def test_non_finite_threshold_fails_closed():
    with pytest.raises(
        ValueError,
        match="threshold",
    ):
        classify_active_motion_sample(
            sample=_row(0),
            active_motion_config=_config(
                threshold=float("nan"),
            ),
        )


def test_unsupported_channel_fails_closed():
    with pytest.raises(
        ValueError,
        match="channel",
    ):
        classify_active_motion_sample(
            sample=_row(0),
            active_motion_config=_config(
                channels=(
                    "x",
                    "w",
                ),
            ),
        )


def test_duplicate_channel_fails_closed():
    with pytest.raises(
        ValueError,
        match="channel",
    ):
        classify_active_motion_sample(
            sample=_row(0),
            active_motion_config=_config(
                channels=(
                    "x",
                    "x",
                ),
            ),
        )


def test_empty_channel_list_fails_closed():
    with pytest.raises(
        ValueError,
        match="channel",
    ):
        classify_active_motion_sample(
            sample=_row(0),
            active_motion_config=_config(
                channels=(),
            ),
        )


def test_missing_sensor_channel_fails_closed():
    sample = {
        "grid_pc_time_ns":
            0,
        "x":
            3.0,
    }

    with pytest.raises(
        ValueError,
        match="channel",
    ):
        classify_active_motion_sample(
            sample=sample,
            active_motion_config=_config(
                channels=("x", "y"),
            ),
        )


def test_non_finite_sensor_value_fails_closed():
    with pytest.raises(
        ValueError,
        match="finite",
    ):
        classify_active_motion_sample(
            sample=_row(
                0,
                x=math.inf,
                y=0.0,
            ),
            active_motion_config=_config(),
        )


def test_configuration_fields_are_not_read_from_sample():
    first = _row(
        0,
        x=3.0,
        y=4.0,
    )

    first["threshold"] = 999999.0
    first["comparison"] = "BROKEN"

    result = classify_active_motion_sample(
        sample=first,
        active_motion_config=_config(
            threshold=5.0,
            comparison="GREATER_EQUAL",
        ),
    )

    assert result is True


def test_active_motion_classification_is_deterministic():
    sample = _row(
        0,
        x=2.5,
        y=4.5,
        z=99.0,
    )

    config = _config(
        channels=("x", "y"),
        threshold=5.0,
    )

    first = classify_active_motion_sample(
        sample=sample,
        active_motion_config=config,
    )

    second = classify_active_motion_sample(
        sample=sample,
        active_motion_config=config,
    )

    assert first == second