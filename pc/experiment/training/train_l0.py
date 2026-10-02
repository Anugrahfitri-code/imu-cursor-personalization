"""Supervised L0 training on development users only.

The training loop is deliberately plain: seeded initialisation, seeded
shuffling, MSE loss, gradient clipping, and no early stopping tuned on
held-out data. Every hyperparameter comes from the L0 config.
"""

from dataclasses import dataclass, field

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from .dataset import L0WindowDataset, StandardScaler
from .model import L0VelocityModel, parameter_count

CHECKPOINT_FORMAT_VERSION = "1.0"


@dataclass(frozen=True)
class TrainingResult:
    model: object
    scaler: object
    window: int
    seed: int
    history: tuple = field(default_factory=tuple)
    parameter_count: int = 0

    @property
    def final_loss(self):
        return float(self.history[-1]) if self.history else float("nan")


def seed_everything(seed):
    """Make initialisation and batch order reproducible."""
    import random

    seed = int(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    return seed


def build_model(config, window):
    architecture = config.architecture
    return L0VelocityModel(
        window=window,
        latent_channels=architecture.latent_dim,
        latent_dim=architecture.latent_dim)


def fit_dataset(config, train_dataset, window, seed, epochs=None):
    """Train on an already-built dataset (used for both final and inner fits)."""
    optimisation = config.optimisation
    epochs = int(optimisation.epochs if epochs is None else epochs)
    seed_everything(seed)

    model = build_model(config, window)
    if not config.deterministic:
        model.train()

    generator = torch.Generator()
    generator.manual_seed(int(seed))
    loader = DataLoader(
        train_dataset, batch_size=int(optimisation.batch_size),
        shuffle=True, generator=generator, drop_last=False)

    optimiser_cls = getattr(torch.optim, optimisation.optimiser)
    optimiser = optimiser_cls(
        model.parameters(), lr=float(optimisation.learning_rate),
        weight_decay=float(optimisation.weight_decay))
    loss_fn = nn.MSELoss()

    history = []
    for _ in range(epochs):
        model.train()
        total, seen = 0.0, 0
        for batch in loader:
            optimiser.zero_grad(set_to_none=True)
            prediction = model(batch["x"])
            loss = loss_fn(prediction, batch["y"])
            loss.backward()
            if float(optimisation.grad_clip_norm) > 0.0:
                nn.utils.clip_grad_norm_(
                    model.parameters(), float(optimisation.grad_clip_norm))
            optimiser.step()
            total += float(loss.detach()) * len(prediction)
            seen += len(prediction)
        history.append(total / seen if seen else float("nan"))
    return TrainingResult(
        model=model, scaler=train_dataset.scaler, window=int(window),
        seed=int(seed), history=tuple(history),
        parameter_count=parameter_count(model))


def predict(model, dataset, batch_size=256):
    """Inference over a dataset, returned as (y_true, y_pred, codes, active)."""
    model.eval()
    loader = DataLoader(dataset, batch_size=int(batch_size), shuffle=False)
    truths, predictions, codes, active = [], [], [], []
    with torch.no_grad():
        for batch in loader:
            predictions.append(model(batch["x"]).cpu().numpy())
            truths.append(batch["y"].cpu().numpy())
            codes.extend(batch["participant_code"])
            active.extend(batch["active_motion"])
    if not truths:
        return (np.zeros((0, 2), dtype=np.float32),
                np.zeros((0, 2), dtype=np.float32), [], [])
    return (np.concatenate(truths, axis=0),
            np.concatenate(predictions, axis=0), codes,
            np.asarray(active, dtype=bool))


def fit_l0(config, rows, grid_interval_ns, window, user_codes=None):
    """Fit the global L0 model on development users.

    The scaler is fitted on the development windows only. Evaluation
    users never reach this function; passing one in raises.
    """
    from .dataset import build_l0_datasets, concatenate_users

    development = config.require_development_users()
    train_users = list(development if user_codes is None else user_codes)
    leaked = sorted(set(train_users) & set(config.evaluation_users))
    if leaked:
        raise ValueError(
            f"evaluation users cannot be trained on: {leaked}")
    if window not in config.window_candidates:
        raise ValueError(
            f"window {window} is not a configured candidate: "
            f"{list(config.window_candidates)}")

    built = build_l0_datasets(rows, window, grid_interval_ns, train_users)
    X, y, codes, active = concatenate_users(built, train_users)
    scaler = StandardScaler().fit(X)
    dataset = L0WindowDataset(X, y, codes, active, scaler=scaler)
    return fit_dataset(config, dataset, window, config.seed)

