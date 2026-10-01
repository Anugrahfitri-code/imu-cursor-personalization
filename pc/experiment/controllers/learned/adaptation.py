"""L2C per-user adaptation: freeze encoder/head, fit gamma/beta only."""

import math

import torch

from .data import (
    build_windows, extract_samples, labelled_targets, learned_dataset_sha256,
)


class AdaptationResult:
    def __init__(self, gamma, beta, dataset_sha256, steps, final_loss):
        self.gamma = gamma
        self.beta = beta
        self.dataset_sha256 = dataset_sha256
        self.steps = steps
        self.final_loss = final_loss


def fit_l2c(config, network, rows, *, identity, steps=400, lr=1e-2):
    """Fit gamma/beta on the user's calibration rows; encoder/head frozen."""
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
    gamma = torch.ones(2, requires_grad=True)
    beta = torch.zeros(2, requires_grad=True)
    optimizer = torch.optim.Adam([gamma, beta], lr=lr)
    previous = None
    executed = 0
    for executed in range(1, steps + 1):
        optimizer.zero_grad()
        with torch.no_grad():
            base = network(X_t)[:, -1, :]
        prediction = base * gamma + beta
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
        base = network(X_t)[:, -1, :]
        final = float(torch.mean((base * gamma + beta - y_t) ** 2))
    return AdaptationResult(gamma.detach().tolist(), beta.detach().tolist(),
                            dataset_sha, executed, final)
