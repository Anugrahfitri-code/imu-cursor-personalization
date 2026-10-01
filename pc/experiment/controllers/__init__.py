"""Stage 2.6 offline affine-controller candidates (not participant release)."""

from .config import AffineConfig
from .controller import AffineController
from .fitting import fit_p2c

__all__ = ["AffineConfig", "AffineController", "fit_p2c"]
