"""L2C per-user latent affine adapter.

The proposal personalises L2C in the latent space of the frozen global model:
``z_new = gamma * z + beta`` for every latent coordinate ``z``. The encoder,
the latent projection, and the regression head are frozen; the adapter is the
only thing that is fitted for a new participant, which is what keeps the
per-user parameter budget at ``2 * d`` (d = 16 -> 32, 32 -> 64, 64 -> 128).

The adapter is initialised as the identity transformation (gamma = 1,
beta = 0) so an unadapted participant replays exactly like L0.
"""

import torch
from torch import nn

from .config import LATENT_DIMS


class LatentAffineAdapter(nn.Module):
    """Coordinate-wise affine map on the frozen latent: z_new = gamma*z + beta."""

    def __init__(self, latent_dim):
        super().__init__()
        if isinstance(latent_dim, bool) or not isinstance(latent_dim, int) \
                or latent_dim not in LATENT_DIMS:
            raise ValueError(f"latent_dim must be one of {LATENT_DIMS}")
        self.latent_dim = latent_dim
        self.gamma = nn.Parameter(torch.ones(latent_dim))
        self.beta = nn.Parameter(torch.zeros(latent_dim))

    def forward(self, z):
        if z.shape[-1] != self.latent_dim:
            raise ValueError(
                f"latent width {z.shape[-1]} does not match adapter {self.latent_dim}")
        return self.gamma * z + self.beta

    def user_parameter_count(self):
        """Only these parameters are fitted for the participant."""
        return 2 * self.latent_dim

    def is_identity(self):
        with torch.no_grad():
            return bool(torch.equal(self.gamma.detach(),
                                    torch.ones(self.latent_dim))
                        and torch.equal(self.beta.detach(),
                                        torch.zeros(self.latent_dim)))


__all__ = ["LatentAffineAdapter"]