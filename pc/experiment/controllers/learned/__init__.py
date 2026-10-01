"""Stage 2.7 learned candidates (L0/L2C); not a participant release."""

from .adapter import LatentAffineAdapter
from .config import (ADAPTER_USER_PARAMETERS, CAPACITIES, LATENT_DIMS,
                     MAX_USER_PARAMETERS, WINDOWS, LearnedConfig)
from .l2c_policy import load_l2c_policy
from .network import build_encoder, parameter_count
from .controller import LearnedController

__all__ = ["LearnedConfig", "CAPACITIES", "WINDOWS", "LATENT_DIMS",
           "ADAPTER_USER_PARAMETERS", "MAX_USER_PARAMETERS",
           "LatentAffineAdapter", "load_l2c_policy",
           "build_encoder", "parameter_count", "LearnedController"]