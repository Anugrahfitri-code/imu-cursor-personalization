"""Fail-closed Stage 2.5 bundle boundary for offline 2C adaptation."""

from collections import Counter
from copy import deepcopy

from pc.experiment.calibration.schema import DIRECTION_CODES
from pc.experiment.preprocessing.config import (
    preprocessing_config_sha256, validate_preprocessing_config,
)
from pc.experiment.preprocessing.manifest import (
    build_preprocessing_manifest, preprocessing_manifest_sha256,
)
from pc.experiment.preprocessing.schema import COMMON_GRID_COLUMNS
from .config import digest, features, finite, sha256

IDENTITY = ("participant_id", "session_id", "calibration_id")
SEQUENCES = {f"C{cycle:02d}_D{direction:02d}": code
             for cycle in (1, 2) for direction, code in enumerate(DIRECTION_CODES, 1)}


def preprocessing_policy_sha256(config):
    """Source bindings vary by session, but the global signal policy must not."""
    policy = dict(validate_preprocessing_config(config))
    del policy["source_artifact_paths"]
    del policy["source_artifact_hashes"]
    return sha256(policy)


def validate_bundle(bundle, config, declaration):
    """Declaration is an audited input, not proof of dataset membership by itself."""
    expected = {"schema_version", "purpose", *IDENTITY}
    if set(declaration) != expected or declaration["schema_version"] != "stage2.6-data-v1":
        raise ValueError("invalid calibration declaration schema")
    if declaration["purpose"] != "CALIBRATION_2C":
        raise ValueError("adaptation accepts CALIBRATION_2C only, never evaluation data")
    manifest = bundle["preprocessing_manifest"]
    for key in IDENTITY:
        if (not isinstance(declaration[key], str) or not declaration[key].strip() or
                declaration[key] != manifest[key]):
            raise ValueError(f"calibration declaration {key} mismatch")
    pc = validate_preprocessing_config(bundle["preprocessing_config"])
    config_sha = preprocessing_config_sha256(pc)
    if digest(bundle["preprocessing_config_sha256"], "config hash") != config_sha:
        raise ValueError("preprocessing configuration hash mismatch")
    if preprocessing_policy_sha256(pc) != config.preprocessing_policy_sha256:
        raise ValueError("preprocessing policy differs from controller candidate")
    if pc["grid_interval_ns"] != config.grid_interval_ns:
        raise ValueError("controller grid interval mismatch")
    rows = bundle["common_grid_rows"]
    quality = bundle["preprocessing_quality"]
    grid_sha, quality_sha = sha256(rows), sha256(quality)
    for name, actual in (("common_grid_sha256", grid_sha),
                         ("preprocessing_quality_sha256", quality_sha)):
        if digest(bundle[name], name) != actual:
            raise ValueError(f"{name} mismatch")
    rebuilt = build_preprocessing_manifest(
        **{k: declaration[k] for k in IDENTITY}, preprocessing_config=pc,
        preprocessing_config_sha256=config_sha,
        source_artifact_hashes=manifest["source_artifact_hashes"],
        upstream_stage24_provenance_sha256=manifest["upstream_stage24_provenance_sha256"],
        common_grid_rows=rows, common_grid_sha256=grid_sha,
        preprocessing_quality=quality, preprocessing_quality_sha256=quality_sha,
        derivation_version=manifest["derivation_version"],
        functional_commit=manifest["functional_commit"],
    )
    if rebuilt != manifest or digest(bundle["preprocessing_manifest_sha256"],
                                    "manifest hash") != preprocessing_manifest_sha256(rebuilt):
        raise ValueError("preprocessing manifest mismatch")
    if manifest["status"] != "VALID" or quality["status"] != "VALID":
        raise ValueError("technically invalid preprocessing cannot be adapted")
    return deepcopy(rows), {
        **{k: declaration[k] for k in IDENTITY},
        "declaration_sha256": sha256(declaration),
        "preprocessing_config_sha256": config_sha,
        "preprocessing_manifest_sha256": preprocessing_manifest_sha256(rebuilt),
        "common_grid_sha256": grid_sha,
        "preprocessing_quality_sha256": quality_sha,
        "source_artifact_hashes": deepcopy(manifest["source_artifact_hashes"]),
        "upstream_stage24_provenance_sha256": manifest["upstream_stage24_provenance_sha256"],
    }



def calibration_arrays(rows, config):
    x, y, indices = [], [], []
    counts = Counter()
    previous_time = None
    previous_sequence = -1
    seen_ids = set()
    order = list(SEQUENCES)
    for index, row in enumerate(rows):
        if set(row) != set(COMMON_GRID_COLUMNS):
            raise ValueError("common-grid row schema mismatch")
        t = row["grid_pc_time_ns"]
        if (type(t) is not int or t < 0 or type(row["grid_index"]) is not int or
                row["grid_index"] != index or (previous_time is not None and
                t - previous_time != config.grid_interval_ns)):
            raise ValueError("common grid must have contiguous monotonic integer timestamps")
        previous_time = t
        record_id = row["grid_record_id"]
        if not isinstance(record_id, str) or not record_id or record_id in seen_ids:
            raise ValueError("duplicate/invalid grid record identity")
        seen_ids.add(record_id)
        if row["label_status"] != "VALID":
            continue
        sequence = row["sequence_id"]
        if sequence not in SEQUENCES or row["direction_code"] != SEQUENCES[sequence]:
            raise ValueError("labels must belong to exactly two eight-direction cycles")
        if order.index(sequence) < previous_sequence:
            raise ValueError("calibration sequences must be chronological")
        previous_sequence = order.index(sequence)
        if row["phase"] not in {"CENTER_HOLD", "OUTBOUND", "TARGET_HOLD", "RETURN"}:
            raise ValueError("invalid calibration phase")
        if row["sensor_status"] != "VALID":
            continue
        if row["gyro_status"] != "VALID" or row["accel_status"] != "VALID":
            raise ValueError("inconsistent sensor validity")
        x.append((*features(row, config), 1.0))
        y.append((finite(row["ref_vx_px_s"], "reference vx"),
                  finite(row["ref_vy_px_s"], "reference vy")))
        indices.append(index)
        counts[sequence] += 1
    if not rows or (len(rows) - len(x)) / len(rows) > config.max_invalid_fraction:
        raise ValueError("excessive invalid/unlabelled calibration rows")
    if any(counts[s] < config.min_samples_per_sequence for s in SEQUENCES):
        raise ValueError("insufficient valid samples in one or more 2C sequences")
    return x, y, indices, dict(sorted(counts.items()))
