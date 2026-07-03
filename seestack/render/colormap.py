"""Small, dependency-free colour maps for turning a normalized scalar field
(0..1) into an RGB image — used to render diagnostic overlays (e.g. the editor's
frame-coverage map) as a legible heatmap instead of an ambiguous grayscale.

Kept in the pure engine (no webapp/Qt imports) so it's reusable and testable.
"""

from __future__ import annotations

import numpy as np

# Anchor points of the perceptually-uniform "viridis" map (matplotlib), sampled
# at 0.0, 0.1, … 1.0. Dark blue/purple = low, yellow = high. Reproduced here so
# we don't take a matplotlib dependency just for a LUT.
_VIRIDIS_ANCHORS = np.array(
    [
        [68, 1, 84],
        [72, 40, 120],
        [62, 74, 137],
        [49, 104, 142],
        [38, 130, 142],
        [31, 158, 137],
        [53, 183, 121],
        [110, 206, 88],
        [181, 222, 43],
        [253, 231, 37],
        [253, 231, 37],
    ],
    dtype=np.float64,
)


def viridis_lut() -> np.ndarray:
    """A ``(256, 3)`` uint8 viridis lookup table (index 0 = low, 255 = high)."""
    grid = np.linspace(0.0, 1.0, 256)
    anchors_x = np.linspace(0.0, 1.0, len(_VIRIDIS_ANCHORS))
    rgb = np.stack(
        [np.interp(grid, anchors_x, _VIRIDIS_ANCHORS[:, c]) for c in range(3)],
        axis=1,
    )
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def apply_viridis(norm: np.ndarray) -> np.ndarray:
    """Map a normalized ``[0, 1]`` array to an ``(H, W, 3)`` uint8 viridis RGB
    image. Values are clipped into range; non-finite entries map to the low end."""
    lut = viridis_lut()
    clipped = np.clip(np.nan_to_num(norm, nan=0.0), 0.0, 1.0)
    idx = np.rint(clipped * 255).astype(np.intp)
    return lut[idx]
