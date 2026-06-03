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
import os
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from itertools import islice
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from seestack.bg.per_frame import BackgroundOptions
from seestack.core.xp import GPU_AVAILABLE
from seestack.io.project import FrameRow, Project
from seestack.stack.accumulator import WeightedSumAccumulator, WelfordAccumulator
from seestack.stack.align import align_one, extract_reference_patch
from seestack.stack.reference import ReferenceChoice, pick_reference_frame
from seestack.stack.weighting import compute_frame_weights, unit_weights

# Peak count of full-canvas float32 RGB arrays alive at once across the stack
# passes (Welford mean/M2/count, or drizzle output/weight/context, plus working
# copies). Used only to *estimate* memory and refuse oversized stacks before
# allocating — a wrong guess just shifts the refusal threshold a little.
_PEAK_CANVAS_ARRAYS = 4
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


def _stack_memory_budget_bytes() -> float:
    """How much working memory a single stack may use. Honors an explicit
    ASTROSTACK_MAX_STACK_GB override, else ~70% of currently-available RAM
    (leaving headroom for worker subprocesses, OS cache and the web app)."""
    override = os.environ.get("ASTROSTACK_MAX_STACK_GB")
    if override:
        try:
            return float(override) * 1e9
        except ValueError:
            pass
    avail = _available_memory_bytes()
    if avail:
        return avail * 0.7
    return _DEFAULT_STACK_BUDGET_GB * 1e9


def _guard_stack_memory(dst_shape: tuple[int, int], *, drizzle: bool,
                        drizzle_scale: float) -> None:
    """Refuse a stack whose output canvas would blow the memory budget instead
    of letting it OOM-kill the whole process. ``dst_shape`` is (h, w) of the
    pre-drizzle canvas; drizzle multiplies each axis by ``drizzle_scale``."""
    h, w = dst_shape
    if drizzle:
        s = max(1.0, float(drizzle_scale))
        out_pixels = int(h * s + 1) * int(w * s + 1)
    else:
        out_pixels = h * w
    need = out_pixels * 3 * 4 * _PEAK_CANVAS_ARRAYS  # float32 RGB working arrays
    budget = _stack_memory_budget_bytes()
    if need > budget:
        raise MemoryError(
            f"stack output canvas {w}×{h}"
            + (f" ×{drizzle_scale:g} drizzle" if drizzle else "")
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
    # Output canvas mode:
    #   'auto'      — union-of-footprints canvas when frames span more than
    #                 one Seestar field (a mosaic), reference frame otherwise.
    #   'union'     — always use the union-of-footprints canvas.
    #   'reference' — always crop to the reference frame's footprint.
    mosaic_canvas: str = "auto"

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


CancelFn = Callable[[], bool]
ProgressFn = Callable[[str, int, int], None]


class StackCancelled(RuntimeError):
    """Raised internally when the user cancels mid-stack."""


def run_stack(
    project: Project,
    options: StackOptions,
    *,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> StackResult:
    """
    Execute a stacking run end-to-end. Synchronous — call this from a worker
    thread if you want a responsive GUI.
    """
    progress = progress or (lambda *a: None)
    cancel = cancel or (lambda: False)

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
    if options.quality_weighted:
        weights, wstats = compute_frame_weights(frames)
        log.info(
            "Quality weights: %d weighted (median=%.2f range=[%.2f, %.2f]), %d neutral",
            wstats.n_weighted, wstats.median_weight, wstats.min_weight,
            wstats.max_weight, wstats.n_neutral,
        )
    else:
        weights = unit_weights(frames)

    # Pre-compute the reference patch for sub-pixel alignment, by aligning
    # the reference frame to itself once and extracting a central luminance
    # window. This happens before the parallel passes so every worker can
    # share it.
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
    backend = "GPU (cupy)" if (
        (options.use_gpu is True) or (options.use_gpu is None and GPU_AVAILABLE)
    ) else "CPU (numpy/scipy)"
    log.info(
        "Stacking %d frames into %dx%d canvas — backend=%s, bg_flatten=%s, sigma_clip=%s",
        n, dst_shape[1], dst_shape[0], backend,
        options.background_flatten, options.sigma_clip,
    )

    canvas_3 = (dst_shape[0], dst_shape[1], 3)
    # Refuse a stack that would exhaust RAM *before* allocating anything — a
    # drizzled near-cap mosaic canvas can otherwise reach tens of GB and get the
    # whole container OOM-killed (there's no cgroup limit to catch it).
    _guard_stack_memory(dst_shape, drizzle=options.drizzle,
                        drizzle_scale=options.drizzle_scale)
    errors: list[str] = []

    # ---- 3a. Drizzle path (alternate single-pass accumulator) -------------
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
        drizzler = DrizzleStacker(ref_wcs, dst_shape, params)
        log.info("Drizzle: pixfrac=%.2f scale=%.2f kernel=%s output=%dx%d",
                 params.pixfrac, params.scale, params.kernel,
                 drizzler.output_canvas_shape[1], drizzler.output_canvas_shape[0])
        n_used = _drizzle_pass(
            frames, ref, drizzler,
            options=options,
            progress=progress, cancel=cancel,
            errors=errors,
        )
        if n_used == 0:
            raise ValueError("drizzle: no usable frames")
        result_image = drizzler.result()
        coverage = drizzler.coverage
        # Write outputs against the **drizzle** output canvas, not the
        # reference canvas. The drizzle WCS lives at drizzler.out_wcs.
        dst_wcs_text = wcs_to_text(drizzler.out_wcs)
        dst_shape = drizzler.output_canvas_shape

    # ---- 3b. Standard path: pass 1 streaming mean + std --------------------
    # If sigma-clipping is off we go directly to the weighted sum and we're
    # done after one pass.
    elif options.sigma_clip and n >= 4:
        wel = WelfordAccumulator(canvas_3)
        ql_state = {"counter": 0}

        def consume_pass1(aligned: np.ndarray, y0: int, x0: int, _weight: float) -> None:
            wel.add_window(aligned, y0, x0)
            if options.quick_look_interval > 0:
                ql_state["counter"] += 1
                if ql_state["counter"] % options.quick_look_interval == 0:
                    _save_quick_look(project.project_dir, wel.mean(),
                                     options.output_name, ql_state["counter"])

        n_used_p1 = _pass(
            frames, ref, dst_wcs_text, dst_shape, weights,
            options=options,
            phase_label="Pass 1/2 (mean & σ)",
            consumer=consume_pass1,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
        )
        if n_used_p1 == 0:
            raise ValueError("pass 1 produced no usable frames")

        # ---- 4. Pass 2: clipped weighted sum ------------------------------
        mean = wel.mean()
        std = wel.std()
        wsum = WeightedSumAccumulator(canvas_3)

        def consume_clipped(aligned: np.ndarray, y0: int, x0: int, weight: float) -> None:
            wh, ww = aligned.shape[:2]
            mean_win = mean[y0:y0 + wh, x0:x0 + ww]
            std_win = std[y0:y0 + wh, x0:x0 + ww]
            valid = np.isfinite(aligned)
            tol = options.sigma_kappa * np.where(np.isfinite(std_win), std_win, np.inf)
            keep = valid & (np.abs(aligned - mean_win) <= tol)
            wsum.add_window(np.where(keep, aligned, np.nan), y0, x0, weight=weight)

        n_used_p2 = _pass(
            frames, ref, dst_wcs_text, dst_shape, weights,
            options=options,
            phase_label="Pass 2/2 (clipped sum)",
            consumer=consume_clipped,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
        )
        n_used = min(n_used_p1, n_used_p2)
        result_image = wsum.result()
        coverage = wsum.coverage
    else:
        # Single-pass weighted mean.
        wsum = WeightedSumAccumulator(canvas_3)
        ql_state_single = {"counter": 0}

        def consume_one_pass(aligned: np.ndarray, y0: int, x0: int, weight: float) -> None:
            wsum.add_window(aligned, y0, x0, weight=weight)
            if options.quick_look_interval > 0:
                ql_state_single["counter"] += 1
                if ql_state_single["counter"] % options.quick_look_interval == 0:
                    _save_quick_look(project.project_dir, wsum.result(),
                                     options.output_name, ql_state_single["counter"])

        n_used = _pass(
            frames, ref, dst_wcs_text, dst_shape, weights,
            options=options,
            phase_label="Stacking",
            consumer=consume_one_pass,
            progress=progress, cancel=cancel,
            errors=errors,
            ref_patch=ref_patch, ref_patch_origin=ref_patch_origin,
        )
        if n_used == 0:
            raise ValueError("no frames could be aligned")
        result_image = wsum.result()
        coverage = wsum.coverage

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

    paths = write_stack_outputs(
        project_dir=project.project_dir,
        rgb=result_image,
        coverage=coverage,
        wcs_text=dst_wcs_text,
        out_basename=options.output_name,
        tiff_mode=options.tiff_mode,
    )
    progress("Saving", 1, 1)

    # Record this run in the project history.
    try:
        from dataclasses import asdict
        from datetime import datetime, timezone
        import json as _json
        from seestack.io.project import StackRunRow

        cov_2d = coverage[..., 0] if coverage.ndim == 3 else coverage
        project.add_stack_run(StackRunRow(
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
            options_json=_json.dumps(asdict(options)),
            notes=color_cal_note or None,
        ))
    except Exception as exc:  # noqa: BLE001 — history is non-critical
        log.warning("Could not record stack run in history: %s", exc)

    # Coverage min/max for diagnostics — taken across all 3 channels.
    cov_2d = coverage[..., 0]  # all channels share the same valid mask in our pipeline
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
) -> int:
    """
    Run one pass over ``frames``, feeding each windowed aligned image plus its
    canvas offset and per-frame quality weight into
    ``consumer(window_rgb, y0, x0, weight)``. Returns the number of frames
    that contributed (post-error).
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
            w = weights.get(f.id or -1, 1.0)
            with consumer_lock:
                consumer(win_rgb, y0, x0, w)
            used += 1
            progress(phase_label, done, total)
    return used


def _drizzle_pass(
    frames: list[FrameRow],
    ref: FrameRow,
    drizzler,
    *,
    options: StackOptions,
    progress: ProgressFn,
    cancel: CancelFn,
    errors: list[str],
) -> int:
    """
    One-shot drizzle accumulation. Drizzle's ``add_image`` mutates internal
    state, so we serialise additions on one thread but parallelise the per-
    frame load+debayer+bg-flatten+pixmap on workers. Workers return prepared
    payloads; the consumer thread feeds them into the drizzler.
    """
    from seestack.io.wcs_io import wcs_from_text

    total = len(frames)
    progress("Drizzle", 0, total)
    max_workers = options.max_workers or max(1, (os.cpu_count() or 4))
    bg_opts = options.background_options()
    used = 0
    done = 0

    def prepare(frame: FrameRow):
        path = frame.cached_path or frame.source_path
        if not path or not Path(path).exists() or not frame.wcs_json:
            return None
        from seestack.bg.per_frame import subtract_background
        from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw

        raw, info = load_seestar_raw(path, debayer=False, out_dtype=np.float32)
        pattern = frame.bayer_pattern or info.bayer_pattern or "RGGB"
        rgb = bilinear_debayer(raw, pattern=pattern)
        if bg_opts.enabled:
            rgb = subtract_background(rgb, bg_opts, use_gpu=options.use_gpu)
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
                progress("Drizzle (cancelled)", done, total)
                break
            try:
                payload = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: {type(exc).__name__}: {exc}")
                progress("Drizzle", done, total)
                continue
            if payload is None:
                progress("Drizzle", done, total)
                continue
            rgb, in_wcs = payload
            try:
                drizzler.add_frame(rgb, in_wcs)
                used += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{Path(f.source_path).name}: drizzle add_image: {exc}")
            progress("Drizzle", done, total)
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
    )
    if result is None:
        return None
    win_rgb, _win_valid, y0, x0 = result
    return win_rgb, y0, x0


def _save_quick_look(
    project_dir: Path,
    rgb: np.ndarray,
    out_basename: str,
    counter: int,
) -> None:
    """
    Write a small autostretched PNG of the current accumulator state.

    Called periodically during pass 1 so the user can peek at how the stack
    is shaping up. Single file (overwritten) so it doesn't accumulate noise
    in the output folder.
    """
    try:
        from PIL import Image
        from seestack.render.thumbnail import autostretch

        # Pass NaN straight through — autostretch is nan-aware and must compute
        # its stats over covered pixels only (a mosaic's no-data gaps would
        # otherwise wreck the colour balance).
        stretched = autostretch(rgb.astype(np.float32, copy=False))
        h, w = stretched.shape[:2]
        max_w = 1024
        if w > max_w:
            new_w = max_w
            new_h = max(1, int(round(h * (new_w / w))))
            u8 = (np.clip(stretched, 0, 1) * 255).astype(np.uint8)
            preview = Image.fromarray(u8, "RGB").resize((new_w, new_h), Image.BOX)
        else:
            u8 = (np.clip(stretched, 0, 1) * 255).astype(np.uint8)
            preview = Image.fromarray(u8, "RGB")
        out_dir = Path(project_dir) / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        ql_path = out_dir / f"{out_basename}_quicklook.png"
        preview.save(ql_path, format="PNG")
        log.debug("Quick-look saved (%d frames in) → %s", counter, ql_path)
    except Exception as exc:  # noqa: BLE001 — never fail the stack over a peek
        log.warning("Quick-look save failed: %s", exc)


def make_test_reference_choice(frame: FrameRow) -> ReferenceChoice:
    """Helper for tests: wrap a single frame as a ReferenceChoice."""
    return ReferenceChoice(frame=frame, n_candidates=1, span_deg=0.0)


__all__ = [
    "StackOptions",
    "StackResult",
    "StackCancelled",
    "run_stack",
]
