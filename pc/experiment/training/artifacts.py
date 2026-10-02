"""Reproducible L0 artifact persistence.

A checkpoint is only useful if it can be traced back to the exact code
and configuration that produced it, so an artifact records the config
digest, the scaler statistics, the seed, the parameter count, and the
git commit alongside the weights.
"""

from dataclasses import asdict
import json
import platform
import subprocess
import sys
from pathlib import Path

import torch

from ..controllers.config import canonical_json, sha256
from .dataset import StandardScaler

ARTIFACT_FORMAT_VERSION = "1.0"
CHECKPOINT_NAME = "l0_model.pt"
SCALER_NAME = "l0_scaler.json"
CONFIG_NAME = "l0_config.json"
METADATA_NAME = "l0_training_metadata.json"


def git_commit_hash(repo_root=None):
    """Current commit hash, or None when git is unavailable.

    Recorded as provenance only: it never gates a run, so a checkout
    without git still trains.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root or "."),
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def environment_metadata():
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": torch.__version__,
    }


def save_artifacts(result, config, output_dir, extra_metadata=None):
    """Write checkpoint, config, scaler, and training metadata.

    Returns the manifest describing what was written.
    """
    if result.scaler is None:
        raise ValueError("a fitted scaler is required to persist L0 artifacts")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    checkpoint_path = directory / CHECKPOINT_NAME
    torch.save({
        "format_version": ARTIFACT_FORMAT_VERSION,
        "state_dict": result.model.state_dict(),
        "window": int(result.window),
        "seed": int(result.seed),
        "parameter_count": int(result.parameter_count),
        "config_sha256": config.config_sha256,
    }, checkpoint_path)

    scaler_state = result.scaler.state_dict()
    (directory / SCALER_NAME).write_text(
        canonical_json(scaler_state), encoding="utf-8")
    (directory / CONFIG_NAME).write_text(
        canonical_json(asdict(config)), encoding="utf-8")

    metadata = {
        "format_version": ARTIFACT_FORMAT_VERSION,
        "configuration_id": config.configuration_id,
        "config_sha256": config.config_sha256,
        "seed": int(result.seed),
        "window": int(result.window),
        "parameter_count": int(result.parameter_count),
        "epochs": len(result.history),
        "final_loss": result.final_loss,
        "history": [float(v) for v in result.history],
        "development_users": list(config.development_users),
        "evaluation_users": list(config.evaluation_users),
        "git_commit_hash": git_commit_hash(),
        "environment": environment_metadata(),
        "checkpoint_sha256": sha256_file(checkpoint_path),
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    (directory / METADATA_NAME).write_text(
        canonical_json(metadata), encoding="utf-8")

    return {
        "directory": str(directory),
        "checkpoint": str(checkpoint_path),
        "scaler": str(directory / SCALER_NAME),
        "config": str(directory / CONFIG_NAME),
        "metadata": str(directory / METADATA_NAME),
        "parameter_count": int(result.parameter_count),
        "seed": int(result.seed),
        "config_sha256": config.config_sha256,
        "git_commit_hash": metadata["git_commit_hash"],
    }


def sha256_file(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def load_artifacts(directory, config):
    """Restore a model and scaler, verifying they match the config."""
    directory = Path(directory)
    payload = torch.load(directory / CHECKPOINT_NAME,
                         map_location="cpu", weights_only=False)
    if payload.get("format_version") != ARTIFACT_FORMAT_VERSION:
        raise ValueError(
            f"checkpoint format {payload.get('format_version')!r} is not "
            f"supported by {ARTIFACT_FORMAT_VERSION!r}")
    if payload.get("config_sha256") != config.config_sha256:
        raise ValueError(
            "checkpoint was trained under a different configuration; "
            "refusing to load a mismatched artifact")
    from .model import L0VelocityModel

    model = L0VelocityModel(
        window=payload["window"], latent_channels=config.architecture.latent_dim,
        latent_dim=config.architecture.latent_dim)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    scaler = StandardScaler.from_state_dict(json.loads(
        (directory / SCALER_NAME).read_text(encoding="utf-8")))
    return model, scaler, payload


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload), encoding="utf-8")
    return str(path)
