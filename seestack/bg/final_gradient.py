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

# Degree of the robust polynomial used to *detrend before detecting* objects, and
# to model each channel's residual colour gradient. Two is the sweet spot: it
# follows the smooth, frame-scale shape light pollution actually has, yet cannot
# bend into a localised galaxy/nebula the way a per-channel Background2D mesh can
# (that mesh-eats-the-nebula failure is exactly why `luminance` is the default).
_POLY_DEG = 2
# The surface is fitted to a coarse grid of per-tile sky *medians* rather than to
# raw pixels. A median is unbiased however many of a tile's pixels the object mask
# removed, whereas least-squares over raw pixels with outlier clipping is not:
# clipping bites harder where the mask is denser, which bends a spurious few-ADU
# surface out of a frame that has no gradient at all (measured). It is also much
# cheaper — ~600 samples instead of millions — so it runs on every preview render.
_POLY_TILES = 24
# A tile needs this fraction of its pixels to be unmasked sky before its median is
# trusted as a sample; otherwise the tile is dropped from the fit.
_POLY_TILE_MIN_FRAC = 0.25
# Smallest detection (full-res px) taken seriously as an object. A real point
# source spans several pixels once the seeing is ~2 px FWHM, while a single-pixel
# spike is noise — and dilating those by dilate_px is what used to swell the mask
# over most of the frame (a 2.5-sigma threshold flags ~0.6 % of pixels *anywhere*,
# and each grows to ~800 px at the default 16 px dilation). Mirrors the classic
# source-extraction minimum detection area.
_MIN_DETECT_AREA = 4
# Smoothing scale (full-res px) for the faint-extended-structure detection pass.
_EXT_SMOOTH_PX = 4.0
# Floor on the extended pass's threshold, as a fraction of the *unsmoothed* sky
# noise. Smoothing shrinks the noise ~10x, so a pure sigma threshold on the
# smoothed frame would flag any small trend-fit residual as "object" and mask the
# sky away again. The floor keeps the pass to genuinely-above-the-grain structure.
_EXT_NOISE_FLOOR = 1.0


@dataclass
class FinalGradientOptions:
    """Knobs for the final-stack gradient pass."""

    enabled: bool = False
    mode: str = "per_channel"        # 'per_channel' | 'luminance'
    box_size: int = DEFAULT_BOX_SIZE
    detect_sigma: float = DEFAULT_DETECT_SIGMA
    dilate_px: int = DEFAULT_DILATE_PX
    # 'luminance' mode only: after subtracting the shared luminance model, also
    # subtract each channel's own *low-order* residual gradient, so light
    # pollution can't leave a spatial colour split across the frame (see
    # _subtract_luminance_with_mask). Default on — it's a correctness fix; set it
    # False for the historical brightness-only behaviour.
    match_channels: bool = True
    # full_w / render_w for a decimated live-preview proxy (1.0 on the export).
    # Full-res pixel measures derived internally (the extended-structure
    # smoothing scale) are divided by it so the preview and the export detect
    # objects at the same *physical* scale — exactly what the caller already does
    # for box_size and dilate_px.
    proxy_scale: float = 1.0


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


def _poly_design(ys: np.ndarray, xs: np.ndarray, deg: int) -> np.ndarray:
    """Design matrix for a 2D polynomial of degree ``deg`` in normalised coords."""
    terms = [np.ones_like(xs)]
    for d in range(1, deg + 1):
        for k in range(d + 1):
            terms.append((xs ** (d - k)) * (ys ** k))
    return np.stack(terms, axis=-1)


def _tile_medians(
    plane: np.ndarray, include: np.ndarray, tiles: int = _POLY_TILES,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Coarse grid of robust sky samples: ``(ys, xs, values)`` in normalised
    ``[-0.5, 0.5]`` coordinates, one entry per tile that held enough sky.
    """
    h, w = plane.shape[:2]
    ny = max(2, min(tiles, h))
    nx = max(2, min(tiles, w))
    y_edges = np.linspace(0, h, ny + 1).astype(int)
    x_edges = np.linspace(0, w, nx + 1).astype(int)
    ys: list[float] = []
    xs: list[float] = []
    vals: list[float] = []
    for iy in range(ny):
        y0, y1 = y_edges[iy], y_edges[iy + 1]
        if y1 <= y0:
            continue
        for ix in range(nx):
            x0, x1 = x_edges[ix], x_edges[ix + 1]
            if x1 <= x0:
                continue
            cell = plane[y0:y1, x0:x1]
            ok = include[y0:y1, x0:x1] & np.isfinite(cell)
            n_ok = int(ok.sum())
            if n_ok < max(8, int(_POLY_TILE_MIN_FRAC * cell.size)):
                continue
            ys.append((y0 + y1) * 0.5 / max(h - 1, 1) - 0.5)
            xs.append((x0 + x1) * 0.5 / max(w - 1, 1) - 0.5)
            vals.append(float(np.median(cell[ok])))
    return (np.asarray(ys, dtype=np.float64),
            np.asarray(xs, dtype=np.float64),
            np.asarray(vals, dtype=np.float64))


def _fit_sky_poly(
    plane: np.ndarray,
    include: np.ndarray | None = None,
    *,
    deg: int = _POLY_DEG,
    iters: int = 3,
) -> np.ndarray | None:
    """
    Robust low-order polynomial surface through the *sky* of a 2D plane.

    ``include`` (optional) restricts the samples to those pixels (the sky mask).
    The solve runs over per-tile medians (see :func:`_tile_medians`), then rejects
    tiles whose residual is a high outlier — nebulosity the mask missed — and
    re-solves, so a faint object cannot drag the surface up around it.

    Returns ``None`` when there is too little sky to fit, so callers can skip
    the pass rather than subtract a garbage surface.
    """
    h, w = plane.shape[:2]
    if include is None:
        include = np.ones((h, w), dtype=bool)
    ys, xs, vals = _tile_medians(plane, include)
    n_terms = (deg + 1) * (deg + 2) // 2
    if vals.size < n_terms * 4:
        return None
    design = _poly_design(ys, xs, deg)
    keep = np.ones(vals.shape, dtype=bool)
    coef = None
    for _ in range(iters):
        if int(keep.sum()) < n_terms * 4:
            break
        coef, *_ = np.linalg.lstsq(design[keep], vals[keep], rcond=None)
        resid = vals - design @ coef
        kept = resid[keep]
        sigma = 1.4826 * float(np.median(np.abs(kept - np.median(kept))))
        if not np.isfinite(sigma) or sigma <= 0.0:
            break
        keep = (resid < 2.5 * sigma) & (resid > -3.0 * sigma)
    if coef is None:
        return None
    yy, xx = np.mgrid[0:h, 0:w]
    full = _poly_design((yy / max(h - 1, 1) - 0.5).ravel().astype(np.float64),
                        (xx / max(w - 1, 1) - 0.5).ravel().astype(np.float64), deg)
    return (full @ coef).reshape(h, w).astype(np.float32)


def _build_object_mask(rgb: np.ndarray, options: FinalGradientOptions) -> np.ndarray:
    """
    True where there's a non-sky object (star, galaxy, nebula). The fitter
    will ignore those pixels.

    Detection is done on the luminance **detrended by a robust low-order
    polynomial**, not against the whole-frame median. That matters a lot: with a
    single global threshold, a frame that still carries an ordinary
    light-pollution gradient reads its whole *bright half* as "object" (measured
    on a realistic S30 scene: 5 % of the dim fifth masked vs 66 % of the bright
    fifth), which starves ``Background2D`` of sky exactly where the gradient is —
    so the gradient pass could only remove ~10 % of the tilt it was there to
    remove. A low-order trend follows light pollution but cannot bend into a
    galaxy or nebula, so subtracting it before thresholding makes the threshold
    *local* without hiding real objects.

    Detections smaller than ``_MIN_DETECT_AREA`` are then dropped, because a
    Nsigma threshold flags ~0.6 % of pixels *wherever* you put it and dilating
    those single-pixel noise spikes by ``dilate_px`` is what swells the mask over
    most of the frame — the same starvation by a different route.

    A second pass detects faint **extended** structure on a smoothed copy (grain
    averages down, a diffuse nebula doesn't), so the fitter's mask covers the
    outer nebulosity a per-pixel threshold misses — the thing that would
    otherwise get quietly absorbed into the "sky" model.
    """
    from astropy.stats import sigma_clipped_stats
    from scipy.ndimage import binary_dilation, gaussian_filter, label

    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    # Normalise every non-finite pixel (NaN *or* inf) to NaN; sigma_clipped_stats
    # auto-clips NaN, so the stats below are computed over the finite sky only.
    finite = np.isfinite(luma)
    if not finite.any():
        return np.zeros(luma.shape, dtype=bool)
    luma_filled = np.where(finite, luma, np.nan)
    trend = _fit_sky_poly(luma_filled)
    resid = luma_filled if trend is None else luma_filled - trend
    _, med, std = sigma_clipped_stats(resid, sigma=3.0, maxiters=5)
    if not np.isfinite(med) or not np.isfinite(std) or std <= 0:
        return ~finite  # mask only NaN pixels if stats failed
    obj_mask = np.where(finite, resid, -np.inf) > (med + options.detect_sigma * std)

    # Drop noise-sized detections. The area is a full-res pixel measure, so it
    # shrinks with the proxy's decimation (a star covers proxy_scale**2 fewer
    # pixels there) — keeping preview and export detecting the same objects.
    scale = max(float(options.proxy_scale), 1e-3)
    min_area = max(1, int(round(_MIN_DETECT_AREA / (scale * scale))))
    if min_area > 1:
        labels, n_found = label(obj_mask)
        if n_found:
            big_enough = np.bincount(labels.ravel()) >= min_area
            big_enough[0] = False           # label 0 is the background
            obj_mask = big_enough[labels]

    # Faint-extended pass. NaN-aware smoothing (normalised convolution) so a
    # mosaic gap doesn't drag its neighbourhood down and mask a false halo.
    smooth_px = max(0.8, _EXT_SMOOTH_PX / scale)
    weight = finite.astype(np.float32)
    num = gaussian_filter(np.where(finite, resid - med, 0.0).astype(np.float32),
                          smooth_px, mode="nearest")
    den = gaussian_filter(weight, smooth_px, mode="nearest")
    smoothed = np.where(den > 1e-3, num / np.maximum(den, 1e-6), 0.0)
    _, ext_med, ext_std = sigma_clipped_stats(
        np.where(finite, smoothed, np.nan), sigma=3.0, maxiters=5)
    if np.isfinite(ext_med) and np.isfinite(ext_std) and ext_std > 0:
        threshold = ext_med + max(options.detect_sigma * ext_std,
                                  _EXT_NOISE_FLOOR * std)
        obj_mask |= np.where(finite, smoothed, -np.inf) > threshold

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
    """
    Fit one gradient on luminance, subtract from all three channels.

    One shared model keeps a localised object safe (a per-channel mesh fit
    interpolates the masked object hole differently in each channel and can
    erase a faint nebula outright), but on its own it leaves a **colour** split
    across the frame: light-pollution gradient amplitude scales with each
    channel's own sky level, so one luminance-weighted model plus a per-channel
    *constant* cannot flatten all three. Measured on a realistic S30 scene with
    an 18 % LP gradient, the finished one-click picture came out magenta down one
    side (−15 % green) and green down the other (+11 %), because the per-channel
    STF stretch then maps any residual spatial tilt into diverging colour.

    So when ``match_channels`` is on (the default), each channel **first** has
    its own low-order polynomial sky surface removed, and only then does the
    shared mesh model mop up what is left. Degree two follows the frame-scale LP
    shape while being far too stiff to bend into a galaxy or nebula, so it keeps
    the shared model's safety; and because it runs on the *original* data (where
    the real gradient dominates) rather than on the mesh's leftovers, a frame
    with no gradient to remove gets a surface of essentially zero amplitude
    instead of one that chases mesh noise into a new colour cast.

    Measured on a realistic 12-sub S30 scene, one-click Auto end to end:

    ==================  ====================  ====================
    18 % LP gradient    before                after
    ==================  ====================  ====================
    sky cast left       −15.3 %               −2.4 %
    sky cast right      +11.2 %               +1.9 %
    luminance tilt      +103 % of sky         +34 % of sky
    nebula core chroma  0.56                  0.62
    ==================  ====================  ====================
    """
    out = rgb.astype(np.float32, copy=True)
    if options.match_channels:
        # Each channel's own frame-scale sky shape — the colour half of the
        # gradient — taken off before the shared model, so the shared model then
        # only ever removes brightness that all three have in common.
        for c in range(3):
            finite = np.isfinite(out[..., c])
            surface = _fit_sky_poly(out[..., c], ~mask & finite)
            if surface is not None:
                out[..., c] = np.where(finite, out[..., c] - surface, out[..., c])

    luma = 0.299 * out[..., 0] + 0.587 * out[..., 1] + 0.114 * out[..., 2]
    try:
        bg_luma = _fit_background_2d(luma, mask, options.box_size)
    except Exception as exc:  # noqa: BLE001
        if errors is not None:
            errors.append(f"luminance gradient fit failed: {exc}")
        log.warning("final luminance gradient fit failed: %s; returning input", exc)
        return rgb
    from astropy.stats import sigma_clipped_stats

    for c in range(3):
        finite = np.isfinite(out[..., c])
        out[..., c] = np.where(finite, out[..., c] - bg_luma, out[..., c])
        # Per-channel level correction so the sky lands near zero in each.
        # Use mode (SExtractor: 2.5·median − 1.5·mean), not median, so faint
        # diffuse signal doesn't pull the zero down by a per-channel-varying
        # amount (which would tint the post-stack background).
        sky_mask = ~mask & finite
        if sky_mask.any():
            sc_mean, sc_med, sc_std = sigma_clipped_stats(out[..., c][sky_mask], sigma=3.0)
            sky = 2.5 * sc_med - 1.5 * sc_mean if np.isfinite(sc_mean) else sc_med
            # Fall back to the median when the skew is too extreme to trust the
            # mode (SExtractor criterion: mean−median within 0.3·σ). The earlier
            # `abs(sky−med) > 5·abs(med−mean)` test was algebraically inert
            # (`sky−med` == `1.5·(med−mean)`, so `1.5·X > 5·X` never fired).
            if (not np.isfinite(sky)
                    or (np.isfinite(sc_std) and sc_std > 0.0
                        and abs(sc_mean - sc_med) > 0.3 * sc_std)):
                sky = sc_med
        else:
            sky = 0.0
        out[..., c] = np.where(finite, out[..., c] - float(sky), out[..., c])
    return out
