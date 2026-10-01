"""Frozen causal Conv1D encoder family; padding is causal (left only)."""

import torch
from torch import nn

from .config import ARCHITECTURE


class CausalConv1d(nn.Module):
    """Conv1d whose receptive field only reaches the current timestep."""

    def __init__(self, channels_in, channels_out, kernel_size, dilation):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(channels_in, channels_out, kernel_size,
                              dilation=dilation)

    def forward(self, x):
        if self.padding:
            x = nn.functional.pad(x, (self.padding, 0))
        return self.conv(x)


class ChannelLayerNorm(nn.Module):
    """Per-timestep LayerNorm over channels only; preserves causality."""

    def __init__(self, channels):
        super().__init__()
        self.norm = nn.LayerNorm(channels)

    def forward(self, x):
        # x: (batch, channels, time) -> norm over channels at each timestep.
        return self.norm(x.transpose(1, 2)).transpose(1, 2)


class Encoder(nn.Module):
    """Four causal Conv1d blocks with LayerNorm, GELU, and dropout."""

    def __init__(self, latent_channels):
        super().__init__()
        blocks = ARCHITECTURE["blocks"]
        kernel = ARCHITECTURE["kernel_size"]
        channels_in = ARCHITECTURE["channels_in"]
        layers = []
        for index in range(blocks):
            layers.extend((
                CausalConv1d(channels_in, latent_channels, kernel,
                             ARCHITECTURE["dilations"][index]),
                ChannelLayerNorm(latent_channels),
                nn.GELU(),
                nn.Dropout(ARCHITECTURE["dropout"]),
            ))
            channels_in = latent_channels
        self.blocks = nn.Sequential(*layers)

    def forward(self, x):
        return self.blocks(x)


class VelocityNet(nn.Module):
    """Causal encoder, latent projection, linear head to (vx, vy)."""

    def __init__(self, latent_channels, latent_dim, outputs):
        super().__init__()
        self.encoder = Encoder(latent_channels)
        self.latent_projection = nn.Linear(latent_channels, latent_dim)
        self.head = nn.Linear(latent_dim, outputs)

    def encode(self, x):
        """x: (batch, window, channels) -> z: (batch, window, latent_dim)."""
        hidden = self.encoder(x.transpose(1, 2))
        return self.latent_projection(hidden.transpose(1, 2))

    def decode(self, z):
        """z: (batch, window, latent_dim) -> outputs: (batch, window, outputs)."""
        return self.head(nn.functional.gelu(z))

    def forward(self, x, adapter=None):
        """optionally adapt the frozen latent before the frozen head"""
        z = self.encode(x)
        if adapter is not None:
            z = adapter(z)
        return self.decode(z)


def build_encoder(config):
    """Construct the candidate network for a frozen LearnedConfig."""
    torch.manual_seed(config.seed)
    return VelocityNet(config.latent_channels, config.latent_dim,
                      ARCHITECTURE["outputs"])


def parameter_count(module):
    return sum(parameter.numel() for parameter in module.parameters())