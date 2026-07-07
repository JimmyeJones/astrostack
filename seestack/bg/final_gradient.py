"""
Final-stack gradient removal.

Per-frame bg flatten can't remove residual gradients that come from the
shifting overlap of frames at the canvas edges, from imperfect flat-fielding,
or from light-pollution that's structured enough to survive averaging. This
module fits a low-frequency surface to the **non-object** pixels of the
final stack and subtracts it.

Why this is safer than per-frame bg flatten on extended objects:

  - We only have one image to fit, so we can afford a careful object mask
    (sigma-clip + binary dilation) — no time pressure.
  - The mask covers the actual galaxy / nebula / cluster shape, so it can't
    eat into the object. Per-frame mode doesn't know what's an object yet.

Modes mirror the per-frame ones: ``per_channel`` (default) or ``luminance``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_BOX_SIZE = 256
DEFAULT_DETECT_SIGMA = 2.5
DEFAULT_DILATE_PX = 16


@dataclass
class FinalGradientOptions:
    """Knobs for the final-stack gradient pass."""

    enabled: bool = False
    mode: str = "per_channel"        # 'per_channel' | 'luminance'
    box_size: int = DEFAULT_BOX_SIZE
    detect_sigma: float = DEFAULT_DETECT_SIGMA
    dilate_px: int = DEFAULT_DILATE_PX


def remove_final_gradient(
    rgb: np.ndarray,
    options: FinalGradientOptions | None = None,
    *,
    errors: list[str] | None = None,
) -> np.ndarray:
    """
    Subtract a sky-gradient model from the final stack.

    Builds a mask of the bright structure (sigma-clip + dilation), then fits
    a 2D background through the unmasked pixels and subtracts it.

    ``errors`` (opt-in): pass a list to make a fit failure *surface* instead of
    being silently swallowed. The stack path leaves it ``None`` (best-effort:
    skip a failed channel / return the input), which is unchanged. The editor
    passes a collector so a failed Background2D fit reaches the UI rather than
    the op looking like a silent no-op; a per-channel failure is then treated as
    all-or-nothing (no partial subtract that would colour-shift the image).
    """
    if options is None:
        options = FinalGradientOptions(enabled=True)
    if not options.enabled:
        return rgb

    mask = _build_object_mask(rgb, options)

    if options.mode == "luminance":
        return _subtract_luminance_with_mask(rgb, mask, options, errors=errors)
    return _subtract_per_channel_with_mask(rgb, mask, options, errors=errors)


def _build_object_mask(rgb: np.ndarray, options: FinalGradientOptions) -> np.ndarray:
    """
    True where there's a non-sky object (star, galaxy, nebula). The fitter
    will ignore those pixels.
    """
    from astropy.stats import sigma_clipped_stats
    from scipy.ndimage import binary_dilation

    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    # Replace NaN with median so sigma_clipped_stats works.
    finite = np.isfinite(luma)
    if not finite.any():
        return np.zeros(luma.shape, dtype=bool)
    luma_filled = np.where(finite, luma, np.nan)
    _, med, std = sigma_clipped_stats(luma_filled, sigma=3.0, maxiters=5)
    if not np.isfinite(med) or not np.isfinite(std) or std <= 0:
        return ~finite  # mask only NaN pixels if stats failed
    obj_mask = luma > (med + options.detect_sigma * std)
    obj_mask |= ~finite
    if options.dilate_px > 0:
        obj_mask = binary_dilation(obj_mask, iterations=options.dilate_px)
    return obj_mask


# exclude_percentile ladder: how much of a box may be masked before the box is
# dropped. We start at the tuned-for-look 80 and, only if the fit *fails* (every
# box is more masked than that — a dense star field or a very flat frame swells
# the object mask past the threshold), degrade to progressively more tolerant
# fits so a busy field still gets a coarse gradient subtract instead of none. A
# succeeding fit at 80 is untouched, so a normal stack's export is unchanged.
_EXCLUDE_PERCENTILE_LADDER = (80.0, 95.0, 100.0)


def _fit_background_2d(channel: np.ndarray, mask: np.ndarray, box_size: int) -> np.ndarray:
    """
    photutils Background2D respecting an object mask. Returns the fitted
    background as a same-shape array.

    On a busy/dense field the object mask can cover >80% of every box, which
    makes ``Background2D`` raise at the default ``exclude_percentile``. Rather
    than give up (which drops the op entirely and silently loses gradient
    removal on clusters and very-flat frames), we retry with a more tolerant
    ``exclude_percentile`` and, if still failing, a smaller box — degrading to a
    coarse fit instead of none.
    """
    from astropy.stats import SigmaClip
    from photutils.background import Background2D, MMMBackground

    # Make sure the channel has no NaN — photutils' mask handles "ignore",
    # so we can stuff zeros into NaN slots and add them to the mask.
    finite = np.isfinite(channel)
    clean = np.where(finite, channel, 0.0).astype(np.float32, copy=False)
    full_mask = mask | ~finite

    # Clamp the box so the grid always tiles the image. On a full-size stack
    # (≥~1080 px, where a 256 px box already tiles 4×) this is a no-op, so the
    # export result is unchanged; but on a small image a box wider than the
    # frame leaves too few unmasked boxes to survive ``exclude_percentile`` and
    # ``Background2D`` raises. Mirrors ``BackgroundOptions.for_image_size`` on
    # the per-frame path so the gradient op degrades instead of failing.
    h, w = clean.shape[:2]
    box = min(int(box_size), max(8, min(h // 4, w // 4)))
    box = max(1, min(box, h, w))

    # MMMBackground (mode ≈ 2.5·median − 1.5·mean) instead of MedianBackground:
    # the median is biased upward by faint diffuse signal in proportion to how
    # much of each tile lies inside that signal, and that bias varies tile by
    # tile across the mosaic — which re-emerges as visible panel steps after
    # stretching. Mode is robust to it. Matches the per-frame bg path.
    def _fit(fit_box: int, exclude_percentile: float) -> np.ndarray:
        bkg = Background2D(
            clean,
            box_size=(fit_box, fit_box),
            filter_size=(3, 3),
            sigma_clip=SigmaClip(sigma=3.0),
            bkg_estimator=MMMBackground(),
            mask=full_mask,
            exclude_percentile=exclude_percentile,
        )
        return bkg.background.astype(np.float32, copy=False)

    # A smaller box is more likely to catch a pocket of sky between the objects,
    # so pair the half-size box with the most tolerant percentile as a last try.
    half = max(1, min(box // 2, h, w))
    attempts: list[tuple[int, float]] = [(box, p) for p in _EXCLUDE_PERCENTILE_LADDER]
    if half < box:
        attempts.append((half, _EXCLUDE_PERCENTILE_LADDER[-1]))

    last_exc: Exception | None = None
    for fit_box, excl in attempts:
        try:
            return _fit(fit_box, excl)
        except Exception as exc:  # noqa: BLE001 — degrade, then re-raise the last
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def _subtract_per_channel_with_mask(
    rgb: np.ndarray, mask: np.ndarray, options: FinalGradientOptions,
    *, errors: list[str] | None = None,
) -> np.ndarray:
    """Independent fit per channel."""
    out = rgb.astype(np.float32, copy=True)
    for c in range(3):
        try:
            bg = _fit_background_2d(out[..., c], mask, options.box_size)
        except Exception as exc:  # noqa: BLE001 — degenerate cases
            if errors is not None:
                # Editor path: surface the failure and don't apply a partial
                # (per-channel) subtraction that would colour-shift the image.
                errors.append(f"gradient fit failed: {exc}")
                return rgb.astype(np.float32, copy=True)
            log.warning("final gradient fit failed for c=%d: %s; skipping", c, exc)
            continue
        # Only subtract where finite — preserve NaN regions.
        finite = np.isfinite(out[..., c])
        out[..., c] = np.where(finite, out[..., c] - bg, out[..., c])
    return out


def _subtract_luminance_with_mask(
    rgb: np.ndarray, mask: np.ndarray, options: FinalGradientOptions,
    *, errors: list[str] | None = None,
) -> np.ndarray:
    """Fit one gradient on luminance, subtract from all three channels."""
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    try:
        bg_luma = _fit_background_2d(luma, mask, options.box_size)
    except Exception as exc:  # noqa: BLE001
        if errors is not None:
            errors.append(f"luminance gradient fit failed: {exc}")
        log.warning("final luminance gradient fit failed: %s; returning input", exc)
        return rgb
    from astropy.stats import sigma_clipped_stats

    out = rgb.astype(np.float32, copy=True)
    for c in range(3):
        finite = np.isfinite(out[..., c])
        out[..., c] = np.where(finite, out[..., c] - bg_luma, out[..., c])
        # Per-channel level correction so the sky lands near zero in each.
        # Use mode (SExtractor: 2.5·median − 1.5·mean), not median, so faint
        # diffuse signal doesn't pull the zero down by a per-channel-varying
        # amount (which would tint the post-stack background).
        sky_mask = ~mask & finite
        if sky_mask.any():
            sc_mean, sc_med, _ = sigma_clipped_stats(out[..., c][sky_mask], sigma=3.0)
            sky = 2.5 * sc_med - 1.5 * sc_mean if np.isfinite(sc_mean) else sc_med
            if not np.isfinite(sky) or abs(sky - sc_med) > 5.0 * abs(sc_med - sc_mean + 1e-9):
                sky = sc_med
        else:
            sky = 0.0
        out[..., c] = np.where(finite, out[..., c] - float(sky), out[..., c])
    return out
