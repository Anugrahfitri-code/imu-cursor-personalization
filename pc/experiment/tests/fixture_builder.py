import csv
import hashlib
import json
from pathlib import Path

from pc.experiment.csv_schema import (
    CALIBRATION_EVENT_COLUMNS,
    CURSOR_SAMPLE_COLUMNS,
    QUALITY_FLAG_COLUMNS,
    TRIAL_EVENT_COLUMNS,
)


PARTICIPANT_ID = "SYNTHETIC_P001"
SESSION_ID = "SYNTHETIC_SESSION_001"


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...] | list[str],
    rows: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_json(
    path: Path,
    data: object,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def build_synthetic_session(
    root: Path,
) -> Path:
    session_dir = root / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": "1.0",
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "dataset_role": "synthetic",
        "session_status": "closed",
        "experiment_protocol_version": "synthetic-v1",
        "condition_order": [
            "P0",
            "P2C",
            "L0",
            "L2C",
        ],
        "functional_commit": "synthetic",
        "experiment_software_version": "stage2.1-test",
        "device": {
            "manufacturer": "synthetic",
            "model": "SM-A175F",
            "android_version": "16",
            "api_level": 36,
            "android_session_id": "SYNTHETIC_ANDROID_001",
        },
        "display": {
            "display_width_px": 1920,
            "display_height_px": 1080,
            "experiment_window_width_px": 1920,
            "experiment_window_height_px": 1080,
            "display_scale_factor": 1.0,
        },
        "android_evidence": {
            "imu_file": "raw/imu/imu.csv",
            "imu_sha256": "0" * 64,
            "android_metadata_file": "raw/imu/meta.txt",
            "android_metadata_sha256": "0" * 64,
        },
        "clock_evidence": {
            "clock_model_file": "raw/clock/clock_model.json",
            "clock_model_sha256": "0" * 64,
            "sync_probes_file": "raw/clock/sync_probes.csv",
            "sync_probes_sha256": "0" * 64,
        },
        "files": [],
    }

    conditions = [
        ("P0", "T001", 1_000),
        ("P2C", "T002", 2_000),
        ("L0", "T003", 3_000),
        ("L2C", "T004", 4_000),
    ]

    trial_rows: list[dict[str, object]] = []

    event_number = 1

    for condition, trial_id, base_time in conditions:
        for event_type, offset in (
            ("trial_start", 0),
            ("trial_complete", 100),
        ):
            trial_rows.append(
                {
                    "event_id": f"E{event_number:03d}",
                    "participant_id": PARTICIPANT_ID,
                    "session_id": SESSION_ID,
                    "condition_code": condition,
                    "block_id": f"B_{condition}",
                    "sequence_id": f"SEQ_{condition}",
                    "trial_id": trial_id,
                    "event_type": event_type,
                    "pc_time_ns": str(base_time + offset),
                    "target_id": f"TARGET_{trial_id}",
                    "target_x_px": "960",
                    "target_y_px": "540",
                    "target_width_px": "80",
                    "target_height_px": "80",
                    "pointer_x_px": "900",
                    "pointer_y_px": "540",
                    "event_note": "",
                }
            )
            event_number += 1

    _write_csv(
        session_dir / "raw" / "trial_events.csv",
        TRIAL_EVENT_COLUMNS,
        trial_rows,
    )

    cursor_rows: list[dict[str, object]] = []

    sample_number = 1

    for condition, trial_id, base_time in conditions:
        for offset, cursor_x in (
            (10, 910),
            (50, 950),
        ):
            cursor_rows.append(
                {
                    "sample_id": f"S{sample_number:03d}",
                    "participant_id": PARTICIPANT_ID,
                    "session_id": SESSION_ID,
                    "condition_code": condition,
                    "block_id": f"B_{condition}",
                    "sequence_id": f"SEQ_{condition}",
                    "trial_id": trial_id,
                    "pc_time_ns": str(base_time + offset),
                    "cursor_x_px": str(cursor_x),
                    "cursor_y_px": "540",
                    "active_target_id": f"TARGET_{trial_id}",
                    "source_seq_start": str(
                        sample_number * 10
                    ),
                    "source_seq_end": str(
                        sample_number * 10 + 9
                    ),
                }
            )
            sample_number += 1

    _write_csv(
        session_dir / "raw" / "cursor_samples.csv",
        CURSOR_SAMPLE_COLUMNS,
        cursor_rows,
    )

    calibration_rows = [
        {
            "calibration_event_id": "C001",
            "participant_id": PARTICIPANT_ID,
            "session_id": SESSION_ID,
            "condition_code": "P2C",
            "calibration_id": "CAL_2C",
            "step_id": "STEP_01",
            "event_type": "calibration_start",
            "pc_time_ns": "500",
            "reference_target_id": "CAL_TARGET_01",
            "source_seq_start": "1",
            "source_seq_end": "10",
            "instruction_code": "CENTER_OUT",
            "event_note": "",
        },
        {
            "calibration_event_id": "C002",
            "participant_id": PARTICIPANT_ID,
            "session_id": SESSION_ID,
            "condition_code": "L2C",
            "calibration_id": "CAL_2C",
            "step_id": "STEP_02",
            "event_type": "calibration_end",
            "pc_time_ns": "900",
            "reference_target_id": "CAL_TARGET_02",
            "source_seq_start": "11",
            "source_seq_end": "20",
            "instruction_code": "RETURN_CENTER",
            "event_note": "",
        },
    ]

    _write_csv(
        session_dir
        / "raw"
        / "calibration_events.csv",
        CALIBRATION_EVENT_COLUMNS,
        calibration_rows,
    )

    _write_csv(
        session_dir
        / "derived"
        / "quality_flags.csv",
        QUALITY_FLAG_COLUMNS,
        [],
    )

    _write_csv(
        session_dir / "raw" / "imu" / "imu.csv",
        [
            "seq",
            "phone_sensor_ts_ns",
            "ax",
            "ay",
            "az",
            "gx",
            "gy",
            "gz",
        ],
        [
            {
                "seq": "1",
                "phone_sensor_ts_ns": "100",
                "ax": "0.0",
                "ay": "0.0",
                "az": "9.81",
                "gx": "0.0",
                "gy": "0.0",
                "gz": "0.0",
            }
        ],
    )

    metadata_path = (
        session_dir / "raw" / "imu" / "meta.txt"
    )
    metadata_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    metadata_path.write_text(
        "synthetic fixture\n",
        encoding="utf-8",
    )

    _write_json(
        session_dir
        / "raw"
        / "clock"
        / "clock_model.json",
        {
            "alpha": 1.0,
            "beta": 0.0,
            "synthetic": True,
        },
    )

    _write_csv(
        session_dir
        / "raw"
        / "clock"
        / "sync_probes.csv",
        [
            "probe_id",
            "phone_time_ns",
            "pc_time_ns",
        ],
        [
            {
                "probe_id": "1",
                "phone_time_ns": "100",
                "pc_time_ns": "100",
            }
        ],
    )

    _write_json(
        session_dir
        / "artifacts"
        / "calibration_parameters.json",
        {
            "synthetic": True,
        },
    )

    _write_json(
        session_dir
        / "artifacts"
        / "model_manifest.json",
        {
            "synthetic": True,
        },
    )

    for section, pairs in (
        ("android_evidence", (("imu_file", "imu_sha256"), ("android_metadata_file", "android_metadata_sha256"))),
        ("clock_evidence", (("clock_model_file", "clock_model_sha256"), ("sync_probes_file", "sync_probes_sha256"))),
    ):
        for path_field, hash_field in pairs:
            manifest[section][hash_field] = hashlib.sha256(
                (session_dir / manifest[section][path_field]).read_bytes()
            ).hexdigest().upper()
    _write_json(session_dir / "manifest.json", manifest)
    return session_dir
