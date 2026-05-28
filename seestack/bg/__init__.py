"""Background flattening (per-frame and post-stack)."""

from seestack.bg.final_gradient import FinalGradientOptions, remove_final_gradient
from seestack.bg.hot_pixels import suppress_hot_cold_pixels
from seestack.bg.per_frame import BackgroundOptions, subtract_background

__all__ = [
    "BackgroundOptions",
    "FinalGradientOptions",
    "remove_final_gradient",
    "subtract_background",
    "suppress_hot_cold_pixels",
]
