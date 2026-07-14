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

# LRGB retargets luminance by scaling each pixel by ``L / luminance(rgb)``. That
# ratio is only well-conditioned where the RGB luminance is a real positive
# signal; on a *linear, background-subtracted* stack the sky sits at ~0 ± noise
# (signed), so a raw ``L / cur`` divides by a tiny, arbitrarily-signed number and
# the background explodes into huge, half-sign-flipped colour speckle (the classic
# technique assumes a stretched, positive-pedestal domain). We floor the
# denominator at ``_LUM_FLOOR_SIGMA`` times the RGB luminance's own robust
# sky-noise scale so a near-zero/negative background pixel gets a bounded, positive
# scale (background stays near-neutral and quiet) while any pixel with real signal
# above the noise (``cur`` well above the floor) is scaled exactly as before.
_LUM_FLOOR_SIGMA = 3.0
_LUM_FLOOR_MIN = 1e-6


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

    if "L" not in channels:
        # A pixel that is NaN in *any supplied* colour channel is uncovered there,
        # so its colour is undefined — mark it NaN across all three channels rather
        # than leaving a hard 0 in the missing channel(s), which renders as a
        # saturated colour speck (a cyan/magenta fringe) instead of an uncovered
        # pixel. This mirrors the LRGB branch below (``scale = np.where(isnan(cur),
        # nan, scale)``) and keeps the "NaN = no coverage" invariant clean at
        # mosaic/RGB seams where per-filter footprints differ. A wholly-absent
        # channel (never supplied — an intentional 0 for a bicolour SHO map) keeps
        # its 0 wherever the supplied channels all cover the pixel.
        supplied_idx = [i for i, c in enumerate(("R", "G", "B")) if c in channels]
        nan_any = np.zeros((h, wid), dtype=bool)
        for i in supplied_idx:
            nan_any |= np.isnan(rgb[..., i])
        if nan_any.any():
            rgb[nan_any, :] = np.nan

    if "L" in channels:
        # LRGB: keep RGB's colour ratios but set the luminance to L.
        lum_target = channels["L"] * w("L")
        cur = luminance(rgb)
        # Floor the divisor at a robust multiple of the RGB luminance's own
        # sky-noise scale so a near-zero/negative background pixel can't blow up or
        # flip sign (see ``_LUM_FLOOR_SIGMA``). Real signal has ``cur`` well above
        # the floor, so it is divided by ``cur`` unchanged; the floor only bites in
        # the noise-dominated background. Robust MAD over the covered pixels, which
        # on a background-dominated stack anchors to the sky.
        finite = cur[np.isfinite(cur)]
        if finite.size:
            med = float(np.median(finite))
            sky_sigma = 1.4826 * float(np.median(np.abs(finite - med)))
        else:
            sky_sigma = 0.0
        floor = max(_LUM_FLOOR_SIGMA * sky_sigma, _LUM_FLOOR_MIN)
        with np.errstate(invalid="ignore", divide="ignore"):
            scale = lum_target / np.maximum(cur, floor)
        # A pixel whose RGB luminance is NaN is uncovered in at least one colour
        # channel — its colour is undefined, so mark it fully uncovered (NaN)
        # rather than zeroing-out the channels that *were* covered. This keeps the
        # "NaN = no coverage" invariant clean at mosaic edges where per-filter
        # footprints differ. (``np.maximum`` already propagates the NaN into
        # ``scale``; this makes the intent explicit and covers a NaN ``lum_target``
        # over a covered pixel too.)
        scale = np.where(np.isnan(cur), np.nan, scale)
        rgb = rgb * scale[..., None]

    return rgb.astype(np.float32, copy=False)
