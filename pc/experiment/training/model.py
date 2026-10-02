"""L0 global model: the frozen causal encoder plus a supervised head.

L0 reuses the Stage 2.7 `VelocityNet` verbatim, so the L0 encoder and the
later L2C frozen encoder are literally the same architecture and the same
implementation. No GRU, no Transformer, no architecture search: the 4
blocks, kernel 5, dilations 1/2/4/8, LayerNorm -> GELU -> Dropout(0.10)
stack is fixed by the proposal and enforced by `pc.experiment.controllers
.learned.config.ARCHITECTURE`.

L0 predicts only the final timestep of each window, which is exactly
X[t-T+1 : t] -> Y(t).
"""

from torch import nn

from ..controllers.learned.config import ARCHITECTURE
from ..controllers.learned.network import VelocityNet
from .dataset import IMU_CHANNELS, TARGET_LABELS


class L0VelocityModel(nn.Module):
    """Causal Conv1D encoder -> latent projection -> linear (vx, vy) head."""

    def __init__(self, window, latent_channels=None, latent_dim=None):
        super().__init__()
        if latent_dim is None:
            raise ValueError("latent_dim is required; no implicit default")
        latent_dim = int(latent_dim)
        latent_channels = int(latent_channels if latent_channels is not None
                              else latent_dim)
        self.window = int(window)
        self.latent_dim = latent_dim
        self.net = VelocityNet(
            latent_channels=latent_channels,
            latent_dim=latent_dim,
            outputs=len(TARGET_LABELS))

    def encode(self, x):
        """x: (B, T, 6) -> z: (B, T, latent_dim), causal at every position."""
        return self.net.encode(x)

    def forward(self, x):
        """Map a (B, T, 6) causal window batch to (B, 2) velocity in px/s."""
        if x.dim() != 3 or x.shape[-1] != len(IMU_CHANNELS):
            raise ValueError(
                f"expected (B, T, {len(IMU_CHANNELS)}) input, got {tuple(x.shape)}")
        decoded = self.net.decode(self.encode(x))
        return decoded[:, -1, :]


def receptive_field():
    """Causal receptive field of the frozen stack, in samples."""
    kernel = ARCHITECTURE["kernel_size"]
    return 1 + sum((kernel - 1) * d for d in ARCHITECTURE["dilations"])


def parameter_count(model):
    return int(sum(p.numel() for p in model.parameters()))


def expected_parameter_count(latent_channels, latent_dim):
    """Closed-form parameter total for the frozen L0 architecture.

    Mirrors VelocityNet exactly so a structural change to the stack
    cannot pass the test suite unnoticed.
    """
    kernel = ARCHITECTURE["kernel_size"]
    outputs = len(TARGET_LABELS)
    total = 0
    channels_in = ARCHITECTURE["channels_in"]
    for index in range(ARCHITECTURE["blocks"]):
        # CausalConv1d weight + bias
        total += channels_in * latent_channels * kernel + latent_channels
        # ChannelLayerNorm weight + bias
        total += 2 * latent_channels
        channels_in = latent_channels
    # latent_projection: Linear(latent_channels, latent_dim)
    total += latent_channels * latent_dim + latent_dim
    # head: Linear(latent_dim, outputs)
    total += latent_dim * outputs + outputs
    return total
