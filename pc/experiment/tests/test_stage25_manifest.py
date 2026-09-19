import re
from copy import deepcopy

import pytest

from pc.experiment.preprocessing.config import (
    preprocessing_config_sha256,
)

from pc.experiment.preprocessing.manifest import (
    build_preprocessing_manifest,
    preprocessing_manifest_sha256,
)

from pc.experiment.preprocessing.schema import (
    PREPROCESSING_MANIFEST_REQUIRED_FIELDS,
)

from pc.experiment.tests.test_stage25_config import (
    HASH_A,
    HASH_B,
    HASH_C,
    _config,
)


UPSTREAM_SHA = "D" * 64
COMMON_GRID_SHA = "E" * 64
QUALITY_SHA = "F" * 64


def _quality(
    *,
    status="VALID",
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
    grid_row_count=2,
):
    return {
        "participant_id":
            participant_id,
        "session_id":
            session_id,
        "calibration_id":
            calibration_id,
        "status":
            status,
        "grid_row_count":
            grid_row_count,
    }


def _grid_rows(
    config_sha,
):
    return [
        {
            "participant_id":
                "PTEST001",
            "session_id":
                "STEST001",
            "calibration_id":
                "CAL2C001",
            "grid_index":
                0,
            "grid_pc_time_ns":
                100,
            "preprocessing_config_sha256":
                config_sha,
        },
        {
            "participant_id":
                "PTEST001",
            "session_id":
                "STEST001",
            "calibration_id":
                "CAL2C001",
            "grid_index":
                1,
            "grid_pc_time_ns":
                200,
            "preprocessing_config_sha256":
                config_sha,
        },
    ]


def _build(
    *,
    config=None,
    config_sha=None,
    source_hashes=None,
    grid_rows=None,
    quality=None,
    upstream_sha=UPSTREAM_SHA,
    common_grid_sha=COMMON_GRID_SHA,
    quality_sha=QUALITY_SHA,
    participant_id="PTEST001",
    session_id="STEST001",
    calibration_id="CAL2C001",
):
    if config is None:
        config = _config()

    actual_config_sha = (
        preprocessing_config_sha256(
            config
        )
    )

    if config_sha is None:
        config_sha = actual_config_sha

    if source_hashes is None:
        source_hashes = {
            "mapped_sensor_times":
                HASH_A,
            "reference_trajectory":
                HASH_B,
            "clock_model":
                HASH_C,
        }

    if grid_rows is None:
        grid_rows = _grid_rows(
            actual_config_sha
        )

    if quality is None:
        quality = _quality()

    return build_preprocessing_manifest(
        participant_id=participant_id,
        session_id=session_id,
        calibration_id=calibration_id,
        preprocessing_config=config,
        preprocessing_config_sha256=config_sha,
        source_artifact_hashes=source_hashes,
        upstream_stage24_provenance_sha256=(
            upstream_sha
        ),
        common_grid_rows=grid_rows,
        common_grid_sha256=common_grid_sha,
        preprocessing_quality=quality,
        preprocessing_quality_sha256=(
            quality_sha
        ),
        derivation_version="stage2.5-test-v1",
        functional_commit="TESTCOMMIT",
    )


def test_manifest_matches_frozen_schema_order():
    result = _build()

    assert tuple(result.keys()) == (
        PREPROCESSING_MANIFEST_REQUIRED_FIELDS
    )


def test_manifest_preserves_all_provenance_hashes():
    result = _build()

    assert result[
        "source_artifact_hashes"
    ] == {
        "mapped_sensor_times":
            HASH_A,
        "reference_trajectory":
            HASH_B,
        "clock_model":
            HASH_C,
    }

    assert (
        result[
            "upstream_stage24_provenance_sha256"
        ]
        == UPSTREAM_SHA
    )

    assert (
        result["common_grid_sha256"]
        == COMMON_GRID_SHA
    )

    assert (
        result[
            "preprocessing_quality_sha256"
        ]
        == QUALITY_SHA
    )


def test_manifest_grid_time_range_and_count_are_exact():
    result = _build()

    assert (
        result["first_grid_pc_time_ns"]
        == 100
    )

    assert (
        result["last_grid_pc_time_ns"]
        == 200
    )

    assert result["grid_row_count"] == 2


def test_manifest_status_follows_quality_artifact():
    result = _build(
        quality=_quality(
            status="VALID"
        )
    )

    assert result["status"] == "VALID"


def test_manifest_preserves_technical_invalid_status():
    result = _build(
        quality=_quality(
            status="TECHNICAL_INVALID"
        )
    )

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )


def test_incorrect_provided_config_hash_fails_closed():
    with pytest.raises(
        ValueError,
        match="config",
    ):
        _build(
            config_sha="9" * 64,
        )


def test_grid_row_config_hash_mismatch_fails_closed():
    config = _config()

    config_sha = (
        preprocessing_config_sha256(
            config
        )
    )

    rows = _grid_rows(
        config_sha
    )

    rows[1] = dict(
        rows[1]
    )

    rows[1][
        "preprocessing_config_sha256"
    ] = "9" * 64

    with pytest.raises(
        ValueError,
        match="config",
    ):
        _build(
            config=config,
            grid_rows=rows,
        )


def test_source_artifact_hash_mismatch_with_config_fails_closed():
    source_hashes = {
        "mapped_sensor_times":
            HASH_A,
        "reference_trajectory":
            HASH_B,
        "clock_model":
            "9" * 64,
    }

    with pytest.raises(
        ValueError,
        match="source",
    ):
        _build(
            source_hashes=source_hashes,
        )


def test_common_grid_identity_mismatch_fails_closed():
    config = _config()

    config_sha = (
        preprocessing_config_sha256(
            config
        )
    )

    rows = _grid_rows(
        config_sha
    )

    rows[1] = dict(
        rows[1]
    )

    rows[1]["participant_id"] = "OTHER"

    with pytest.raises(
        ValueError,
        match="participant",
    ):
        _build(
            config=config,
            grid_rows=rows,
        )


def test_quality_identity_mismatch_fails_closed():
    with pytest.raises(
        ValueError,
        match="calibration",
    ):
        _build(
            quality=_quality(
                calibration_id="OTHER"
            )
        )


def test_quality_grid_count_mismatch_fails_closed():
    with pytest.raises(
        ValueError,
        match="count",
    ):
        _build(
            quality=_quality(
                grid_row_count=999
            )
        )


@pytest.mark.parametrize(
    (
        "argument_name",
        "invalid_hash",
    ),
    [
        (
            "upstream_sha",
            "INVALID",
        ),
        (
            "common_grid_sha",
            "1234",
        ),
        (
            "quality_sha",
            "XYZ",
        ),
    ],
)
def test_invalid_manifest_sha256_inputs_fail_closed(
    argument_name,
    invalid_hash,
):
    kwargs = {
        argument_name:
            invalid_hash,
    }

    with pytest.raises(
        ValueError,
        match="SHA",
    ):
        _build(
            **kwargs
        )


def test_manifest_is_deterministic():
    first = _build()
    second = _build()

    assert first == second


def test_manifest_sha256_is_deterministic_uppercase_hex():
    manifest = _build()

    first = preprocessing_manifest_sha256(
        manifest
    )

    second = preprocessing_manifest_sha256(
        manifest
    )

    assert first == second

    assert re.fullmatch(
        r"[0-9A-F]{64}",
        first,
    )


def test_manifest_hash_changes_when_manifest_changes():
    first = _build()
    second = deepcopy(
        first
    )

    second[
        "common_grid_sha256"
    ] = "9" * 64

    assert (
        preprocessing_manifest_sha256(
            first
        )
        != preprocessing_manifest_sha256(
            second
        )
    )


def test_manifest_builder_does_not_mutate_inputs():
    config = _config()

    source_hashes = deepcopy(
        config[
            "source_artifact_hashes"
        ]
    )

    config_sha = (
        preprocessing_config_sha256(
            config
        )
    )

    rows = _grid_rows(
        config_sha
    )

    quality = _quality()

    config_before = deepcopy(
        config
    )

    source_before = deepcopy(
        source_hashes
    )

    rows_before = deepcopy(
        rows
    )

    quality_before = deepcopy(
        quality
    )

    _build(
        config=config,
        source_hashes=source_hashes,
        grid_rows=rows,
        quality=quality,
    )

    assert config == config_before
    assert source_hashes == source_before
    assert rows == rows_before
    assert quality == quality_before