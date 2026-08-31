"""
Stack orchestrator.

Drives the full stacking pipeline:

  1. Pick a reference frame and lock in the output canvas (its WCS + shape).
  2. **Pass 1**: stream every accepted frame through ``align_one`` and feed it
     into a Welford accumulator → per-pixel mean and σ.
  3. (If sigma-clipping enabled.) **Pass 2**: re-stream and only contribute
     pixels within ``mean ± k·σ`` of pass-1's estimate, into a weighted-sum
     accumulator. Final image = sum / weight.
  4. (If clipping disabled.) The pass-1 accumulator's mean *is* the final image
     and we skip pass 2 entirely.

Parallelism: I/O + reproject runs in worker threads via ``ThreadPoolExecutor``.
The numpy and reproject operations release the GIL during their hot loops so
threads give close to linear speedup. The accumulator update is done on the
main thread as ``Future``s complete — no locking needed.

Progress is reported via a simple callback ``cb(phase, done, total)``. The GUI
adapter wraps this into Qt signals.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from seestack.bg.per_frame import BackgroundOptions
from seestack.core.xp import GPU_AVAILABLE
from seestack.io.project import (
    FrameRow,
    Project,
    count_unreadable_frames,
    readable_frame_path,
)
from seestack.stack.accumulator import (
    MinMaxRejectAccumulator,
    WeightedSumAccumulator,
    WelfordAccumulator,
)
from seestack.stack.align import (
    REF_PATCH_MIN_COVERAGE, align_one, extract_reference_patch,
)
from seestack.stack.output import _sanitize_basename
from seestack.stack.reference import ReferenceChoice, pick_reference_frame
from seestack.stack.photometric import PhotometricStats, compute_photometric_scales
from seestack.stack.weighting import (
    WeightingStats,
    combine_weights_with_photometric,
    compute_frame_weights,
    unit_weights,
)

if TYPE_CHECKING:
    from seestack.calibrate.apply import CalibrationMasters

# Peak count of full-canvas float32 RGB arrays alive at once across the stack
# passes (Welford mean/M2/count, or drizzle output/weight, plus working
# copies). Used only to *estimate* memory and refuse oversized stacks before
# allocating — a wrong guess just shifts the refusal threshold a little.
_PEAK_CANVAS_ARRAYS = 4
# Two-pass drizzle rejection holds more at once during pass 1: the value and
# value² drizzlers (img+wht each → 4 RGB-equivalents) plus the mean/tol maps
# being extracted (2) and per-channel temporaries (~1).
_PEAK_CANVAS_ARRAYS_DRIZZLE_REJECT = 7
_DEFAULT_STACK_BUDGET_GB = 12.0


def _available_memory_bytes() -> int | None:
    """Linux MemAvailable in bytes, or None if it can't be read."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return None


def _stack_memory_budget_bytes(setting_gb: float | None = None) -> float:
    """How much working memory a single stack may use. Precedence:
    the ``ASTROSTACK_MAX_STACK_GB`` env override (a deployment/container knob)
    wins, then an explicit ``setting_gb`` (the user-facing Settings value passed
    in by the webapp), then ~70% of currently-available RAM (leaving headroom
    for worker subprocesses, OS cache and the web app)."""
    override = os.environ.get("ASTROSTACK_MAX_STACK_GB")
    if override:
        try:
            return float(override) * 1e9
        except ValueError:
            pass
    if setting_gb is not None and setting_gb > 0:
        return float(setting_gb) * 1e9
    avail = _available_memory_bytes()
    if avail:
        return avail * 0.7
    return _DEFAULT_STACK_BUDGET_GB * 1e9


def _min_max_reject_arrays(reject_count: int) -> int:
    """Canvas-plane count the ``MinMaxRejectAccumulator`` holds at once for a given
    reject count: ``sum`` + ``count`` + k min-planes + k max-planes = ``2 + 2k``.
    Charged in the memory estimate so a large k can't slip past the OOM guard."""
    return 2 + 2 * max(1, int(reject_count))


def _records_rejection_map(options: "StackOptions", n: int) -> bool:
    """Will this run actually allocate a per-pixel rejection map?

    Only the two **data-driven** rejections record one, under exactly the
    conditions their own branches in :func:`run_stack` take: two-pass drizzle
    (``drizzle and drizzle_reject and n >= 4``) and κ-σ (``sigma_clip and
    n >= 4``, drizzle off, min/max not taking precedence). Everything else — a
    single-pass drizzle, a min/max reject whose drop is structural rather than
    data-driven, a plain mean, a stack too small to reject at all — records
    nothing and writes no sibling.

    Pass the *effective* options (post ``_resolve_auto_reject`` /
    ``_afford_drizzle_reject``), so the memory guard, the in-flight cap and the
    pre-submit estimate all charge the plane exactly when the run allocates it.
    """
    if not options.record_rejection_map:
        return False
    if options.drizzle:
        return bool(options.drizzle_reject) and n >= 4
    if options.min_max_reject and n >= 3:
        return False
    return bool(options.sigma_clip) and n >= 4


def _estimate_peak_bytes(dst_shape: tuple[int, int], *, drizzle: bool,
                         drizzle_scale: float,
                         drizzle_reject: bool = False,
                         reject_arrays: int = 0,
                         rejection_map: bool = False,
                         ) -> tuple[int, tuple[int, int]]:
    """Peak working-memory estimate for a stack and its post-drizzle output
    shape. ``dst_shape`` is (h, w) of the pre-drizzle canvas; drizzle multiplies
    each axis by ``drizzle_scale``. Returns ``(peak_bytes, (out_h, out_w))``.

    ``reject_arrays`` is the number of canvas planes a top/bottom-k min/max reject
    accumulator holds at once (see ``_min_max_reject_arrays``); it raises the array
    factor when a k>1 reject would need more than the baseline working set.

    ``rejection_map`` adds the one ``uint16`` **2-D** plane
    ``StackOptions.record_rejection_map`` allocates — charged at its true size
    (2 bytes/pixel, a sixth of an RGB float32 array) rather than rounded up to a
    whole array, so asking for the overlay can't push a run over the budget by
    six times what it actually costs.

    Shared by ``_guard_stack_memory`` (which refuses over-budget stacks) and
    ``estimate_stack`` (which surfaces the same number to the UI *before* a run
    is refused), so the warning and the guard can never disagree."""
    h, w = dst_shape
    if drizzle:
        s = max(1.0, float(drizzle_scale))
        # Match the *actual* drizzle canvas formula in
        # ``drizzle_path._compute_output_canvas`` (``int(round(dim·scale))``)
        # exactly, so the estimated/guarded output shape equals the file the run
        # really writes. The old ``int(dim·s + 1)`` over-stated each axis by up to
        # 1 px whenever ``dim·s`` was near-integer — harmless for the memory guard
        # (it only over-reserved) but it surfaced wrong ``output_w``/``output_h``
        # dimensions in the pre-run estimate the UI shows.
        out_h, out_w = int(round(h * s)), int(round(w * s))
    else:
        out_h, out_w = h, w
    out_pixels = out_h * out_w
    if drizzle and drizzle_reject:
        arrays = _PEAK_CANVAS_ARRAYS_DRIZZLE_REJECT
    else:
        arrays = max(_PEAK_CANVAS_ARRAYS, reject_arrays)
    need = out_pixels * 3 * 4 * arrays  # float32 RGB working arrays
    if rejection_map:
        need += out_pixels * 2  # one uint16 2-D drop-count plane
    return need, (out_h, out_w)


def _memory_bounded_in_flight(
    per_frame_shape: tuple[int, int],
    dst_shape: tuple[int, int],
    *,
    max_in_flight: int,
    drizzle: bool = False,
    drizzle_scale: float = 1.0,
    drizzle_reject: bool = False,
    reject_arrays: int = 0,
    rejection_map: bool = False,
    memory_budget_gb: float | None = None,
) -> int:
    """Cap the number of in-flight per-frame worker buffers so they can't exceed the
    RAM left over after the persistent canvas arrays the OOM guard already charged.

    ``_pass``/``_drizzle_pass`` keep up to ``max_in_flight`` reprojected/debayered
    frame buffers alive at once (``_imap_bounded``), each ~one **native reference
    frame** RGB float32 array (``per_frame_shape`` — independent of the drizzle
    scale, which enlarges only the canvas). :func:`_estimate_peak_bytes` — the
    number the OOM guard refuses on — charges only the canvas arrays and never this
    per-worker term, so on a many-core box with a large sensor those buffers can OOM
    a run the guard just certified "safe". Bounding ``max_in_flight`` to
    ``headroom // per_frame_bytes`` prevents that OOM at the cost of throughput only
    (never correctness). Never drops below 2 — a little pipelining is needed to
    overlap the parallel load with the serialised consumer — and is inert for the
    Seestar target (small frames / few cores keep the cap above ``max_workers·2``)."""
    h, w = per_frame_shape
    per_frame_bytes = int(h) * int(w) * 3 * 4  # native RGB float32 worker buffer
    if per_frame_bytes <= 0:
        return max_in_flight
    budget = _stack_memory_budget_bytes(memory_budget_gb)
    canvas_peak, _ = _estimate_peak_bytes(
        dst_shape, drizzle=drizzle, drizzle_scale=drizzle_scale,
        drizzle_reject=drizzle_reject, reject_arrays=reject_arrays,
        rejection_map=rejection_map)
    headroom = budget - canvas_peak
    cap = int(headroom // per_frame_bytes)
    return max(2, min(max_in_flight, cap))


def _largest_drizzle_scale_within_budget(
    dst_shape: tuple[int, int], *, drizzle_reject: bool, budget: int,
    max_scale: float, step: float = 0.1,
) -> float | None:
    """Largest drizzle scale (rounded down to ``step``, in [1.0, ``max_scale``))
    whose estimated peak memory stays within ``budget``. Used to turn an
    over-budget refusal into a one-click "use ×N instead" suggestion. Returns
    None when even ×1.0 drizzle exceeds the budget (drizzle can't help — the
    user must drop to the reference canvas or reject frames instead)."""
    # Memory grows ~ scale²; start from the analytic fit, then step down to be
    # exact against ``_estimate_peak_bytes`` (which carries +1 offsets and the
    # rejection-pass array factor the closed form ignores).
    peak_at_max, _ = _estimate_peak_bytes(
        dst_shape, drizzle=True, drizzle_scale=max_scale,
        drizzle_reject=drizzle_reject)
    if peak_at_max <= budget:
        return None  # the requested scale already fits — nothing to suggest
    ratio = budget / peak_at_max if peak_at_max else 0.0
    guess = max_scale * (ratio ** 0.5)
    # Round down to the step grid and clamp into [1.0, max_scale).
    s = min(max_scale, max(1.0, (int(guess / step) * step)))
    # Walk down until it genuinely fits (analytic guess can round high).
    while s >= 1.0:
        peak, _ = _estimate_peak_bytes(
            dst_shape, drizzle=True, drizzle_scale=s,
            drizzle_reject=drizzle_reject)
        if peak <= budget and s < max_scale:
            return round(s, 2)
        s = round(s - step, 2)
    return None


@dataclass
class MemoryFix:
    """The single least-destructive change that brings an over-budget stack within
    the memory budget, as a machine-actionable suggestion.

    ``kind`` names the lever so the same fix can be rendered as a one-click button
    on the Stack form *and* worded into the run-time refusal message (one source of
    truth, so pre-submit advice and the post-refusal error can never disagree):

    * ``"drizzle_scale"`` — set ``drizzle_scale`` to ``value`` (a smaller super-res
      scale on the 0.1 grid).
    * ``"reduce_outlier_passes"`` — set ``min_max_reject_count`` to 1 (drop the
      extra min/max outlier passes; ``value`` is ``None``).
    * ``"reference_canvas"`` — set ``mosaic_canvas`` to ``"reference"`` (crop a
      mosaic union canvas to the reference frame; ``value`` is ``None``).

    ``peak_bytes`` is the peak the run lands at *after* the change, computed from
    the same :func:`_estimate_peak_bytes` the guard refuses on."""

    kind: str
    value: float | None
    peak_bytes: int


def _memory_fix_sentence(fix: MemoryFix) -> str:
    """The imperative clause naming ``fix`` for the run-time refusal message
    (e.g. ``"lower the drizzle scale to ×1.5"``). Kept beside :class:`MemoryFix`
    so the pre-submit button and the error string stay worded consistently."""
    if fix.kind == "drizzle_scale":
        return f"lower the drizzle scale to ×{fix.value:g}"
    if fix.kind == "reduce_outlier_passes":
        return "lower Extra outlier passes to 1"
    if fix.kind == "reference_canvas":
        return "switch Canvas mode to 'reference'"
    return ""  # unreachable — every kind above is enumerated


def _best_memory_fix(
    dst_shape: tuple[int, int], ref_shape: tuple[int, int] | None, *,
    is_mosaic: bool, drizzle: bool, drizzle_scale: float,
    drizzle_reject: bool, reject_arrays: int, min_max_reject_count: int,
    budget: int, rejection_map: bool = False,
) -> MemoryFix | None:
    """The single least-destructive concrete change that brings an over-budget
    stack within ``budget`` — a :class:`MemoryFix` — or ``None`` when no one lever
    obviously fits (the caller then keeps the generic four-lever guidance).

    A beginner on a RAM-capped NAS gets no help from "reduce drizzle scale, switch
    canvas, reject frames, or raise the budget" — they can't tell *which* one, or
    *how far*. This names the specific lever and the memory it lands at, computed
    from the same :func:`_estimate_peak_bytes` the guard refuses on, so the named
    "fits at ~X GB" can never disagree with the threshold. Both the pre-submit
    :func:`estimate_stack` and the run-time :func:`_guard_stack_memory` call this,
    so the one-click fix the UI offers and the refusal message always agree."""
    # Drizzle on → the only in-family lever is a smaller super-res scale (matches
    # estimate_stack's ``suggested_drizzle_scale``). If even ×1.0 can't fit, there
    # is no clean single fix — fall back to the generic guidance.
    if drizzle:
        s = _largest_drizzle_scale_within_budget(
            dst_shape, drizzle_reject=drizzle_reject, budget=budget,
            max_scale=float(drizzle_scale))
        if s is not None:
            peak, _ = _estimate_peak_bytes(
                dst_shape, drizzle=True, drizzle_scale=s,
                drizzle_reject=drizzle_reject, rejection_map=rejection_map)
            return MemoryFix("drizzle_scale", s, int(peak))
        return None
    # Non-drizzle levers, least-destructive first. Dropping extra outlier passes
    # (k>1 → the proven single min/max) costs only a little trail rejection; the
    # reference canvas crops a mosaic's field, a bigger change, so it's tried last.
    if reject_arrays > _min_max_reject_arrays(1) and min_max_reject_count > 1:
        peak, _ = _estimate_peak_bytes(
            dst_shape, drizzle=False, drizzle_scale=1.0,
            reject_arrays=_min_max_reject_arrays(1), rejection_map=rejection_map)
        if peak <= budget:
            return MemoryFix("reduce_outlier_passes", None, int(peak))
    if is_mosaic and ref_shape is not None:
        peak, _ = _estimate_peak_bytes(
            ref_shape, drizzle=False, drizzle_scale=1.0,
            reject_arrays=reject_arrays, rejection_map=rejection_map)
        if peak <= budget:
            return MemoryFix("reference_canvas", None, int(peak))
    return None


def _guard_stack_memory(dst_shape: tuple[int, int], *, drizzle: bool,
                        drizzle_scale: float,
                        drizzle_reject: bool = False,
                        reject_arrays: int = 0,
                        ref_shape: tuple[int, int] | None = None,
                        is_mosaic: bool = False,
                        min_max_reject_count: int = 1,
                        rejection_map: bool = False,
                        memory_budget_gb: float | None = None) -> None:
    """Refuse a stack whose output canvas would blow the memory budget instead
    of letting it OOM-kill the whole process. ``dst_shape`` is (h, w) of the
    pre-drizzle canvas; drizzle multiplies each axis by ``drizzle_scale``.

    When one concrete lever would make the run fit (:func:`_best_memory_fix`), the
    refusal names *that* change and the memory it lands at, so a beginner on a
    RAM-capped box gets an actionable next step instead of a generic list."""
    h, w = dst_shape
    need, _ = _estimate_peak_bytes(dst_shape, drizzle=drizzle,
                                   drizzle_scale=drizzle_scale,
                                   drizzle_reject=drizzle_reject,
                                   reject_arrays=reject_arrays,
                                   rejection_map=rejection_map)
    budget = _stack_memory_budget_bytes(memory_budget_gb)
    if need > budget:
        fix = _best_memory_fix(
            dst_shape, ref_shape, is_mosaic=is_mosaic, drizzle=drizzle,
            drizzle_scale=drizzle_scale, drizzle_reject=drizzle_reject,
            reject_arrays=reject_arrays, rejection_map=rejection_map,
            min_max_reject_count=min_max_reject_count, budget=int(budget))
        if fix is not None:
            advice = (f"To fit, {_memory_fix_sentence(fix)} "
                      f"(~{fix.peak_bytes / 1e9:.1f} GB), or raise "
                      f"ASTROSTACK_MAX_STACK_GB to override.")
        else:
            advice = ("Reduce drizzle scale, switch Canvas mode to 'reference', "
                      "reject outlier/off-target frames, or raise "
                      "ASTROSTACK_MAX_STACK_GB to override.")
        raise MemoryError(
            f"stack output canvas {w}×{h}"
            + (f" ×{drizzle_scale:g} drizzle" if drizzle else "")
            + (" with outlier rejection" if (drizzle and drizzle_reject) else "")
            + f" needs ~{need / 1e9:.1f} GB of working memory, over the "
            f"~{budget / 1e9:.1f} GB budget. " + advice
        )

log = logging.getLogger(__name__)


@dataclass
class StackOptions:
    """User-configurable knobs for one stack run."""

    sigma_clip: bool = True
    sigma_kappa: float = 3.0
    # Min/max (extremes) rejection: an order-statistic alternative to κ-σ that
    # drops exactly one per-pixel minimum and maximum before averaging, so it
    # removes a lone satellite/plane trail or hot/cold sample *even in a small
    # stack* where κ-σ mathematically can't (a lone outlier's deviation stays
    # below κ for n<11). Single streaming pass; needs ≥3 frames to spare two
    # samples (falls back to a plain mean per pixel below that). Ignores quality
    # weights (it's an order statistic). Off by default; when on it takes
    # precedence over ``sigma_clip`` on the standard (non-drizzle) path.
    min_max_reject: bool = False
    # How many per-pixel extremes to drop *per side* when ``min_max_reject`` is on.
    # 1 = the classic single min/max drop (today's behaviour). Raise it to clip
    # multiple trails crossing one pixel across a session (k=3 → up to 3 satellite/
    # plane trails). Applied only where a pixel has ≥ 2k+1 samples; below that it
    # degrades to the proven single min/max drop. Costs 2k canvas planes (charged
    # in the memory guard). Kept small — the Stack form bounds it at 5.
    min_max_reject_count: int = 1
    # Auto-pick the outlier-rejection method from the number of subs, so a
    # beginner never has to know κ-σ vs min/max. When on (and not drizzling), it
    # resolves — per :func:`_resolve_auto_reject` — to order-statistic min/max on
    # small stacks (where κ-σ is mathematically blind to a lone satellite/plane
    # trail: a point's z-score against stats that include it stays below κ until
    # ~11 frames) and to weight-respecting κ-σ once the stack is large enough for
    # it to bite. Off by default → existing configs and run records are
    # byte-for-byte unchanged; a run with it off ignores it entirely. Overrides
    # the ``sigma_clip``/``min_max_reject`` toggles when set. No-op on the drizzle
    # path (drizzle has its own two-pass rejection).
    auto_reject: bool = False
    # Record *where* outlier rejection dropped samples, not just how many: a
    # per-pixel ``uint16`` drop count written beside the picture as
    # ``{base}_rejected.fits``, which the app overlays on the finished image so
    # the user can see the satellite trails and cosmic rays that were cleaned out
    # for them. Purely observational — it watches the same keep/drop decision the
    # combine already applied, so a run with it on is pixel-identical to one with
    # it off. Costs one extra 2-bytes-per-pixel canvas plane, charged through the
    # OOM guard, which is why it is **opt-in** rather than always on.
    #
    # Recorded on the two rejection paths whose decision is *data-driven* — κ-σ
    # and two-pass drizzle — and deliberately **not** on min/max, whose drop is
    # structural (every pixel with ≥3 samples loses exactly 2k of them, see
    # ``MinMaxRejectAccumulator.rejection_counts``): a map of that is a flat wash
    # over the whole canvas, which would tell the user nothing and imply damage
    # that isn't there. A run that records nothing simply writes no sibling, and
    # every consumer reads that as "no overlay available".
    record_rejection_map: bool = False
    background_flatten: bool = True
    background_box_size: int = 128
    # 'per_channel' (default, good for star fields and small targets)
    # 'luminance'   (preserves colour on extended emission nebulas)
    background_mode: str = "per_channel"
    # Hot / cold pixel suppression: median-residual filter, ~10ms/frame.
    suppress_hot_pixels: bool = True
    hot_pixel_sigma: float = 5.0
    # Quality-weighted stack: weight each frame by FWHM / star_count / sky.
    quality_weighted: bool = False
    # Photometric (multiplicative) normalization: gain-match each frame's signal
    # to the run's median transparency before combining, so haze/airmass flux
    # variation across a multi-night session doesn't inflate the rejection spread
    # or let hazy nights dim the result. Derived from each frame's own
    # ``transparency_score``, bounded, neutral fallback, off by default.
    # Independent of (and composes with) ``quality_weighted``.
    photometric_normalize: bool = False
    # Lucky imaging: keep only the top X% of frames by FWHM. 1.0 = keep all.
    lucky_fraction: float = 1.0
    # Final-stack gradient removal with object masking (post-stack pass).
    final_gradient_removal: bool = False
    final_gradient_mode: str = "per_channel"  # 'per_channel' | 'luminance'
    final_gradient_box_size: int = 256
    # Sub-pixel alignment refinement (phase correlation against ref patch).
    subpixel_refine: bool = False
    # Save an autostretched preview PNG every N frames during pass 1. Useful
    # for 10k-frame runs so the user can peek at progress. 0 disables.
    quick_look_interval: int = 0
    # Keep a short "watch your picture come together" progress reel: a handful
    # of evenly-spaced autostretched snapshots collected during pass 1 and
    # assembled into a small looping animation next to the master. Off by
    # default (byte-for-byte unchanged output when off); a friendly beginner
    # extra, purely downstream of the finished stack.
    save_progress: bool = False
    # Photometric color calibration (post-stack).
    color_calibration: bool = False
    color_calibration_mode: str = "gray_star"  # 'gray_star' | 'gaia'
    max_workers: int | None = None  # default: os.cpu_count()
    output_name: str = "master"
    use_gpu: bool | None = None  # None = auto-detect
    # 'linear' (default, like DSS): TIFF preserves linear data, dark on screen
    # 'autostretch': TIFF gets a gentle stretch for direct viewing
    tiff_mode: str = "linear"
    # Drizzle is an alternate stacking path. When enabled it overrides
    # ``sigma_clip`` (drizzle does its own one-pass accumulation).
    drizzle: bool = False
    drizzle_pixfrac: float = 0.8
    drizzle_scale: float = 1.5  # 1.0 = same res as ref, 2.0 = full super-res
    drizzle_kernel: str = "square"
    # Two-pass drizzle outlier rejection: pass 1 drizzles values + squares to
    # get per-output-pixel mean/σ of the contributions, pass 2 re-drizzles
    # zero-weighting contributions outside mean ± sigma_kappa·σ. Removes
    # satellites/plane trails/cosmic rays that single-pass drizzle keeps, at
    # roughly 2–3× the stacking time. Needs ≥4 frames.
    drizzle_reject: bool = False
    # Output canvas mode:
    #   'auto'      — union-of-footprints canvas when frames span more than
    #                 one Seestar field (a mosaic), reference frame otherwise.
    #   'union'     — always use the union-of-footprints canvas.
    #   'reference' — always crop to the reference frame's footprint.
    mosaic_canvas: str = "auto"
    # Mono stacking: treat each raw frame as a single-channel luminance image
    # (no debayer) and stack it into a grayscale result. For mono cameras and
    # filtered (L / R / G / B / narrowband) subs. Off = OSC debayer (default).
    mono: bool = False
    # Dark/flat calibration. Server-side filesystem paths to master FITS frames
    # (resolved from the calibration store by the webapp — never user input).
    # None disables that correction. Applied to the raw Bayer mosaic per frame.
    dark_path: str | None = None
    flat_path: str | None = None
    # Optional dark/bias matched to the flat's exposure. Subtracted from the
    # flat before normalising for a more correct flat (a "flat-dark"). Only used
    # when ``flat_path`` is also set. Server-resolved path, never client input.
    flat_dark_path: str | None = None
    # Optional master bias subtracted from the *lights* as the readout pedestal,
    # for the bias+flat (no dark) workflow — ``(light − bias) / flat``. Ignored
    # when ``dark_path`` is set (a dark already contains the bias, so both would
    # double-subtract it). Server-resolved path, never client input.
    bias_path: str | None = None
    # Exposure-scale a master dark whose exposure differs from the lights:
    # ``dark = bias + (dark − bias)·(t_light / t_dark)``. Needs a master bias
    # (to hold the readout pedestal fixed) and known exposures; falls back to the
    # unscaled dark otherwise. Off by default. Lets a dark library shot at one
    # exposure still calibrate subs at another.
    scale_dark_to_light: bool = False
    # **Posture, not a knob:** True when *nobody is watching this run* — the
    # walk-away chains (watcher auto-stack, "Process target") set it; the manual
    # Stack form, the desktop app and reprocess-all never do. It is not a user
    # setting: it has no form descriptor (it lives in ``NON_FORM_KEYS``), a client
    # can't set it (``webapp.pipeline._stack_target`` writes it last, after every
    # merge), and it changes no picture on its own.
    #
    # It exists because several decisions in here are a genuine fork on *that*
    # question and nothing else: when a user is sitting in front of the Stack form
    # and the run doesn't fit in memory, refusing with one concrete fix ("lower the
    # drizzle scale to ×1.3") is the *better* outcome — they click it and get the
    # picture they asked for. At 3 a.m. with nobody there, the identical refusal
    # produces no picture at all on a target that made one yesterday. Before this
    # flag, ``_afford_drizzle_reject`` read ``auto_reject`` as the proxy for
    # "unattended", which is wrong: ``get_stack_defaults`` seeds ``auto_reject=True``
    # into the *manual form* for a never-configured target, so a watching beginner
    # posted it too and was quietly degraded instead of being told the fix.
    # Off by default → every existing run record, config and desktop run is
    # byte-for-byte unchanged.
    unattended: bool = False

    def background_options(self) -> BackgroundOptions:
        return BackgroundOptions(
            box_size=self.background_box_size,
            enabled=self.background_flatten,
            mode=self.background_mode,
        )


@dataclass
class StackResult:
    """Outcome of a stack run."""

    output_dir: Path
    fits_path: Path
    tiff_path: Path
    preview_path: Path
    n_frames_used: int
    canvas_shape: tuple[int, int]
    coverage_min: int
    coverage_max: int
    options: StackOptions
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)
    # Frames dropped (and flagged rejected) for a bad plate-solve that would
    # have flung the mosaic canvas across the sky. Human-readable labels.
    excluded_frames: list[str] = field(default_factory=list)
    # Honest frame accounting for the finished stack: how many subs the stacker
    # *attempted* to combine (post lucky/mosaic-outlier filtering) and how many of
    # those could not be aligned (load failure, or a footprint that missed the
    # canvas — usually a stray sub from another target or a bad plate-solve).
    # ``n_offered - n_align_failed == n_frames_used``. Both 0 on a cancelled /
    # nothing-aligned run that returns before the passes complete.
    n_offered: int = 0
    n_align_failed: int = 0
    # Of ``n_align_failed``, how many were simply **not on disk** when the run
    # started — neither the Stage-1 cache nor the original source file existed
    # (a cleared cache while the originals sit on an offline NAS share, an
    # unmounted drive, moved files). A subset of ``n_align_failed``, measured by
    # a cheap stat() preflight over the same frame list the passes iterate, so a
    # walk-away stack can say "142 of your 500 subs couldn't be read" instead of
    # blaming alignment for a storage problem. 0 when everything was readable.
    n_unreadable: int = 0
    # How many distinct subs raised an error while a pass was reading/aligning
    # them — the counted form of ``errors``, which is a list of raw per-file
    # strings nothing ever showed the user. Different from ``n_unreadable``
    # (whose file wasn't on disk at all): these files existed and then failed
    # mid-read, which is what a flaking share or a bad sector looks like.
    # ``n_read_recovered`` is the subset a two-pass run's *other* pass read fine
    # and combined anyway, so their light is in the picture (the same frames
    # whose error line ``_mark_recovered_errors`` qualifies). Both 0 on a healthy
    # run, which is every run with an empty ``errors`` list.
    n_read_errors: int = 0
    n_read_recovered: int = 0
    # How many contributing subs sub-pixel refine had to leave *only roughly
    # aligned* (its measured shift exceeded ``SUBPIXEL_SHIFT_CAP_PX``, so the
    # frame stacked unshifted → possibly soft/doubled stars). 0 when refine was
    # off. Observational only — it never changes which frames contribute.
    n_roughly_aligned: int = 0
    # The new ``stack_runs`` row id for this run (None if history recording was
    # skipped — e.g. a cancelled run — or failed). Lets callers deep-link the
    # finished run's editor instead of just its target's History list.
    run_id: int | None = None
    # The outlier-rejection tally, mirrored from the persisted run record so a
    # caller (e.g. the Jobs "Process target" result) can name the invisible
    # clean-up without re-reading the run row. ``rejection_mode`` is one of
    # ``"sigma-clip"`` / ``"min-max-reject"`` / ``"drizzle-reject"``; both are
    # None when no rejection pass ran (a plain-mean stack) — exactly the same
    # gate the ``stack_runs`` columns use.
    rejection_mode: str | None = None
    rejection_fraction: float | None = None
    # Advisory (non-fatal) mismatches between the master dark and the lights it
    # calibrated — a dark shot at a different exposure or a very different sensor
    # temperature over/under-subtracts its pedestal on *every* frame. These used
    # to go only to the server log, which nobody running a walk-away stack reads,
    # so a quietly mis-calibrated picture arrived with nothing to explain it.
    # Plain-language sentences straight from ``CalibrationMasters
    # .calibration_warnings`` (the wording lives there, once). Empty when the dark
    # matches, when no dark was applied, or when the headers didn't say.
    calibration_warnings: list[str] = field(default_factory=list)


@dataclass
class PrintPlan:
    """What the stack these settings describe would **print** at, said before it
    is run.

    ``printexport`` can already tell a *finished* picture the largest paper it
    fills sharply and what it would take to reach the next size up — but by then
    the canvas is fixed and the one lever that sets it (Drizzle) is a knob on a
    form the user has already left. This is the same answer in the tense that can
    still change the outcome: megapixels turned into a paper size, plus the
    concrete drizzle scale that would reach one size bigger.

    ``bigger_*`` are all None whenever there is nothing honest to offer: the
    output already fills the largest paper, the gap needs more super-resolution
    than :data:`~seestack.printexport.DRIZZLE_MAX_USEFUL_SCALE`, or the bigger
    canvas would not fit the memory budget (the estimate's own over-budget
    verdict owns that case — this must never talk past it)."""

    # The largest paper the output would print sharply at, None when the canvas
    # is too small for even the smallest size offered.
    name: str | None
    dpi: int | None
    text: str                          # the finished plain-language sentence
    bigger_name: str | None = None     # the next paper size up…
    bigger_drizzle_scale: float | None = None   # …and the scale that reaches it
    bigger_text: str | None = None


def _print_plan(out_w: int, out_h: int, dst_shape: tuple[int, int], *,
                drizzle: bool, drizzle_scale: float, drizzle_reject: bool,
                rejection_map: bool, budget: int) -> PrintPlan:
    """Turn a pre-run output canvas into :class:`PrintPlan` (see there).

    The drizzle scale offered is *verified*, not derived and hoped for: the
    candidate is stepped up the same 0.1 grid the form uses until the canvas it
    really produces qualifies for the paper, so the sentence can't promise a size
    the run would just miss. It is dropped entirely when the canvas at that scale
    would exceed ``budget``, so the nudge never argues with the memory guard."""
    from seestack.printexport import DRIZZLE_MAX_USEFUL_SCALE, bigger_print, print_options

    options = print_options(out_w, out_h)
    best = options[0] if options else None
    if best is not None:
        text = f"This stack would print sharply up to {best.name}."
    else:
        text = ("This stack won't have enough pixels for a sharp print — that "
                "takes more resolution (Drizzle, or shooting a mosaic), not "
                "more subs.")
    plan = PrintPlan(name=(best.name if best else None),
                     dpi=(best.dpi if best else None), text=text)

    nxt = bigger_print(out_w, out_h)
    if nxt is None:
        return plan
    # Output = canvas × scale, so reaching ``nxt.scale`` times more detail per
    # side means multiplying whatever scale is set now (×1.0 when drizzle is off).
    current = float(drizzle_scale) if drizzle else 1.0
    step = 0.1
    candidate = math.ceil(current * nxt.scale / step) * step
    while round(candidate, 2) <= DRIZZLE_MAX_USEFUL_SCALE + 1e-9:
        candidate = round(candidate, 2)
        peak, (cand_h, cand_w) = _estimate_peak_bytes(
            dst_shape, drizzle=True, drizzle_scale=candidate,
            drizzle_reject=drizzle_reject, rejection_map=rejection_map)
        if any(o.name == nxt.name
               for o in print_options(cand_w, cand_h)):
            if int(peak) > budget:
                return plan     # the memory verdict owns this case, not us
            verb = (f"Raising Drizzle to ×{candidate:g}" if drizzle
                    else f"Turning Drizzle on at ×{candidate:g}")
            return replace(
                plan, bigger_name=nxt.name, bigger_drizzle_scale=candidate,
                bigger_text=(f"{verb} would print it at {nxt.name} instead — "
                             "super-resolution needs plenty of well-dithered "
                             "subs to pay off."))
        candidate += step
    return plan


@dataclass
class StackEstimate:
    """A dry-run sizing of a stack: the output canvas it would produce and the
    peak working memory it would need — computed without stacking anything, so
    the UI can warn ("Drizzle ×2 → ~7680×4320, ≈2.1 GB peak, over budget")
    *before* a run is submitted and refused."""

    n_frames: int
    canvas_w: int          # pre-drizzle canvas width
    canvas_h: int          # pre-drizzle canvas height
    output_w: int          # post-drizzle output width
    output_h: int          # post-drizzle output height
    is_mosaic: bool        # union-of-footprints canvas (spans >1 field)
    peak_bytes: int
    budget_bytes: int
    would_exceed: bool     # peak_bytes > budget_bytes → run would be refused
    # When a drizzle run would_exceed the budget, the largest drizzle scale
    # (< the requested one) whose peak still fits — a one-click "use ×N instead"
    # the UI can offer. None when drizzle is off, the run already fits, or even
    # ×1.0 drizzle exceeds (drizzle can't rescue it).
    suggested_drizzle_scale: float | None = None
    # When a NON-drizzle mosaic (union canvas) run would_exceed the budget,
    # whether the reference-frame canvas alone would fit — a one-click "use the
    # reference canvas instead" the UI can offer (the drizzle-off mirror of
    # ``suggested_drizzle_scale``). False when drizzle is on, the run already
    # fits, it isn't a mosaic, or even the reference canvas exceeds the budget.
    suggested_reference_canvas: bool = False
    # The single least-destructive one-click fix (with the memory it lands at)
    # that brings an over-budget run within the budget — the *same*
    # :class:`MemoryFix` the run-time refusal message names, so the pre-submit
    # button and the error can never disagree. It also covers a lever the two
    # coarse fields above miss (dropping extra min/max outlier passes on a
    # non-drizzle stack). None when the run fits or no single lever obviously does.
    memory_fix: MemoryFix | None = None
    # What this canvas would *print* at, and the drizzle scale that would reach
    # one size bigger — the megapixel count in the unit a human actually wants,
    # said at the one moment the lever is still on screen. Never contradicts the
    # memory verdict (see :class:`PrintPlan`).
    print_plan: PrintPlan | None = None


def kappa_min_frames(kappa: float) -> int:
    """Smallest frame count at which κ-σ can reject a *lone* outlier.

    A single point's z-score against statistics that still include it is at most
    ``(n−1)/√n``; that first reaches ``κ`` at ``n = ⌈((κ+√(κ²+4))/2)²⌉``. Below
    this, κ-σ is mathematically blind to a lone satellite/plane trail, so
    ``auto`` uses the order-statistic min/max drop (which removes an extreme even
    at n=3) instead. Floored at 3 (min/max needs ≥3 to spare two samples).

    Public because it is also the honest answer to "could this stack's rejection
    have removed anything?" — ``seestack.stackhealth`` reads it to tell a user
    whose small stack ran κ-σ that the pass could not, mathematically, have
    clipped a lone satellite trail. One definition, so the note and the
    method-picker can never disagree."""
    u = (kappa + math.sqrt(kappa * kappa + 4.0)) / 2.0
    return max(3, int(math.ceil(u * u)))


def auto_reject_method(kappa: float, n: int) -> str:
    """Which concrete method ``auto_reject`` picks for an ``n``-frame stack:
    ``"sigma_clip"`` or ``"min_max"``.

    Public because the Stack form has to be able to *say* which one will run —
    with "Auto outlier removal" on, the sigma-clip / min-max toggles below it
    are overridden, and a form that still shows them as live tells a beginner
    the opposite of what happens. One definition, read by both the picker
    (:func:`_resolve_auto_reject`) and the form, so they cannot disagree.

    ``auto_reject_switch_frames`` is the smallest ``n`` this returns
    ``"sigma_clip"`` at — the number the form quotes as "switches at ~N"."""
    use_kappa = n >= kappa_min_frames(kappa)
    # κ-σ's own dispatch needs ≥4 frames (see :func:`_resolve_auto_reject`).
    if use_kappa and n < 4:
        use_kappa = False
    return "sigma_clip" if use_kappa else "min_max"


def auto_reject_switch_frames(kappa: float) -> int:
    """The frame count at which :func:`auto_reject_method` switches from
    ``min_max`` to ``sigma_clip`` — both of its floors folded into one number."""
    return max(4, kappa_min_frames(kappa))


def _resolve_auto_reject(options: StackOptions, n: int) -> StackOptions:
    """Resolve ``auto_reject`` into concrete ``sigma_clip``/``min_max_reject``.

    When ``auto_reject`` is on (and not drizzling), pick order-statistic min/max
    for small stacks — the only method that removes a lone outlier below
    :func:`kappa_min_frames` — and weight-respecting κ-σ once the stack is
    large enough for κ-σ to bite. Returns ``options`` unchanged when
    ``auto_reject`` is off or drizzle is on (drizzle has its own two-pass
    rejection), so a run that doesn't opt in is byte-for-byte identical."""
    if not options.auto_reject or options.drizzle:
        return options
    # The ≥4-frame floor inside :func:`auto_reject_method` is κ-σ's own dispatch
    # requirement (its pass-2 clip branch gates on ``n >= 4``);
    # ``kappa_min_frames`` floors at 3 for the min/max side, so at a small κ
    # (``sigma_kappa`` ≲ 1.155, reachable via the webapp's min of 1.0)
    # ``kappa_min_frames`` returns 3 and a 3-frame stack would pick κ-σ — which
    # then never runs, silently falling through to a plain mean with NO rejection
    # despite ``auto_reject``. Below 4 frames, use the order-statistic min/max drop
    # (which rejects a lone extreme at n≥3) so the user's rejection intent is met.
    use_kappa = auto_reject_method(options.sigma_kappa, n) == "sigma_clip"
    return replace(options, sigma_clip=use_kappa, min_max_reject=not use_kappa)


def _afford_drizzle_reject(options: StackOptions, n: int,
                           dst_shape: tuple[int, int],
                           memory_budget_gb: float | None) -> bool:
    """Whether the two-pass drizzle rejection actually runs for this stack.

    Folds in the ``n >= 4`` floor the pass needs for its statistics to mean
    anything, and — on an **unattended** run — whether the memory budget can
    afford it.

    Two-pass rejection holds ``_PEAK_CANVAS_ARRAYS_DRIZZLE_REJECT`` (7)
    full-canvas RGB planes against the single pass's ``_PEAK_CANVAS_ARRAYS`` (4):
    a 1.75× jump in the number :func:`_guard_stack_memory` refuses on. That is the
    right trade when a *watching* user submitted the run — the refusal names one
    concrete fix ("lower the drizzle scale to ×1.3") and they can act on it — so
    an attended run is passed through untouched and still refuses loudly.

    But the walk-away chains turn the pass on for the user (``_stack_target`` sets
    ``drizzle_reject`` alongside ``auto_reject`` when the merged options express no
    preference), and nobody is watching an unattended stack at 3 a.m. There, a
    refusal doesn't produce a better picture — it produces **no picture at all** on
    a target that made one yesterday, which is worse than the satellites the pass
    removes. The owner drizzles a mosaic union canvas, the largest canvas this app
    builds, so that is a real way for the v0.271.1 auto-enable to stop an install
    that works today. When the extra planes are what push the run over budget, the
    rejection is simply not taken and the run proceeds exactly as it did before it
    was ever auto-enabled.

    The posture comes from ``options.unattended``, not from ``auto_reject``.
    ``auto_reject`` looks like the same question ("the user expressed no
    preference") and was used for it until v0.281.0, but it isn't: the Stack form
    seeds ``auto_reject=True`` for a never-configured target
    (``get_stack_defaults``), so a beginner sitting *right there* posted it too and
    had their explicitly-ticked rejection quietly dropped instead of being handed
    the one-line fix — the opposite of what this docstring promised.

    Only the *rejection* is forgiven, never the canvas: this returns the
    single-pass answer, so a canvas that doesn't fit without the pass either is
    still refused by the guard — with a message and a suggested fix computed for
    the run that would actually be attempted.

    This lives in the engine rather than in ``_stack_target`` because pricing it
    needs the real output canvas, and for a mosaic that union canvas is computed
    inside :func:`run_stack`."""
    if not (options.drizzle and options.drizzle_reject and n >= 4):
        return False
    if not options.unattended:
        return True  # someone is watching — let the guard refuse loudly instead
    need, _ = _estimate_peak_bytes(
        dst_shape, drizzle=True, drizzle_scale=options.drizzle_scale,
        drizzle_reject=True)
    return need <= _stack_memory_budget_bytes(memory_budget_gb)


def _kappa_sigma_keep_mask(
    aligned: np.ndarray,
    mean_win: np.ndarray,
    std_win: np.ndarray,
    kappa: float,
) -> np.ndarray:
    """Per-pixel keep mask for the κ-σ pass-2 clip: keep a finite contribution
    unless it lies outside ``mean ± kappa·σ``.

    Two "no reference to clip against" cases widen to keep-all, so the clip can
    never turn real pass-2 data into a NaN coverage gap:

    * **σ unknown** (pass-1 ``n < 2`` → NaN std) → ``+inf`` tolerance, which
      keeps single-coverage mosaic-edge pixels (the ``WelfordAccumulator``
      variance contract).
    * **mean unknown** (pass-1 ``n == 0`` → NaN mean) → this pixel had *no*
      pass-1 coverage at all, so there is nothing to clip toward. Without this
      guard ``|aligned − NaN| ≤ tol`` is ``False`` and a frame that *does* cover
      the pixel in pass 2 is silently dropped to NaN — a black hole in the final
      image. Only reachable when pass-1 and pass-2 coverage diverge (a frame that
      failed to align in pass 1, e.g. a transient I/O error on a NAS over a long
      run, but succeeded in pass 2); when it happens the invariant "NaN = no
      coverage; never turn real data into a gap" must still hold, so keep it.

    An all-finite, fully-covered stack (the common case) has finite mean/σ
    everywhere covered, so both widenings are no-ops and the mask is byte-for-byte
    the plain ``mean ± kappa·σ`` test.
    """
    valid = np.isfinite(aligned)
    tol = kappa * np.where(np.isfinite(std_win), std_win, np.inf)
    within = ~np.isfinite(mean_win) | (np.abs(aligned - mean_win) <= tol)
    return valid & within


def estimate_stack(project: Project, options: StackOptions,
                   memory_budget_gb: float | None = None) -> StackEstimate:
    """Compute the output canvas dimensions and estimated peak working memory a
    stack *would* need, without running it.

    Mirrors ``run_stack``'s reference-pick and canvas-selection (reference vs
    union-of-footprints), then reuses ``_estimate_peak_bytes`` /
    ``_stack_memory_budget_bytes`` so the pre-run number matches the guard that
    would refuse the run. Only the canvas-affecting options are consulted
    (``drizzle``, ``drizzle_scale``, ``drizzle_reject``, ``mosaic_canvas``);
    everything else is irrelevant to sizing. Raises ``ValueError`` with the same
    guidance as ``run_stack`` when there's nothing solved to stack."""
    choice = pick_reference_frame(project)
    if choice is None:
        raise ValueError(
            "No accepted frames are plate-solved yet. Run Plate Solve first, "
            "and make sure at least one accepted frame solved successfully."
        )
    ref = choice.frame
    if not ref.wcs_json or ref.width_px is None or ref.height_px is None:
        raise ValueError("reference frame is missing WCS or dimensions")
    ref_shape = (int(ref.height_px), int(ref.width_px))

    frames = [
        f for f in project.iter_frames(accepted_only=True)
        if f.wcs_json and (f.cached_path or f.source_path)
    ]
    if not frames:
        raise ValueError("no accepted, plate-solved frames to stack")

    dst_shape = ref_shape
    is_mosaic = False
    if options.mosaic_canvas != "reference":
        try:
            from seestack.stack.mosaic import compute_mosaic_canvas

            canvas = compute_mosaic_canvas(frames, ref_shape)
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 — mirror run_stack's fallback
            log.warning("Mosaic canvas estimate failed (%s); "
                        "using reference-frame canvas", exc)
            canvas = None
        if canvas is not None and canvas.excluded_frame_ids:
            # Mirror run_stack: gross plate-solve outliers dropped during canvas
            # sizing don't reach the stacker, so they must not inflate the
            # estimate's frame count (or, where n straddles the n>=4 κ-σ / n>=3
            # min/max reject-method gate, its method and peak). Read-only here —
            # unlike run_stack this estimate never flags them rejected in the DB.
            bad = set(canvas.excluded_frame_ids)
            frames = [f for f in frames if getattr(f, "id", None) not in bad]
        if canvas is not None and (options.mosaic_canvas == "union"
                                   or canvas.is_mosaic):
            dst_shape = canvas.shape
            is_mosaic = canvas.is_mosaic

    n = len(frames)
    # Resolve auto-reject so the pre-run memory estimate matches the method
    # ``run_stack`` will actually use (min/max costs extra canvas planes), and the
    # drizzle half of the same question — an auto-enabled two-pass rejection is
    # only taken when it fits, so the estimate must not warn about planes the run
    # would decline to allocate.
    options = _resolve_auto_reject(options, n)
    options = replace(options, drizzle_reject=_afford_drizzle_reject(
        options, n, dst_shape, memory_budget_gb))
    peak, (out_h, out_w) = _estimate_peak_bytes(
        dst_shape, drizzle=options.drizzle, drizzle_scale=options.drizzle_scale,
        drizzle_reject=options.drizzle_reject,
        reject_arrays=(_min_max_reject_arrays(options.min_max_reject_count)
                       if options.min_max_reject and not options.drizzle and n >= 3
                       else 0),
        rejection_map=_records_rejection_map(options, n),
    )
    budget = int(_stack_memory_budget_bytes(memory_budget_gb))
    would_exceed = int(peak) > budget
    # The single least-destructive concrete fix (with its resulting peak) — the
    # same one the run-time guard would name, computed from the resolved options
    # so a k>1 min/max reject that busts the budget can offer "drop to k=1"
    # pre-submit, not only after a refusal.
    memory_fix = (
        _best_memory_fix(
            dst_shape, ref_shape, is_mosaic=is_mosaic, drizzle=options.drizzle,
            drizzle_scale=options.drizzle_scale,
            drizzle_reject=options.drizzle_reject,
            reject_arrays=(_min_max_reject_arrays(options.min_max_reject_count)
                           if options.min_max_reject and not options.drizzle
                           and n >= 3 else 0),
            rejection_map=_records_rejection_map(options, n),
            min_max_reject_count=options.min_max_reject_count, budget=budget)
        if would_exceed else None
    )
    suggested_scale: float | None = None
    suggest_ref_canvas = False
    if would_exceed and options.drizzle:
        suggested_scale = _largest_drizzle_scale_within_budget(
            dst_shape, drizzle_reject=options.drizzle_reject,
            budget=budget, max_scale=float(options.drizzle_scale),
        )
    elif would_exceed and is_mosaic:
        # Drizzle off and the union mosaic canvas alone blows the budget — would
        # the smaller reference-frame canvas fit? If so the UI can offer a
        # one-click "use the reference canvas instead". Charge the *same*
        # min/max-reject planes the main peak (and the run-time guard) charge, so
        # a k>1 reject can't make us suggest a reference canvas the guard would
        # then refuse with MemoryError (the suggestion must match the guard).
        ref_peak, _ = _estimate_peak_bytes(
            ref_shape, drizzle=False, drizzle_scale=1.0,
            reject_arrays=(_min_max_reject_arrays(options.min_max_reject_count)
                           if options.min_max_reject and n >= 3
                           else 0),
            rejection_map=_records_rejection_map(options, n))
        suggest_ref_canvas = int(ref_peak) <= budget
    return StackEstimate(
        n_frames=n,
        canvas_w=dst_shape[1], canvas_h=dst_shape[0],
        output_w=out_w, output_h=out_h,
        is_mosaic=is_mosaic,
        peak_bytes=int(peak), budget_bytes=budget,
        would_exceed=would_exceed,
        suggested_drizzle_scale=suggested_scale,
        suggested_reference_canvas=suggest_ref_canvas,
        memory_fix=memory_fix,
        print_plan=_print_plan(
            out_w, out_h, dst_shape,
            drizzle=options.drizzle, drizzle_scale=options.drizzle_scale,
            drizzle_reject=options.drizzle_reject,
            rejection_map=_records_rejection_map(options, n), budget=budget),
    )


CancelFn = Callable[[], bool]
ProgressFn = Callable[[str, int, int], None]


class StackCancelled(RuntimeError):
    """Raised internally when the user cancels mid-stack."""


def _integration_time_s(frames: list, n_used: int) -> float | None:
    """Effective integration time = median sub exposure × frames combined.

    The honest figure when a few candidate subs are dropped mid-stack. Returns
    ``None`` when no frame carries a usable exposure."""
    exposures = [
        float(f.exposure_s) for f in frames
        if getattr(f, "exposure_s", None) and f.exposure_s > 0
    ]
    if not exposures or not n_used:
        return None
    exposures.sort()
    per_sub = exposures[len(exposures) // 2]  # median
    return round(per_sub * n_used, 2)


def _capture_window(frames: list) -> tuple[str | None, str | None]:
    """When the subs going into this stack were *shot*: ``(earliest, latest)``
    ``timestamp_utc`` among ``frames``, verbatim as they were recorded.

    A stack's own ``timestamp_utc`` says when it *ran*, which is the wrong answer
    to "when was this picture taken" the moment anyone re-stacks — a Seestar
    owner arriving with a back catalogue gets a whole library whose every picture
    claims to have been shot on install day. Recording the window here is the
    only place that knows which subs actually went in.

    Ordering is by *parsed instant*, never by string: the app writes UTC stamps
    in more than one shape (a ``…Z`` suffix, a full ``+00:00`` offset, an
    occasional naive stamp), so a lexicographic min/max would pick whichever
    *spelling* sorts first. Undated frames are skipped; a set with nothing dated
    yields ``(None, None)`` and every caller drops the clause rather than
    guessing. Returns the recorded strings, not the parsed values, so nothing is
    normalised away on the way into the row.

    This is the *candidate* set — the same list :func:`_integration_time_s`
    medians over. A sub that failed mid-stack is not subtracted, so the window
    can be a little wider than the subs that truly contributed; it is a date
    range for a caption, not an accounting of contributions.
    """
    from seestack.activity_calendar import parse_utc

    dated = []  # (parsed instant, the string as recorded)
    for f in frames:
        raw = getattr(f, "timestamp_utc", None)
        if not raw:
            continue
        parsed = parse_utc(str(raw))
        if parsed is not None:
            dated.append((parsed, str(raw)))
    if not dated:
        return None, None
    return min(dated)[1], max(dated)[1]


def _capture_hours(frames: list) -> list[str]:
    """The distinct **UTC hours** this run's subs were shot in, sorted, written
    as instants on the hour (``"2024-11-15T21:00:00Z"``). ``[]`` when nothing is
    dated.

    Why this exists rather than a plain night *count*: the sentence a person
    actually says about a picture is *"600 subs over 4 nights"*, and an observing
    night is a **local** noon-to-noon bucket, so the count depends on the
    observer's longitude — which lives in ``webapp`` and which the engine may not
    import (AGENTS.md §6). Storing when the light arrived, and letting the read
    side bucket it, keeps the honest answer available for whatever location the
    owner later sets, instead of freezing a UTC-bucketed guess into the row.

    Why *hours* rather than the stamps themselves: a 500-sub run would otherwise
    write 500 timestamps into one row. Truncating to the hour caps the list at 24
    entries per observing day (a year of imaging is a few thousand), and costs
    nothing in accuracy — truncation can only move a frame across a night
    boundary if its hour *contains* local noon, which is broad daylight and not
    when subs are taken.

    Same candidate set as :func:`_capture_window`, for the same reason: it is a
    date range for a caption, not an accounting of which subs contributed.
    """
    from seestack.activity_calendar import parse_utc

    hours = set()
    for f in frames:
        raw = getattr(f, "timestamp_utc", None)
        if not raw:
            continue
        parsed = parse_utc(str(raw))
        if parsed is not None:
            hours.add(parsed.strftime("%Y-%m-%dT%H:00:00Z"))
    return sorted(hours)


# A mosaic panel needs at least this many measured subs before it counts as a
# separable pointing group (the same floor the photometric pass uses).
_TRANSPARENCY_PANEL_MIN_FRAMES = 3


def _panel_transparency_ratios(all_rows: list, run_rows: list) -> list[float]:
    """Per-**mosaic-panel** ``median(run) / p90(all)`` ratios, or ``[]``.

    ``transparency_score`` is the median flux of a frame's brightest stars, so it
    is a property of where the scope pointed as much as of the sky. A mosaic's
    panels are different star fields, so one target-wide p90 baseline is set by
    the richest panel and every other panel reads as haze — measured on a
    synthetic 3-panel mosaic shot under a perfectly steady sky: ratio **0.50**,
    i.e. a "Hazy night" badge claiming "~50% below this target's clearest
    nights". (Same class of mistake as the target-wide QC grading fixed in
    v0.270.2 and the target-wide photometric reference fixed in v0.271.0.)

    Returns ``[]`` — meaning "use the one target-wide baseline, exactly as
    before" — unless the pointings split soundly (the shared
    :func:`~seestack.stack.pointings.pointing_groups` gate) *and* at least two
    panels carry the same sample this function has always demanded on both sides
    (5 baseline frames, 3 run frames). So a single-field target, an unsolved
    target and a too-tightly-packed mosaic are all bit-for-bit unaffected.
    """
    from seestack.stack.pointings import pointing_groups

    radecs = [(f.ra_center_deg, f.dec_center_deg) for f in all_rows + run_rows]
    labels = pointing_groups(radecs, min_members=_TRANSPARENCY_PANEL_MIN_FRAMES)
    if labels is None:
        return []
    n_all = len(all_rows)
    base: dict[int, list[float]] = {}
    for label, f in zip(labels[:n_all], all_rows, strict=True):
        if label >= 0:
            base.setdefault(label, []).append(float(f.transparency_score))
    run: dict[int, list[float]] = {}
    for label, f in zip(labels[n_all:], run_rows, strict=True):
        if label >= 0:
            run.setdefault(label, []).append(float(f.transparency_score))

    ratios: list[float] = []
    for label, run_scores in run.items():
        base_scores = base.get(label, [])
        if len(base_scores) < 5 or len(run_scores) < 3:
            continue
        baseline = float(np.percentile(base_scores, 90))
        if baseline <= 0:
            continue
        ratios.append(float(np.percentile(run_scores, 50)) / baseline)
    # One panel's ratio is just the target-wide answer with a smaller sample —
    # only a real split (≥2 measurable panels) is worth preferring over it.
    return ratios if len(ratios) >= 2 else []


def _compute_transparency_ratio(project: Project, frames: list) -> float | None:
    """Median transparency of the stacked frames vs this target's clear-sky
    baseline, normalised within the target (the raw ``transparency_score`` isn't
    comparable across gain/exposure).

    Returns ``median(run) / p90(all)`` — a value well below 1.0 means the stack
    was shot through haze / thin cloud relative to the target's clearest nights.
    Mirrors the Stack form's pre-run hint so a completed run can carry the same
    verdict for an at-a-glance "hazy night" badge. ``None`` when there isn't a
    meaningful sample on both sides. Best-effort: never raises into the caller.

    On a **mosaic** the comparison is made panel by panel and the panels' ratios
    combined (median), because comparing one panel's star field against another's
    is not a measure of the sky — see :func:`_panel_transparency_ratios`.
    """
    try:
        run_rows = [f for f in frames
                    if getattr(f, "transparency_score", None) and f.transparency_score > 0]
        all_rows = [f for f in project.iter_frames()
                    if f.transparency_score is not None and f.transparency_score > 0]
        # Need a reasonable sample on both sides to say anything meaningful.
        if len(all_rows) < 5 or len(run_rows) < 3:
            return None
        per_panel = _panel_transparency_ratios(all_rows, run_rows)
        if per_panel:
            return round(float(np.median(per_panel)), 4)
        baseline = float(np.percentile([f.transparency_score for f in all_rows], 90))
        if baseline <= 0:
            return None
        run_med = float(np.percentile([f.transparency_score for f in run_rows], 50))
        return round(run_med / baseline, 4)
    except Exception:  # noqa: BLE001 — a diagnostic must never break the stack
        return None


def _compute_stack_fwhm(
    rgb: np.ndarray, *, drizzle: bool, drizzle_scale: float,
) -> float | None:
    """Median star size (FWHM) of the finished stack, in *native-frame* pixels.

    The per-run counterpart of :func:`_compute_noise_sigma`: it turns "are the
    stars sharp?" into one number a user can compare across their stacks of a
    target (lower = tighter stars), the way noise σ answers "is it clean?".

    Measured to match the per-frame QC ``fwhm_px`` so the value is comparable to
    it (and to the target-wide frame median): QC detects on a *half-resolution*
    green plane (``green_channel``), so we 2×2 block-average the stacked green
    plane before detecting — putting a non-drizzle stack on exactly that sampling
    — then divide out the drizzle super-resolution so the result is always in
    native-frame pixels regardless of canvas scale. Reuses the existing
    ``detect_stars``/``median_fwhm`` (no new detection pass elsewhere).

    Best-effort: any failure (too few stars, a fit that won't converge, a mono
    canvas) returns ``None`` and never raises into the stack.
    """
    try:
        from seestack.qc.metrics import detect_stars, estimate_sky, median_fwhm

        green = rgb[..., 1] if rgb.ndim == 3 else rgb
        green = np.asarray(green, dtype=np.float32)
        # 2×2 block-average to the half-res sampling QC's green_channel uses, so a
        # non-drizzle stack's FWHM lands on the same footing as a frame's. Crop to
        # even dims first; skip (too small to mean anything) if either axis < 4.
        h, w = green.shape[:2]
        if h < 4 or w < 4:
            return None
        h2, w2 = h - (h % 2), w - (w % 2)
        half = 0.25 * (
            green[0:h2:2, 0:w2:2] + green[1:h2:2, 0:w2:2]
            + green[0:h2:2, 1:w2:2] + green[1:h2:2, 1:w2:2]
        )
        if not np.isfinite(half).any():
            return None
        # detect_stars/median_fwhm are NaN-intolerant in the sky estimate; the
        # stacked canvas carries NaN = no-coverage, so fill gaps with the robust
        # sky median before detection (a no-op on a fully-covered single field).
        finite = half[np.isfinite(half)]
        if finite.size == 0:
            return None
        half = np.where(np.isfinite(half), half, float(np.median(finite)))
        sky_med, sky_std = estimate_sky(half)
        sources = detect_stars(half, sky_median=sky_med, sky_std=sky_std)
        fwhm = median_fwhm(half, sources)
        if fwhm is None or not np.isfinite(fwhm):
            return None
        # Undo drizzle super-resolution: the block-averaged green is drizzle_scale×
        # finer than native, so its FWHM in pixels is that much larger.
        scale = float(drizzle_scale) if drizzle else 1.0
        if scale <= 0:
            scale = 1.0
        return round(float(fwhm) / scale, 3)
    except Exception:  # noqa: BLE001 — a diagnostic must never break the stack
        return None


def _compute_noise_sigma(rgb: np.ndarray) -> float | None:
    """Background-noise σ of the finished stack, normalized to its own signal
    range so the value is comparable across gain/exposure (lower = cleaner).

    Reuses the editor's robust adjacent-pixel-difference estimator so a user can
    compare several stacks of one target by a number rather than by eye. Records
    the run's cleanliness for the History/Gallery "cleanest stack" readout.
    Best-effort: never raises into the caller."""
    try:
        from seestack.edit.noise import estimate_noise_sigma
        sigma = estimate_noise_sigma(rgb)
        return round(float(sigma), 5) if sigma is not None else None
    except Exception:  # noqa: BLE001 — a diagnostic must never break the stack
        return None


def _compute_seam_residual(
    rgb: np.ndarray,
    coverage: np.ndarray,
    frame_coverage: np.ndarray | None,
    *,
    is_mosaic: bool,
) -> float | None:
    """How flat this mosaic's panel joins actually came out (``None`` if N/A).

    The per-coverage leveling pass pushes every coverage level's sky to zero,
    but it can't always succeed — an unreadable level takes a neighbour's
    interpolated offset, and one filled by real structure is deliberately left
    alone — and until now **nothing checked the result**, so the one mosaic
    failure mode a beginner can see but not diagnose (a coloured seam grid) was
    found only by a human eyeballing an export.

    Measured on the *finished* image, so it accounts for everything downstream
    of leveling too. Returns the residual step in units of the picture's own
    grain (see :class:`~seestack.bg.coverage_leveling.SeamResidual`).

    Only runs on a **mosaic** canvas: a single-field stack has one coverage
    level and therefore no joins to compare, so it costs nothing on the ordinary
    path. Best-effort — a diagnostic must never break a finished stack.
    """
    if not is_mosaic:
        return None
    try:
        from seestack.bg.coverage_leveling import measure_seam_residual

        result = measure_seam_residual(
            rgb, coverage, frame_coverage=frame_coverage)
        return round(float(result.ratio), 4) if result is not None else None
    except Exception:  # noqa: BLE001 — a diagnostic must never break the stack
        return None


@dataclass
class RejectionStats:
    """How much a rejection pass actually clipped, measured while it ran.

    A memory-free trust signal: the standard κ-σ pass-2 already computes a
    per-pixel ``keep`` mask, so we sum two scalars over it — the total samples
    that contributed (finite/covered) and the subset that failed the κ-σ test —
    without allocating any extra canvas. ``fraction`` is the share of covered
    samples the rejection removed; a healthy value is small (transient outliers
    — satellites, planes, cosmic rays), while a large one flags a too-tight κ
    that may be eating real signal. Stamped into the FITS header + surfaced on
    the History Info panel so the user can trust the rejection did its job."""

    mode: str
    n_contributed: int
    n_rejected: int

    @property
    def fraction(self) -> float:
        return self.n_rejected / self.n_contributed if self.n_contributed else 0.0


def _build_output_header_meta(
    project: Project, frames: list, options: StackOptions, n_used: int,
    wstats: WeightingStats | None = None,
    calibration: "Any | None" = None,
    pstats: PhotometricStats | None = None,
    photometric_auto: bool = False,
    rstats: "RejectionStats | None" = None,
    weights_applied: bool = True,
    n_roughly_aligned: int = 0,
    refine_active: bool | None = None,
    n_unreadable: int = 0,
    n_read_errors: int = 0,
    n_read_recovered: int = 0,
    drizzle_reject_declined: bool = False,
    drizzle_scale_requested: float | None = None,
    min_max_reject_count_requested: int | None = None,
    rejection_map_written: bool | None = None,
) -> dict[str, Any]:
    """Collect provenance for the output FITS header.

    Records the target name, frame count, integration time, per-sub exposure and
    stacking method so the saved ``master.fits`` self-documents how it was made
    (Siril/PixInsight/APP surface these keys). Best-effort: any lookup that fails
    is simply omitted rather than aborting the write.

    ``EXPTOTAL`` is the effective integration time — the median sub exposure times
    the number of frames that actually contributed (``n_used``), which is the
    honest figure when a few candidate subs were dropped mid-stack.
    """
    meta: dict[str, Any] = {}
    try:
        name = project.get_meta("name")
        if name:
            meta["OBJECT"] = (name, "target name")
    except Exception:  # noqa: BLE001 — provenance is non-critical
        pass
    if n_used:
        meta["NFRAMES"] = (int(n_used), "frames combined")
    exposures = [
        float(f.exposure_s) for f in frames
        if getattr(f, "exposure_s", None) and f.exposure_s > 0
    ]
    if exposures:
        exposures.sort()
        per_sub = exposures[len(exposures) // 2]  # median
        meta["EXPOSURE"] = (round(per_sub, 3), "per-sub exposure (s)")
        total = _integration_time_s(frames, n_used)
        if total is not None:
            meta["EXPTOTAL"] = (total, "integration time (s)")
    # When the light in this master was actually collected. The master carried no
    # capture time at all until now — so a file opened in Siril/PixInsight, and
    # the app's own acquisition nameplate (which reads this card), had no date to
    # show, while this module's docstring claimed otherwise. DATE-OBS is the
    # first sub's start and DATE-END the last sub's, which is the FITS
    # convention for a combined frame; both are omitted when no sub carries a
    # capture time, exactly as every other card here degrades.
    capture_start, capture_end = _capture_window(frames)
    if capture_start:
        meta["DATE-OBS"] = (capture_start, "start of the first sub combined")
    if capture_end and capture_end != capture_start:
        meta["DATE-END"] = (capture_end, "start of the last sub combined")
    # Label the method the dispatcher actually ran, applying the *same* frame-count
    # gates it uses (`min_max_reject and n >= 3`, `sigma_clip and n >= 4`): below
    # those counts the dispatcher silently falls through to plain mean (no rejection
    # pass runs — REJMODE is correctly absent), so a 3-frame default stack or a
    # 2-frame min-max stack must record STACKER="mean", not the rejection method.
    # `len(frames)` here is the candidate count `n` the dispatcher gated on.
    n = len(frames)
    if options.drizzle:
        method = "drizzle"
    elif options.min_max_reject and n >= 3:
        method = "min-max-reject"
    elif options.sigma_clip and n >= 4:
        method = "sigma-clip"
    else:
        method = "mean"
    meta["STACKER"] = (method, "stacking method")
    meta["COLORTYP"] = ("mono" if options.mono else "OSC", "sensor/stack colour mode")
    # Calibration provenance: which masters were actually applied to the lights
    # ("dark+flat", "bias+flat", "flat", …) so a calibrated stack self-documents.
    # Omitted when nothing was applied (describe() == "none").
    if calibration is not None:
        applied = calibration.describe()
        if applied and applied != "none":
            meta["CALSTAT"] = (applied, "calibration masters applied")
    # Dark exposure-scaling provenance: when the (off-by-default) scale_dark_to_light
    # option actually scaled a master dark to the subs' integration time — i.e. the
    # option was on, a master bias was present to hold the pedestal fixed, a dark
    # was set, and the dark's exposure differs from the subs' — record both
    # exposures so the run Info / History can show "Dark scaled to sub exposure ·
    # 30s → 10s" and the user can trust the off-by-default feature did something.
    # The scale is applied per-frame, so this stamps the run-level option + the
    # (median) exposures, not a per-pixel value. Omitted (like PHOTNORM) whenever
    # nothing was actually scaled — matched exposures leave the dark unscaled.
    # The "did it actually scale?" test is asked of the bundle itself
    # (``dark_scaling_provenance``) rather than re-derived here: this stamp used
    # to check only that *a* bias was loaded, but a bias whose shape doesn't
    # match the dark can't hold the pedestal fixed, so the engine subtracts the
    # dark unscaled — and the run then claimed "Dark scaled to sub exposure ·
    # 30s → 10s" about a dark it hadn't touched.
    if calibration is not None and getattr(calibration, "scale_dark_to_light", False):
        light_exp = exposures[len(exposures) // 2] if exposures else None
        provenance = getattr(calibration, "dark_scaling_provenance", None)
        scaled = provenance(light_exp) if callable(provenance) else None
        if scaled is not None:
            dark_exp, light_exp = scaled
            meta["DARKSCAL"] = ("exposure", "dark exposure-scaling mode")
            meta["DARKDEXP"] = (round(float(dark_exp), 3), "master dark exposure (s)")
            meta["DARKLEXP"] = (round(float(light_exp), 3),
                                "sub exposure dark scaled to (s)")
    # Quality-weighting provenance: lets the run Info panel report how many subs
    # weighting actually demoted and over what range, so the user can trust the
    # (off-by-default) weighting did something and gauge how aggressive it was.
    # Only stamp it when the weights actually influenced the result: the min/max
    # order-statistic path (min_max_reject on a ≥3-frame non-drizzle stack)
    # combines by rank and *ignores* per-frame weights entirely, so a stack with
    # both quality_weighted and min_max_reject on must not claim "N frames
    # down-weighted" — the weights had no effect there (weights_applied=False).
    if wstats is not None and wstats.n_weighted and weights_applied:
        meta["WGTMODE"] = ("quality", "frame weighting mode")
        meta["WGTNDOWN"] = (int(wstats.n_downweighted), "frames down-weighted")
        meta["WGTMIN"] = (round(float(wstats.min_weight), 3), "min frame weight")
        meta["WGTMAX"] = (round(float(wstats.max_weight), 3), "max frame weight")
        meta["WGTMED"] = (round(float(wstats.median_weight), 3), "median frame weight")
    # …and the mirror image: weighting was asked for and computed, but the path
    # that ran ignores it. Stamping *nothing* (the WGTMODE gate above) is honest
    # about the result but silent about the cause — and on the walk-away chains
    # (watcher auto-stack / one-click Process target) the user never sees the
    # Stack form's pick-time warning, so "quality weighting had no effect" is
    # indistinguishable from "weighting was off". Record the reason instead.
    # ``auto`` vs ``manual`` matters to the wording: an auto-picked min/max
    # switches itself back to weight-respecting κ-σ once the stack is big enough
    # (WGTSKMIN frames), which is a *wait for more subs* answer; an explicitly
    # ticked min/max is a *change this setting* answer.
    elif wstats is not None and wstats.n_weighted and not weights_applied:
        meta["WGTSKIP"] = ("minmax", "weighting requested but not applied")
        meta["WGTSKAUT"] = (bool(options.auto_reject), "min/max was auto-picked")
        if options.auto_reject:
            meta["WGTSKMIN"] = (int(kappa_min_frames(options.sigma_kappa)),
                                "frames needed for weighting to apply")
    # Photometric-normalization provenance: records that frames were gain-matched
    # and over what scale range, so a normalised stack self-documents (mirrors the
    # WGT* keys). Omitted when nothing was actually scaled.
    if pstats is not None and pstats.n_scaled:
        meta["PHOTNORM"] = ("transparency", "photometric normalization mode")
        meta["PHOTNADJ"] = (int(pstats.n_adjusted), "frames photometrically scaled")
        # …and whether the *user* asked for it or the mosaic path turned it on
        # itself (mirrors the auto-for-mosaic final gradient pass), so a run the
        # user never ticked a box for still explains itself.
        meta["PHOTAUTO"] = (bool(photometric_auto), "auto-enabled for a mosaic")
        meta["PHOTMIN"] = (round(float(pstats.min_scale), 3), "min frame scale")
        meta["PHOTMAX"] = (round(float(pstats.max_scale), 3), "max frame scale")
        meta["PHOTMED"] = (round(float(pstats.median_scale), 3), "median frame scale")
        # …and how many panels were matched against *themselves* rather than
        # against each other, so a mosaic's owner can see the normalization
        # didn't reach across the join. Omitted on a single-field run.
        if pstats.n_pointing_groups:
            meta["PHOTPANL"] = (int(pstats.n_pointing_groups),
                                "panels normalized against themselves")
    # Rejection provenance: how much the κ-σ pass actually clipped, so the user
    # can trust the rejection removed transient outliers (satellites/planes)
    # without over-clipping real signal. Stamped whenever a rejection pass ran
    # (n_contributed > 0), even at 0% — "clipped nothing" is itself a signal.
    if rstats is not None and rstats.n_contributed > 0:
        meta["REJMODE"] = (rstats.mode, "outlier rejection method")
        meta["REJFRAC"] = (round(float(rstats.fraction), 6),
                           "fraction of samples rejected")
        meta["REJNREJ"] = (int(rstats.n_rejected), "samples rejected")
        meta["REJNTOT"] = (int(rstats.n_contributed), "samples contributed")
        # …and whether the *spatial* record of those drops was kept beside the
        # picture, so a consumer can tell "this run wasn't asked to record where"
        # from "it recorded, and nothing was removed" without stat()-ing a file.
        if rejection_map_written is not None:
            meta["REJMAP"] = (bool(rejection_map_written),
                              "per-pixel rejection map written")
    # …and the other half of that story: an auto-enabled drizzle rejection the
    # memory budget couldn't afford, which the run deliberately skipped rather
    # than refusing outright (see :func:`_afford_drizzle_reject`). Stamped so the
    # finished picture self-documents *why* it carries no REJMODE, long after the
    # server log has rolled.
    if drizzle_reject_declined:
        meta["DRZREJSK"] = ("memory", "drizzle rejection skipped (over budget)")
    # …and the same story one level up: an unattended run whose *canvas* didn't fit,
    # stepped down to the largest super-resolution scale the budget could hold
    # rather than refusing to make a picture at all. ``options.drizzle_scale`` here
    # is already the scale that ran (the caller passes the effective options), so
    # the pair reads "asked for ×1.5, made ×1.3" — the finished image explains its
    # own size without anyone finding the job log.
    if drizzle_scale_requested is not None:
        meta["DRZSCLAD"] = (round(float(options.drizzle_scale), 4),
                            "drizzle scale lowered to fit memory budget")
        meta["DRZSCLRQ"] = (round(float(drizzle_scale_requested), 4),
                            "drizzle scale originally requested")
    # …and the same story for the *non-drizzle* lever: an unattended run whose
    # extra outlier passes didn't fit, stepped back to the single min/max drop
    # rather than refusing to make a picture. Nothing about the picture's size or
    # shape changed, so this is quieter than DRZSCLAD — but a header that says so
    # is how a REJMODE of "min/max ×1" on a run configured for ×3 explains itself
    # long after the job log has rolled.
    if min_max_reject_count_requested is not None:
        meta["REJKAD"] = (int(options.min_max_reject_count),
                          "extremes/side lowered to fit memory")
        meta["REJKRQ"] = (int(min_max_reject_count_requested),
                          "extremes/side originally requested")
    # Frame-accounting provenance: how many of the subs the stacker *attempted*
    # to combine actually made it in. ``frames`` here is the post-filter list the
    # passes iterated (after lucky-imaging selection and any gross plate-solve
    # outlier exclusion), and ``n_used`` is how many contributed — so a frame that
    # couldn't be loaded, or whose footprint didn't intersect the canvas (a stray
    # sub from a different target, a bad plate-solve), shows up as the gap. Persisting
    # it in the header means the History Info panel can honestly report "1,850 of
    # 2,000 subs combined; 150 couldn't be aligned" long after the Jobs page is gone,
    # and flag a large align-failure fraction (usually mixed targets / bad solves).
    n_offered = len(frames)
    if n_offered:
        n_failed = max(0, n_offered - int(n_used))
        meta["NOFFERED"] = (int(n_offered), "subs offered to the stacker")
        meta["NALIGNFL"] = (int(n_failed), "subs that could not be aligned")
        # How many of those failures were simply *missing files* — neither the
        # Stage-1 cache nor the original source was on disk when the run started
        # (a cleared cache plus an offline NAS share, an unmounted drive, moved
        # files). Without this the whole gap reads as "couldn't be aligned",
        # which sends the user hunting for mixed targets or bad plate-solves
        # when the real fix is to plug the drive back in. Stamped alongside
        # NALIGNFL (0 included) so its absence means "older master", not "none".
        meta["NUNREAD"] = (int(max(0, n_unreadable)),
                           "subs whose file was not on disk")
        # …and the *other* storage failure, which NUNREAD can't see: a sub whose
        # file was there at the preflight but blew up when a worker actually read
        # it (a flaking NAS share, a bad sector, a half-written file). Those only
        # ever reached the run's per-frame ``errors`` list, which no screen reads,
        # so a night of dropped reads looked like ordinary align failures.
        # NREADREC is the reassuring half: of those subs, how many the *other*
        # pass of a two-pass run read fine and combined anyway (see
        # ``_mark_recovered_errors``), so their light IS in the picture. Stamped
        # beside NUNREAD, 0 included, so absence means "older master", not "none".
        meta["NREADERR"] = (int(max(0, n_read_errors)),
                            "subs that hit a read error")
        meta["NREADREC"] = (int(max(0, min(n_read_recovered, n_read_errors))),
                            "of those, subs combined on the other pass")
    # Sub-pixel refine accounting: how many contributing subs the refine step
    # had to leave *only roughly aligned* (its measured shift exceeded the cap,
    # so the frame stacked unshifted). Softer/doubled stars the user sees but
    # can't otherwise explain. Stamped only when refine actually ran (so the
    # card's absence means "refine off / older master", not "0 flagged"), even
    # at 0 — "nothing was rough" is itself an honest, reassuring signal (mirrors
    # REJFRAC stamping at 0%). Drizzle uses a pixmap, not the refine step, so it
    # never leaves a frame "roughly aligned" — don't stamp a meaningless 0 there.
    # ``refine_active=False`` means refine was asked for but stood down before any
    # frame (no usable reference patch), which is the same "it didn't run" as the
    # option being off — so omit the card rather than claim nothing was rough.
    # ``None`` (a caller that doesn't know) keeps the option-only gate.
    if options.subpixel_refine and not options.drizzle and refine_active is not False:
        meta["NROUGHAL"] = (int(max(0, n_roughly_aligned)),
                            "subs only roughly aligned (over cap)")
    return meta


def run_stack(
    project: Project,
    options: StackOptions,
    *,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
    memory_budget_gb: float | None = None,
    app_version: str | None = None,
) -> StackResult:
    """
    Execute a stacking run end-to-end. Synchronous — call this from a worker
    thread if you want a responsive GUI.

    ``app_version`` (optional) is recorded on the resulting ``stack_runs`` row for
    provenance — the webapp passes its ``__version__`` so History can show which
    build produced each image. The engine never imports the webapp, so it's passed
    in rather than looked up; ``None`` leaves the run's version unrecorded.
    """
    progress = progress or (lambda *a: None)
    cancel = cancel or (lambda: False)

    if not (0.0 < options.lucky_fraction <= 1.0):
        raise ValueError(
            f"lucky_fraction must be in (0, 1], got {options.lucky_fraction!r}"
        )
    # Sanitize up front (not just inside write_stack_outputs) so the
    # quick-look preview path below — which builds its own filename from
    # options.output_name — can't be used to escape <project>/output/ either.
    options.output_name = _sanitize_basename(options.output_name)

    # ---- 1. Pick reference -------------------------------------------------
    progress("Setup", 0, 1)
    choice = pick_reference_frame(project)
    if choice is None:
        raise ValueError(
            "No accepted frames are plate-solved yet. Run Plate Solve first, "
            "and make sure at least one accepted frame solved successfully."
        )
    ref = choice.frame
    if not ref.wcs_json or ref.width_px is None or ref.height_px is None:
        raise ValueError("reference frame is missing WCS or dimensions")
    ref_shape = (int(ref.height_px), int(ref.width_px))

    # ---- 2. Build frame list ----------------------------------------------
    frames = [
        f for f in project.iter_frames(accepted_only=True)
        if f.wcs_json and (f.cached_path or f.source_path)
    ]
    if not frames:
        raise ValueError("no accepted, plate-solved frames to stack")

    # ---- 1a. Load calibration masters (once, shared across workers) --------
    calibration = None
    # Advisory master-dark mismatches, carried out on the result so the *user*
    # sees them (they used to reach the server log only — see StackResult).
    calib_warnings: list[str] = []
    if options.dark_path or options.flat_path or options.bias_path:
        from seestack.calibrate.apply import CalibrationMasters

        calibration = CalibrationMasters.load(
            options.dark_path, options.flat_path, options.flat_dark_path,
            options.bias_path,
            scale_dark_to_light=options.scale_dark_to_light,
        )
        if calibration.is_empty:
            calibration = None
        else:
            # Fail fast on a camera/binning mismatch (raw dims = the un-debayered
            # reference frame size) rather than silently skipping every frame.
            calibration.validate(ref_shape)
            log.info("Calibration: applying %s master(s)", calibration.describe())
            # Advisory (non-fatal): a master dark whose exposure/temperature
            # doesn't match the lights silently over/under-subtracts on every
            # frame. Log it *and* carry it out on the result, so the walk-away
            # user who never opens the server log still learns why their picture
            # came out crushed or grainy — the reference frame's exposure/
            # temperature stands in for the (uniform) session.
            calib_warnings = list(calibration.calibration_warnings(
                ref.exposure_s, ref.sensor_temp_c
            ))
            for _warn in calib_warnings:
                log.warning("Calibration: %s", _warn)

    # ---- 1b. Build the output canvas --------------------------------------
    # For a single-target stack the reference frame's footprint is fine. For a
    # mosaic the canvas must be the *union* of all footprints, or off-panel
    # frames have nowhere to land and overlap edges get bright contamination.
    dst_shape = ref_shape
    dst_wcs_text = ref.wcs_json
    is_mosaic_canvas = False
    excluded_frames: list[str] = []
    if options.mosaic_canvas != "reference":
        try:
            from seestack.stack.mosaic import compute_mosaic_canvas

            canvas = compute_mosaic_canvas(frames, ref_shape)
        except ValueError as exc:
            # Canvas too large — surface it; this is a real problem to fix.
            raise ValueError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            log.warning("Mosaic canvas computation failed (%s); "
                        "using reference-frame canvas", exc)
            canvas = None
        if canvas is not None:
            # Frames dropped as gross plate-solve outliers during canvas sizing
            # must also be excluded from the stack — otherwise they'd reproject
            # to the wrong place (or off-canvas) and contaminate the result.
            if canvas.excluded_frame_ids:
                bad = set(canvas.excluded_frame_ids)
                dropped = [f for f in frames if getattr(f, "id", None) in bad]
                frames = [f for f in frames if getattr(f, "id", None) not in bad]
                for f in dropped:
                    label = Path(f.source_path).name if f.source_path else f"frame {f.id}"
                    excluded_frames.append(label)
                    # Flag it rejected so it's visible in the Frames table and
                    # doesn't keep breaking this (and future) stacks.
                    try:
                        project.update_frame(
                            f.id, accept=False,
                            reject_reason="bad plate-solve (footprint far from the group)",
                        )
                    except Exception as exc:  # noqa: BLE001 — flagging is best-effort
                        log.warning("Could not flag outlier frame %s: %s", f.id, exc)
                log.warning(
                    "Excluded %d frame(s) with a bad plate-solve from the stack "
                    "and flagged them rejected: %s", len(dropped), excluded_frames,
                )
            use_union = options.mosaic_canvas == "union" or canvas.is_mosaic
            if use_union:
                dst_wcs_text = canvas.wcs_text
                dst_shape = canvas.shape
                is_mosaic_canvas = canvas.is_mosaic
                log.info(
                    "Output canvas: %d×%d union of %d footprints "
                    "(span %.2f°, %s)",
                    dst_shape[1], dst_shape[0], canvas.n_footprints,
                    canvas.span_deg,
                    "mosaic" if canvas.is_mosaic else "forced union",
                )
            else:
                log.info("Output canvas: %d×%d reference frame "
                         "(footprints fit within one field)",
                         dst_shape[1], dst_shape[0])
    log.info("Stack reference: id=%s ref_shape=%s span=%.3f° (%d candidates)",
             ref.id, ref_shape, choice.span_deg, choice.n_candidates)

    # Lucky imaging: filter to the top fraction by FWHM (sharper = better).
    if options.lucky_fraction < 1.0:
        with_fwhm = [f for f in frames if f.fwhm_px is not None]
        without_fwhm = [f for f in frames if f.fwhm_px is None]
        if with_fwhm:
            n_keep = max(1, int(len(with_fwhm) * options.lucky_fraction))
            with_fwhm.sort(key=lambda f: f.fwhm_px)  # type: ignore[return-value, arg-type]
            kept = with_fwhm[:n_keep]
            log.info(
                "Lucky imaging: keeping top %d of %d frames (cutoff FWHM %.2f)",
                n_keep, len(with_fwhm),
                with_fwhm[n_keep - 1].fwhm_px or 0.0,
            )
            frames = kept + without_fwhm

    # Readability preflight over the *final* frame list (post lucky-imaging), so
    # the run can name a storage problem instead of leaving it to look like an
    # alignment one. ``_align_for_stack`` already skips a frame with nothing to
    # read, silently, as a benign failure — a target whose Stage-1 cache was
    # cleared while its originals sit on an offline share therefore produces a
    # thin stack (or "no frames could be aligned") with no plain-language reason.
    # One stat() per frame, off the pixel hot path.
    n_unreadable = count_unreadable_frames(frames)
    if n_unreadable:
        log.warning(
            "%d of %d subs have no readable file (neither the Stage-1 cache nor "
            "the original source is on disk) — they cannot be stacked",
            n_unreadable, len(frames),
        )

    # Build the per-frame weight map. Defaults to all-1.0 unless quality_weighted.
    # On a mosaic the star-count / sky / transparency medians are taken per panel
    # rather than target-wide: those three metrics depend on *where the scope
    # pointed*, and target-wide they can only penalise a panel aimed at an
    # emptier patch of sky (measured 0.73×, i.e. a quarter of that panel's depth
    # thrown away for no reason). See ``weighting``'s module docstring.
    wstats: WeightingStats | None = None
    if options.quality_weighted:
        weights, wstats = compute_frame_weights(
            frames, group_by_pointing=bool(is_mosaic_canvas))
        log.info(
            "Quality weights: %d weighted (median=%.2f range=[%.2f, %.2f]), %d neutral",
            wstats.n_weighted, wstats.median_weight, wstats.min_weight,
            wstats.max_weight, wstats.n_neutral,
        )
    else:
        weights = unit_weights(frames)

    # Build the per-frame photometric scale map (all-1.0 unless enabled). Applied
    # to each frame's pixels *before* accumulation so it flows consistently
    # through every accumulator and rejection path (κ-σ, min/max, drizzle).
    #
    # Auto-enabled on a mosaic canvas for the same reason the final-stack
    # gradient pass below is (and with the same shape): a mosaic's panels are
    # shot at different times through different air, and the corrections that
    # already run automatically only touch the *sky*. The per-frame background
    # flatten removes each frame's additive sky offset and the coverage-leveling
    # pass removes the panel-to-panel sky step — but a panel shot through haze is
    # dimmed **multiplicatively**, which leaves the sky alone and survives both.
    # Gain-matching the frames is the correction for that, so a mosaic gets it
    # without the user having to know the word. Self-neutralising: a run whose
    # subs carry no usable transparency score scales nothing (``n_scaled == 0``)
    # and comes out byte-for-byte as before.
    #
    # On a mosaic the panels are matched against **themselves**, never against
    # each other (``group_by_pointing``): ``transparency_score`` is the median
    # flux of a frame's brightest stars, so a panel aimed at an emptier patch of
    # sky reads as "hazy" to a target-wide comparison and gets gain-matched away
    # from its neighbours — measured at a 2.2× panel step. See
    # ``photometric._pointing_references``.
    pscales: dict[int, float] | None = None
    pstats: PhotometricStats | None = None
    photometric_auto = bool(is_mosaic_canvas) and not options.photometric_normalize
    if options.photometric_normalize or is_mosaic_canvas:
        pscales, pstats = compute_photometric_scales(
            frames, group_by_pointing=bool(is_mosaic_canvas))
        log.info(
            "Photometric normalization%s: %d scaled (median=%.3f range=[%.3f, %.3f]), "
            "%d adjusted, %d neutral, %d panel(s)",
            " (auto for mosaic)" if photometric_auto else "",
            pstats.n_scaled, pstats.median_scale, pstats.min_scale,
            pstats.max_scale, pstats.n_adjusted, pstats.n_neutral,
            pstats.n_pointing_groups,
        )
        # Nothing measurable → don't carry a no-op scale map (keeps the hot path
        # and the provenance honest).
        if pstats.n_scaled == 0:
            pscales = None
            photometric_auto = False

    # Inverse-variance combine weight: gain-matching a hazy frame up by ``s``
    # amplifies its noise by ``s`` too, so the *weighted-sum* combine down-weights
    # it by ``1/s²`` (and a scaled-down transparent frame is trusted more). Only
    # the final weighted combines (single-pass mean, κ-σ pass 2, drizzle final)
    # use these; the rejection-reference passes (κ-σ pass 1, min/max, drizzle
    # statistics) keep the plain quality ``weights``. When photometric scaling is
    # off (``pscales`` is None), this returns ``weights`` unchanged → byte-for-byte
    # identical stack. NB: the weighted-sum accumulator's coverage map is Σ of the
    # weights fed in, so a photometric run's ``master_coverage.fits`` shifts with
    # the 1/s² factor — a benign diagnostic change. The *leveling* binning no
    # longer rides on it: both the in-stack pass and the editor bin by the honest
    # per-pixel frame count (``frame_coverage`` / the ``_framecov.fits`` sibling),
    # which is what makes the auto-for-mosaic enable above safe.
    combine_weights = combine_weights_with_photometric(weights, pscales)

    # Pre-compute the reference patch for sub-pixel alignment, by aligning
    # the reference frame to itself once and extracting a central luminance
    # window. This happens before the parallel passes so every worker can
    # share it.
    canvas_3 = (dst_shape[0], dst_shape[1], 3)  # needed by the sub-pixel block below
    ref_patch: np.ndarray | None = None
    ref_patch_origin: tuple[int, int] | None = None
    if options.subpixel_refine:
        try:
            ref_result = align_one(
                fits_path=str(readable_frame_path(ref) or ""),
                bayer_pattern=ref.bayer_pattern,
                # The reference frame's *own* WCS is the source; the canvas WCS
                # is the destination (these differ once a mosaic canvas is used).
                src_wcs_text=ref.wcs_json,
                dst_wcs_text=dst_wcs_text,
                dst_shape=dst_shape,
                background_options=options.background_options(),
                use_gpu=options.use_gpu,
                suppress_hot_pixels=options.suppress_hot_pixels,
                hot_pixel_sigma=options.hot_pixel_sigma,
                # Build the reference patch in the *same* domain as the frames it
                # will be phase-correlated against (below, via _align_for_stack):
                # calibrated when calibration is applied, and mono-luminance for a
                # mono stack. Omitting these made the reference OSC-debayered /
                # uncalibrated while every frame was mono / calibrated — a domain
                # mismatch that degrades the measured sub-pixel shift.
                calibration=calibration,
                mono=options.mono,
            )
            if ref_result is None:
                raise ValueError("reference frame did not intersect the canvas")
            ref_win, _ref_valid, ref_y0, ref_x0 = ref_result
            # Embed the windowed reference into a full canvas once (cheap — one
            # allocation at setup) so extract_reference_patch can take a
            # central patch in canvas coordinates.
            ref_full = np.full(canvas_3, np.nan, dtype=np.float32)
            rh, rw = ref_win.shape[:2]
            ref_full[ref_y0:ref_y0 + rh, ref_x0:ref_x0 + rw] = ref_win
            # Centre the patch on the reference *panel*, not blindly on the
            # canvas. On a mosaic the union canvas is larger than any one tile,
            # so a reference tile whose footprint misses the canvas centre used
            # to yield an all-NaN patch — and then every frame's phase
            # correlation raised and was swallowed, leaving the whole stack on
            # whole-pixel alignment with nothing to say why. For a single-field
            # target the panel is the canvas, so this picks the same window.
            ref_patch, ref_patch_origin = extract_reference_patch(
                ref_full, centre=(ref_y0 + rh // 2, ref_x0 + rw // 2))
            # Belt and braces: even centred, a reference window clipped to a thin
            # sliver of the canvas can leave the patch mostly uncovered, and an
            # uncovered pixel is filled with the patch median. Correlating against
            # a mostly-flat patch is worse than not refining, so stand down
            # visibly rather than fail silently once per frame.
            _pph, _ppw = ref_patch.shape
            _py0, _px0 = ref_patch_origin
            covered = float(np.isfinite(
                ref_full[_py0:_py0 + _pph, _px0:_px0 + _ppw, 1]).mean())
            if covered < REF_PATCH_MIN_COVERAGE:
                log.info(
                    "Sub-pixel refinement disabled: the reference frame covers "
                    "only %.0f%% of its patch at origin %s", covered * 100.0,
                    ref_patch_origin)
                ref_patch = None
                ref_patch_origin = None
            else:
                log.info("Sub-pixel refinement: ref patch %s at origin %s "
                         "(%.0f%% covered)",
                         ref_patch.shape, ref_patch_origin, covered * 100.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not build reference patch for sub-pixel refine: %s", exc)
            ref_patch = None
            ref_patch_origin = None
    # Whether refinement is actually *running*, as opposed to merely requested:
    # the patch build can stand down (the reference frame missed the canvas, or
    # barely covers its patch). The provenance card and the history row both key
    # off this rather than off the option, so a stack that never refined reports
    # no roughly-aligned count at all instead of a reassuring "0 were rough".
    refine_active = bool(options.subpixel_refine and ref_patch is not None)

    n = len(frames)
    # Effective options with ``auto_reject`` resolved to a concrete method from the
    # frame count. The original ``options`` (with the user's choice intact) is what
    # gets persisted in the run record; ``eff`` drives the method dispatch, the
    # memory guard, and the STACKER provenance card so all three agree.
    eff = _resolve_auto_reject(options, n)
    # …and the drizzle half of the same question, which can only be answered here:
    # pricing the two-pass rejection needs the real output canvas, and for a
    # mosaic that union canvas was only just computed. ``eff.drizzle_reject`` then
    # drives the dispatch, the memory guard and the in-flight cap alike, so the
    # three can never disagree about which pass is running.
    # Only a *drizzled* run can want the drizzle rejection: a saved default can
    # carry ``drizzle_reject`` with ``drizzle`` off (the form hides the box, it
    # doesn't clear the value), and that combination has always been an inert
    # no-op — it must not now produce a "not run: over budget" warning or a
    # DRZREJSK card on a run that was never going to run the pass at all.
    _drizzle_reject_wanted = eff.drizzle and eff.drizzle_reject and n >= 4
    eff = replace(eff, drizzle_reject=_afford_drizzle_reject(
        eff, n, dst_shape, memory_budget_gb))
    if _drizzle_reject_wanted and not eff.drizzle_reject:
        _reject_need, _ = _estimate_peak_bytes(
            dst_shape, drizzle=True, drizzle_scale=options.drizzle_scale,
            drizzle_reject=True)
        log.warning(
            "Drizzle outlier rejection not run: its second pass would need "
            "~%.1f GB of working memory, over the ~%.1f GB budget. Stacking "
            "without it rather than refusing the run — lower the drizzle scale "
            "or raise ASTROSTACK_MAX_STACK_GB to get it back.",
            _reject_need / 1e9,
            _stack_memory_budget_bytes(memory_budget_gb) / 1e9,
        )
    # …and the second half of the same asymmetry, one level up: the *canvas*
    # itself over budget. Dropping the rejection above only frees the extra
    # rejection planes; when even the single pass doesn't fit, the guard below
    # refuses the whole run. For a watching user that refusal is the better
    # outcome — it names the one lever that would fit ("lower the drizzle scale
    # to ×1.3 (~4.2 GB)") and they click it. At 3 a.m. nobody reads it, so the
    # target simply stops producing pictures until the owner next opens the Jobs
    # page — on an install that made a picture yesterday.
    #
    # So on an unattended run only, when the least-destructive fix the engine
    # already computes *is* a smaller super-resolution scale, take it instead of
    # refusing. A picture at ×1.3 beats no picture; nothing is lost but zoom, and
    # the run stamps DRZSCLAD so the finished image says so. Deliberately narrow:
    # only the ``drizzle_scale`` lever is auto-applied. ``reference_canvas`` is
    # not — silently cropping the field a user spent five nights building is a
    # different order of change — and an attended run is untouched.
    drizzle_scale_requested: float | None = None
    if eff.unattended and eff.drizzle:
        _need, _ = _estimate_peak_bytes(
            dst_shape, drizzle=True, drizzle_scale=eff.drizzle_scale,
            drizzle_reject=eff.drizzle_reject)
        _budget = int(_stack_memory_budget_bytes(memory_budget_gb))
        if int(_need) > _budget:
            _fix = _best_memory_fix(
                dst_shape, ref_shape, is_mosaic=is_mosaic_canvas, drizzle=True,
                drizzle_scale=eff.drizzle_scale,
                drizzle_reject=eff.drizzle_reject, reject_arrays=0,
                min_max_reject_count=1, budget=_budget)
            if _fix is not None and _fix.kind == "drizzle_scale":
                drizzle_scale_requested = float(eff.drizzle_scale)
                eff = replace(eff, drizzle_scale=float(_fix.value))
                log.warning(
                    "Unattended stack: the ×%g drizzle canvas would need ~%.1f GB "
                    "of working memory, over the ~%.1f GB budget. Using ×%g "
                    "(~%.1f GB) instead of refusing the run — the picture is "
                    "slightly less zoomed-in, nothing else changes.",
                    drizzle_scale_requested, _need / 1e9, _budget / 1e9,
                    eff.drizzle_scale, _fix.peak_bytes / 1e9,
                )
    # …and the *non-drizzle* half of exactly the same asymmetry, which the block
    # above deliberately left out. A plain stack's least-destructive lever is
    # dropping the **extra** outlier passes — k>1 back to the proven single
    # min/max drop — and that is even safer to take than the scale step above:
    # same canvas, same pixel grid, same output file, just a little less
    # multi-trail rejection. So a walk-away stack with k=3 on a tight budget need
    # not go dark when k=1 would have made the picture. ``reference_canvas`` stays
    # a refusal here for the same reason it does above — cropping a mosaic's field
    # is a different order of change — and an attended run is untouched.
    min_max_reject_count_requested: int | None = None
    _mmr_charged = eff.min_max_reject and not options.drizzle and n >= 3
    if eff.unattended and _mmr_charged and eff.min_max_reject_count > 1:
        _arrays = _min_max_reject_arrays(eff.min_max_reject_count)
        _need, _ = _estimate_peak_bytes(
            dst_shape, drizzle=False, drizzle_scale=1.0, reject_arrays=_arrays)
        _budget = int(_stack_memory_budget_bytes(memory_budget_gb))
        if int(_need) > _budget:
            _fix = _best_memory_fix(
                dst_shape, ref_shape, is_mosaic=is_mosaic_canvas, drizzle=False,
                drizzle_scale=1.0, drizzle_reject=False, reject_arrays=_arrays,
                min_max_reject_count=eff.min_max_reject_count, budget=_budget)
            if _fix is not None and _fix.kind == "reduce_outlier_passes":
                min_max_reject_count_requested = int(eff.min_max_reject_count)
                eff = replace(eff, min_max_reject_count=1)
                log.warning(
                    "Unattended stack: dropping %d outlier extremes per side would "
                    "need ~%.1f GB of working memory, over the ~%.1f GB budget. "
                    "Dropping 1 (~%.1f GB) instead of refusing the run — the "
                    "picture is the same size and shape, with a little less "
                    "multi-trail rejection.",
                    min_max_reject_count_requested, _need / 1e9, _budget / 1e9,
                    _fix.peak_bytes / 1e9,
                )
    backend = "GPU (cupy)" if (
        (options.use_gpu is True) or (options.use_gpu is None and GPU_AVAILABLE)
    ) else "CPU (numpy/scipy)"
    log.info(
        "Stacking %d frames into %dx%d canvas — backend=%s, bg_flatten=%s, sigma_clip=%s",
        n, dst_shape[1], dst_shape[0], backend,
        options.background_flatten, eff.sigma_clip,
    )

    # Refuse a stack that would exhaust RAM *before* allocating anything — a
    # drizzled near-cap mosaic canvas can otherwise reach tens of GB and get the
    # whole container OOM-killed (there's no cgroup limit to catch it).
    # (Rejection is skipped below 4 frames, so don't charge its extra arrays.)
    # ``eff.drizzle_scale`` (not ``options``) from here down: an unattended
    # over-budget run may have just stepped it down, and the guard, the in-flight
    # cap and the drizzler must all price the canvas that is actually allocated.
    _guard_stack_memory(dst_shape, drizzle=options.drizzle,
                        drizzle_scale=eff.drizzle_scale,
                        drizzle_reject=eff.drizzle_reject,
                        reject_arrays=(_min_max_reject_arrays(eff.min_max_reject_count)
                                       if eff.min_max_reject and not options.drizzle and n >= 3
                                       else 0),
                        ref_shape=ref_shape, is_mosaic=is_mosaic_canvas,
                        min_max_reject_count=(eff.min_max_reject_count
                                              if eff.min_max_reject and not options.drizzle and n >= 3
                                              else 1),
                        rejection_map=_records_rejection_map(eff, n),
                        memory_budget_gb=memory_budget_gb)
    # Bound the in-flight aligned/prepared frame buffers (each ~one native
    # reference frame, ``max_workers·2`` of them by default) to the RAM left after
    # the canvas arrays the guard above charged — the guard's estimate never counts
    # these per-worker buffers, so on a many-core box with a large sensor they could
    # OOM a run it just certified "safe". Inert for the Seestar target (small frames
    # / few cores keep the cap above ``max_workers·2``); only ever trims throughput.
    _max_workers = options.max_workers or max(1, (os.cpu_count() or 4))
    max_in_flight = _memory_bounded_in_flight(
        ref_shape, dst_shape,
        max_in_flight=_max_workers * 2,
        drizzle=options.drizzle, drizzle_scale=eff.drizzle_scale,
        drizzle_reject=eff.drizzle_reject,
        reject_arrays=(_min_max_reject_arrays(eff.min_max_reject_count)
                       if eff.min_max_reject and not options.drizzle and n >= 3
                       else 0),
        rejection_map=_records_rejection_map(eff, n),
        memory_budget_gb=memory_budget_gb)
    errors: list[str] = []
    # Set by the κ-σ pass-2 branch to record how much rejection actually clipped
    # (a memory-free trust signal stamped into the output header). None on paths
    # that don't run a data-driven κ-σ pass (mean / min-max / drizzle).
    rej_stats: RejectionStats | None = None
    # Per-pixel *frame count* (2-D) for the coverage_min/max diagnostics, set by
    # the weighted-sum branches. With quality weighting on, ``coverage`` there is
    # Σweights (not a frame count), so the honest "N frames per pixel" figure
    # comes from the accumulator's unweighted count instead. Left None on the
    # min/max path (whose ``coverage`` is already a true count) and the drizzle
    # path (which falls back to its weight map).
    frame_cov: np.ndarray | None = None
    # Per-pixel "how many samples did rejection drop here" map, when the run asked
    # for one (``record_rejection_map``). Filled by the κ-σ and two-pass-drizzle
    # branches below — the two rejections whose decision is data-driven — and left
    # None everywhere else, including on a run that recorded nothing, which is what
    # every consumer reads as "no overlay available".
    rejection_map: np.ndarray | None = None

    # Periodic pass-1 previews: the legacy quick-look PNG and, when
    # ``save_progress`` is on, the "watch it appear" reel. Wired into the
    # standard (non-drizzle) accumulator paths below; assembled after the
    # outputs are written (post-archive).
    ql = _QuickLook(project.project_dir, options.output_name, options, n)

    # Honest-accounting: contributing frames that sub-pixel refine had to leave
    # unshifted because the measured shift exceeded its cap (only roughly
    # aligned → possibly soft/doubled stars). A set so the two κ-σ passes, which
    # refine the same frames twice, count each frame once. Stays empty when
    # refine is off (drizzle never refines), so a run with it off is unaffected.
    roughly_ids: set[int] = set()

    # Honest-accounting, storage half: every pass gets a ``_PassFrameLog`` (not
    # only the two-pass ones that re-word their error lines) so the run can count
    # how many *distinct* subs hit a read error. Counting the ``errors`` list
    # itself would double-count a sub that failed both passes — the one case the
    # count most needs to get right, since that sub really is lost.
    pass_logs: list[_PassFrameLog] = []
    n_read_recovered = 0

    def _new_pass_log() -> "_PassFrameLog":
        pass_logs.append(_PassFrameLog())
        return pass_logs[-1]

    # ---- 3a. Drizzle path (alternate accumulator) --------------------------
    if options.drizzle:
        from seestack.io.wcs_io import wcs_from_text, wcs_to_text
        from seestack.stack.drizzle_path import DrizzleParams, DrizzleStacker

        ref_wcs = wcs_from_text(dst_wcs_text)
        if ref_wcs is None:
            raise ValueError("reference WCS could not be parsed for drizzle")
        params = DrizzleParams(
            pixfrac=options.drizzle_pixfrac,
            # ``eff``, not ``options``: an unattended over-budget run stepped this
            # down to what the memory budget can hold, and the drizzler must build
            # exactly the canvas the guard above certified.
            scale=eff.drizzle_scale,
            kernel=options.drizzle_kernel,
        )
        # Optional two-pass outlier rejection: pass 1 accumulates value and
        # value² to get per-output-pixel contribution statistics, pass 2
        # re-drizzles with outliers (satellites, plane trails, cosmic rays)
        # zero-weighted. Mirrors the standard path's n>=4 sigma-clip gate.
        # ``eff.drizzle_reject`` already folds in the >=4-frame floor and the
        # affordability check above, so the pass that runs is the one the memory
        # guard was charged for.
        reject = eff.drizzle_reject
        if options.drizzle_reject and n < 4:
            log.info("Drizzle outlier rejection skipped: needs >=4 frames, have %d", n)
        clip = None
        # Only populated on the two-pass (rejection) drizzle, where a frame the
        # statistics pass couldn't read may still be deposited by pass 2.
        dz_stats_log: _PassFrameLog | None = None
        dz_final_log = _new_pass_log()
        if reject:
            stats = DrizzleStacker(ref_wcs, dst_shape, params, compute_stats=True)
            dz_stats_log = _new_pass_log()
            n_stats = _drizzle_pass(
                frames, ref, stats, weights,
                options=options,
                phase_label="Drizzle 1/2 (statistics)",
                progress=progress, cancel=cancel,
                errors=errors,
                calibration=calibration,
                mono=options.mono,
                photometric_scales=pscales,
                max_in_flight=max_in_flight,
                frame_log=dz_stats_log,
            )
            if n_stats == 0 and not cancel():
                raise ValueError("drizzle: no usable frames")
            if not cancel():
                clip = stats.clip_reference(options.sigma_kappa)
            # Free the statistics accumulators before pass 2 allocates its own.
            del stats
        # Only pass 2 is asked to record where samples were dropped: pass 1 builds
        # the mean/σ reference and clips nothing, so a map from it would be empty.
        # ``reject`` gates it too, because a single-pass drizzle has no clip to
        # record — that run writes no sibling, which reads as "no overlay".
        drizzler = DrizzleStacker(
            ref_wcs, dst_shape, params,
            record_rejection_map=bool(reject and options.record_rejection_map))
        log.info("Drizzle: pixfrac=%.2f scale=%.2f kernel=%s reject=%s output=%dx%d",
                 params.pixfrac, params.scale, params.kernel, clip is not None,
                 drizzler.output_canvas_shape[1], drizzler.output_canvas_shape[0])
        n_used = _drizzle_pass(
            frames, ref, drizzler, combine_weights,
            options=options,
            phase_label="Drizzle 2/2 (outlier-clipped)" if clip is not None else "Drizzle",
            clip=clip,
            progress=progress, cancel=cancel,
            errors=errors,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
            max_in_flight=max_in_flight,
            frame_log=dz_final_log,
        )
        if n_used == 0 and not cancel():
            raise ValueError("drizzle: no usable frames")
        # A sub the statistics pass blipped on but this one deposited is in the
        # picture; say so on its error line rather than leave the run's error
        # list claiming a frame the header counts as used.
        if dz_stats_log is not None:
            n_read_recovered += _mark_recovered_errors(errors, dz_stats_log,
                                                       dz_final_log)
        # Surface how much the two-pass drizzle rejection actually clipped
        # (only when rejection ran — single-pass drizzle has no clip to tally).
        if clip is not None:
            _dz_contrib, _dz_rej = drizzler.rejection_counts()
            rej_stats = RejectionStats(
                mode="drizzle-reject",
                n_contributed=_dz_contrib,
                n_rejected=_dz_rej,
            )
            rejection_map = drizzler.rejection_map
        result_image = drizzler.result()
        coverage = drizzler.coverage
        # Honest per-pixel *frame count* for the coverage_min/max diagnostics:
        # drizzle's ``coverage`` (out_wht) is Σ of weighted footprint overlap —
        # fractional under quality weighting / pixfrac<1 / scale≠1, so it is not
        # a frame count. Read the accumulator's unweighted count instead (mirrors
        # the standard weighted-sum path). ``coverage`` itself is unchanged, so
        # the coverage map output / level_by_coverage are byte-for-byte identical.
        frame_cov = drizzler.frame_coverage
        # Write outputs against the **drizzle** output canvas, not the
        # reference canvas. The drizzle WCS lives at drizzler.out_wcs.
        dst_wcs_text = wcs_to_text(drizzler.out_wcs)
        dst_shape = drizzler.output_canvas_shape

    # ---- 3a2. Min/max (extremes) rejection: single-pass order statistic ----
    # Takes precedence over κ-σ on the standard path when enabled. Rejects a
    # lone per-pixel extreme (satellite/plane trail, hot/cold sample) that κ-σ
    # can't in a small stack. Needs ≥3 frames to spare two samples.
    elif eff.min_max_reject and n >= 3:
        mmr = MinMaxRejectAccumulator(canvas_3, reject_count=eff.min_max_reject_count)

        def consume_min_max(aligned: np.ndarray, y0: int, x0: int, weight: float) -> None:
            mmr.add_window(aligned, y0, x0)
            ql.on_frame(mmr.result)

        n_used = _pass(
            frames, ref, dst_wcs_text, dst_shape, weights,
            options=options,
            phase_label="Stacking (min/max reject)",
            consumer=consume_min_max,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
            max_in_flight=max_in_flight,
            roughly_aligned_ids=roughly_ids,
            frame_log=_new_pass_log(),
        )
        if n_used == 0 and not cancel():
            raise ValueError("no frames could be aligned")
        result_image = mmr.result()
        coverage = mmr.coverage
        _mmr_contrib, _mmr_rej = mmr.rejection_counts()
        rej_stats = RejectionStats(
            mode="min-max-reject",
            n_contributed=_mmr_contrib,
            n_rejected=_mmr_rej,
        )

    # ---- 3b. Standard path: pass 1 streaming mean + std --------------------
    # If sigma-clipping is off we go directly to the weighted sum and we're
    # done after one pass.
    elif eff.sigma_clip and n >= 4:
        wel = WelfordAccumulator(canvas_3)
        p1_log = _new_pass_log()
        p2_log = _new_pass_log()

        def consume_pass1(aligned: np.ndarray, y0: int, x0: int, _weight: float) -> None:
            wel.add_window(aligned, y0, x0)
            ql.on_frame(wel.mean)

        n_used_p1 = _pass(
            frames, ref, dst_wcs_text, dst_shape, weights,
            options=options,
            phase_label="Pass 1/2 (mean & σ)",
            consumer=consume_pass1,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
            max_in_flight=max_in_flight,
            roughly_aligned_ids=roughly_ids,
            frame_log=p1_log,
        )
        if n_used_p1 == 0 and not cancel():
            raise ValueError("pass 1 produced no usable frames")

        # ---- 4. Pass 2: clipped weighted sum ------------------------------
        mean = wel.mean()
        std = wel.std()
        # Free the pass-1 Welford accumulator (n/mean/M2 — 3 full-canvas arrays)
        # before pass 2 allocates its own buffers. ``mean()``/``std()`` return
        # fresh arrays, so ``wel`` is dead here, and ``del`` also empties the cell
        # the pass-1 consumer closure shares with it. Without this the pass-1
        # accumulator stays live all through pass 2, so the peak is ~7 canvas
        # arrays, not the 4 the OOM guard (``_PEAK_CANVAS_ARRAYS``) charges — a
        # large mosaic the guard certified as safe could then OOM mid-stack. The
        # drizzle two-pass path already frees its pass-1 stats the same way.
        del wel
        wsum = WeightedSumAccumulator(canvas_3)
        # Memory-free rejection tally: sum two scalars over the per-pixel keep
        # mask this pass already computes (no extra canvas). "contributed" = the
        # covered samples seen; "rejected" = those clipped by the κ-σ test. Where
        # there's no pass-1 reference to clip against (σ unknown → +inf tol, or
        # mean unknown → keep — see ``_kappa_sigma_keep_mask``) nothing is
        # clipped, so it's excluded from rejected but still counted as
        # contributed — the honest denominator.
        clip_counts = {"contributed": 0, "rejected": 0}
        # …and, when asked for, the *spatial* half of the same truth: how many
        # samples the clip dropped at each pixel, so the finished picture can show
        # the user the satellite trail it removed rather than only a percentage.
        # One uint16 plane (a sixth of an RGB float32 canvas), charged through the
        # OOM guard by ``_estimate_peak_bytes``; ``None`` when not recording, which
        # is the default and costs nothing.
        rej_map = (
            np.zeros(dst_shape, dtype=np.uint16)
            if options.record_rejection_map else None)

        def consume_clipped(aligned: np.ndarray, y0: int, x0: int, weight: float) -> None:
            wh, ww = aligned.shape[:2]
            mean_win = mean[y0:y0 + wh, x0:x0 + ww]
            std_win = std[y0:y0 + wh, x0:x0 + ww]
            keep = _kappa_sigma_keep_mask(aligned, mean_win, std_win, options.sigma_kappa)
            valid = np.isfinite(aligned)
            dropped = valid & ~keep
            clip_counts["contributed"] += int(valid.sum())
            clip_counts["rejected"] += int(np.count_nonzero(dropped))
            if rej_map is not None:
                # One count per *frame* that lost anything here, OR-ed across the
                # channels — κ-σ clips per channel, and a trail that only reddens
                # a pixel is still a trail the user should see. ``where=`` makes
                # the add saturating rather than wrapping, so a pathological
                # 65 535-sample pixel pins at the top instead of falling to 0.
                win = rej_map[y0:y0 + wh, x0:x0 + ww]
                np.add(win, dropped.any(axis=2), out=win,
                       where=win < np.uint16(65535), casting="unsafe")
            wsum.add_window(np.where(keep, aligned, np.nan), y0, x0, weight=weight)

        n_used_p2 = _pass(
            frames, ref, dst_wcs_text, dst_shape, combine_weights,
            options=options,
            phase_label="Pass 2/2 (clipped sum)",
            consumer=consume_clipped,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
            max_in_flight=max_in_flight,
            roughly_aligned_ids=roughly_ids,
            frame_log=p2_log,
        )
        # ...and the presentation half of the same truth: a sub that blipped in
        # pass 1 and loaded fine in pass 2 still carries its pass-1 error line, so
        # the run's error list would report a failure for a frame ``NFRAMES`` says
        # was combined. Qualify that line (never drop it — see
        # ``_mark_recovered_errors``) so the storage signal survives without the
        # contradiction.
        n_read_recovered += _mark_recovered_errors(errors, p1_log, p2_log)
        # The frames that actually contributed *pixels* are pass 2's — pass 1 only
        # built the mean/σ reference the clip is measured against, and a frame it
        # missed is still combined (``_kappa_sigma_keep_mask`` keeps a sample whose
        # reference is unknown, which is exactly the transient-read-error case it
        # was written for). Counting ``min(p1, p2)`` credited the *smaller* pass, so
        # a sub that blipped in pass 1 and loaded fine in pass 2 was silently left
        # out of NFRAMES, the integration time and the align-failure tally, even
        # though its light is in the picture. Identical on every ordinary run, where
        # the two passes see the same frames; the difference only ever shows up when
        # they diverge, and only ever in the direction of the truth.
        n_used = n_used_p2
        # Pass 1 succeeded but pass 2 aligned nothing (e.g. the cached/source
        # frames became unreadable *between* the two passes on a long run) →
        # ``wsum`` is empty and ``result()`` is all-NaN. Guard it exactly like
        # the min/max, pass-1, and single-pass branches do: raise rather than
        # fall through to writing a silent all-NaN master recorded as a
        # *successful* run with ``n_frames_used=0`` (the same hazard the drizzle
        # two-pass path already guards against). The ``not cancel()`` clause (as
        # on the drizzle path, line ~1107) is essential: a user cancel *during*
        # pass 1 leaves ``n_used_p1>0`` but makes pass 2 break on its first
        # frame (``n_used_p2==0`` → ``n_used==0``), so without it a routine
        # cancel of the *default* κ-σ stack raises a spurious error instead of
        # returning the graceful cancelled result below.
        if n_used == 0 and not cancel():
            raise ValueError("pass 2 produced no usable frames")
        result_image = wsum.result()
        coverage = wsum.coverage
        frame_cov = wsum.frame_coverage
        rej_stats = RejectionStats(
            mode="sigma-clip",
            n_contributed=clip_counts["contributed"],
            n_rejected=clip_counts["rejected"],
        )
        rejection_map = rej_map
    else:
        # Single-pass weighted mean.
        wsum = WeightedSumAccumulator(canvas_3)

        def consume_one_pass(aligned: np.ndarray, y0: int, x0: int, weight: float) -> None:
            wsum.add_window(aligned, y0, x0, weight=weight)
            ql.on_frame(wsum.result)

        n_used = _pass(
            frames, ref, dst_wcs_text, dst_shape, combine_weights,
            options=options,
            phase_label="Stacking",
            consumer=consume_one_pass,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
            max_in_flight=max_in_flight,
            roughly_aligned_ids=roughly_ids,
            frame_log=_new_pass_log(),
        )
        if n_used == 0 and not cancel():
            raise ValueError("no frames could be aligned")
        result_image = wsum.result()
        coverage = wsum.coverage
        frame_cov = wsum.frame_coverage

    if cancel():
        return StackResult(
            output_dir=project.project_dir / "output",
            fits_path=Path(),
            tiff_path=Path(),
            preview_path=Path(),
            n_frames_used=n_used,
            canvas_shape=dst_shape,
            coverage_min=0, coverage_max=0,
            options=options,
            cancelled=True,
            errors=errors,
            # A cancelled run produced no picture, but the mismatch was measured
            # before the passes ran and is just as true — say it rather than drop it.
            calibration_warnings=calib_warnings,
        )

    # ---- 4.4. Per-coverage sky leveling -----------------------------------
    # Always run — it's effectively a no-op when coverage is uniform (single-
    # target stacks). For any stack with varying coverage (mosaics, dither
    # margins, partial captures) it kills the panel-rectangle steps that come
    # from per-frame biases the upstream pipeline couldn't fully remove.
    from seestack.bg.coverage_leveling import level_by_coverage

    progress("Levelling panels", 0, 1)
    # Bin by the true per-pixel frame count (not the quality-weighted Σ-weight
    # map) so panel-step removal groups pixels by real coverage even under
    # quality weighting; ``frame_cov`` is None only on paths where coverage is
    # already an exact count (min/max), where the fallback is identical.
    result_image = level_by_coverage(
        result_image, coverage, frame_coverage=frame_cov)
    progress("Levelling panels", 1, 1)

    # ---- 4.5. Final-stack gradient removal (with object masking) ----------
    # Auto-enable on mosaic canvases: per-frame bg flatten can't fully
    # eliminate panel-to-panel level differences (different panels see
    # different sky conditions). A masked post-stack gradient pass evens it
    # out without eating the target.
    do_final_grad = options.final_gradient_removal or is_mosaic_canvas
    if do_final_grad:
        from seestack.bg.final_gradient import FinalGradientOptions, remove_final_gradient

        why = "(auto for mosaic)" if is_mosaic_canvas and not options.final_gradient_removal else ""
        log.info("Final-stack gradient removal %s", why)
        progress("Removing residual gradient", 0, 1)
        fg_opts = FinalGradientOptions(
            enabled=True,
            mode=options.final_gradient_mode,
            box_size=options.final_gradient_box_size,
        )
        result_image = remove_final_gradient(result_image, fg_opts)
        progress("Removing residual gradient", 1, 1)

    # ---- 4.7. Photometric color calibration -------------------------------
    color_cal_note = ""
    if options.color_calibration:
        from seestack.io.wcs_io import wcs_from_text
        from seestack.post.color_cal import ColorCalibrationOptions, calibrate_color

        progress("Photometric color calibration", 0, 1)
        cc_opts = ColorCalibrationOptions(
            enabled=True, mode=options.color_calibration_mode,
        )
        result_image, cc_result = calibrate_color(
            result_image, wcs=wcs_from_text(dst_wcs_text), options=cc_opts,
        )
        log.info("Color cal: mode=%s scale=R%.3f G%.3f B%.3f from %d stars (%s)",
                 cc_result.mode_used, *cc_result.scale_rgb,
                 cc_result.n_stars_used, cc_result.notes)
        color_cal_note = f"{cc_result.mode_used} from {cc_result.n_stars_used} stars"
        progress("Photometric color calibration", 1, 1)

    # ---- 5. Write outputs -------------------------------------------------
    progress("Saving", 0, 1)
    from seestack.stack.output import write_stack_outputs

    # Measure the finished stack's background noise once and reuse it for both the
    # self-documenting FITS header and the run record, so the two never disagree.
    noise_sigma = _compute_noise_sigma(result_image)
    # Measure the finished stack's own median star size (sharpness) once, for both
    # the FITS header and the run record. Normalised to native-frame pixels (see
    # _compute_stack_fwhm) so it's comparable to the per-frame QC fwhm_px.
    stack_fwhm = _compute_stack_fwhm(
        result_image, drizzle=eff.drizzle, drizzle_scale=eff.drizzle_scale)
    # Did the panels of this mosaic actually come out flat? Measured on the same
    # finished image, in units of its own grain, so "How's my stack?" can say so
    # in plain words instead of the owner having to spot a seam grid by eye.
    # None (and free) on every single-field stack.
    seam_residual = _compute_seam_residual(
        result_image, coverage, frame_cov, is_mosaic=bool(is_mosaic_canvas))
    # The min/max order-statistic path combines by rank and ignores per-frame
    # weights, so weighting provenance must not be stamped when it ran (it's the
    # active path only for a non-drizzle ≥3-frame min-max-reject stack). Every
    # other path (drizzle, κ-σ pass 2, plain weighted sum, and the min/max
    # fall-back-to-mean when n < 3) does apply the weights.
    weights_applied = not (eff.min_max_reject and not options.drizzle and n >= 3)
    n_roughly = len(roughly_ids)
    # Never claim more unreadable subs than actually dropped out of the stack: a
    # frame the preflight found missing whose share came back before its worker
    # read it would otherwise make "couldn't be read" exceed the whole gap.
    n_unreadable = min(n_unreadable, max(0, len(frames) - n_used))
    # Distinct subs that errored in *any* pass, and how many of those a two-pass
    # run combined anyway. A frame that failed both passes appears in both logs
    # and is counted once; a frame with no id is never logged (the same rule the
    # error re-wording and the roughly-aligned tally already use), so on a run
    # over rows straight from the project DB this is exact.
    read_error_ids: set[int] = set()
    for _plog in pass_logs:
        read_error_ids.update(_plog.error_slot)
    n_read_errors = len(read_error_ids)
    n_read_recovered = min(n_read_recovered, n_read_errors)
    # Whether the spatial record of the drops is going beside the picture. Decided
    # here, not inside the writer, so the header card and the file on disk are the
    # same answer: a map that is all-zero writes no sibling (a canvas-sized file
    # saying "nothing was removed", which the absence already says), so the card
    # reads False. ``None`` — no map recorded at all — omits the card entirely,
    # which is what every run before this feature looks like.
    rejection_map_written = (
        bool(np.any(rejection_map)) if rejection_map is not None else None)
    header_meta = _build_output_header_meta(project, frames, eff, n_used, wstats,
                                            calibration=calibration, pstats=pstats,
                                            photometric_auto=photometric_auto,
                                            rstats=rej_stats,
                                            weights_applied=weights_applied,
                                            n_roughly_aligned=n_roughly,
                                            refine_active=refine_active,
                                            n_unreadable=n_unreadable,
                                            n_read_errors=n_read_errors,
                                            n_read_recovered=n_read_recovered,
                                            drizzle_reject_declined=(
                                                _drizzle_reject_wanted
                                                and not eff.drizzle_reject),
                                            drizzle_scale_requested=(
                                                drizzle_scale_requested),
                                            min_max_reject_count_requested=(
                                                min_max_reject_count_requested),
                                            rejection_map_written=(
                                                rejection_map_written))
    if noise_sigma is not None:
        header_meta["BKGSIGMA"] = (noise_sigma, "normalized background noise sigma")
    if stack_fwhm is not None:
        header_meta["STKFWHM"] = (stack_fwhm, "median star FWHM, native-frame px")
    if seam_residual is not None:
        header_meta["SEAMRES"] = (seam_residual, "mosaic panel-seam step, in sky sigma")
    paths = write_stack_outputs(
        project_dir=project.project_dir,
        rgb=result_image,
        coverage=coverage,
        wcs_text=dst_wcs_text,
        out_basename=options.output_name,
        tiff_mode=options.tiff_mode,
        header_meta=header_meta,
        # The honest per-pixel frame count, so the *editor* can bin this mosaic's
        # panels by subs rather than by a sum of weights when it re-levels the
        # sky. The in-stack leveling pass above already gets it directly; the
        # editor reloads from disk and until now had nothing to reload.
        frame_coverage=frame_cov,
        # …and, when the run was asked to record it, *where* rejection dropped
        # samples — so the app can show the user the satellite trail it cleaned
        # out instead of only telling them a percentage.
        rejection_map=rejection_map,
    )
    # Assemble the "watch it appear" reel now that the previous run's reel (if
    # any) has been archived aside by write_stack_outputs — so this becomes the
    # current ``{base}_progress`` sibling. Best-effort; never fails the stack.
    ql.finish()
    progress("Saving", 1, 1)

    # If this run archived a previous output set (a re-stack of an already-stacked
    # target), repoint that previous run's history row at its archived files so it
    # keeps serving *its* image — the new ``master.*`` belongs to this run. Done
    # before recording this run so the freshly-written paths aren't repointed.
    archived = paths.get("archived") or {}
    if archived:
        try:
            project.repoint_stack_runs(archived)
        except Exception as exc:  # noqa: BLE001 — history repoint is non-critical
            log.warning("Could not repoint previous stack run(s): %s", exc)

    # Record this run in the project history.
    run_id: int | None = None
    try:
        from dataclasses import asdict
        from datetime import datetime, timezone
        import json as _json
        from seestack.io.project import StackRunRow

        # Frame-count map for the coverage_min/max diagnostics: the unweighted
        # per-pixel count when we have it (so "N frames per pixel" stays honest
        # under quality weighting — the standard weighted-sum and drizzle paths
        # both provide it), else the coverage map itself (already a true count on
        # the min/max path). Identical to the old coverage[...,0] for an
        # unweighted non-drizzle stack.
        cov_2d = frame_cov if frame_cov is not None else (
            coverage[..., 0] if coverage.ndim == 3 else coverage)
        applied_cal = calibration.describe() if calibration is not None else None
        if applied_cal in (None, "", "none"):
            applied_cal = None
        capture_start, capture_end = _capture_window(frames)
        capture_hours = _capture_hours(frames)
        run_id = project.add_stack_run(StackRunRow(
            id=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            output_basename=options.output_name,
            fits_path=str(paths["fits"]),
            tiff_path=str(paths["tiff"]),
            preview_path=str(paths["preview"]),
            n_frames_used=n_used,
            canvas_h=dst_shape[0],
            canvas_w=dst_shape[1],
            coverage_min=int(cov_2d.min()),
            coverage_max=int(cov_2d.max()),
            # Persist the *effective* options: when auto_reject resolved to a
            # concrete method, record that method (so the History rejection badge
            # and any re-run reflect what actually ran) while ``auto_reject`` stays
            # True in the record to show it was auto-picked. With auto_reject off
            # (the default), ``eff is options`` so this is byte-for-byte unchanged.
            options_json=_json.dumps(asdict(eff)),
            notes=color_cal_note or None,
            total_exposure_s=_integration_time_s(frames, n_used),
            # When the subs were *shot*, as opposed to when this stack ran —
            # the only honest source for anything that says "shot on …".
            capture_start_utc=capture_start,
            capture_end_utc=capture_end,
            # …and how the light was spread out: the hours it arrived in, so the
            # read side can count the *nights* for the observer's own longitude.
            # A window of 15→18 Nov is equally consistent with two nights and
            # with four; only this says which.
            capture_hours_json=(
                _json.dumps(capture_hours) if capture_hours else None),
            transparency_ratio=_compute_transparency_ratio(project, frames),
            noise_sigma=noise_sigma,
            calstat=applied_cal,
            is_mosaic=bool(is_mosaic_canvas),
            engine_version=app_version,
            # Persist the outlier-rejection tally so "How's my stack?" can name the
            # trails/cosmic-rays the pass removed, without re-reading the FITS. Only
            # recorded when a rejection pass actually ran and saw samples; a plain
            # mean stack leaves both NULL (no clean-up to speak of).
            rejection_fraction=(
                rej_stats.fraction
                if rej_stats is not None and rej_stats.n_contributed > 0 else None
            ),
            rejection_mode=(
                rej_stats.mode
                if rej_stats is not None and rej_stats.n_contributed > 0 else None
            ),
            # Persist the roughly-aligned count (contributing subs refine left
            # unshifted past its cap) so the "How's my stack?" health panel can
            # name the soft-star cause without re-reading the FITS header. Only
            # meaningful when refine ran on a non-drizzle stack — otherwise NULL
            # (mirrors the NROUGHAL card gate), so an off-by-default run records
            # no signal rather than a misleading 0.
            n_roughly_aligned=(
                n_roughly
                if (eff.subpixel_refine and not eff.drizzle and refine_active)
                else None
            ),
            # This stack's own median star size (native-frame px). NULL when too
            # few stars to fit — old runs read NULL and callers self-hide.
            stack_fwhm_px=stack_fwhm,
            # How flat this mosaic's panel joins came out, in units of the
            # picture's own grain. NULL on a single-field stack (no joins) and
            # when it couldn't be measured — callers self-hide either way.
            seam_residual=seam_residual,
        ))
    except Exception as exc:  # noqa: BLE001 — history is non-critical
        log.warning("Could not record stack run in history: %s", exc)

    # Coverage min/max for diagnostics — an honest *frame* count (unweighted)
    # when available, so quality weighting doesn't understate it; else the
    # coverage map (channels share the valid mask in our pipeline). Mirror the
    # history-record slice above: guard ``ndim == 3`` so a future path returning
    # a 2-D coverage map alongside ``frame_cov=None`` takes the whole map, not a
    # wrong ``[..., 0]`` slice.
    cov_2d = frame_cov if frame_cov is not None else (
        coverage[..., 0] if coverage.ndim == 3 else coverage)
    # Mirror the exact gate the ``stack_runs`` row uses (only a rejection pass
    # that saw samples counts) so the returned tally can never disagree with the
    # persisted one.
    _rej_recorded = rej_stats is not None and rej_stats.n_contributed > 0
    return StackResult(
        output_dir=project.project_dir / "output",
        fits_path=paths["fits"],
        tiff_path=paths["tiff"],
        preview_path=paths["preview"],
        n_frames_used=n_used,
        canvas_shape=dst_shape,
        coverage_min=int(cov_2d.min()),
        coverage_max=int(cov_2d.max()),
        options=options,
        errors=errors,
        excluded_frames=excluded_frames,
        n_offered=len(frames),
        n_align_failed=max(0, len(frames) - n_used),
        n_unreadable=n_unreadable,
        n_read_errors=n_read_errors,
        n_read_recovered=n_read_recovered,
        n_roughly_aligned=n_roughly,
        run_id=run_id,
        rejection_mode=rej_stats.mode if _rej_recorded else None,
        rejection_fraction=rej_stats.fraction if _rej_recorded else None,
        calibration_warnings=calib_warnings,
    )


def _imap_bounded(ex: ThreadPoolExecutor, fn, items, max_in_flight: int):
    """Submit at most ``max_in_flight`` tasks to ``ex`` at a time, yielding
    ``(item, future)`` as each completes and only then topping up.

    The plain ``{ex.submit(fn, x): x for x in items}`` pattern submits *every*
    task up front; when each result is a full-resolution image and the consumer
    is slower than the workers, completed results pile up unbounded and can OOM
    the process (thousands of frames × tens of MB each). Capping in-flight work
    bounds peak memory to ~``max_in_flight`` results regardless of frame count.
    """
    it = iter(items)
    item_of: dict = {}
    pending: set = set()
    for item in islice(it, max_in_flight):
        fu = ex.submit(fn, item)
        item_of[fu] = item
        pending.add(fu)
    while pending:
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        for fu in done:
            yield item_of.pop(fu), fu
        for item in islice(it, max_in_flight - len(pending)):
            fu = ex.submit(fn, item)
            item_of[fu] = item
            pending.add(fu)


# Appended to the error line a pass recorded for a frame the *other* pass of a
# two-pass run went on to combine. The line is re-worded rather than dropped: the
# read really did fail, and a NAS share that drops one sub in a hundred is exactly
# what the run's error list exists to show — but leaving it unqualified made the
# list claim a lost sub for a frame ``NFRAMES`` says is in the picture.
RECOVERED_ERROR_SUFFIX = (
    " — read again on the other pass and combined, so this sub IS in the picture")


@dataclass
class _PassFrameLog:
    """Per-frame bookkeeping for one :func:`_pass` / :func:`_drizzle_pass`.

    ``error_slot`` maps a frame's ``id`` to the index of the line that pass
    appended to the run's shared ``errors`` list, so the line can later be
    re-worded **in place**; ``used`` holds the ids that actually contributed
    pixels. Together they let a two-pass run tell a transient read blip
    (failed here, combined there) from a genuinely lost sub, which is the only
    case :func:`_mark_recovered_errors` touches. Optional everywhere — a
    single-pass run simply doesn't ask for one.
    """

    error_slot: dict[int, int] = field(default_factory=dict)
    used: set[int] = field(default_factory=set)


def _mark_recovered_errors(errors: list[str], first: _PassFrameLog,
                           second: _PassFrameLog) -> int:
    """Qualify each error ``first`` recorded for a frame ``second`` combined.

    Returns how many lines were re-worded. A frame that failed **both** passes is
    left exactly as it was — that is the real failure the list is for — and so is
    one that failed the *second* pass, whose light genuinely isn't in the picture
    (``n_frames_used`` is pass 2's count). Idempotent, and a frame with no ``id``
    is never recorded in the first place, so nothing here can mis-attribute a line.
    """
    n = 0
    for fid, slot in first.error_slot.items():
        if fid not in second.used or not (0 <= slot < len(errors)):
            continue
        if errors[slot].endswith(RECOVERED_ERROR_SUFFIX):
            continue
        errors[slot] += RECOVERED_ERROR_SUFFIX
        n += 1
    return n


def _pass(
    frames: list[FrameRow],
    ref: FrameRow,
    dst_wcs_text: str,
    dst_shape: tuple[int, int],
    weights: dict[int, float],
    *,
    options: StackOptions,
    phase_label: str,
    consumer: Callable[[np.ndarray, int, int, float], None],
    progress: ProgressFn,
    cancel: CancelFn,
    errors: list[str],
    ref_patch: np.ndarray | None = None,
    ref_patch_origin: tuple[int, int] | None = None,
    calibration: "CalibrationMasters | None" = None,
    mono: bool = False,
    photometric_scales: dict[int, float] | None = None,
    max_in_flight: int | None = None,
    roughly_aligned_ids: set[int] | None = None,
    frame_log: _PassFrameLog | None = None,
) -> int:
    """
    Run one pass over ``frames``, feeding each windowed aligned image plus its
    canvas offset and per-frame quality weight into
    ``consumer(window_rgb, y0, x0, weight)``. Returns the number of frames
    that contributed (post-error).

    ``roughly_aligned_ids`` (optional): a mutable set the pass adds a
    contributing frame's ``id`` to when sub-pixel refine measured a shift past
    its cap (the frame stacked unshifted — only *roughly* aligned). Threaded in
    (rather than returned) so the same set dedupes across the two κ-σ passes,
    which refine the same frames twice. Left empty when refine is off. Purely an
    honest-accounting signal; it never changes which frames contribute.

    ``max_in_flight`` caps how many aligned frame buffers may be in flight at once
    (memory-bounded by the caller via :func:`_memory_bounded_in_flight`); when None
    it falls back to ``max_workers·2`` — the historical bound.

    ``photometric_scales`` (optional) gain-matches each frame's *pixels* by an
    in-place multiply before the consumer sees them, so the scaling is applied
    identically in every pass and every accumulator/rejection path.

    ``frame_log`` (optional) records which frames this pass errored on (and where
    it put each line in ``errors``) and which contributed, so a two-pass caller can
    qualify a pass-1 error for a frame pass 2 combined — see
    :func:`_mark_recovered_errors`.
    """
    total = len(frames)
    progress(phase_label, 0, total)
    max_workers = options.max_workers or max(1, (os.cpu_count() or 4))
    in_flight = max_in_flight if max_in_flight is not None else max_workers * 2
    used = 0
    done = 0
    consumer_lock = threading.Lock()

    bg_opts = options.background_options()
    sp_refine = options.subpixel_refine and ref_patch is not None
    def _submit(f: FrameRow):
        return _align_for_stack(
            f, dst_wcs_text, dst_shape, bg_opts,
            options.use_gpu, options.suppress_hot_pixels, options.hot_pixel_sigma,
            ref_patch if sp_refine else None,
            ref_patch_origin if sp_refine else None,
            sp_refine,
            calibration,
            mono,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        # Bounded in-flight work: aligned full-res frames must not pile up
        # faster than the (serialised) consumer drains them, or thousands of
        # frames will OOM the process.
        for f, fut in _imap_bounded(ex, _submit, frames, in_flight):
            done += 1
            if cancel():
                progress(phase_label + " (cancelled)", done, total)
                break
            try:
                aligned = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: {type(exc).__name__}: {exc}")
                if frame_log is not None and f.id is not None:
                    frame_log.error_slot[f.id] = len(errors) - 1
                progress(phase_label, done, total)
                continue
            if aligned is None:
                # Frame failed to load, or its footprint didn't intersect the
                # canvas (e.g. a stray frame from a different target).
                progress(phase_label, done, total)
                continue
            win_rgb, y0, x0, roughly = aligned
            if roughly and roughly_aligned_ids is not None and f.id is not None:
                # Refine measured a shift past the cap, so this contributing
                # frame stacked only roughly aligned. Record its id (a set, so
                # a κ-σ two-pass counts it once).
                roughly_aligned_ids.add(f.id)
            if photometric_scales is not None:
                scale = photometric_scales.get(f.id if f.id is not None else -1, 1.0)
                if scale != 1.0:
                    # ``win_rgb`` is this frame's own freshly-reprojected array,
                    # so scale it in place (no extra allocation on the hot path);
                    # NaN gaps stay NaN, preserving coverage.
                    win_rgb *= np.float32(scale)
            w = weights.get(f.id if f.id is not None else -1, 1.0)
            with consumer_lock:
                consumer(win_rgb, y0, x0, w)
            used += 1
            if frame_log is not None and f.id is not None:
                frame_log.used.add(f.id)
            progress(phase_label, done, total)
    return used


def _drizzle_pass(
    frames: list[FrameRow],
    ref: FrameRow,
    drizzler,
    weights: dict[int, float],
    *,
    options: StackOptions,
    progress: ProgressFn,
    cancel: CancelFn,
    errors: list[str],
    phase_label: str = "Drizzle",
    clip: tuple[np.ndarray, np.ndarray] | None = None,
    calibration: "CalibrationMasters | None" = None,
    mono: bool = False,
    photometric_scales: dict[int, float] | None = None,
    max_in_flight: int | None = None,
    frame_log: _PassFrameLog | None = None,
) -> int:
    """
    One-shot drizzle accumulation. Drizzle's ``add_image`` mutates internal
    state, so we serialise additions on one thread but parallelise the per-
    frame load+debayer+bg-flatten+pixmap on workers. Workers return prepared
    payloads; the consumer thread feeds them into the drizzler.

    ``max_in_flight`` caps how many prepared frame buffers may be in flight at once
    (memory-bounded by the caller via :func:`_memory_bounded_in_flight`); when None
    it falls back to ``max_workers·2`` — the historical bound.

    ``frame_log`` (optional) records this pass's per-frame errors and contributions
    for :func:`_mark_recovered_errors`, exactly as :func:`_pass` does.
    """
    from seestack.io.wcs_io import wcs_from_text

    total = len(frames)
    progress(phase_label, 0, total)
    max_workers = options.max_workers or max(1, (os.cpu_count() or 4))
    in_flight = max_in_flight if max_in_flight is not None else max_workers * 2
    bg_opts = options.background_options()
    used = 0
    done = 0

    def prepare(frame: FrameRow):
        path = readable_frame_path(frame)
        if not path or not frame.wcs_json:
            return None
        from seestack.bg.hot_pixels import suppress_hot_cold_pixels
        from seestack.bg.per_frame import subtract_background
        from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw

        raw, info = load_seestar_raw(path, debayer=False, out_dtype=np.float32)
        if calibration is not None:
            raw = calibration.apply_raw(raw, light_exposure_s=info.exposure_s)
        if mono:
            rgb = np.repeat(raw[..., None], 3, axis=2)
        else:
            pattern = frame.bayer_pattern or info.bayer_pattern or "RGGB"
            rgb = bilinear_debayer(raw, pattern=pattern)
        # Same per-frame cleanup order as the standard path (align_one):
        # debayer → hot-pixel suppression → background flatten.
        if options.suppress_hot_pixels:
            rgb = suppress_hot_cold_pixels(
                rgb, sigma=options.hot_pixel_sigma, use_gpu=options.use_gpu
            )
        if bg_opts.enabled:
            rgb = subtract_background(rgb, bg_opts, use_gpu=options.use_gpu)
        # Photometric gain-match (in place — ``rgb`` is this frame's own array),
        # applied after the sky is zeroed so it scales signal, not the pedestal.
        if photometric_scales is not None:
            scale = photometric_scales.get(frame.id if frame.id is not None else -1, 1.0)
            if scale != 1.0:
                rgb = rgb * np.float32(scale)
        in_wcs = wcs_from_text(frame.wcs_json)
        if in_wcs is None:
            return None
        return rgb, in_wcs

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        # Bounded in-flight work: prepared full-res RGB frames must not pile up
        # faster than the (serialised) drizzler consumes them — submitting all
        # frames at once is what drove the OOM on large (5k+ frame) targets.
        for f, fut in _imap_bounded(ex, prepare, frames, in_flight):
            done += 1
            if cancel():
                progress(phase_label + " (cancelled)", done, total)
                break
            try:
                payload = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: {type(exc).__name__}: {exc}")
                if frame_log is not None and f.id is not None:
                    frame_log.error_slot[f.id] = len(errors) - 1
                progress(phase_label, done, total)
                continue
            if payload is None:
                progress(phase_label, done, total)
                continue
            rgb, in_wcs = payload
            try:
                aligned = drizzler.add_frame(
                    rgb, in_wcs,
                    weight=weights.get(f.id if f.id is not None else -1, 1.0),
                    clip=clip)
                # Only count a frame that actually intersected the canvas.
                # A stray sub from a different pointing reprojects entirely
                # off-canvas and deposits nothing — counting it would inflate
                # n_frames_used / hide the align failure (NALIGNFL), and, worse,
                # if *every* frame is off-canvas it would slip past the
                # ``n_used == 0`` guard and write an all-NaN image to disk.
                # This mirrors the standard path's ``align_one`` → ``None`` skip.
                if aligned:
                    used += 1
                    if frame_log is not None and f.id is not None:
                        frame_log.used.add(f.id)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: drizzle add_image: {exc}")
                if frame_log is not None and f.id is not None:
                    frame_log.error_slot[f.id] = len(errors) - 1
            progress(phase_label, done, total)
    return used


def _align_for_stack(
    frame: FrameRow,
    dst_wcs_text: str,
    dst_shape: tuple[int, int],
    bg_options: BackgroundOptions,
    use_gpu: bool | None,
    suppress_hot_pixels: bool,
    hot_pixel_sigma: float,
    ref_patch: np.ndarray | None,
    ref_patch_origin: tuple[int, int] | None,
    subpixel_refine: bool,
    calibration: "CalibrationMasters | None" = None,
    mono: bool = False,
) -> tuple[np.ndarray, int, int, bool] | None:
    """
    Worker entry point. Returns ``(window_rgb, y0, x0, roughly_aligned)`` — the
    reprojected frame cropped to its footprint, its canvas offset, and a flag
    that is ``True`` when sub-pixel refine measured a shift past its cap so the
    frame stacks only *roughly* aligned (unshifted) — or ``None`` on benign
    failure (missing file, no WCS, footprint off-canvas). The flag is always
    ``False`` when refine didn't run; it never affects the pixels.
    """
    path = readable_frame_path(frame)
    if not path:
        return None
    if not frame.wcs_json:
        return None
    refine_stats: dict = {}
    result = align_one(
        fits_path=path,
        bayer_pattern=frame.bayer_pattern,
        src_wcs_text=frame.wcs_json,
        dst_wcs_text=dst_wcs_text,
        dst_shape=dst_shape,
        background_options=bg_options,
        use_gpu=use_gpu,
        suppress_hot_pixels=suppress_hot_pixels,
        hot_pixel_sigma=hot_pixel_sigma,
        ref_patch=ref_patch,
        ref_patch_origin=ref_patch_origin,
        subpixel_refine=subpixel_refine,
        calibration=calibration,
        mono=mono,
        refine_stats=refine_stats,
    )
    if result is None:
        return None
    win_rgb, _win_valid, y0, x0 = result
    return win_rgb, y0, x0, bool(refine_stats.get("over_cap"))


# Keep at most this many evenly-spaced snapshots in the progress reel, so a
# 5,000-sub run doesn't hoard memory or produce a bloated animation — ~a dozen
# frames make a smooth "watch it appear" clip.
_PROGRESS_MAX_FRAMES = 12
# Don't bother assembling a reel from fewer than this — too few frames to read
# as an animation (a 2-frame stack has nothing to "watch come together").
_PROGRESS_MIN_FRAMES = 3
# Downscale reel frames to this width so the in-memory buffer stays tiny
# regardless of a mosaic's full canvas size (bounded ~a dozen small frames).
_PROGRESS_FRAME_WIDTH = 800


def _render_preview(rgb: np.ndarray, max_w: int):
    """Autostretch + downscale an accumulator state to a small RGB PIL image.

    NaN is passed straight through — ``autostretch`` is nan-aware and must
    compute its stats over covered pixels only (a mosaic's no-data gaps would
    otherwise wreck the colour balance).
    """
    from PIL import Image
    from seestack.render.thumbnail import autostretch

    stretched = autostretch(rgb.astype(np.float32, copy=False))
    u8 = (np.clip(stretched, 0, 1) * 255).astype(np.uint8)
    h, w = u8.shape[:2]
    if w > max_w:
        new_w = max_w
        new_h = max(1, int(round(h * (new_w / w))))
        return Image.fromarray(u8, "RGB").resize((new_w, new_h), Image.BOX)
    return Image.fromarray(u8, "RGB")


class _QuickLook:
    """Periodic previews of the accumulator during pass 1.

    Drives two independent, best-effort outputs that share the (expensive)
    autostretch when a frame is due for both:

    * the legacy single overwritten ``{base}_quicklook.png`` — a live peek for
      very long runs, every ``quick_look_interval`` frames (unchanged); and
    * the opt-in ``save_progress`` reel — up to ``_PROGRESS_MAX_FRAMES``
      evenly-spaced snapshots held in memory and, once the stack finishes,
      assembled by :func:`assemble_progress_reel` into a small looping
      "watch your picture come together" animation beside the master.

    Neither may ever fail the stack, so every save is guarded.
    """

    def __init__(self, project_dir: Path, out_basename: str,
                 options: "StackOptions", total_frames: int) -> None:
        from seestack.stack.output import safe_basename

        self.project_dir = Path(project_dir)
        # Sanitise like write_stack_outputs: output_name is free-text from the
        # web API, so it must never place a separator/``..`` into the reel path.
        self.out_basename = safe_basename(out_basename)
        self.counter = 0
        self.ql_interval = max(0, int(options.quick_look_interval))
        # Aim for ~a dozen evenly-spaced snapshots regardless of stack size.
        self.progress_interval = (
            max(1, total_frames // _PROGRESS_MAX_FRAMES)
            if getattr(options, "save_progress", False) and total_frames > 0
            else 0
        )
        self.progress_frames: list = []

    @property
    def enabled(self) -> bool:
        return self.ql_interval > 0 or self.progress_interval > 0

    def on_frame(self, result_fn) -> None:
        """Called once per accumulated frame with a lazy accumulator-result fn."""
        if not self.enabled:
            return
        self.counter += 1
        want_ql = self.ql_interval > 0 and self.counter % self.ql_interval == 0
        want_progress = (
            self.progress_interval > 0
            and len(self.progress_frames) < _PROGRESS_MAX_FRAMES
            and self.counter % self.progress_interval == 0
        )
        if not (want_ql or want_progress):
            return
        try:
            rgb = result_fn()
            if want_ql:
                out_dir = self.project_dir / "output"
                out_dir.mkdir(parents=True, exist_ok=True)
                _render_preview(rgb, 1024).save(
                    out_dir / f"{self.out_basename}_quicklook.png", format="PNG")
                log.debug("Quick-look saved (%d frames in)", self.counter)
            if want_progress:
                # Keep a small downscaled copy in memory; assembled after the
                # stack so we never touch a stale on-disk reel mid-run.
                self.progress_frames.append(_render_preview(rgb, _PROGRESS_FRAME_WIDTH))
        except Exception as exc:  # noqa: BLE001 — never fail the stack over a peek
            log.warning("Quick-look/progress save failed: %s", exc)

    def finish(self) -> Path | None:
        """Assemble the collected reel beside the master. Returns its path.

        Written *after* :func:`write_stack_outputs` has archived any previous
        run's reel aside, so this becomes the current ``{base}_progress`` sibling
        (mirroring how ``master.fits`` is written post-archive). No-op unless
        enough snapshots were gathered.
        """
        if len(self.progress_frames) < _PROGRESS_MIN_FRAMES:
            return None
        try:
            out_dir = self.project_dir / "output"
            out_dir.mkdir(parents=True, exist_ok=True)
            return assemble_progress_reel(self.progress_frames, out_dir, self.out_basename)
        except Exception as exc:  # noqa: BLE001 — a reel is a nicety, never critical
            log.warning("Progress reel assembly failed: %s", exc)
            return None


def assemble_progress_reel(frames: list, out_dir: Path, out_basename: str) -> Path | None:
    """Write ``frames`` (PIL RGB images) as one looping animation beside master.

    Prefers animated WEBP (small, full colour) and falls back to APNG when the
    Pillow build lacks WEBP — both animate in a plain ``<img>`` and download as
    a shareable clip. The last frame holds a little longer so the finished look
    lands. Returns the written path, or ``None`` if there's nothing to write.
    """
    from PIL import Image, features

    if not frames:
        return None
    # Normalise to a common size (frames can differ by a rounding pixel as the
    # canvas grows) so the animation encoder is happy.
    base = frames[0]
    norm = [f if f.size == base.size else f.resize(base.size, Image.BOX) for f in frames]
    # Per-frame durations (ms): steady build, longer hold on the finished frame.
    durations = [400] * (len(norm) - 1) + [1400]
    out_dir = Path(out_dir)
    if features.check("webp"):
        path = out_dir / f"{out_basename}_progress.webp"
        norm[0].save(path, format="WEBP", save_all=True, append_images=norm[1:],
                     duration=durations, loop=0, minimize_size=True)
    else:
        path = out_dir / f"{out_basename}_progress.png"
        norm[0].save(path, format="PNG", save_all=True, append_images=norm[1:],
                     duration=durations, loop=0)
    log.info("Progress reel saved (%d frames) → %s", len(norm), path.name)
    return path


def make_test_reference_choice(frame: FrameRow) -> ReferenceChoice:
    """Helper for tests: wrap a single frame as a ReferenceChoice."""
    return ReferenceChoice(frame=frame, n_candidates=1, span_deg=0.0)


__all__ = [
    "StackOptions",
    "StackResult",
    "StackCancelled",
    "run_stack",
]
