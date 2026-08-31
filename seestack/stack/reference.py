"""
Reference-frame selection.

The reference frame defines the **output canvas**: every other accepted frame
gets reprojected onto its WCS. Picking it well saves you a lot of pain — bad
choices lead to half the data falling off the edges of the output, or the
output being aligned to a frame with bad seeing.

Selection rules (in order):

  1. Frame must be ``accept=True`` AND have a WCS solution.
  2. Among those, prefer frames near the **median** RA/Dec (typical pointing).
  3. Tie-break by lowest FWHM (sharpest frame).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from seestack.coords import unwrap_ra_deg
from seestack.io.project import FrameRow, Project

log = logging.getLogger(__name__)


@dataclass
class ReferenceChoice:
    """The chosen reference frame plus a few diagnostics."""

    frame: FrameRow
    n_candidates: int
    span_deg: float  # rough angular span of all candidates' centers


def pick_central_frame(candidates: list[FrameRow]) -> FrameRow | None:
    """
    The frame nearest the *median* pointing of ``candidates`` (tie-break: lowest
    FWHM), or ``None`` when the list is empty.

    The selection core of :func:`pick_reference_frame`, pulled out so the same
    rule can pick a reference for a **subset** of frames — one mosaic panel's
    subs, when the sub-pixel refine step wants a reference patch per panel
    rather than one patch on whichever panel happens to hold the target-wide
    reference. Callers pass frames they have already filtered (solved, with a
    pointing); a frame without a pointing is skipped here rather than scored.
    """
    solved = [
        f for f in candidates
        if f.ra_center_deg is not None and f.dec_center_deg is not None
    ]
    if not solved:
        return None

    # Median center. RA wraps at 0°/360°: a target imaged near RA=0h has frames
    # straddling the boundary (some at ~359.9°, some at ~0.1°), and a naive
    # median/subtraction would put the apparent centre ~180° away, score the
    # wrapped frames as hugely distant — so unwrap first and do the median and
    # the distances in that continuous space. With no wrap this leaves every
    # value untouched, so a normal target behaves exactly as before.
    uras = unwrap_ra_deg([f.ra_center_deg for f in solved])  # type: ignore[misc]
    decs = [f.dec_center_deg for f in solved]  # type: ignore[misc]
    med_ra = sorted(uras)[len(uras) // 2]
    med_dec = sorted(decs)[len(decs) // 2]
    cos_dec = math.cos(math.radians(med_dec))

    # Pick the frame with the smallest distance to median, breaking ties by
    # the lowest FWHM. Frames without a measured FWHM go last in tiebreaks.
    def score(idx: int) -> tuple[float, float]:
        f = solved[idx]
        dx = (uras[idx] - med_ra) * cos_dec
        dy = decs[idx] - med_dec
        dist = math.hypot(dx, dy)
        fwhm = f.fwhm_px if f.fwhm_px is not None else float("inf")
        return (dist, fwhm)

    return solved[min(range(len(solved)), key=score)]


def pick_reference_frame(project: Project) -> ReferenceChoice | None:
    """
    Pick the best reference frame from a project. Returns None if no accepted
    frame has been plate-solved yet.
    """
    candidates = [
        f for f in project.iter_frames(accepted_only=True)
        if f.wcs_json and f.ra_center_deg is not None and f.dec_center_deg is not None
    ]
    if not candidates:
        return None

    # RA wraps at 0°/360°: a target imaged near RA=0h has frames straddling the
    # boundary (some at ~359.9°, some at ~0.1°), and a naive subtraction would
    # report a ~360° span. Unwrap the candidate RAs into a continuous range first
    # (the same fix ``compute_mosaic_canvas`` and ``pick_central_frame`` use),
    # then take the span in that unwrapped space. With no wrap this leaves every
    # value untouched, so a normal target behaves exactly as before.
    raw_ras = [f.ra_center_deg for f in candidates]  # type: ignore[misc]
    uras = unwrap_ra_deg(raw_ras)
    decs = [f.dec_center_deg for f in candidates]  # type: ignore[misc]
    med_dec = sorted(decs)[len(decs) // 2]
    cos_dec = math.cos(math.radians(med_dec))

    # Pick the frame with the smallest distance to median, breaking ties by
    # the lowest FWHM (:func:`pick_central_frame` — the same rule a mosaic
    # panel uses to pick its own reference).
    best = pick_central_frame(candidates)
    assert best is not None  # candidates are pre-filtered to solved frames

    # Diagnostic: angular span (max distance between any two centers).
    if len(candidates) > 1:
        # Approximate via bounding box; fine for rough Tip in Tips sidebar later.
        ra_span = (max(uras) - min(uras)) * cos_dec
        dec_span = max(decs) - min(decs)
        span_deg = math.hypot(ra_span, dec_span)
    else:
        span_deg = 0.0

    log.info(
        "Reference frame: id=%s name=%s  candidates=%d  span=%.3f°",
        best.id, best.source_path, len(candidates), span_deg,
    )
    return ReferenceChoice(frame=best, n_candidates=len(candidates), span_deg=span_deg)
