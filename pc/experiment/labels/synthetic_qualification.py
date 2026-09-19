import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pc.experiment.calibration.provenance import (
    build_calibration_manifest,
    calibration_provenance_sha256,
)
from pc.experiment.calibration.schema import (
    DIRECTION_CODES,
    REFERENCE_TRAJECTORY_COLUMNS,
)
from pc.experiment.calibration.trajectory import (
    generate_guided_2c,
)
from pc.experiment.calibration.validator import (
    validate_reference_trajectory,
)
from pc.experiment.labels.clock_mapping import (
    map_sensor_records,
)
from pc.experiment.labels.label_builder import (
    build_native_labels,
)
from pc.experiment.labels.manifest import (
    build_label_manifest,
)
from pc.experiment.labels.schema import (
    LABEL_CONFIG_REQUIRED_FIELDS,
    MAPPED_SENSOR_TIME_COLUMNS,
    NATIVE_LABEL_COLUMNS,
)
from pc.experiment.labels.validator import (
    assess_label_build,
)


_PARTICIPANT_ID = "SYNTHETIC_PARTICIPANT"
_SESSION_ID = "SYNTHETIC_SESSION"
_CALIBRATION_ID = "SYNTHETIC_CAL2C001"

_TRAJECTORY_VERSION = "stage2.3-synthetic-v1"
_DERIVATION_VERSION = "stage2.4-synthetic-v1"

_START_PC_TIME_NS = 1_000_000_000_000

_SYNTHETIC_CLOCK_OFFSET_NS = 50_000_000
_SYNTHETIC_RECEIVE_EXTRA_NS = 7_000_000

_ALIGNMENT_LAG_NS = 5_000_000


_TRAJECTORY_CONFIG = {
    "center_x_px": 960.0,
    "center_y_px": 540.0,
    "radius_px": 120.0,
    "center_hold_ns": 20_000_000,
    "outbound_ns": 40_000_000,
    "target_hold_ns": 20_000_000,
    "return_ns": 40_000_000,
    "sample_interval_ns": 10_000_000,
    "speed_profile_code": "SYNTHETIC_LINEAR_V1",
    "trajectory_version": _TRAJECTORY_VERSION,
}


_ARTIFACT_PATHS = {
    "raw_imu":
        "raw/imu/imu.csv",
    "clock_model":
        "artifacts/calibration/clock_model.json",
    "reference_trajectory":
        "raw/calibration/reference_trajectory.csv",
    "calibration_manifest":
        "raw/calibration/calibration_manifest.json",
    "mapped_sensor_times":
        "derived/calibration/mapped_sensor_times.csv",
    "native_reference_labels":
        "derived/calibration/native_reference_labels.csv",
    "label_config":
        "artifacts/calibration/label_config.json",
    "label_manifest":
        "derived/calibration/label_manifest.json",
}


_RAW_IMU_COLUMNS = (
    "source_row_index",
    "source_sequence",
    "phone_sensor_ts_ns",
    "pc_receive_ts_ns",
)


class _SyntheticClockModel:
    def __init__(
        self,
        offset_ns: int,
    ) -> None:
        self.offset_ns = int(
            offset_ns
        )

    def map_phone_to_pc_ns(
        self,
        phone_time_ns: int,
    ) -> int:
        return (
            int(phone_time_ns)
            + self.offset_ns
        )


def _write_json(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    )

    path.write_text(
        text + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(
    path: Path,
    *,
    fieldnames,
    rows,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="raise",
            lineterminator="\n",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def _sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(
                1024 * 1024
            )

            if not block:
                break

            digest.update(block)

    return digest.hexdigest().upper()


def _sha256_json(
    payload: Any,
) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(
        canonical
    ).hexdigest().upper()


def _artifact_file(
    root: Path,
    key: str,
) -> Path:
    return (
        root
        / _ARTIFACT_PATHS[key]
    )


def _build_raw_rows(
    reference_rows,
) -> list[dict[str, int]]:
    """
    Create deterministic synthetic IMU timing records.

    Only reference timestamps that occur once are used so
    exact label lookup cannot become ambiguous at phase or
    sequence boundaries.
    """
    time_counts = Counter(
        int(row["pc_time_ns"])
        for row in reference_rows
    )

    eligible_reference_rows = [
        row
        for row in reference_rows
        if time_counts[
            int(row["pc_time_ns"])
        ] == 1
    ]

    if not eligible_reference_rows:
        raise RuntimeError(
            "Synthetic qualification produced no "
            "unambiguous reference timestamps."
        )

    rows = []

    for index, reference in enumerate(
        eligible_reference_rows,
        start=1,
    ):
        reference_time = int(
            reference["pc_time_ns"]
        )

        mapped_time = (
            reference_time
            + _ALIGNMENT_LAG_NS
        )

        phone_time = (
            mapped_time
            - _SYNTHETIC_CLOCK_OFFSET_NS
        )

        receive_time = (
            mapped_time
            + _SYNTHETIC_RECEIVE_EXTRA_NS
        )

        rows.append(
            {
                "source_row_index":
                    index,
                "source_sequence":
                    1000 + index,
                "phone_sensor_ts_ns":
                    phone_time,
                "pc_receive_ts_ns":
                    receive_time,
            }
        )

    return rows


def run_synthetic_qualification(
    *,
    output_root,
    functional_commit: str,
    clock_quality_passed: bool = True,
) -> dict[str, Any]:
    """
    Execute deterministic synthetic-only Stage 2.3/2.4
    qualification.

    No participant or human-recorded sensor data are read.
    """
    root = Path(output_root)

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------
    # Guided 2C reference trajectory
    # -----------------------------------------------------

    reference_rows = generate_guided_2c(
        participant_id=_PARTICIPANT_ID,
        session_id=_SESSION_ID,
        calibration_id=_CALIBRATION_ID,
        start_pc_time_ns=_START_PC_TIME_NS,
        config=_TRAJECTORY_CONFIG,
    )

    reference_errors = (
        validate_reference_trajectory(
            reference_rows
        )
    )

    if reference_errors:
        raise RuntimeError(
            "Synthetic reference trajectory failed "
            "validation: "
            f"{reference_errors!r}"
        )

    reference_path = _artifact_file(
        root,
        "reference_trajectory",
    )

    _write_csv(
        reference_path,
        fieldnames=REFERENCE_TRAJECTORY_COLUMNS,
        rows=reference_rows,
    )

    reference_sha256 = _sha256_file(
        reference_path
    )

    trajectory_config_sha256 = (
        _sha256_json(
            _TRAJECTORY_CONFIG
        )
    )

    # -----------------------------------------------------
    # Synthetic raw timing source
    # -----------------------------------------------------

    raw_rows = _build_raw_rows(
        reference_rows
    )

    raw_path = _artifact_file(
        root,
        "raw_imu",
    )

    _write_csv(
        raw_path,
        fieldnames=_RAW_IMU_COLUMNS,
        rows=raw_rows,
    )

    raw_imu_sha256 = _sha256_file(
        raw_path
    )

    # -----------------------------------------------------
    # Deterministic synthetic clock model artifact
    # -----------------------------------------------------

    clock_payload = {
        "model_type":
            "SYNTHETIC_CONSTANT_OFFSET",
        "mapping_method":
            "map_phone_to_pc_ns",
        "offset_ns":
            _SYNTHETIC_CLOCK_OFFSET_NS,
        "qualification_only":
            True,
    }

    clock_path = _artifact_file(
        root,
        "clock_model",
    )

    _write_json(
        clock_path,
        clock_payload,
    )

    clock_model_sha256 = _sha256_file(
        clock_path
    )

    clock_model = _SyntheticClockModel(
        _SYNTHETIC_CLOCK_OFFSET_NS
    )

    # -----------------------------------------------------
    # Exact source slice / calibration provenance
    # -----------------------------------------------------

    first_mapped_time = (
        int(
            raw_rows[0][
                "phone_sensor_ts_ns"
            ]
        )
        + _SYNTHETIC_CLOCK_OFFSET_NS
    )

    last_mapped_time = (
        int(
            raw_rows[-1][
                "phone_sensor_ts_ns"
            ]
        )
        + _SYNTHETIC_CLOCK_OFFSET_NS
    )

    source_selection = {
        "source_file":
            _ARTIFACT_PATHS[
                "raw_imu"
            ],
        "source_file_sha256":
            raw_imu_sha256,
        "source_first_row":
            int(
                raw_rows[0][
                    "source_row_index"
                ]
            ),
        "source_last_row":
            int(
                raw_rows[-1][
                    "source_row_index"
                ]
            ),
        "source_first_sequence":
            int(
                raw_rows[0][
                    "source_sequence"
                ]
            ),
        "source_last_sequence":
            int(
                raw_rows[-1][
                    "source_sequence"
                ]
            ),
        "calibration_start_pc_ns":
            first_mapped_time,
        "calibration_end_pc_ns":
            last_mapped_time,
        "calibration_id":
            _CALIBRATION_ID,
    }

    calibration_manifest = (
        build_calibration_manifest(
            participant_id=_PARTICIPANT_ID,
            session_id=_SESSION_ID,
            calibration_id=_CALIBRATION_ID,
            calibration_start_pc_ns=(
                first_mapped_time
            ),
            calibration_end_pc_ns=(
                last_mapped_time
            ),
            cycle_count=2,
            reference_trajectory_file=(
                _ARTIFACT_PATHS[
                    "reference_trajectory"
                ]
            ),
            trajectory_version=(
                _TRAJECTORY_VERSION
            ),
            trajectory_config_sha256=(
                trajectory_config_sha256
            ),
            raw_imu_sha256=(
                raw_imu_sha256
            ),
            clock_model_sha256=(
                clock_model_sha256
            ),
            source_selection=(
                source_selection
            ),
        )
    )

    calibration_manifest_path = (
        _artifact_file(
            root,
            "calibration_manifest",
        )
    )

    _write_json(
        calibration_manifest_path,
        calibration_manifest,
    )

    calibration_manifest_sha256 = (
        _sha256_file(
            calibration_manifest_path
        )
    )

    calibration_provenance_digest = (
        calibration_provenance_sha256(
            calibration_manifest
        )
    )

    # -----------------------------------------------------
    # Native timestamp mapping + native labels
    # -----------------------------------------------------

    if clock_quality_passed:
        mapped_rows = map_sensor_records(
            records=raw_rows,
            participant_id=_PARTICIPANT_ID,
            session_id=_SESSION_ID,
            calibration_id=_CALIBRATION_ID,
            source_file=(
                _ARTIFACT_PATHS[
                    "raw_imu"
                ]
            ),
            clock_model=clock_model,
            clock_model_sha256=(
                clock_model_sha256
            ),
            clock_quality_passed=True,
            derivation_version=(
                _DERIVATION_VERSION
            ),
        )

        label_rows = build_native_labels(
            mapped_sensor_times=(
                mapped_rows
            ),
            reference_trajectory=(
                reference_rows
            ),
            alignment_lag_ns=(
                _ALIGNMENT_LAG_NS
            ),
            derivation_version=(
                _DERIVATION_VERSION
            ),
        )
    else:
        # Fail closed: do not map or construct
        # supervision labels under a failed clock gate.
        mapped_rows = []
        label_rows = []

    mapped_path = _artifact_file(
        root,
        "mapped_sensor_times",
    )

    _write_csv(
        mapped_path,
        fieldnames=MAPPED_SENSOR_TIME_COLUMNS,
        rows=mapped_rows,
    )

    labels_path = _artifact_file(
        root,
        "native_reference_labels",
    )

    _write_csv(
        labels_path,
        fieldnames=NATIVE_LABEL_COLUMNS,
        rows=label_rows,
    )

    mapped_sha256 = _sha256_file(
        mapped_path
    )

    labels_sha256 = _sha256_file(
        labels_path
    )

    # -----------------------------------------------------
    # Frozen label configuration
    # -----------------------------------------------------

    label_config = {
        "schema_version":
            "1.0",
        "trajectory_version":
            _TRAJECTORY_VERSION,
        "lag_sign_convention":
            (
                "label_pc_time_ns = "
                "pc_mapped_ts_ns - "
                "alignment_lag_ns"
            ),
        "alignment_lag_ns":
            _ALIGNMENT_LAG_NS,
        "clock_mapping_method":
            "ClockModel.map_phone_to_pc_ns",
        "reference_lookup_method":
            "lookup_reference_state",
        "reference_interpolation_rule":
            (
                "linear only within identical "
                "calibration_id, sequence_id, "
                "segment_index, direction_code, "
                "and phase"
            ),
        "out_of_range_policy":
            "OUTSIDE_REFERENCE",
        "source_artifact_paths":
            {
                "raw_imu":
                    _ARTIFACT_PATHS[
                        "raw_imu"
                    ],
                "clock_model":
                    _ARTIFACT_PATHS[
                        "clock_model"
                    ],
                "reference_trajectory":
                    _ARTIFACT_PATHS[
                        "reference_trajectory"
                    ],
                "calibration_manifest":
                    _ARTIFACT_PATHS[
                        "calibration_manifest"
                    ],
            },
        "source_artifact_hashes":
            {
                "raw_imu":
                    raw_imu_sha256,
                "clock_model":
                    clock_model_sha256,
                "reference_trajectory":
                    reference_sha256,
                "calibration_manifest":
                    calibration_manifest_sha256,
            },
        "derivation_version":
            _DERIVATION_VERSION,
        "functional_commit":
            functional_commit,
        "configuration_role":
            "synthetic",
    }

    if (
        tuple(label_config.keys())
        != LABEL_CONFIG_REQUIRED_FIELDS
    ):
        raise RuntimeError(
            "Internal label config schema "
            "order mismatch."
        )

    label_config_path = _artifact_file(
        root,
        "label_config",
    )

    _write_json(
        label_config_path,
        label_config,
    )

    label_config_sha256 = _sha256_file(
        label_config_path
    )

    # -----------------------------------------------------
    # Build assessment + frozen label manifest
    # -----------------------------------------------------

    assessment = assess_label_build(
        label_rows=label_rows,
        clock_model_present=True,
        clock_quality_passed=(
            bool(clock_quality_passed)
        ),
        source_evidence_present=True,
        provenance_present=True,
    )

    label_manifest = build_label_manifest(
        participant_id=_PARTICIPANT_ID,
        session_id=_SESSION_ID,
        calibration_id=_CALIBRATION_ID,
        label_rows=label_rows,
        assessment=assessment,
        raw_imu_sha256=raw_imu_sha256,
        reference_trajectory_sha256=(
            reference_sha256
        ),
        clock_model_sha256=(
            clock_model_sha256
        ),
        label_config_sha256=(
            label_config_sha256
        ),
        derivation_version=(
            _DERIVATION_VERSION
        ),
        functional_commit=(
            functional_commit
        ),
    )

    label_manifest_path = _artifact_file(
        root,
        "label_manifest",
    )

    _write_json(
        label_manifest_path,
        label_manifest,
    )

    # -----------------------------------------------------
    # Artifact digest set
    # -----------------------------------------------------

    artifact_sha256 = {
        key: _sha256_file(
            _artifact_file(
                root,
                key,
            )
        )
        for key in _ARTIFACT_PATHS
    }

    reproducibility_digest = (
        _sha256_json(
            {
                "artifact_sha256":
                    artifact_sha256,
                "source_selection":
                    source_selection,
                "functional_commit":
                    functional_commit,
                "clock_quality_passed":
                    bool(
                        clock_quality_passed
                    ),
            }
        )
    )

    return {
        "status":
            assessment["status"],
        "dataset_role":
            "synthetic",
        "real_participant_data_used":
            False,
        "clock_quality_passed":
            bool(clock_quality_passed),
        "cycle_count":
            2,
        "direction_order":
            list(DIRECTION_CODES),
        "mapped_record_count":
            assessment[
                "mapped_record_count"
            ],
        "valid_label_count":
            assessment[
                "valid_label_count"
            ],
        "invalid_label_count":
            assessment[
                "invalid_label_count"
            ],
        "technical_errors":
            assessment[
                "technical_errors"
            ],
        "synthetic_clock_offset_ns":
            _SYNTHETIC_CLOCK_OFFSET_NS,
        "alignment_lag_ns":
            _ALIGNMENT_LAG_NS,
        "source_selection":
            source_selection,
        "calibration_provenance_sha256":
            calibration_provenance_digest,
        "artifact_paths":
            dict(_ARTIFACT_PATHS),
        "artifact_sha256":
            artifact_sha256,
        "reproducibility_digest":
            reproducibility_digest,
        "output_root":
            str(root),
    }