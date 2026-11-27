"""Are stars in the owner's finished stacks fatter than in the subs they came from?

Roadmap 1.0, test R6. Subs are aligned by their plate solutions alone. If a
solve is off by half a pixel, every star in the stack is smeared, and no amount
of editing brings that back. The audit estimated a 0.6 px solve error would
make stars ~17 % fatter, but ASTAP's real error on his subs is unknown.

**Method.** For his ten deepest targets that still have a stack on disk: the
median star size (FWHM) of the accepted subs, as QC measured it on each sub's
half-resolution green plane, against the median star size measured the same
way on a central crop of the newest stack's green channel (put on the same
half-resolution scale, allowing for drizzle). A ratio near 1.0 means alignment
costs nothing; 1.15 or more means sharpness is being lost in registration.
Only the crop is read from the stack (memory-mapped).

Read-only; catalogue names and numbers only.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import numpy as np

from seestack.diag import Diagnostic, DiagnosticStopped, iter_sub_refs, sub_path

MAX_TARGETS = 10
CROP = 1600  # px, a side, from the centre of the stack


def _green_fwhm_halfres(green: np.ndarray, scale: float) -> tuple[float | None, int]:
    """Median star FWHM of a full-resolution green plane, in QC's half-res pixels."""
    from seestack.qc.metrics import detect_stars, estimate_sky, median_fwhm

    crop = np.asarray(green, dtype=np.float32)
    finite = np.isfinite(crop)
    if not finite.any():
        return None, 0
    crop = np.where(finite, crop, float(np.median(crop[finite])))
    sky, std = estimate_sky(crop)
    src = detect_stars(crop, fwhm_guess_px=3.0 * 2 * scale, sky_median=sky, sky_std=std)
    fwhm = median_fwhm(crop, src, box_size=int(11 * 2 * scale) | 1)
    n = 0 if src is None else int(len(src))
    if fwhm is None:
        return None, n
    return float(fwhm) / (2.0 * scale), n


def _centre(plane, side: int) -> np.ndarray:  # noqa: ANN001
    h, w = plane.shape
    y0, x0 = max(0, h // 2 - side // 2), max(0, w // 2 - side // 2)
    return np.array(plane[y0:y0 + side, x0:x0 + side], dtype=np.float32)


def _stack_fwhm_halfres(fits_path: str, scale: float) -> tuple[float | None, int]:
    from astropy.io import fits

    with fits.open(fits_path, memmap=True) as hdul:
        data = next((h.data for h in hdul if getattr(h, "data", None) is not None
                     and h.data.ndim in (2, 3)), None)
        if data is None:
            return None, 0
        g = data[1] if data.ndim == 3 and data.shape[0] >= 3 else (
            data if data.ndim == 2 else data[0])
        crop = _centre(g, int(CROP * max(scale, 1.0)))
    return _green_fwhm_halfres(crop, scale)


def _sub_same_method(paths: list[str]) -> float | None:
    """The same measurement on single debayered subs — the baseline a perfect
    registration would reproduce (debayer and the measurement add their own
    blur, so the honest comparison is like with like)."""
    from seestack.io.fits_loader import load_seestar_raw

    vals = []
    for p in paths:
        try:
            rgb, _ = load_seestar_raw(p, debayer=True)
        except Exception:  # noqa: BLE001
            continue
        f, _ = _green_fwhm_halfres(_centre(rgb[..., 1], CROP), 1.0)
        if f:
            vals.append(f)
    return statistics.median(vals) if vals else None


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    from seestack.stack.output import fits_is_display_space

    entries = sorted(library.list_targets(), key=lambda e: -(e.n_frames_accepted or 0))
    rows: list[dict[str, Any]] = []
    for e in entries:
        if len(rows) >= MAX_TARGETS:
            break
        if should_stop is not None and should_stop():
            raise DiagnosticStopped("stopped")
        try:
            proj = library.open_target(e.safe_name)
        except Exception:  # noqa: BLE001
            continue
        try:
            run_row = next((r for r in proj.iter_stack_runs()
                            if r.fits_path and Path(r.fits_path).exists()
                            and not fits_is_display_space(r.fits_path)), None)
            if run_row is None:
                continue
            subs = [float(f) for (f,) in proj.iter_frame_columns("fwhm_px", accepted_only=True)
                    if f]
            refs = list(iter_sub_refs(proj, accepted_only=True))
        finally:
            proj.close()
        if len(subs) < 5:
            continue
        try:
            opts = json.loads(run_row.options_json or "{}")
        except ValueError:
            opts = {}
        scale = float(opts.get("drizzle_scale") or 1.0) if opts.get("drizzle") else 1.0
        if progress is not None:
            progress("measuring stars in stacks", len(rows), MAX_TARGETS)
        try:
            stack_fwhm, n_stars = _stack_fwhm_halfres(run_row.fits_path, scale)
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": e.name, "error": type(exc).__name__})
            continue
        sub_med = statistics.median(subs)
        step = max(1, len(refs) // 3)
        baseline = _sub_same_method([p for p in (sub_path(r) for r in refs[::step][:3]) if p])
        rows.append({
            "name": e.name, "subs_in_stack": run_row.n_frames_used,
            "mosaic": bool(run_row.is_mosaic), "drizzle_scale": scale,
            "sub_fwhm_median": round(sub_med, 3),
            "sub_fwhm_p10_p90": [round(float(np.percentile(subs, 10)), 3),
                                 round(float(np.percentile(subs, 90)), 3)],
            "stack_fwhm": None if stack_fwhm is None else round(stack_fwhm, 3),
            "stack_stars_found": n_stars,
            "ratio_stack_to_subs": (None if stack_fwhm is None
                                    else round(stack_fwhm / sub_med, 3)),
            "sub_fwhm_same_method": None if baseline is None else round(baseline, 3),
            "ratio_stack_to_single_sub_same_method": (
                None if stack_fwhm is None or not baseline else round(stack_fwhm / baseline, 3)),
        })
    ratios = [r["ratio_stack_to_single_sub_same_method"] for r in rows
              if r.get("ratio_stack_to_single_sub_same_method")]
    return {
        "targets": rows,
        "median_ratio": round(statistics.median(ratios), 3) if ratios else None,
        "how_to_read": ("median_ratio compares each stack with single subs measured the same "
                        "way: ~1.0-1.08 alignment costs little; >=1.15 registration is "
                        "smearing stars and star-based refinement would help"),
    }


DIAGNOSTIC = Diagnostic(
    name="registration_sharpness",
    version=1,
    question=("Are stars in the owner's stacks fatter than in their subs, i.e. is "
              "plate-solve-only alignment costing sharpness? (1.0 roadmap R6)"),
    run=run,
    on_demand=True,
    ready=lambda library: any((e.n_frames_accepted or 0) >= 10 for e in library.list_targets()),
)
