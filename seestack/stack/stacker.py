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
from seestack.io.project import FrameRow, Project
from seestack.stack.accumulator import (
    MinMaxRejectAccumulator,
    WeightedSumAccumulator,
    WelfordAccumulator,
)
from seestack.stack.align import align_one, extract_reference_patch
from seestack.stack.output import _sanitize_basename
from seestack.stack.reference import ReferenceChoice, pick_reference_frame
from seestack.stack.photometric import PhotometricStats, compute_photometric_scales
from seestack.stack.weighting import WeightingStats, compute_frame_weights, unit_weights

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


def _estimate_peak_bytes(dst_shape: tuple[int, int], *, drizzle: bool,
                         drizzle_scale: float,
                         drizzle_reject: bool = False,
                         reject_arrays: int = 0,
                         ) -> tuple[int, tuple[int, int]]:
    """Peak working-memory estimate for a stack and its post-drizzle output
    shape. ``dst_shape`` is (h, w) of the pre-drizzle canvas; drizzle multiplies
    each axis by ``drizzle_scale``. Returns ``(peak_bytes, (out_h, out_w))``.

    ``reject_arrays`` is the number of canvas planes a top/bottom-k min/max reject
    accumulator holds at once (see ``_min_max_reject_arrays``); it raises the array
    factor when a k>1 reject would need more than the baseline working set.

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
    return need, (out_h, out_w)


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


def _guard_stack_memory(dst_shape: tuple[int, int], *, drizzle: bool,
                        drizzle_scale: float,
                        drizzle_reject: bool = False,
                        reject_arrays: int = 0,
                        memory_budget_gb: float | None = None) -> None:
    """Refuse a stack whose output canvas would blow the memory budget instead
    of letting it OOM-kill the whole process. ``dst_shape`` is (h, w) of the
    pre-drizzle canvas; drizzle multiplies each axis by ``drizzle_scale``."""
    h, w = dst_shape
    need, _ = _estimate_peak_bytes(dst_shape, drizzle=drizzle,
                                   drizzle_scale=drizzle_scale,
                                   drizzle_reject=drizzle_reject,
                                   reject_arrays=reject_arrays)
    budget = _stack_memory_budget_bytes(memory_budget_gb)
    if need > budget:
        raise MemoryError(
            f"stack output canvas {w}×{h}"
            + (f" ×{drizzle_scale:g} drizzle" if drizzle else "")
            + (" with outlier rejection" if (drizzle and drizzle_reject) else "")
            + f" needs ~{need / 1e9:.1f} GB of working memory, over the "
            f"~{budget / 1e9:.1f} GB budget. Reduce drizzle scale, switch Canvas "
            f"mode to 'reference', reject outlier/off-target frames, or raise "
            f"ASTROSTACK_MAX_STACK_GB to override."
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
    # The new ``stack_runs`` row id for this run (None if history recording was
    # skipped — e.g. a cancelled run — or failed). Lets callers deep-link the
    # finished run's editor instead of just its target's History list.
    run_id: int | None = None


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


def _auto_kappa_min_frames(kappa: float) -> int:
    """Smallest frame count at which κ-σ can reject a *lone* outlier.

    A single point's z-score against statistics that still include it is at most
    ``(n−1)/√n``; that first reaches ``κ`` at ``n = ⌈((κ+√(κ²+4))/2)²⌉``. Below
    this, κ-σ is mathematically blind to a lone satellite/plane trail, so
    ``auto`` uses the order-statistic min/max drop (which removes an extreme even
    at n=3) instead. Floored at 3 (min/max needs ≥3 to spare two samples)."""
    u = (kappa + math.sqrt(kappa * kappa + 4.0)) / 2.0
    return max(3, int(math.ceil(u * u)))


def _resolve_auto_reject(options: StackOptions, n: int) -> StackOptions:
    """Resolve ``auto_reject`` into concrete ``sigma_clip``/``min_max_reject``.

    When ``auto_reject`` is on (and not drizzling), pick order-statistic min/max
    for small stacks — the only method that removes a lone outlier below
    :func:`_auto_kappa_min_frames` — and weight-respecting κ-σ once the stack is
    large enough for κ-σ to bite. Returns ``options`` unchanged when
    ``auto_reject`` is off or drizzle is on (drizzle has its own two-pass
    rejection), so a run that doesn't opt in is byte-for-byte identical."""
    if not options.auto_reject or options.drizzle:
        return options
    use_kappa = n >= _auto_kappa_min_frames(options.sigma_kappa)
    return replace(options, sigma_clip=use_kappa, min_max_reject=not use_kappa)


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
        if canvas is not None and (options.mosaic_canvas == "union"
                                   or canvas.is_mosaic):
            dst_shape = canvas.shape
            is_mosaic = canvas.is_mosaic

    n = len(frames)
    # Resolve auto-reject so the pre-run memory estimate matches the method
    # ``run_stack`` will actually use (min/max costs extra canvas planes).
    options = _resolve_auto_reject(options, n)
    peak, (out_h, out_w) = _estimate_peak_bytes(
        dst_shape, drizzle=options.drizzle, drizzle_scale=options.drizzle_scale,
        drizzle_reject=options.drizzle_reject and n >= 4,
        reject_arrays=(_min_max_reject_arrays(options.min_max_reject_count)
                       if options.min_max_reject and not options.drizzle and n >= 3
                       else 0),
    )
    budget = int(_stack_memory_budget_bytes(memory_budget_gb))
    would_exceed = int(peak) > budget
    suggested_scale: float | None = None
    suggest_ref_canvas = False
    if would_exceed and options.drizzle:
        suggested_scale = _largest_drizzle_scale_within_budget(
            dst_shape, drizzle_reject=options.drizzle_reject and n >= 4,
            budget=budget, max_scale=float(options.drizzle_scale),
        )
    elif would_exceed and is_mosaic:
        # Drizzle off and the union mosaic canvas alone blows the budget — would
        # the smaller reference-frame canvas fit? If so the UI can offer a
        # one-click "use the reference canvas instead".
        ref_peak, _ = _estimate_peak_bytes(
            ref_shape, drizzle=False, drizzle_scale=1.0)
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


def _compute_transparency_ratio(project: Project, frames: list) -> float | None:
    """Median transparency of the stacked frames vs this target's clear-sky
    baseline, normalised within the target (the raw ``transparency_score`` isn't
    comparable across gain/exposure).

    Returns ``median(run) / p90(all)`` — a value well below 1.0 means the stack
    was shot through haze / thin cloud relative to the target's clearest nights.
    Mirrors the Stack form's pre-run hint so a completed run can carry the same
    verdict for an at-a-glance "hazy night" badge. ``None`` when there isn't a
    meaningful sample on both sides. Best-effort: never raises into the caller.
    """
    try:
        run = [f.transparency_score for f in frames
               if getattr(f, "transparency_score", None) and f.transparency_score > 0]
        all_scores = [f.transparency_score for f in project.iter_frames()
                      if f.transparency_score is not None and f.transparency_score > 0]
        # Need a reasonable sample on both sides to say anything meaningful.
        if len(all_scores) < 5 or len(run) < 3:
            return None
        baseline = float(np.percentile(all_scores, 90))
        if baseline <= 0:
            return None
        run_med = float(np.percentile(run, 50))
        return round(run_med / baseline, 4)
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
    rstats: "RejectionStats | None" = None,
    weights_applied: bool = True,
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
    if options.drizzle:
        method = "drizzle"
    elif options.min_max_reject:
        method = "min-max-reject"
    elif options.sigma_clip:
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
    if calibration is not None and getattr(calibration, "scale_dark_to_light", False):
        dark_exp = getattr(calibration, "dark_exposure_s", None)
        has_bias = getattr(calibration, "bias", None) is not None
        has_dark = getattr(calibration, "dark", None) is not None
        light_exp = exposures[len(exposures) // 2] if exposures else None
        if (has_bias and has_dark and dark_exp and light_exp
                and dark_exp > 0 and light_exp > 0
                and abs(float(light_exp) / float(dark_exp) - 1.0) > 1e-3):
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
    # Photometric-normalization provenance: records that frames were gain-matched
    # and over what scale range, so a normalised stack self-documents (mirrors the
    # WGT* keys). Omitted when nothing was actually scaled.
    if pstats is not None and pstats.n_scaled:
        meta["PHOTNORM"] = ("transparency", "photometric normalization mode")
        meta["PHOTNADJ"] = (int(pstats.n_adjusted), "frames photometrically scaled")
        meta["PHOTMIN"] = (round(float(pstats.min_scale), 3), "min frame scale")
        meta["PHOTMAX"] = (round(float(pstats.max_scale), 3), "max frame scale")
        meta["PHOTMED"] = (round(float(pstats.median_scale), 3), "median frame scale")
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

    # Build the per-frame weight map. Defaults to all-1.0 unless quality_weighted.
    wstats: WeightingStats | None = None
    if options.quality_weighted:
        weights, wstats = compute_frame_weights(frames)
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
    pscales: dict[int, float] | None = None
    pstats: PhotometricStats | None = None
    if options.photometric_normalize:
        pscales, pstats = compute_photometric_scales(frames)
        log.info(
            "Photometric normalization: %d scaled (median=%.3f range=[%.3f, %.3f]), "
            "%d adjusted, %d neutral",
            pstats.n_scaled, pstats.median_scale, pstats.min_scale,
            pstats.max_scale, pstats.n_adjusted, pstats.n_neutral,
        )
        # Nothing measurable → don't carry a no-op scale map (keeps the hot path
        # and the provenance honest).
        if pstats.n_scaled == 0:
            pscales = None

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
                fits_path=str(ref.cached_path or ref.source_path),
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
            ref_patch, ref_patch_origin = extract_reference_patch(ref_full)
            log.info("Sub-pixel refinement: ref patch %s at origin %s",
                     ref_patch.shape, ref_patch_origin)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not build reference patch for sub-pixel refine: %s", exc)
            ref_patch = None

    n = len(frames)
    # Effective options with ``auto_reject`` resolved to a concrete method from the
    # frame count. The original ``options`` (with the user's choice intact) is what
    # gets persisted in the run record; ``eff`` drives the method dispatch, the
    # memory guard, and the STACKER provenance card so all three agree.
    eff = _resolve_auto_reject(options, n)
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
    _guard_stack_memory(dst_shape, drizzle=options.drizzle,
                        drizzle_scale=options.drizzle_scale,
                        drizzle_reject=options.drizzle_reject and n >= 4,
                        reject_arrays=(_min_max_reject_arrays(eff.min_max_reject_count)
                                       if eff.min_max_reject and not options.drizzle and n >= 3
                                       else 0),
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

    # Periodic pass-1 previews: the legacy quick-look PNG and, when
    # ``save_progress`` is on, the "watch it appear" reel. Wired into the
    # standard (non-drizzle) accumulator paths below; assembled after the
    # outputs are written (post-archive).
    ql = _QuickLook(project.project_dir, options.output_name, options, n)

    # ---- 3a. Drizzle path (alternate accumulator) --------------------------
    if options.drizzle:
        from seestack.io.wcs_io import wcs_from_text, wcs_to_text
        from seestack.stack.drizzle_path import DrizzleParams, DrizzleStacker

        ref_wcs = wcs_from_text(dst_wcs_text)
        if ref_wcs is None:
            raise ValueError("reference WCS could not be parsed for drizzle")
        params = DrizzleParams(
            pixfrac=options.drizzle_pixfrac,
            scale=options.drizzle_scale,
            kernel=options.drizzle_kernel,
        )
        # Optional two-pass outlier rejection: pass 1 accumulates value and
        # value² to get per-output-pixel contribution statistics, pass 2
        # re-drizzles with outliers (satellites, plane trails, cosmic rays)
        # zero-weighted. Mirrors the standard path's n>=4 sigma-clip gate.
        reject = options.drizzle_reject and n >= 4
        if options.drizzle_reject and not reject:
            log.info("Drizzle outlier rejection skipped: needs >=4 frames, have %d", n)
        clip = None
        if reject:
            stats = DrizzleStacker(ref_wcs, dst_shape, params, compute_stats=True)
            n_stats = _drizzle_pass(
                frames, ref, stats, weights,
                options=options,
                phase_label="Drizzle 1/2 (statistics)",
                progress=progress, cancel=cancel,
                errors=errors,
                calibration=calibration,
                mono=options.mono,
                photometric_scales=pscales,
            )
            if n_stats == 0 and not cancel():
                raise ValueError("drizzle: no usable frames")
            if not cancel():
                clip = stats.clip_reference(options.sigma_kappa)
            # Free the statistics accumulators before pass 2 allocates its own.
            del stats
        drizzler = DrizzleStacker(ref_wcs, dst_shape, params)
        log.info("Drizzle: pixfrac=%.2f scale=%.2f kernel=%s reject=%s output=%dx%d",
                 params.pixfrac, params.scale, params.kernel, clip is not None,
                 drizzler.output_canvas_shape[1], drizzler.output_canvas_shape[0])
        n_used = _drizzle_pass(
            frames, ref, drizzler, weights,
            options=options,
            phase_label="Drizzle 2/2 (outlier-clipped)" if clip is not None else "Drizzle",
            clip=clip,
            progress=progress, cancel=cancel,
            errors=errors,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
        )
        if n_used == 0 and not cancel():
            raise ValueError("drizzle: no usable frames")
        # Surface how much the two-pass drizzle rejection actually clipped
        # (only when rejection ran — single-pass drizzle has no clip to tally).
        if clip is not None:
            _dz_contrib, _dz_rej = drizzler.rejection_counts()
            rej_stats = RejectionStats(
                mode="drizzle-reject",
                n_contributed=_dz_contrib,
                n_rejected=_dz_rej,
            )
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
        )
        if n_used == 0:
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
        )
        if n_used_p1 == 0:
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
        # σ is unknown (NaN → +inf tol) nothing is clipped, so it's excluded from
        # rejected but still counted as contributed — the honest denominator.
        clip_counts = {"contributed": 0, "rejected": 0}

        def consume_clipped(aligned: np.ndarray, y0: int, x0: int, weight: float) -> None:
            wh, ww = aligned.shape[:2]
            mean_win = mean[y0:y0 + wh, x0:x0 + ww]
            std_win = std[y0:y0 + wh, x0:x0 + ww]
            valid = np.isfinite(aligned)
            tol = options.sigma_kappa * np.where(np.isfinite(std_win), std_win, np.inf)
            keep = valid & (np.abs(aligned - mean_win) <= tol)
            clip_counts["contributed"] += int(valid.sum())
            clip_counts["rejected"] += int(np.count_nonzero(valid & ~keep))
            wsum.add_window(np.where(keep, aligned, np.nan), y0, x0, weight=weight)

        n_used_p2 = _pass(
            frames, ref, dst_wcs_text, dst_shape, weights,
            options=options,
            phase_label="Pass 2/2 (clipped sum)",
            consumer=consume_clipped,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
        )
        n_used = min(n_used_p1, n_used_p2)
        # Pass 1 succeeded but pass 2 aligned nothing (e.g. the cached/source
        # frames became unreadable *between* the two passes on a long run) →
        # ``wsum`` is empty and ``result()`` is all-NaN. Guard it exactly like
        # the min/max, pass-1, and single-pass branches do: raise rather than
        # fall through to writing a silent all-NaN master recorded as a
        # *successful* run with ``n_frames_used=0`` (the same hazard the drizzle
        # two-pass path already guards against).
        if n_used == 0:
            raise ValueError("pass 2 produced no usable frames")
        result_image = wsum.result()
        coverage = wsum.coverage
        frame_cov = wsum.frame_coverage
        rej_stats = RejectionStats(
            mode="sigma-clip",
            n_contributed=clip_counts["contributed"],
            n_rejected=clip_counts["rejected"],
        )
    else:
        # Single-pass weighted mean.
        wsum = WeightedSumAccumulator(canvas_3)

        def consume_one_pass(aligned: np.ndarray, y0: int, x0: int, weight: float) -> None:
            wsum.add_window(aligned, y0, x0, weight=weight)
            ql.on_frame(wsum.result)

        n_used = _pass(
            frames, ref, dst_wcs_text, dst_shape, weights,
            options=options,
            phase_label="Stacking",
            consumer=consume_one_pass,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
            calibration=calibration,
            mono=options.mono,
            photometric_scales=pscales,
        )
        if n_used == 0:
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
        )

    # ---- 4.4. Per-coverage sky leveling -----------------------------------
    # Always run — it's effectively a no-op when coverage is uniform (single-
    # target stacks). For any stack with varying coverage (mosaics, dither
    # margins, partial captures) it kills the panel-rectangle steps that come
    # from per-frame biases the upstream pipeline couldn't fully remove.
    from seestack.bg.coverage_leveling import level_by_coverage

    progress("Levelling panels", 0, 1)
    result_image = level_by_coverage(result_image, coverage)
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
    # The min/max order-statistic path combines by rank and ignores per-frame
    # weights, so weighting provenance must not be stamped when it ran (it's the
    # active path only for a non-drizzle ≥3-frame min-max-reject stack). Every
    # other path (drizzle, κ-σ pass 2, plain weighted sum, and the min/max
    # fall-back-to-mean when n < 3) does apply the weights.
    weights_applied = not (eff.min_max_reject and not options.drizzle and n >= 3)
    header_meta = _build_output_header_meta(project, frames, eff, n_used, wstats,
                                            calibration=calibration, pstats=pstats,
                                            rstats=rej_stats,
                                            weights_applied=weights_applied)
    if noise_sigma is not None:
        header_meta["BKGSIGMA"] = (noise_sigma, "normalized background noise sigma")
    paths = write_stack_outputs(
        project_dir=project.project_dir,
        rgb=result_image,
        coverage=coverage,
        wcs_text=dst_wcs_text,
        out_basename=options.output_name,
        tiff_mode=options.tiff_mode,
        header_meta=header_meta,
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
            transparency_ratio=_compute_transparency_ratio(project, frames),
            noise_sigma=noise_sigma,
            calstat=applied_cal,
            is_mosaic=bool(is_mosaic_canvas),
            engine_version=app_version,
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
        run_id=run_id,
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
) -> int:
    """
    Run one pass over ``frames``, feeding each windowed aligned image plus its
    canvas offset and per-frame quality weight into
    ``consumer(window_rgb, y0, x0, weight)``. Returns the number of frames
    that contributed (post-error).

    ``photometric_scales`` (optional) gain-matches each frame's *pixels* by an
    in-place multiply before the consumer sees them, so the scaling is applied
    identically in every pass and every accumulator/rejection path.
    """
    total = len(frames)
    progress(phase_label, 0, total)
    max_workers = options.max_workers or max(1, (os.cpu_count() or 4))
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
        for f, fut in _imap_bounded(ex, _submit, frames, max_workers * 2):
            done += 1
            if cancel():
                progress(phase_label + " (cancelled)", done, total)
                break
            try:
                aligned = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: {type(exc).__name__}: {exc}")
                progress(phase_label, done, total)
                continue
            if aligned is None:
                # Frame failed to load, or its footprint didn't intersect the
                # canvas (e.g. a stray frame from a different target).
                progress(phase_label, done, total)
                continue
            win_rgb, y0, x0 = aligned
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
) -> int:
    """
    One-shot drizzle accumulation. Drizzle's ``add_image`` mutates internal
    state, so we serialise additions on one thread but parallelise the per-
    frame load+debayer+bg-flatten+pixmap on workers. Workers return prepared
    payloads; the consumer thread feeds them into the drizzler.
    """
    from seestack.io.wcs_io import wcs_from_text

    total = len(frames)
    progress(phase_label, 0, total)
    max_workers = options.max_workers or max(1, (os.cpu_count() or 4))
    bg_opts = options.background_options()
    used = 0
    done = 0

    def prepare(frame: FrameRow):
        path = frame.cached_path or frame.source_path
        if not path or not Path(path).exists() or not frame.wcs_json:
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
        for f, fut in _imap_bounded(ex, prepare, frames, max_workers * 2):
            done += 1
            if cancel():
                progress(phase_label + " (cancelled)", done, total)
                break
            try:
                payload = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: {type(exc).__name__}: {exc}")
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
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: drizzle add_image: {exc}")
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
) -> tuple[np.ndarray, int, int] | None:
    """
    Worker entry point. Returns ``(window_rgb, y0, x0)`` — the reprojected
    frame cropped to its footprint plus its canvas offset — or ``None`` on
    benign failure (missing file, no WCS, footprint off-canvas).
    """
    path = frame.cached_path or frame.source_path
    if not path or not Path(path).exists():
        return None
    if not frame.wcs_json:
        return None
    result = align_one(
        fits_path=str(path),
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
    )
    if result is None:
        return None
    win_rgb, _win_valid, y0, x0 = result
    return win_rgb, y0, x0


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
