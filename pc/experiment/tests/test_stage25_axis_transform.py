import re

import pytest

from pc.experiment.preprocessing.axis_transform import (
    axis_transform_sha256,
    canonical_axis_transform_json,
    transform_sensor_sample,
)


def _identity_family():
    return {
        "x": {
            "source_axis": "x",
            "sign": 1,
        },
        "y": {
            "source_axis": "y",
            "sign": 1,
        },
        "z": {
            "source_axis": "z",
            "sign": 1,
        },
    }


def _identity_config():
    return {
        "ACCEL": _identity_family(),
        "GYRO": _identity_family(),
    }


def _sample(
    *,
    x=1.0,
    y=2.0,
    z=3.0,
    extra="preserve-me",
):
    return {
        "x": x,
        "y": y,
        "z": z,
        "extra": extra,
    }


def test_accel_identity_transform_preserves_axes():
    result = transform_sensor_sample(
        sample=_sample(
            x=1.0,
            y=2.0,
            z=3.0,
        ),
        sensor_family="ACCEL",
        axis_transform=_identity_config(),
    )

    assert result["x"] == 1.0
    assert result["y"] == 2.0
    assert result["z"] == 3.0


def test_gyro_identity_transform_preserves_axes():
    result = transform_sensor_sample(
        sample=_sample(
            x=4.0,
            y=5.0,
            z=6.0,
        ),
        sensor_family="GYRO",
        axis_transform=_identity_config(),
    )

    assert result["x"] == 4.0
    assert result["y"] == 5.0
    assert result["z"] == 6.0


def test_sign_inversion_is_explicit():
    config = _identity_config()

    config["ACCEL"]["x"] = {
        "source_axis": "x",
        "sign": -1,
    }

    result = transform_sensor_sample(
        sample=_sample(
            x=3.5,
            y=2.0,
            z=1.0,
        ),
        sensor_family="ACCEL",
        axis_transform=config,
    )

    assert result["x"] == -3.5
    assert result["y"] == 2.0
    assert result["z"] == 1.0


def test_axis_swap_is_explicit():
    config = _identity_config()

    config["GYRO"] = {
        "x": {
            "source_axis": "y",
            "sign": 1,
        },
        "y": {
            "source_axis": "x",
            "sign": 1,
        },
        "z": {
            "source_axis": "z",
            "sign": 1,
        },
    }

    result = transform_sensor_sample(
        sample=_sample(
            x=10.0,
            y=20.0,
            z=30.0,
        ),
        sensor_family="GYRO",
        axis_transform=config,
    )

    assert result["x"] == 20.0
    assert result["y"] == 10.0
    assert result["z"] == 30.0


@pytest.mark.parametrize(
    (
        "input_vector",
        "expected_vector",
    ),
    [
        (
            (1.0, 0.0, 0.0),
            (0.0, -1.0, 0.0),
        ),
        (
            (0.0, 1.0, 0.0),
            (1.0, 0.0, 0.0),
        ),
        (
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 1.0),
        ),
    ],
)
def test_basis_vectors_verify_axis_and_sign_mapping(
    input_vector,
    expected_vector,
):
    config = _identity_config()

    config["ACCEL"] = {
        "x": {
            "source_axis": "y",
            "sign": 1,
        },
        "y": {
            "source_axis": "x",
            "sign": -1,
        },
        "z": {
            "source_axis": "z",
            "sign": 1,
        },
    }

    result = transform_sensor_sample(
        sample=_sample(
            x=input_vector[0],
            y=input_vector[1],
            z=input_vector[2],
        ),
        sensor_family="ACCEL",
        axis_transform=config,
    )

    assert (
        result["x"],
        result["y"],
        result["z"],
    ) == expected_vector


def test_accel_and_gyro_transform_can_be_explicitly_different():
    config = _identity_config()

    config["ACCEL"]["x"] = {
        "source_axis": "x",
        "sign": -1,
    }

    config["GYRO"]["y"] = {
        "source_axis": "y",
        "sign": -1,
    }

    sample = _sample(
        x=1.0,
        y=2.0,
        z=3.0,
    )

    accel = transform_sensor_sample(
        sample=sample,
        sensor_family="ACCEL",
        axis_transform=config,
    )

    gyro = transform_sensor_sample(
        sample=sample,
        sensor_family="GYRO",
        axis_transform=config,
    )

    assert (
        accel["x"],
        accel["y"],
        accel["z"],
    ) == (
        -1.0,
        2.0,
        3.0,
    )

    assert (
        gyro["x"],
        gyro["y"],
        gyro["z"],
    ) == (
        1.0,
        -2.0,
        3.0,
    )


def test_non_axis_fields_are_preserved():
    result = transform_sensor_sample(
        sample=_sample(
            extra="provenance",
        ),
        sensor_family="ACCEL",
        axis_transform=_identity_config(),
    )

    assert result["extra"] == "provenance"


def test_input_sample_is_not_mutated():
    sample = _sample(
        x=1.0,
        y=2.0,
        z=3.0,
    )

    original = dict(sample)

    config = _identity_config()

    config["ACCEL"]["x"] = {
        "source_axis": "x",
        "sign": -1,
    }

    transform_sensor_sample(
        sample=sample,
        sensor_family="ACCEL",
        axis_transform=config,
    )

    assert sample == original


def test_unknown_sensor_family_fails_closed():
    with pytest.raises(
        ValueError,
        match="sensor",
    ):
        transform_sensor_sample(
            sample=_sample(),
            sensor_family="MAGNETOMETER",
            axis_transform=_identity_config(),
        )


def test_invalid_sign_fails_closed():
    config = _identity_config()

    config["ACCEL"]["x"] = {
        "source_axis": "x",
        "sign": 0,
    }

    with pytest.raises(
        ValueError,
        match="sign",
    ):
        transform_sensor_sample(
            sample=_sample(),
            sensor_family="ACCEL",
            axis_transform=config,
        )


def test_unknown_source_axis_fails_closed():
    config = _identity_config()

    config["ACCEL"]["x"] = {
        "source_axis": "w",
        "sign": 1,
    }

    with pytest.raises(
        ValueError,
        match="axis",
    ):
        transform_sensor_sample(
            sample=_sample(),
            sensor_family="ACCEL",
            axis_transform=config,
        )


def test_duplicate_source_axis_mapping_fails_closed():
    config = _identity_config()

    config["ACCEL"] = {
        "x": {
            "source_axis": "x",
            "sign": 1,
        },
        "y": {
            "source_axis": "x",
            "sign": 1,
        },
        "z": {
            "source_axis": "z",
            "sign": 1,
        },
    }

    with pytest.raises(
        ValueError,
        match="axis",
    ):
        transform_sensor_sample(
            sample=_sample(),
            sensor_family="ACCEL",
            axis_transform=config,
        )


def test_missing_output_axis_fails_closed():
    config = _identity_config()

    del config["GYRO"]["z"]

    with pytest.raises(
        ValueError,
        match="axis",
    ):
        transform_sensor_sample(
            sample=_sample(),
            sensor_family="GYRO",
            axis_transform=config,
        )


def test_canonical_json_is_independent_of_dictionary_order():
    first = _identity_config()

    second = {
        "GYRO": {
            "z": {
                "sign": 1,
                "source_axis": "z",
            },
            "y": {
                "sign": 1,
                "source_axis": "y",
            },
            "x": {
                "sign": 1,
                "source_axis": "x",
            },
        },
        "ACCEL": {
            "z": {
                "sign": 1,
                "source_axis": "z",
            },
            "y": {
                "sign": 1,
                "source_axis": "y",
            },
            "x": {
                "sign": 1,
                "source_axis": "x",
            },
        },
    }

    assert (
        canonical_axis_transform_json(first)
        == canonical_axis_transform_json(second)
    )


def test_transform_sha256_is_deterministic_uppercase_hex():
    config = _identity_config()

    first = axis_transform_sha256(
        config
    )

    second = axis_transform_sha256(
        config
    )

    assert first == second

    assert re.fullmatch(
        r"[0-9A-F]{64}",
        first,
    )


def test_transform_hash_changes_when_sign_changes():
    first_config = _identity_config()
    second_config = _identity_config()

    second_config["ACCEL"]["x"] = {
        "source_axis": "x",
        "sign": -1,
    }

    assert (
        axis_transform_sha256(
            first_config
        )
        != axis_transform_sha256(
            second_config
        )
    )


def test_transform_is_deterministic():
    config = _identity_config()

    config["ACCEL"] = {
        "x": {
            "source_axis": "y",
            "sign": -1,
        },
        "y": {
            "source_axis": "z",
            "sign": 1,
        },
        "z": {
            "source_axis": "x",
            "sign": -1,
        },
    }

    sample = _sample(
        x=7.0,
        y=8.0,
        z=9.0,
    )

    first = transform_sensor_sample(
        sample=sample,
        sensor_family="ACCEL",
        axis_transform=config,
    )

    second = transform_sensor_sample(
        sample=sample,
        sensor_family="ACCEL",
        axis_transform=config,
    )

    assert first == second