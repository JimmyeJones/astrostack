"""Combine several mono/luminance stacks into one colour image (LRGB / RGB).

Mono workflows produce one stack per filter (L, R, G, B, or narrowband mapped to
channels). This combines them:

* **RGB** — assign a stack to each of R/G/B; the result is a colour image.
* **LRGB** — additionally supply a luminance (L) stack; the RGB provides the
  colour and L replaces the luminance, the classic high-SNR-detail technique.
* **L only** — a single luminance stack → a grayscale image.

All inputs must share the same pixel grid (same canvas/shape). Per-channel
weights let you balance exposure differences between filters. NaN (uncovered)
pixels are preserved.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import luminance

CHANNELS = ("L", "R", "G", "B")


def combine_channels(
    channels: dict[str, np.ndarray],
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    """Combine per-channel 2-D arrays into an ``(H, W, 3)`` float32 RGB image.

    ``channels`` maps any of ``L/R/G/B`` to a 2-D array; all must be the same
    shape. ``weights`` optionally scales each channel (default 1.0).
    """
    if not channels:
        raise ValueError("no channels supplied")
    weights = weights or {}
    arrays = list(channels.values())
    ref = arrays[0].shape
    for name, arr in channels.items():
        if arr.ndim != 2:
            raise ValueError(f"channel {name} must be 2-D, got shape {arr.shape}")
        if arr.shape != ref:
            raise ValueError(
                f"channel {name} is {arr.shape[1]}×{arr.shape[0]} but the first "
                f"channel is {ref[1]}×{ref[0]} — all stacks must share the same "
                f"canvas. Stack them on a common reference first."
            )

    def w(name: str) -> float:
        return float(weights.get(name, 1.0))

    h, wid = ref
    has_color = any(c in channels for c in ("R", "G", "B"))

    if not has_color:
        # Luminance-only → grayscale.
        lum = channels["L"] * w("L")
        return np.repeat(lum[..., None], 3, axis=2).astype(np.float32, copy=False)

    rgb = np.zeros((h, wid, 3), dtype=np.float32)
    # Missing colour channels stay 0 (e.g. a bicolour SHO map without one band).
    if "R" in channels:
        rgb[..., 0] = channels["R"] * w("R")
    if "G" in channels:
        rgb[..., 1] = channels["G"] * w("G")
    if "B" in channels:
        rgb[..., 2] = channels["B"] * w("B")

    if "L" in channels:
        # LRGB: keep RGB's colour ratios but set the luminance to L.
        lum_target = channels["L"] * w("L")
        cur = luminance(rgb)
        with np.errstate(invalid="ignore", divide="ignore"):
            scale = np.where(np.abs(cur) > 1e-6, lum_target / cur, 0.0)
        rgb = rgb * scale[..., None]

    return rgb.astype(np.float32, copy=False)
