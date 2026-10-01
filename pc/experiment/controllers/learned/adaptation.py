"""L2C per-user adaptation: freeze the network, fit only the latent adapter."""

import math

import torch

from .adapter import LatentAffineAdapter
from .data import (
    build_windows, extract_samples, labelled_targets, learned_dataset_sha256,
)


class AdaptationResult:
    def __init__(self, gamma, beta, dataset_sha256, steps, final_loss,
                 latent_dim, user_parameter_count, adapter=None):
        self.gamma = gamma
        self.beta = beta
        self.dataset_sha256 = dataset_sha256
        self.steps = steps
        self.final_loss = final_loss
        self.latent_dim = latent_dim
        self.user_parameter_count = user_parameter_count
        self.adapter = adapter


def fit_l2c(config, network, rows, *, identity, steps=400, lr=1e-2):
    """Fit the latent adapter gamma/beta; the network stays frozen.

    Adaptation happens on the latent z, not on the output velocity:
    ``z_new = gamma * z + beta``, then the frozen head reads ``z_new``.
    Only the ``2 * latent_dim`` adapter parameters receive gradients.
    """
    network.eval()
    for parameter in network.parameters():
        parameter.requires_grad_(False)
    samples, labels, times, flags, run_starts = extract_samples(rows, config,
                                                                expect_identity=identity)
    X, y, active = build_windows(samples, labels, flags, config, run_starts)
    indices, targets = labelled_targets(y)
    dataset_sha = learned_dataset_sha256(samples, labels, times, flags, run_starts)
    X_t = torch.tensor([X[i] for i in indices], dtype=torch.float64).float()
    y_t = torch.tensor(targets, dtype=torch.float64).float()
    adapter = LatentAffineAdapter(config.latent_dim)
    optimizer = torch.optim.Adam(adapter.parameters(), lr=lr)
    previous = None
    executed = 0
    for executed in range(1, steps + 1):
        optimizer.zero_grad()
        with torch.no_grad():
            z = network.encode(X_t)[:, -1, :]
        prediction = network.decode(adapter(z))
        loss = torch.mean((prediction - y_t) ** 2)
        detached = loss.detach()
        if not math.isfinite(detached.item()):
            raise ValueError("nonfinite adaptation loss")
        loss.backward()
        optimizer.step()
        current = detached.item()
        if previous is not None and abs(previous - current) < 1e-10:
            break
        previous = current
    with torch.no_grad():
        z = network.encode(X_t)[:, -1, :]
        final = float(torch.mean((network.decode(adapter(z)) - y_t) ** 2))
    return AdaptationResult(adapter.gamma.detach().tolist(),
                            adapter.beta.detach().tolist(),
                            dataset_sha, executed, final, config.latent_dim,
                            adapter.user_parameter_count(), adapter)


