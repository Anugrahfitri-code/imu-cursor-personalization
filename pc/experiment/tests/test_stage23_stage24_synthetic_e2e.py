import csv
import json
from pathlib import Path

from pc.experiment.calibration.schema import (
    DIRECTION_CODES,
)
from pc.experiment.labels.synthetic_qualification import (
    run_synthetic_qualification,
)


FUNCTIONAL_COMMIT = "SYNTHETIC_TEST_COMMIT"

EXPECTED_ARTIFACT_KEYS = frozenset(
    {
        "raw_imu",
        "clock_model",
        "reference_trajectory",
        "calibration_manifest",
        "mapped_sensor_times",
        "native_reference_labels",
        "label_config",
        "label_manifest",
    }
)


def _run(
    tmp_path: Path,
    *,
    name="qualification",
    clock_quality_passed=True,
):
    return run_synthetic_qualification(
        output_root=tmp_path / name,
        functional_commit=FUNCTIONAL_COMMIT,
        clock_quality_passed=(
            clock_quality_passed
        ),
    )


def _artifact_path(
    result,
    key,
):
    return (
        Path(result["output_root"])
        / result["artifact_paths"][key]
    )


def _read_json(path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def _read_csv(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle)
        )


def test_valid_synthetic_qualification_completes_end_to_end(
    tmp_path,
):
    result = _run(tmp_path)

    assert result["status"] == "VALID"

    assert (
        result["dataset_role"]
        == "synthetic"
    )

    assert (
        result["real_participant_data_used"]
        is False
    )

    assert (
        result["clock_quality_passed"]
        is True
    )

    assert result["cycle_count"] == 2

    assert tuple(
        result["direction_order"]
    ) == DIRECTION_CODES

    assert (
        result["mapped_record_count"]
        > 0
    )

    assert (
        result["valid_label_count"]
        > 0
    )


def test_required_artifact_set_is_written(
    tmp_path,
):
    result = _run(tmp_path)

    assert (
        frozenset(
            result["artifact_paths"].keys()
        )
        == EXPECTED_ARTIFACT_KEYS
    )

    for key in EXPECTED_ARTIFACT_KEYS:
        path = _artifact_path(
            result,
            key,
        )

        assert path.is_file(), (
            f"Missing synthetic artifact: "
            f"{key}: {path}"
        )


def test_reference_artifact_contains_exact_two_cycle_order(
    tmp_path,
):
    result = _run(tmp_path)

    rows = _read_csv(
        _artifact_path(
            result,
            "reference_trajectory",
        )
    )

    cycles = sorted(
        {
            int(row["cycle_index"])
            for row in rows
        }
    )

    assert cycles == [1, 2]

    for cycle_index in cycles:
        cycle_rows = [
            row
            for row in rows
            if int(
                row["cycle_index"]
            ) == cycle_index
        ]

        direction_order = []
        seen_sequences = set()

        for row in cycle_rows:
            sequence_id = row[
                "sequence_id"
            ]

            if (
                sequence_id
                not in seen_sequences
            ):
                seen_sequences.add(
                    sequence_id
                )

                direction_order.append(
                    row["direction_code"]
                )

        assert tuple(
            direction_order
        ) == DIRECTION_CODES


def test_e2e_mapping_uses_sensor_time_not_receive_time(
    tmp_path,
):
    result = _run(tmp_path)

    raw_rows = _read_csv(
        _artifact_path(
            result,
            "raw_imu",
        )
    )

    mapped_rows = _read_csv(
        _artifact_path(
            result,
            "mapped_sensor_times",
        )
    )

    assert len(raw_rows) == len(
        mapped_rows
    )

    assert len(raw_rows) > 0

    synthetic_offset_ns = (
        result["synthetic_clock_offset_ns"]
    )

    for raw, mapped in zip(
        raw_rows,
        mapped_rows,
        strict=True,
    ):
        phone_time = int(
            raw["phone_sensor_ts_ns"]
        )

        receive_time = int(
            raw["pc_receive_ts_ns"]
        )

        mapped_time = int(
            mapped["pc_mapped_ts_ns"]
        )

        assert mapped_time == (
            phone_time
            + synthetic_offset_ns
        )

        # Receive time is deliberately different.
        assert mapped_time != receive_time


def test_e2e_lag_sign_and_reference_velocity_are_preserved(
    tmp_path,
):
    result = _run(tmp_path)

    label_config = _read_json(
        _artifact_path(
            result,
            "label_config",
        )
    )

    labels = _read_csv(
        _artifact_path(
            result,
            "native_reference_labels",
        )
    )

    lag_ns = int(
        label_config[
            "alignment_lag_ns"
        ]
    )

    assert lag_ns > 0

    assert (
        label_config[
            "lag_sign_convention"
        ]
        ==
        "label_pc_time_ns = "
        "pc_mapped_ts_ns - "
        "alignment_lag_ns"
    )

    valid_rows = [
        row
        for row in labels
        if row["label_status"]
        == "VALID"
    ]

    assert valid_rows

    for row in valid_rows:
        assert (
            int(
                row["label_pc_time_ns"]
            )
            ==
            int(
                row["pc_mapped_ts_ns"]
            )
            - lag_ns
        )

        assert row[
            "ref_vx_px_s"
        ] != ""

        assert row[
            "ref_vy_px_s"
        ] != ""


def test_calibration_provenance_records_exact_source_slice(
    tmp_path,
):
    result = _run(tmp_path)

    manifest = _read_json(
        _artifact_path(
            result,
            "calibration_manifest",
        )
    )

    selection = manifest[
        "source_selection"
    ]

    expected = result[
        "source_selection"
    ]

    assert selection == expected

    assert (
        selection["source_file_sha256"]
        ==
        manifest["raw_imu_sha256"]
    )

    assert (
        selection["calibration_id"]
        ==
        manifest["calibration_id"]
    )

    assert (
        selection["source_first_row"]
        <= selection["source_last_row"]
    )

    assert (
        selection[
            "source_first_sequence"
        ]
        <=
        selection[
            "source_last_sequence"
        ]
    )


def test_same_synthetic_inputs_are_reproducible(
    tmp_path,
):
    first = _run(
        tmp_path,
        name="first",
    )

    second = _run(
        tmp_path,
        name="second",
    )

    assert (
        first["artifact_sha256"]
        ==
        second["artifact_sha256"]
    )

    assert (
        first["reproducibility_digest"]
        ==
        second["reproducibility_digest"]
    )

    assert (
        first["source_selection"]
        ==
        second["source_selection"]
    )


def test_invalid_clock_quality_fails_closed_end_to_end(
    tmp_path,
):
    result = _run(
        tmp_path,
        name="invalid_clock",
        clock_quality_passed=False,
    )

    assert (
        result["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        result["clock_quality_passed"]
        is False
    )

    assert (
        result["valid_label_count"]
        == 0
    )

    manifest = _read_json(
        _artifact_path(
            result,
            "label_manifest",
        )
    )

    assert (
        manifest["status"]
        == "TECHNICAL_INVALID"
    )

    assert (
        result["real_participant_data_used"]
        is False
    )