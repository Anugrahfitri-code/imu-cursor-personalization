import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pc.experiment.preprocessing.active_motion import (
    classify_active_motion_sample,
)

from pc.experiment.preprocessing.axis_transform import (
    transform_sensor_sample,
)

from pc.experiment.preprocessing.bias import (
    apply_sensor_bias_correction,
    estimate_sensor_bias,
)

from pc.experiment.preprocessing.config import (
    preprocessing_config_sha256,
    validate_preprocessing_config,
)

from pc.experiment.preprocessing.filtering import (
    filter_sensor_stream,
)

from pc.experiment.preprocessing.grid import (
    build_common_grid,
)

from pc.experiment.preprocessing.labels import (
    attach_common_grid_reference_labels,
)

from pc.experiment.preprocessing.manifest import (
    build_preprocessing_manifest,
    preprocessing_manifest_sha256,
)

from pc.experiment.preprocessing.quality import (
    assess_preprocessing_quality,
)

from pc.experiment.preprocessing.resampling import (
    detect_source_gap_events,
    resample_sensor_streams,
)

from pc.experiment.preprocessing.schema import (
    COMMON_GRID_COLUMNS,
    SENSOR_FAMILIES,
)

from pc.experiment.preprocessing.source_validation import (
    apply_stream_anomaly_policy,
    normalize_sensor_streams,
)


_RESULT_FIELDS = (
    "preprocessing_config",
    "preprocessing_config_sha256",
    "common_grid_rows",
    "preprocessing_quality",
    "preprocessing_manifest",
    "common_grid_sha256",
    "preprocessing_quality_sha256",
    "preprocessing_manifest_sha256",
    "source_diagnostics",
    "gap_events",
)


_AXES = (
    "x",
    "y",
    "z",
)


def _canonical_sha256(
    value: Any,
) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode(
            "utf-8"
        )
    ).hexdigest().upper()


def _grid_origin_pc_ns(
    grid_origin_rule: str,
) -> int:
    if grid_origin_rule == "ALIGN_TO_ORIGIN":
        return 0

    raise ValueError(
        "unsupported grid origin rule: "
        f"{grid_origin_rule!r}."
    )


def _combined_sensor_status(
    *,
    accel_status: str,
    gyro_status: str,
) -> str:
    accel_valid = (
        accel_status == "VALID"
    )

    gyro_valid = (
        gyro_status == "VALID"
    )

    if accel_valid and gyro_valid:
        return "VALID"

    if (
        not accel_valid
        and gyro_valid
    ):
        return "INVALID_ACCEL"

    if (
        accel_valid
        and not gyro_valid
    ):
        return "INVALID_GYRO"

    return "INVALID_BOTH"


def _transform_native_stream(
    *,
    stream: Sequence[Mapping[str, Any]],
    sensor_family: str,
    axis_transform: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        transform_sensor_sample(
            sample=row,
            sensor_family=sensor_family,
            axis_transform=axis_transform,
        )
        for row in stream
    ]


def _estimate_family_biases(
    *,
    streams: Mapping[
        str,
        Sequence[Mapping[str, Any]]
    ],
    axis_transform: Mapping[str, Any],
    bias_config: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    estimates: dict[
        str,
        dict[str, Any],
    ] = {}

    for sensor_family in SENSOR_FAMILIES:
        transformed_native = (
            _transform_native_stream(
                stream=streams[
                    sensor_family
                ],
                sensor_family=sensor_family,
                axis_transform=axis_transform,
            )
        )

        estimates[
            sensor_family
        ] = estimate_sensor_bias(
            stream=transformed_native,
            sensor_family=sensor_family,
            method=bias_config[
                "method"
            ],
            window_start_pc_ns=(
                bias_config[
                    "window_start_pc_ns"
                ]
            ),
            window_end_pc_ns=(
                bias_config[
                    "window_end_pc_ns"
                ]
            ),
            channels=bias_config[
                "channels"
            ],
            minimum_samples=bias_config[
                "minimum_samples"
            ],
        )

    return estimates


def _transform_and_bias_grid_stream(
    *,
    rows: Sequence[Mapping[str, Any]],
    sensor_family: str,
    axis_transform: Mapping[str, Any],
    bias_estimate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result: list[
        dict[str, Any]
    ] = []

    for source_row in rows:
        if source_row[
            "status"
        ] != "VALID":
            result.append(
                deepcopy(
                    dict(source_row)
                )
            )

            continue

        transformed = (
            transform_sensor_sample(
                sample=source_row,
                sensor_family=sensor_family,
                axis_transform=axis_transform,
            )
        )

        corrected = (
            apply_sensor_bias_correction(
                stream=[
                    transformed
                ],
                bias_estimate=bias_estimate,
            )[0]
        )

        result.append(
            corrected
        )

    return result


def _filter_valid_runs(
    *,
    rows: Sequence[Mapping[str, Any]],
    filter_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    filter_channels = tuple(
        filter_config.get(
            "channels",
            _AXES,
        )
    )

    output: list[
        dict[str, Any]
    ] = []

    valid_run: list[
        Mapping[str, Any]
    ] = []

    def flush_run() -> None:
        nonlocal valid_run

        if not valid_run:
            return

        output.extend(
            filter_sensor_stream(
                stream=valid_run,
                filter_config=filter_config,
                channels=filter_channels,
                reset_before_indices=(),
            )
        )

        valid_run = []

    for row in rows:
        if row[
            "status"
        ] == "VALID":
            valid_run.append(
                row
            )

            continue

        flush_run()

        output.append(
            deepcopy(
                dict(row)
            )
        )

    flush_run()

    return output


def _build_base_grid_rows(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    config_sha256: str,
    derivation_version: str,
    grid_pc_times_ns: Sequence[int],
    processed_streams: Mapping[
        str,
        Sequence[Mapping[str, Any]]
    ],
    active_motion_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    accel_rows = processed_streams[
        "ACCEL"
    ]

    gyro_rows = processed_streams[
        "GYRO"
    ]

    if (
        len(accel_rows)
        != len(grid_pc_times_ns)
        or len(gyro_rows)
        != len(grid_pc_times_ns)
    ):
        raise RuntimeError(
            "resampled sensor row count does not "
            "match common-grid row count."
        )

    active_family = (
        active_motion_config.get(
            "sensor_family",
            "GYRO",
        )
    )

    if active_family not in SENSOR_FAMILIES:
        raise ValueError(
            "active-motion sensor family must be "
            f"one of {SENSOR_FAMILIES!r}."
        )

    result: list[
        dict[str, Any]
    ] = []

    for grid_index, grid_pc_time_ns in enumerate(
        grid_pc_times_ns
    ):
        accel = accel_rows[
            grid_index
        ]

        gyro = gyro_rows[
            grid_index
        ]

        sensor_status = (
            _combined_sensor_status(
                accel_status=accel[
                    "status"
                ],
                gyro_status=gyro[
                    "status"
                ],
            )
        )

        motion_row = (
            accel
            if active_family == "ACCEL"
            else gyro
        )

        if motion_row[
            "status"
        ] == "VALID":
            active_motion_flag = (
                classify_active_motion_sample(
                    sample=motion_row,
                    active_motion_config=(
                        active_motion_config
                    ),
                )
            )
        else:
            active_motion_flag = False

        row = {
            "grid_record_id":
                (
                    f"{calibration_id}:"
                    f"GRID:{grid_index:06d}"
                ),
            "participant_id":
                participant_id,
            "session_id":
                session_id,
            "calibration_id":
                calibration_id,
            "grid_index":
                grid_index,
            "grid_pc_time_ns":
                grid_pc_time_ns,
            "preprocessing_config_sha256":
                config_sha256,
            "accel_x":
                accel["x"],
            "accel_y":
                accel["y"],
            "accel_z":
                accel["z"],
            "gyro_x":
                gyro["x"],
            "gyro_y":
                gyro["y"],
            "gyro_z":
                gyro["z"],
            "accel_status":
                accel["status"],
            "gyro_status":
                gyro["status"],
            "sensor_status":
                sensor_status,
            "active_motion_flag":
                active_motion_flag,
            "grid_label_pc_time_ns":
                None,
            "sequence_id":
                None,
            "direction_code":
                None,
            "phase":
                None,
            "ref_x_px":
                None,
            "ref_y_px":
                None,
            "ref_vx_px_s":
                None,
            "ref_vy_px_s":
                None,
            "label_status":
                None,
            "derivation_version":
                derivation_version,
        }

        result.append(
            row
        )

    return result


def _order_common_grid_rows(
    rows: Sequence[
        Mapping[str, Any]
    ],
) -> list[dict[str, Any]]:
    return [
        {
            column:
                row.get(
                    column
                )
            for column in COMMON_GRID_COLUMNS
        }
        for row in rows
    ]


def build_stage25_preprocessing(
    *,
    participant_id: str,
    session_id: str,
    calibration_id: str,
    records: Sequence[Mapping[str, Any]],
    reference_trajectory: Sequence[
        Mapping[str, Any]
    ],
    preprocessing_config: Mapping[str, Any],
    upstream_stage24_provenance_sha256: str,
    upstream_clock_quality_passed: bool,
    technical_errors: Sequence[Any] = (),
) -> dict[str, Any]:
    """
    Build a deterministic Stage 2.5 preprocessing bundle.

    Alignment is based exclusively on pc_mapped_ts_ns.

    pc_receive_ts_ns, experiment condition identifiers,
    and evaluation outcomes do not select or modify a
    preprocessing path.

    This is an in-memory numerical kernel. Source hashes are caller
    declarations; use build_stage25_from_artifacts for verified files.
    Initialization samples remain in the raw evidence but are never
    published as causal model inputs before bias estimation has ended.
    """
    if upstream_clock_quality_passed is not True:
        raise ValueError(
            "upstream clock quality gate did not pass."
        )

    normalized_config = (
        validate_preprocessing_config(
            preprocessing_config
        )
    )

    config_sha = (
        preprocessing_config_sha256(
            normalized_config
        )
    )

    if (
        normalized_config[
            "grid_domain_rule"
        ]
        != "INTERSECTION"
    ):
        raise ValueError(
            "unsupported grid domain rule."
        )

    if (
        normalized_config[
            "gap_policy"
        ]
        != "EXPLICIT_STATUS"
    ):
        raise ValueError(
            "unsupported gap policy."
        )

    low_pass_config = (
        normalized_config[
            "low_pass_filter"
        ]
    )

    if (
        normalized_config[
            "filter_reset_policy"
        ]
        != low_pass_config[
            "reset_policy"
        ]
    ):
        raise ValueError(
            "filter reset policy mismatch."
        )

    normalized = normalize_sensor_streams(
        records=records,
        participant_id=participant_id,
        session_id=session_id,
        calibration_id=calibration_id,
    )

    anomaly_result = (
        apply_stream_anomaly_policy(
            normalized_result=normalized,
            reorder_policy=(
                normalized_config[
                    "reorder_policy"
                ]
            ),
            duplicate_policy=(
                normalized_config[
                    "duplicate_policy"
                ]
            ),
        )
    )

    streams = anomaly_result[
        "streams"
    ]

    source_diagnostics = (
        anomaly_result[
            "diagnostics"
        ]
    )

    gap_events = {
        sensor_family:
            detect_source_gap_events(
                stream=streams[
                    sensor_family
                ],
                expected_interval_ns=(
                    normalized_config[
                        "grid_interval_ns"
                    ]
                ),
                max_source_gap_ns=(
                    normalized_config[
                        "max_source_gap_ns"
                    ]
                ),
            )
        for sensor_family in SENSOR_FAMILIES
    }

    grid_origin_pc_ns = (
        _grid_origin_pc_ns(
            normalized_config[
                "grid_origin_rule"
            ]
        )
    )

    grid_result = build_common_grid(
        accel_stream=streams[
            "ACCEL"
        ],
        gyro_stream=streams[
            "GYRO"
        ],
        grid_interval_ns=(
            normalized_config[
                "grid_interval_ns"
            ]
        ),
        grid_origin_pc_ns=(
            grid_origin_pc_ns
        ),
        grid_domain_rule=(
            normalized_config[
                "grid_domain_rule"
            ]
        ),
    )

    grid_pc_times_ns = (
        grid_result[
            "grid_pc_times_ns"
        ]
    )

    bias_end = int(normalized_config["bias_correction"]["window_end_pc_ns"])
    grid_pc_times_ns = [t for t in grid_pc_times_ns if t > bias_end]
    if not grid_pc_times_ns:
        raise ValueError("no common-grid output remains after the bias window.")

    resampled = resample_sensor_streams(
        accel_stream=streams[
            "ACCEL"
        ],
        gyro_stream=streams[
            "GYRO"
        ],
        grid_pc_times_ns=(
            grid_pc_times_ns
        ),
        accel_method=(
            normalized_config[
                "accel_resampling_method"
            ]
        ),
        gyro_method=(
            normalized_config[
                "gyro_resampling_method"
            ]
        ),
        max_source_gap_ns=(
            normalized_config[
                "max_source_gap_ns"
            ]
        ),
    )

    bias_estimates = (
        _estimate_family_biases(
            streams=streams,
            axis_transform=(
                normalized_config[
                    "axis_transform"
                ]
            ),
            bias_config=(
                normalized_config[
                    "bias_correction"
                ]
            ),
        )
    )

    processed_streams: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for sensor_family in SENSOR_FAMILIES:
        transformed_and_corrected = (
            _transform_and_bias_grid_stream(
                rows=resampled[
                    sensor_family
                ],
                sensor_family=sensor_family,
                axis_transform=(
                    normalized_config[
                        "axis_transform"
                    ]
                ),
                bias_estimate=(
                    bias_estimates[
                        sensor_family
                    ]
                ),
            )
        )

        processed_streams[
            sensor_family
        ] = _filter_valid_runs(
            rows=transformed_and_corrected,
            filter_config=low_pass_config,
        )

    base_grid_rows = (
        _build_base_grid_rows(
            participant_id=participant_id,
            session_id=session_id,
            calibration_id=calibration_id,
            config_sha256=config_sha,
            derivation_version=(
                normalized_config[
                    "derivation_version"
                ]
            ),
            grid_pc_times_ns=(
                grid_pc_times_ns
            ),
            processed_streams=(
                processed_streams
            ),
            active_motion_config=(
                normalized_config[
                    "active_motion"
                ]
            ),
        )
    )

    labeled_rows = (
        attach_common_grid_reference_labels(
            common_grid_rows=(
                base_grid_rows
            ),
            reference_trajectory=(
                reference_trajectory
            ),
            alignment_lag_ns=(
                normalized_config[
                    "alignment_lag_ns"
                ]
            ),
        )
    )

    common_grid_rows = (
        _order_common_grid_rows(
            labeled_rows
        )
    )

    common_grid_sha = (
        _canonical_sha256(
            common_grid_rows
        )
    )

    preprocessing_quality = (
        assess_preprocessing_quality(
            participant_id=participant_id,
            session_id=session_id,
            calibration_id=calibration_id,
            source_streams=streams,
            source_diagnostics=(
                source_diagnostics
            ),
            gap_events=gap_events,
            common_grid_rows=(
                common_grid_rows
            ),
            technical_errors=(
                technical_errors
            ),
            derivation_version=(
                normalized_config[
                    "derivation_version"
                ]
            ),
        )
    )

    preprocessing_quality_sha = (
        _canonical_sha256(
            preprocessing_quality
        )
    )

    preprocessing_manifest = (
        build_preprocessing_manifest(
            participant_id=participant_id,
            session_id=session_id,
            calibration_id=calibration_id,
            preprocessing_config=(
                normalized_config
            ),
            preprocessing_config_sha256=(
                config_sha
            ),
            source_artifact_hashes=(
                normalized_config[
                    "source_artifact_hashes"
                ]
            ),
            upstream_stage24_provenance_sha256=(
                upstream_stage24_provenance_sha256
            ),
            common_grid_rows=(
                common_grid_rows
            ),
            common_grid_sha256=(
                common_grid_sha
            ),
            preprocessing_quality=(
                preprocessing_quality
            ),
            preprocessing_quality_sha256=(
                preprocessing_quality_sha
            ),
            derivation_version=(
                normalized_config[
                    "derivation_version"
                ]
            ),
            functional_commit=(
                normalized_config[
                    "functional_commit"
                ]
            ),
        )
    )

    manifest_sha = (
        preprocessing_manifest_sha256(
            preprocessing_manifest
        )
    )

    result = {
        "preprocessing_config":
            deepcopy(
                normalized_config
            ),
        "preprocessing_config_sha256":
            config_sha,
        "common_grid_rows":
            common_grid_rows,
        "preprocessing_quality":
            preprocessing_quality,
        "preprocessing_manifest":
            preprocessing_manifest,
        "common_grid_sha256":
            common_grid_sha,
        "preprocessing_quality_sha256":
            preprocessing_quality_sha,
        "preprocessing_manifest_sha256":
            manifest_sha,
        "source_diagnostics":
            deepcopy(
                source_diagnostics
            ),
        "gap_events":
            deepcopy(
                gap_events
            ),
    }

    if (
        tuple(result.keys())
        != _RESULT_FIELDS
    ):
        raise RuntimeError(
            "Stage 2.5 builder result does not "
            "match frozen bundle order."
        )

    return result
