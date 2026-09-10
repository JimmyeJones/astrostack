"""Cross-panel gain matching for a mosaic, measured **in the overlaps**.

A mosaic's panels are shot on different nights through different air. Thin haze
dims a panel's *signal* multiplicatively while leaving its sky where it is, so
neither of the corrections that already run automatically can touch it: the
per-frame background flatten and ``bg.coverage_leveling`` both remove *additive*
sky offsets. The result is a tile of the finished picture that is uniformly
dimmer than its neighbours, with a step along the join — the panel grid this app
exists to avoid.

:mod:`seestack.stack.photometric` cannot fix it either, and deliberately does not
try. It gain-matches each sub against **its own panel's** median transparency
(``group_by_pointing``), so a panel whose subs are *all* hazy is its own
reference and comes out unchanged. That restraint is not an oversight: prior to
v0.276.0 the pass compared panels against each other by ``transparency_score``,
which is the median flux of a frame's brightest stars and therefore measures
*where the scope pointed* as much as the sky it looked through. On two
identically-exposed panels whose only difference was their star fields that
manufactured a **2.23× relative panel gain error** —
:func:`seestack.stack.photometric._pointing_references` carries the measurement.
``transparency_score`` cannot tell "hazy panel" from "emptier patch of sky", and
it never will.

**The signal that can: the overlap.** Adjacent Seestar mosaic panels overlap, and
in the overlap both panels image *the same sky* — the same stars, the same
nebulosity. The ratio of sky-subtracted signal there, panel A over panel B, is an
honest, pointing-independent gain ratio: whatever is in that strip contributes to
both sides of the fraction. That is the one comparison between panels this engine
can make soundly, so it is the only one this module makes.

How it works, as a cheap pre-pass rather than a change to the accumulate:

  1. Take each panel's **clearest few** subs (by ``transparency_score`` *within*
     the panel — the comparison v0.276.0 established is sound) and run each
     through :func:`seestack.stack.align.align_one` onto the run's own canvas
     WCS, so the pre-pass sees exactly the calibrated, debayered,
     background-flattened pixels the stack will.
  2. Block-mean each aligned window into a coarse per-panel luminance map
     (:data:`_TARGET_LONG_EDGE_PX`, so a nine-panel canvas costs tens of MB, not
     gigabytes — the stack's memory bound is not this pass's to spend). Block
     means, not a coarse reprojection: a star sampled at a coarse grid point is
     a lottery, a star *averaged* into a coarse cell is a measurement.
  3. For each pair of panels sharing enough coarse pixels, check the strip
     really is the same sky — overlapping *footprints* only mean two WCS
     solutions agree, and a mis-solved panel claims a patch it never pointed at.
     Correlation settles it, and is blind to gain, which is precisely the thing
     being measured. Then subtract each side's own robust sky, keep the pixels
     carrying real signal on **both** sides, and take the median per-pixel ratio.
  4. Solve one log-scale per panel by least squares over that pair graph,
     normalise so the median panel scale is 1.0 (the picture's overall brightness
     does not move), and clamp.

**Fail neutral, never fail guessy.** A wrong cross-panel gain *is* the failure
this pass exists to prevent, so every uncertainty resolves to "change nothing":
a pair with too little shared signal is dropped, a pair whose strip doesn't
correlate is dropped (that is not shared sky), a pair whose ratio is outside the
clamp is dropped (a panel is not credibly 5× its neighbour), a panel that loses
every pair keeps 1.0, a pair that disagrees with the rest of the fit is dropped
and the rest re-fitted, a graph that only agrees once nothing is left to disagree
with stands the whole pass down, and any exception returns ``None`` — which the stacker reads as "apply nothing", i.e.
today's behaviour byte for byte.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np

from seestack.io.project import FrameRow, readable_frame_path

log = logging.getLogger(__name__)

# The coarse grid the overlaps are measured on. Chosen so the per-panel maps stay
# tens of MB on the owner's real canvases (a 3494×2470 nine-panel mosaic folds to
# ~400×283 per panel, i.e. ~1 MB each) while still leaving thousands of cells in
# a typical 20 % overlap strip to take a median over.
_TARGET_LONG_EDGE_PX = 400

# Frames per panel fed through the aligner. The overlap ratio is a median over
# many cells, so a handful of subs is plenty to average the read noise down; each
# extra one costs a full frame load + reproject at stack setup.
MAX_FRAMES_PER_PANEL = 5

# A pair needs this many coarse cells covered by both panels before its ratio is
# worth believing, and this many of *those* carrying signal above the sky.
MIN_SHARED_CELLS = 40
MIN_SIGNAL_CELLS = 12

# How far above a panel's own sky noise a cell must sit to count as signal. The
# ratio of two sky cells is a ratio of two noise samples and tells us nothing, so
# only stars and nebulosity vote.
SIGNAL_SIGMA = 4.0

# How strongly the two panels' structure must correlate across the strip they
# share before the strip is believed to be the *same sky*. Correlation is blind
# to gain (that is the whole point — it is the gain we are trying to measure),
# so genuinely shared sky scores near 1 however different the two panels'
# brightness is, and two unrelated star fields score near 0. 0.5 leaves a wide
# margin on both sides.
MIN_OVERLAP_CORRELATION = 0.5

# Bounds on any one panel's scale, and on a single pair's measured ratio. A panel
# that measures as 5× its neighbour is a broken measurement, not a hazy night.
MAX_PANEL_RATIO = 2.0

# The fit is over-determined once the panels form a loop (a 2×2 mosaic gives four
# pairs for four unknowns), so its residual is a free consistency check: if the
# pairs disagree by more than this in the ratio, the measurement is not
# describing a single per-panel gain and the whole pass stands down.
MAX_FIT_RESIDUAL_RATIO = 1.25


@dataclass
class OverlapGainStats:
    """What the pass did, for the stack log and the FITS provenance."""

    n_panels: int          # panels that got a measured scale (≠ 1.0 possible)
    n_pairs: int           # panel pairs whose overlap yielded a usable ratio
    min_scale: float
    max_scale: float


def _downsample_factor(shape: tuple[int, int]) -> int:
    """Block size that folds ``shape`` to about :data:`_TARGET_LONG_EDGE_PX`."""
    long_edge = max(int(shape[0]), int(shape[1]))
    return max(1, int(round(long_edge / float(_TARGET_LONG_EDGE_PX))))


def _block_reduce_into(sums: np.ndarray, counts: np.ndarray,
                       window: np.ndarray, y0: int, x0: int, ds: int) -> None:
    """Block-mean ``window`` (a canvas-space luminance patch at full resolution,
    NaN where uncovered) into the coarse ``sums``/``counts`` accumulators.

    The window's corner is wherever the frame landed, so it is padded out to the
    surrounding block boundaries with NaN before the reshape — cheap (one array
    the size of the window) and exact, since NaN contributes to neither sum nor
    count.
    """
    wh, ww = window.shape[:2]
    ly0, lx0 = y0 // ds, x0 // ds
    ly1 = min(counts.shape[0], -(-(y0 + wh) // ds))
    lx1 = min(counts.shape[1], -(-(x0 + ww) // ds))
    if ly1 <= ly0 or lx1 <= lx0:
        return
    pad = np.full(((ly1 - ly0) * ds, (lx1 - lx0) * ds), np.nan, dtype=np.float32)
    # The slice of the window that lands inside the padded block region.
    ph, pw = pad.shape
    oy, ox = y0 - ly0 * ds, x0 - lx0 * ds
    take_h, take_w = min(wh, ph - oy), min(ww, pw - ox)
    if take_h <= 0 or take_w <= 0:
        return
    pad[oy:oy + take_h, ox:ox + take_w] = window[:take_h, :take_w]
    blocks = pad.reshape(ly1 - ly0, ds, lx1 - lx0, ds)
    finite = np.isfinite(blocks)
    sums[ly0:ly1, lx0:lx1] += np.where(finite, blocks, 0.0).sum(
        axis=(1, 3), dtype=np.float64)
    counts[ly0:ly1, lx0:lx1] += finite.sum(axis=(1, 3), dtype=np.int32)


def _panel_frames(frames: list[FrameRow], limit: int) -> list[FrameRow]:
    """This panel's clearest few solved, readable subs.

    Ranked by ``transparency_score`` *within the panel*, which is the comparison
    v0.276.0 established is sound (same patch of sky, so the score is measuring
    the air and not the star field). A sub with no score sorts last rather than
    being excluded — a panel whose subs were never QC'd still deserves a
    measurement.
    """
    scored = [f for f in frames if f.wcs_json and readable_frame_path(f)]
    scored.sort(
        key=lambda f: (
            f.transparency_score is None,
            -(f.transparency_score or 0.0),
            f.id or 0,
        ))
    return scored[:max(1, int(limit))]


def _panel_map(
    frames: list[FrameRow],
    *,
    canvas_wcs_text: str,
    canvas_shape: tuple[int, int],
    coarse_shape: tuple[int, int],
    ds: int,
    align_frame,  # noqa: ANN001 — injected aligner, see compute_overlap_gain_scales
) -> tuple[np.ndarray, np.ndarray] | None:
    """One panel's coarse luminance map and its per-cell contributing counts.

    Each sub is aligned onto the **full** canvas — ``align_one`` windows it to
    its own footprint, so this costs one frame-sized array at a time, never a
    canvas-sized one — and folded down here. Reprojecting straight onto a coarse
    grid would be cheaper and wrong: a star landing between two coarse sample
    points is a lottery whose outcome differs per panel, which is noise injected
    into exactly the pixels the ratio is taken from.
    """
    sums = np.zeros(coarse_shape, dtype=np.float64)
    counts = np.zeros(coarse_shape, dtype=np.int32)
    n_aligned = 0
    for frame in frames:
        result = align_frame(frame, canvas_wcs_text, canvas_shape)
        if result is None:
            continue
        window, _valid, y0, x0 = result
        # A frame's window is NaN outside its own footprint, so whole rows of it
        # are all-NaN — the ordinary "no coverage" case, not a problem to warn
        # about once per row.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            lum = (np.nanmean(window, axis=2) if window.ndim == 3
                   else np.asarray(window, dtype=np.float32))
        _block_reduce_into(sums, counts, np.asarray(lum, dtype=np.float32),
                           int(y0), int(x0), ds)
        n_aligned += 1
        del window, lum
    if n_aligned == 0:
        return None
    return sums, counts


def _sky_and_sigma(values: np.ndarray) -> tuple[float, float]:
    """Robust sky level and its noise, from a panel's covered cells."""
    sky = float(np.median(values))
    mad = float(np.median(np.abs(values - sky)))
    return sky, mad * 1.4826


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation of two cell samples; 0.0 when either is flat."""
    if a.size < 2:
        return 0.0
    da, db = a - a.mean(), b - b.mean()
    denom = float(np.sqrt(float(da @ da) * float(db @ db)))
    if not np.isfinite(denom) or denom <= 0:
        return 0.0
    value = float(da @ db) / denom
    return value if np.isfinite(value) else 0.0


def _pair_ratio(lum_a: np.ndarray, cov_a: np.ndarray,
                lum_b: np.ndarray, cov_b: np.ndarray) -> float | None:
    """Median signal ratio A/B over the cells both panels cover, or ``None``.

    Each side's own sky is removed first (the aligner has already flattened each
    frame, so this is a small residual), and only cells carrying real signal on
    **both** sides vote: the ratio of two sky cells is a ratio of two noise
    samples, and averaging thousands of those in would pull every panel toward
    a meaningless 1.0 exactly when there is something to correct.
    """
    shared = cov_a & cov_b
    if int(shared.sum()) < MIN_SHARED_CELLS:
        return None
    sky_a, sigma_a = _sky_and_sigma(lum_a[cov_a])
    sky_b, sigma_b = _sky_and_sigma(lum_b[cov_b])
    sig_a = lum_a - sky_a
    sig_b = lum_b - sky_b
    bright_a = sig_a > SIGNAL_SIGMA * max(sigma_a, 1e-12)
    bright_b = sig_b > SIGNAL_SIGMA * max(sigma_b, 1e-12)

    # Prove the two panels really are looking at the same sky before believing
    # anything the strip says. Overlapping *footprints* only mean the two WCS
    # solutions claim the same patch — a mis-solved panel lands its stars
    # somewhere else entirely, and then the "shared" cells hold two unrelated
    # star fields whose median ratio is a number with no meaning behind it (a
    # fixture built that way measured a 2.6× gain between two equally-exposed
    # panels). Real shared sky correlates strongly whatever the gain difference
    # is, because a gain is exactly what a correlation is blind to.
    seen = shared & (bright_a | bright_b)
    if int(seen.sum()) < MIN_SIGNAL_CELLS:
        return None
    correlation = _correlation(sig_a[seen], sig_b[seen])
    if correlation < MIN_OVERLAP_CORRELATION:
        log.info(
            "Overlap panel gain: the shared strip's structure only correlates "
            "%.2f between the two panels — not the same sky, pair dropped",
            correlation)
        return None

    signal = shared & bright_a & bright_b
    if int(signal.sum()) < MIN_SIGNAL_CELLS:
        return None
    ratios = sig_a[signal] / sig_b[signal]
    ratios = ratios[np.isfinite(ratios) & (ratios > 0)]
    if ratios.size < MIN_SIGNAL_CELLS:
        return None
    return float(np.median(ratios))


def _solve_once(labels: list[int], pairs: dict[tuple[int, int], float],
                ) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int]]]:
    """Least-squares per-panel log scale, its residuals, and the pair order.

    One equation per pair: ``x_a - x_b = -log(g_ab)``, since a panel measured
    ``g_ab`` times brighter than its neighbour must be scaled *down* by that much
    to meet it. ``lstsq``'s minimum-norm solution fixes the otherwise-free gauge
    per connected component, so a panel that shares an overlap with nobody comes
    back at 0 (scale 1.0) instead of dragging the rest of the mosaic with it.
    """
    index = {label: i for i, label in enumerate(labels)}
    keys = sorted(pairs)
    design = np.zeros((len(keys), len(labels)), dtype=np.float64)
    rhs = np.zeros(len(keys), dtype=np.float64)
    for row, (a, b) in enumerate(keys):
        design[row, index[a]] = 1.0
        design[row, index[b]] = -1.0
        rhs[row] = -np.log(pairs[(a, b)])
    solution, *_ = np.linalg.lstsq(design, rhs, rcond=None)
    return solution, design @ solution - rhs, keys


def _normalise(labels: list[int], pairs: dict[tuple[int, int], float],
               solution: np.ndarray) -> np.ndarray:
    """Centre the *measured* panels on 1.0, and leave every other panel there.

    Two jobs at once, and doing only the first is the bug this function was
    extracted for. **Centre:** the pass moves panels relative to each other, so
    the finished picture's overall brightness must not move with them — the
    median *measured* panel therefore stays at 1.0. **Leave alone:** a panel
    that ends the fit sharing no surviving pair has no evidence behind it at
    all, and this module's rule is that no evidence means no change.

    Subtracting a median taken over **every** panel did the first and quietly
    undid the second. ``lstsq``'s minimum-norm solution does give an unpaired
    panel 0, but 0 only means "scale 1.0" while the median it is then shifted
    by is itself 0 — which a lopsided pair graph makes false. Measured on three
    panels each reading 1.2× against a fourth, plus one panel sharing nothing:
    that last panel came out at **0.955**, a 4.5 % dimming of a whole tile on
    an overlap it never had.

    A mosaic whose panels are all measured — the ordinary case, and every one
    the pass was shipped against — is byte-for-byte unchanged: the two medians
    are then the same number over the same values, and nothing is pinned.
    """
    measured = {panel for key in pairs for panel in key}
    keep = np.array([label in measured for label in labels], dtype=bool)
    out = np.zeros_like(solution)
    if not keep.any():  # pragma: no cover — ``pairs`` is non-empty here
        return out
    out[keep] = solution[keep] - float(np.median(solution[keep]))
    return out


def _solve_log_scales(labels: list[int],
                      pairs: dict[tuple[int, int], float]) -> np.ndarray | None:
    """Per-panel log scale consistent with the pairs, or ``None`` to stand down.

    Once the panels form a loop the fit is over-determined — a 2×2 mosaic gives
    up to six pairs for four unknowns — so its residual is a free consistency
    check on measurements that each passed their own guards. It is a check with
    a *cause*, though: a mosaic's diagonal neighbours share only a small corner,
    so one noisy pair among five sound ones is the ordinary case, not evidence
    that the mosaic has no per-panel gain. Drop the worst pair and re-solve while
    that keeps helping.

    What is never done is dropping pairs until the graph has no loops left. A
    graph with no loop is consistent by construction — its residual is exactly
    zero however wrong its ratios are — so "agreeing" at that point is not
    evidence of anything. A drop is therefore only taken while it would leave a
    loop behind, and a fit that still disagrees at that limit stands the pass
    down instead.

    The accepted fit is handed to :func:`_normalise`, which centres it on the
    panels that actually carry a *surviving* pair — the drop loop above is why
    that set has to be read at the end rather than at the start.
    """
    remaining = dict(pairs)
    tol = float(np.log(MAX_FIT_RESIDUAL_RATIO))
    for _ in range(len(pairs)):
        solution, residual, keys = _solve_once(labels, remaining)
        worst = float(np.max(np.abs(residual))) if residual.size else 0.0
        if worst <= tol:
            return _normalise(labels, remaining, solution)
        # A connected graph of ``n`` panels needs ``n - 1`` pairs to be a tree,
        # and a tree fits any ratios at all with zero residual. Only drop while
        # at least one loop would survive the drop.
        n_nodes = len({panel for key in remaining for panel in key})
        if len(remaining) <= n_nodes:
            break
        dropped = keys[int(np.argmax(np.abs(residual)))]
        log.info(
            "Overlap panel gain: panels %d/%d disagree with the rest by %.2f× "
            "— dropping that pair and re-fitting", dropped[0], dropped[1],
            float(np.exp(worst)))
        del remaining[dropped]
    log.info(
        "Overlap panel gain: the overlap ratios never settle into one gain per "
        "panel — standing down rather than guessing")
    return None


def compute_overlap_gain_scales(
    frames_by_panel: dict[int, list[FrameRow]],
    canvas_wcs_text: str,
    canvas_shape: tuple[int, int],
    *,
    align_frame,  # noqa: ANN001 — callable(frame, dst_wcs_text, dst_shape)
    max_ratio: float = MAX_PANEL_RATIO,
    max_frames_per_panel: int = MAX_FRAMES_PER_PANEL,
) -> tuple[dict[int, float], OverlapGainStats] | None:
    """``{panel label: multiplicative scale}`` measured in the panel overlaps.

    ``align_frame(frame, dst_wcs_text, dst_shape)`` is the caller's own aligner —
    the stacker passes a closure over :func:`seestack.stack.align.align_one` with
    the run's calibration, background and hot-pixel options bound, so the
    pre-pass measures the *same* pixels the stack will combine. It returns
    ``(window_rgb, window_valid, y0, x0)`` or ``None``, exactly as ``align_one``
    does.

    Returns ``None`` — "could not measure; apply nothing" — for every case where
    the evidence is thin: fewer than two panels, a canvas too small to fold, no
    panel that aligned, no pair whose overlap holds enough correlated signal, or
    a pair graph whose ratios disagree. Never raises: an
    unexpected failure inside the pass is logged and becomes ``None`` too, so the
    worst this can cost a stack is the time it took.
    """
    try:
        return _compute(
            frames_by_panel, canvas_wcs_text, canvas_shape,
            align_frame=align_frame, max_ratio=max_ratio,
            max_frames_per_panel=max_frames_per_panel)
    except Exception as exc:  # noqa: BLE001 — never let a diagnostic pass fail a stack
        log.warning("Overlap panel gain matching failed (%s) — panels left as shot", exc)
        return None


def _compute(
    frames_by_panel: dict[int, list[FrameRow]],
    canvas_wcs_text: str,
    canvas_shape: tuple[int, int],
    *,
    align_frame,  # noqa: ANN001
    max_ratio: float,
    max_frames_per_panel: int,
) -> tuple[dict[int, float], OverlapGainStats] | None:
    labels = sorted(label for label, group in frames_by_panel.items() if group)
    if len(labels) < 2 or not canvas_wcs_text:
        return None

    ds = _downsample_factor(canvas_shape)
    coarse_shape = (int(canvas_shape[0]) // ds, int(canvas_shape[1]) // ds)
    if min(coarse_shape) < 2:
        return None

    maps: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for label in labels:
        picked = _panel_frames(frames_by_panel[label], max_frames_per_panel)
        if not picked:
            continue
        built = _panel_map(
            picked, canvas_wcs_text=canvas_wcs_text, canvas_shape=canvas_shape,
            coarse_shape=coarse_shape, ds=ds, align_frame=align_frame)
        if built is not None:
            maps[label] = built
    if len(maps) < 2:
        return None

    lums: dict[int, np.ndarray] = {}
    covs: dict[int, np.ndarray] = {}
    for label, (sums, counts) in maps.items():
        covered = counts > 0
        lum = np.zeros(coarse_shape, dtype=np.float64)
        np.divide(sums, counts, out=lum, where=covered)
        lums[label], covs[label] = lum, covered
    del maps

    measured = sorted(lums)
    pairs: dict[tuple[int, int], float] = {}
    lo, hi = 1.0 / max(1.0, float(max_ratio)), max(1.0, float(max_ratio))
    for i, a in enumerate(measured):
        for b in measured[i + 1:]:
            ratio = _pair_ratio(lums[a], covs[a], lums[b], covs[b])
            if ratio is None:
                continue
            if not (lo <= ratio <= hi):
                # Not a hazy night — a broken measurement. Drop the pair rather
                # than clamp it, so a wild number can't drag its panel along.
                log.info("Overlap panel gain: panels %d/%d measured %.2f× apart, "
                         "outside the %.1f× bound — pair dropped", a, b, ratio, hi)
                continue
            pairs[(a, b)] = ratio
    if not pairs:
        log.info("Overlap panel gain: no panel pair shares enough signal to "
                 "measure — panels left as shot")
        return None

    solution = _solve_log_scales(measured, pairs)
    if solution is None:
        return None

    scales = {
        label: float(np.clip(np.exp(value), lo, hi))
        for label, value in zip(measured, solution, strict=True)
    }
    values = list(scales.values())
    stats = OverlapGainStats(
        n_panels=len(scales), n_pairs=len(pairs),
        min_scale=float(min(values)), max_scale=float(max(values)))
    return scales, stats
