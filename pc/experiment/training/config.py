"""Fail-closed L0 training configuration; no implicit research defaults.

Every optimisation constant is declared in configs/experiment/
l0_training_config.yaml. This module validates the declaration and
refuses to invent values, so a missing or malformed field is an error
rather than a silent fallback.
"""

from dataclasses import asdict, dataclass

from ..controllers.config import finite, sha256

SUPPORTED_WINDOWS = (32, 48, 64)
PERMITTED_OPTIMISERS = ("Adam",)
PERMITTED_LOSSES = ("mse",)
PERMITTED_NORMALISATIONS = ("standard",)


@dataclass(frozen=True)
class ArchitectureConfig:
    blocks: int
    kernel_size: int
    dilations: tuple
    dropout: float
    latent_dim: int
    head_dim: int


@dataclass(frozen=True)
class OptimisationConfig:
    optimiser: str
    learning_rate: float
    weight_decay: float
    epochs: int
    batch_size: int
    loss: str
    grad_clip_norm: float


@dataclass(frozen=True)
class ValidationConfig:
    strategy: str
    outer: str
    inner: str
    inner_folds: int
    scaler_fit_scope: str


@dataclass(frozen=True)
class QualificationConfig:
    zero_velocity_rmse_ratio_max: float
    active_speed_threshold_px_s: float
    min_active_samples: int
    min_direction_agreement: float
    max_mean_latency_ms: float
    latency_warmup_runs: int
    latency_measured_runs: int


@dataclass(frozen=True)
class L0TrainingConfig:
    schema_version: str
    configuration_id: str
    status: str
    window_candidates: tuple
    architecture: ArchitectureConfig
    optimisation: OptimisationConfig
    validation: ValidationConfig
    qualification: QualificationConfig
    normalisation: str
    seed: int
    deterministic: bool
    development_users: tuple
    evaluation_users: tuple

    @property
    def config_sha256(self):
        return sha256(asdict(self))

    def require_development_users(self):
        """L0 may only be built from development users; fail closed."""
        if not self.development_users:
            raise ValueError(
                "development_users is empty: L0 must be built from an "
                "explicit development cohort, never from every participant")
        overlap = set(self.development_users) & set(self.evaluation_users)
        if overlap:
            raise ValueError(
                f"participants declared as both development and "
                f"evaluation: {sorted(overlap)}")
        return self.development_users


def _section(raw, name):
    if name not in raw or not isinstance(raw[name], dict):
        raise ValueError(f"l0 config is missing the '{name}' section")
    return raw[name]


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _probability(value, name):
    value = finite(value, name)
    if not 0.0 <= value < 1.0:
        raise ValueError(f"{name} must be within [0, 1)")
    return value


def _roster(raw, name):
    if name not in raw or not isinstance(raw[name], list):
        raise ValueError(f"l0 config is missing the '{name}' roster")
    values = tuple(str(entry) for entry in raw[name])
    if len(set(values)) != len(values):
        raise ValueError(f"{name} contains duplicate participant codes")
    return values


def _architecture(raw):
    arch = _section(raw, "architecture")
    dilations = arch.get("dilations")
    if (not isinstance(dilations, list)
            or tuple(dilations) != (1, 2, 4, 8)
            or _positive_int(arch.get("blocks"), "architecture.blocks") != 4):
        raise ValueError(
            "architecture is fixed by proposal: 4 blocks with kernel 5 "
            "and dilations [1, 2, 4, 8]")
    if _positive_int(arch.get("kernel_size"), "kernel_size") != 5:
        raise ValueError("architecture.kernel_size must be 5")
    if _positive_int(arch.get("head_dim"), "head_dim") != 2:
        raise ValueError("head_dim must be 2 (vx_ref, vy_ref)")
    return ArchitectureConfig(
        blocks=4, kernel_size=5, dilations=tuple(dilations),
        dropout=_probability(arch["dropout"], "architecture.dropout"),
        latent_dim=_positive_int(arch["latent_dim"], "latent_dim"),
        head_dim=2)


def _optimisation(raw):
    opt = _section(raw, "optimisation")
    if opt.get("optimiser") not in PERMITTED_OPTIMISERS:
        raise ValueError(
            f"optimiser must be one of {list(PERMITTED_OPTIMISERS)}")
    if opt.get("loss") not in PERMITTED_LOSSES:
        raise ValueError(f"loss must be one of {list(PERMITTED_LOSSES)}")
    if finite(opt["learning_rate"], "learning_rate") <= 0.0:
        raise ValueError("learning_rate must be positive")
    return OptimisationConfig(
        optimiser=str(opt["optimiser"]),
        learning_rate=finite(opt["learning_rate"], "learning_rate"),
        weight_decay=finite(opt["weight_decay"], "weight_decay"),
        epochs=_positive_int(opt["epochs"], "epochs"),
        batch_size=_positive_int(opt["batch_size"], "batch_size"),
        loss=str(opt["loss"]),
        grad_clip_norm=finite(opt["grad_clip_norm"], "grad_clip_norm"))


def _validation(raw):
    val = _section(raw, "validation")
    if val.get("outer") != "leave_one_user_out":
        raise ValueError("outer validation must be leave_one_user_out")
    if val.get("inner") != "grouped_kfold":
        raise ValueError("inner validation must be grouped_kfold")
    if val.get("scaler_fit_scope") != "inner_training_users":
        raise ValueError(
            "scaler_fit_scope must be inner_training_users so the held-out "
            "user never contributes to normalisation")
    folds = _positive_int(val["inner_folds"], "inner_folds")
    if folds < 2:
        raise ValueError("inner_folds must be at least 2")
    return ValidationConfig(
        strategy=str(val["strategy"]), outer="leave_one_user_out",
        inner="grouped_kfold", inner_folds=folds,
        scaler_fit_scope="inner_training_users")


def _qualification(raw):
    qual = _section(raw, "qualification")
    agreement = finite(qual["min_direction_agreement"], "min_direction_agreement")
    if not 0.0 < agreement <= 1.0:
        raise ValueError("min_direction_agreement must be within (0, 1]")
    ratio = finite(qual["zero_velocity_rmse_ratio_max"],
                   "zero_velocity_rmse_ratio_max")
    if not 0.0 < ratio <= 1.0:
        raise ValueError("zero_velocity_rmse_ratio_max must be within (0, 1]")
    return QualificationConfig(
        zero_velocity_rmse_ratio_max=ratio,
        active_speed_threshold_px_s=finite(
            qual["active_speed_threshold_px_s"], "active_speed_threshold_px_s"),
        min_active_samples=_positive_int(
            qual["min_active_samples"], "min_active_samples"),
        min_direction_agreement=agreement,
        max_mean_latency_ms=finite(
            qual["max_mean_latency_ms"], "max_mean_latency_ms"),
        latency_warmup_runs=_positive_int(
            qual["latency_warmup_runs"], "latency_warmup_runs"),
        latency_measured_runs=_positive_int(
            qual["latency_measured_runs"], "latency_measured_runs"))


def load_l0_config(path):
    """Parse and validate the L0 training configuration."""
    import yaml  # local import: model code must not depend on the parser

    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("l0 config must be a mapping")

    windows = raw.get("window_candidates")
    if (not isinstance(windows, list) or not windows
            or any(w not in SUPPORTED_WINDOWS for w in windows)):
        raise ValueError(
            "window_candidates must be a non-empty subset of "
            f"{list(SUPPORTED_WINDOWS)}")
    if len(set(windows)) != len(windows):
        raise ValueError("window_candidates contains duplicates")

    seed = raw.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")

    norm = _section(raw, "normalisation")
    if norm.get("method") not in PERMITTED_NORMALISATIONS:
        raise ValueError(
            "normalisation.method must be one of "
            f"{list(PERMITTED_NORMALISATIONS)}")

    for key in ("schema_version", "configuration_id", "status"):
        if key not in raw or not isinstance(raw[key], str) or not raw[key]:
            raise ValueError(f"l0 config requires a non-empty '{key}' string")

    return L0TrainingConfig(
        schema_version=raw["schema_version"],
        configuration_id=raw["configuration_id"],
        status=raw["status"],
        window_candidates=tuple(int(w) for w in windows),
        architecture=_architecture(raw),
        optimisation=_optimisation(raw),
        validation=_validation(raw),
        qualification=_qualification(raw),
        normalisation=str(norm["method"]),
        seed=seed,
        deterministic=bool(raw.get("deterministic", True)),
        development_users=_roster(raw, "development_users"),
        evaluation_users=_roster(raw, "evaluation_users"),
    )
