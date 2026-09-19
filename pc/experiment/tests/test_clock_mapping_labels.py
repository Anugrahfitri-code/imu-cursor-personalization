import pytest

from pc.experiment.labels.schema import (
    MAPPED_SENSOR_TIME_COLUMNS,
)
from pc.experiment.labels.clock_mapping import (
    map_sensor_records,
)


CLOCK_MODEL_SHA256 = "A" * 64


class FakeClockModel:
    """
    Test double exposing only the qualified public mapping
    method required by Stage 2.4.

    It deliberately does not expose alpha/beta so production
    code cannot pass these tests by independently
    reimplementing affine mapping.
    """

    def __init__(
        self,
        mapper,
    ):
        self._mapper = mapper
        self.calls = []

    def map_phone_to_pc_ns(
        self,
        phone_time_ns,
    ):
        self.calls.append(phone_time_ns)
        return self._mapper(phone_time_ns)


def _record(
    *,
    source_row_index=10,
    phone_sensor_ts_ns=1_000_000_000,
    pc_receive_ts_ns=9_999_999_999,
):
    return {
        "source_row_index":
            source_row_index,
        "phone_sensor_ts_ns":
            phone_sensor_ts_ns,
        "pc_receive_ts_ns":
            pc_receive_ts_ns,
    }


def _map(
    records,
    clock_model,
    *,
    clock_quality_passed=True,
):
    return map_sensor_records(
        records=records,
        participant_id="PTEST001",
        session_id="STEST001",
        calibration_id="CAL2C001",
        source_file="raw/imu/imu.csv",
        clock_model=clock_model,
        clock_model_sha256=(
            CLOCK_MODEL_SHA256
        ),
        clock_quality_passed=(
            clock_quality_passed
        ),
        derivation_version=(
            "stage2.4-test-v1"
        ),
    )


def test_mapped_rows_follow_exact_schema():
    model = FakeClockModel(
        lambda timestamp: timestamp + 100
    )

    rows = _map(
        [_record()],
        model,
    )

    assert len(rows) == 1

    assert tuple(rows[0].keys()) == (
        MAPPED_SENSOR_TIME_COLUMNS
    )


def test_known_mapping_uses_clock_model_method():
    model = FakeClockModel(
        lambda timestamp: timestamp * 2 + 5
    )

    rows = _map(
        [
            _record(
                phone_sensor_ts_ns=1234
            )
        ],
        model,
    )

    assert model.calls == [1234]

    assert (
        rows[0]["pc_mapped_ts_ns"]
        == 2473
    )

    assert (
        rows[0]["mapping_status"]
        == "MAPPED"
    )


def test_large_nanosecond_timestamp_maps_correctly():
    source_time = (
        9_000_000_000_000_000
    )

    model = FakeClockModel(
        lambda timestamp:
            timestamp + 123_456_789
    )

    rows = _map(
        [
            _record(
                phone_sensor_ts_ns=source_time
            )
        ],
        model,
    )

    assert (
        rows[0]["pc_mapped_ts_ns"]
        ==
        source_time + 123_456_789
    )


def test_mapping_uses_phone_sensor_timestamp_not_receive_time():
    phone_time = 1_234_567
    receive_time = 8_888_888_888

    model = FakeClockModel(
        lambda timestamp: timestamp + 7
    )

    rows = _map(
        [
            _record(
                phone_sensor_ts_ns=phone_time,
                pc_receive_ts_ns=receive_time,
            )
        ],
        model,
    )

    assert model.calls == [
        phone_time
    ]

    assert receive_time not in model.calls

    assert (
        rows[0]["pc_mapped_ts_ns"]
        == phone_time + 7
    )


def test_positive_mapping_preserves_order():
    model = FakeClockModel(
        lambda timestamp:
            timestamp + 1_000
    )

    records = [
        _record(
            source_row_index=10,
            phone_sensor_ts_ns=100,
        ),
        _record(
            source_row_index=11,
            phone_sensor_ts_ns=200,
        ),
        _record(
            source_row_index=12,
            phone_sensor_ts_ns=300,
        ),
    ]

    rows = _map(
        records,
        model,
    )

    mapped = [
        row["pc_mapped_ts_ns"]
        for row in rows
    ]

    assert mapped == [
        1100,
        1200,
        1300,
    ]

    assert mapped == sorted(mapped)


def test_invalid_source_timestamp_is_flagged_without_mapping():
    model = FakeClockModel(
        lambda timestamp:
            timestamp + 1
    )

    rows = _map(
        [
            _record(
                phone_sensor_ts_ns=(
                    "not-an-integer"
                )
            )
        ],
        model,
    )

    assert model.calls == []

    assert (
        rows[0]["mapping_status"]
        == "INVALID_SOURCE_TIMESTAMP"
    )

    assert (
        rows[0]["pc_mapped_ts_ns"]
        is None
    )


def test_source_identity_and_clock_hash_are_preserved():
    model = FakeClockModel(
        lambda timestamp:
            timestamp + 10
    )

    rows = _map(
        [
            _record(
                source_row_index=321,
                phone_sensor_ts_ns=999,
            )
        ],
        model,
    )

    row = rows[0]

    assert (
        row["participant_id"]
        == "PTEST001"
    )

    assert (
        row["session_id"]
        == "STEST001"
    )

    assert (
        row["calibration_id"]
        == "CAL2C001"
    )

    assert (
        row["source_file"]
        == "raw/imu/imu.csv"
    )

    assert (
        row["source_row_index"]
        == 321
    )

    assert (
        row["phone_sensor_ts_ns"]
        == 999
    )

    assert (
        row["clock_model_sha256"]
        == CLOCK_MODEL_SHA256
    )

    assert (
        row["derivation_version"]
        == "stage2.4-test-v1"
    )


def test_mapped_record_ids_are_unique_and_deterministic():
    records = [
        _record(
            source_row_index=1,
            phone_sensor_ts_ns=100,
        ),
        _record(
            source_row_index=2,
            phone_sensor_ts_ns=200,
        ),
    ]

    first_model = FakeClockModel(
        lambda timestamp: timestamp
    )

    second_model = FakeClockModel(
        lambda timestamp: timestamp
    )

    first = _map(
        records,
        first_model,
    )

    second = _map(
        records,
        second_model,
    )

    first_ids = [
        row["mapped_record_id"]
        for row in first
    ]

    second_ids = [
        row["mapped_record_id"]
        for row in second
    ]

    assert len(first_ids) == 2
    assert len(set(first_ids)) == 2
    assert first_ids == second_ids


def test_invalid_clock_quality_fails_closed():
    model = FakeClockModel(
        lambda timestamp: timestamp
    )

    with pytest.raises(
        ValueError,
        match="clock",
    ):
        _map(
            [_record()],
            model,
            clock_quality_passed=False,
        )

    assert model.calls == []