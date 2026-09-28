"""
Star-pattern registration — placing a sub that has no plate solution.

The stacker registers frames by plate-solved WCS and reprojection, and the
bootstrap rescue (:mod:`seestack.solve.bootstrap`) widens that to a burst whose
subs never solved individually: it phase-correlates each sub onto a reference and
offsets ``CRPIX`` by the measured shift. Phase correlation measures a
**translation**, which is all a short tracked burst needs — the audit measured
±2 px of uncompensated drift across the window it integrates.

A whole night is not a short burst. The Seestar is alt-az, so the field *rotates*
through a session: by the end of a long run the first and last sub differ by a
rotation no translation can absorb, and phase correlation either fails outright or
locks onto a smeared peak. Those subs are then left unsolved and never stack — on
exactly the faint targets the rescue exists for.

This module measures the **similarity** transform (rotation + translation + a
small scale) between two subs from their star *patterns*, the way DSS and Siril
register when there is no plate solution, via the ``astroalign`` triangle matcher
(the dependency the owner approved for it, 2026-09-25). It is deliberately
narrow:

* it answers about **pixels**, never about the sky. Turning a transform into a
  WCS is :func:`seestack.io.wcs_io.wcs_text_after_pixel_affine`'s job, and that
  composition is exact for the linear part of a WCS, which is all a similarity of
  the pixel grid can touch.
* it **refuses far more readily than it accepts**. A transform comes back only
  when enough control points matched, the fit's residual is sub-pixel, the matrix
  really is a similarity of positive determinant (no mirror — one camera cannot
  flip), the scale is within a hair of 1 and the frame's own centre moved less
  than the caller's cap. A wrongly-placed frame silently corrupts a stack,
  whereas a refused one is left out — which is precisely what happens to it
  today, so refusing costs nothing that is not already lost.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Detection knobs handed to astroalign. Its defaults, named here so a caller can
# see what it is asking for: 5σ over the background with a 5-pixel minimum area
# is a conservative star floor on a sky-subtracted Seestar sub, and 50 control
# points is far more than the fit needs while keeping the triangle match cheap.
DEFAULT_DETECTION_SIGMA = 5.0
DEFAULT_MIN_AREA = 5
DEFAULT_MAX_CONTROL_POINTS = 50

# A fit on fewer than this many matched stars is refused. astroalign can fit a
# similarity from 3 points, and a 3-point "match" is exactly the shape a chance
# triangle coincidence takes; six mutually-consistent stars at a sub-pixel
# residual is not something noise produces.
DEFAULT_MIN_CONTROL_POINTS = 6

# RMS residual (pixels) of the matched control points under the fitted transform.
# This is the real guard: a wrong match is a *random* transform, so its points do
# not land back on each other. astroalign's own matching tolerance is ~2 px, so
# asking for well under that asks the fit to be better than merely plausible.
DEFAULT_MAX_RESIDUAL_PX = 1.5

# The scale must be ~1: two subs of one target through one telescope have the
# same plate scale. A fit that wants to resize the field has matched the wrong
# stars.
DEFAULT_MAX_SCALE_DEVIATION = 0.01

# A sanity bound on the rotation, not a physical one. Alt-az field rotation over
# a long session is genuinely large (tens of degrees), which is the whole reason
# this module exists, so this cap is deliberately generous: it exists to refuse an
# absurd lock, and the residual above is what makes a wrong match essentially
# impossible.
DEFAULT_MAX_ROTATION_DEG = 90.0

# ``sep``, the source extractor astroalign detects stars with, limits how many
# sub-objects one deblend may produce — 1024 by default — and a **rich** field
# overflows it. astroalign then re-raises that as a generic "Input type for source
# not supported", i.e. indistinguishable from having been handed something that is
# not an image at all, so the symptom is a matcher that quietly never matches.
#
# **What the original measurement behind this number was really measuring, found
# 2026-09-28.** It was "0 of 8 subs matched at sep's default, 8 of 8 at 8192" on a
# 480x320 field of 30 stars — a field far too sparse to deblend 1024 sub-objects
# out of. It did so because :func:`registration_gray` clipped the sky noise's
# negative half away, which collapsed the noise estimate sep sets its detection
# threshold from, so *noise* was being deblended. With the negatives kept, the same
# fixture matches 8 of 8 at sep's own default, and so do 1,200 stars on 480x320 and
# 3,000 on 1920x1080 — all measured. So nothing synthetic needs this any more.
# It is kept, not removed: the limit only sizes an internal buffer, so a sparse
# field pays nothing for it, and a real crowded sky (a globular, the galactic
# plane) is not a synthetic one. What it must not be read as any more is evidence
# that a rich field overflows at sep's default.
SEP_SUB_OBJECT_LIMIT = 65536


# A star-matched frame whose own centre sits further than this from the reference's
# is refused. One target is one pointing, with only dither and drift between its
# subs, so a large displacement means the match locked onto the wrong stars —
# which is the one failure a caller cannot see in the result. Shared rather than
# re-spelled per caller so "how far may a sub have moved" has one answer; the
# bootstrap rescue passes its own, because there the same number also bounds a
# phase-correlation peak.
DEFAULT_MAX_SHIFT_PX = 200.0


def registration_gray(path: str) -> np.ndarray | None:
    """Load a sub as a background-flattened luminance plane, ready to register.

    Debayer to RGB, average to one luminance plane, then subtract a robust sky
    level, so what a matcher sees is the **stars** rather than the (frame-varying)
    sky pedestal or the Bayer checkerboard. Returns ``None`` on any read or decode
    problem — a sub that cannot be read is skipped, never fatal.

    Both sides of a registration have to be prepared the same way or their
    difference is in the preparation rather than in the sky, which is why this
    lives beside the matcher and why the bootstrap rescue's phase-correlation pass
    calls it too.

    **The sky noise's negative half is kept, deliberately** — see the comment on
    the subtraction below. Clipping it away, which this used to do, made the star
    matcher inert on a real Seestar sub while every 480x320 fixture passed.
    """
    try:
        from seestack.io.fits_loader import load_seestar_raw

        rgb, _info = load_seestar_raw(path, debayer=True, out_dtype=np.float32)
    except Exception as exc:  # noqa: BLE001 — a bad sub must never sink the batch
        log.debug("registration gray: could not load %s: %s", path, exc)
        return None
    gray = np.asarray(rgb, dtype=np.float32)
    if gray.ndim == 3:
        gray = gray.mean(axis=2)
    if gray.ndim != 2 or gray.size == 0:
        return None
    # Robust sky subtraction: the median is a stable pedestal estimate on a
    # star-sparse field, and subtracting it is the whole of what a matcher needs.
    # The negatives it leaves behind are the lower half of the sky noise and are
    # **kept**: clipping them away (which this used to do) parks half the frame's
    # pixels at exactly 0.0, and that spike at zero collapses the noise estimate
    # every star extractor derives its detection threshold from. Measured on a
    # real-sized sub (1920x1080, 120 stars): ``sep`` — the extractor astroalign
    # detects with — reported a global RMS of **0.0006** clipped against **21.6**
    # unclipped, put its 5-sigma threshold inside the noise, and read **63 % of
    # the frame** as star pixels instead of 0.6 %. That is past sep's 300,000-pixel
    # extraction buffer, so it refused outright, astroalign re-raised the refusal
    # as its generic "input type not supported", and ``find_star_transform``
    # returned ``None`` for every sub — the whole star-match path silently placed
    # nothing on a real frame. Unclipped, the same frame yields 118 of its 120
    # stars. A 480x320 fixture cannot exhibit it: it has 153,600 pixels in total,
    # so it can never reach a 300,000-pixel buffer however wrong the threshold is,
    # and its top-50-by-flux control points are the real stars anyway.
    sky = float(np.nanmedian(gray))
    flat = gray - sky
    # A frame that came back all-NaN or flat (no signal) can't register.
    if not np.isfinite(flat).any() or float(np.nanmax(flat)) <= 0.0:
        return None
    return np.nan_to_num(flat, nan=0.0, posinf=0.0, neginf=0.0)


@dataclass(frozen=True)
class StarTransform:
    """A validated similarity transform from one sub's pixels onto another's.

    ``matrix`` and ``translation`` express ``p_reference = matrix · p_moving +
    translation`` in **0-based** pixel coordinates, ``(x, y)`` = ``(column,
    row)`` — the ordering both astroalign and FITS ``CRPIX`` use. Plain tuples
    rather than arrays so the whole thing stays JSON-safe and printable; call
    :meth:`affine` for the numpy form.

    The rest is the evidence for it, kept so a caller can report *why* a frame was
    placed rather than only that it was: how many stars matched, how well they
    landed, and how far this frame's own centre sits from the reference's.
    """

    matrix: tuple[tuple[float, float], tuple[float, float]]
    translation: tuple[float, float]
    rotation_deg: float
    scale: float
    n_matched: int
    residual_px: float
    centre_shift_px: tuple[float, float]

    def affine(self) -> tuple[np.ndarray, np.ndarray]:
        """``(A, b)`` as float64 arrays, for the WCS composition."""
        return (
            np.asarray(self.matrix, dtype=float),
            np.asarray(self.translation, dtype=float),
        )

    def as_summary(self) -> dict:
        """JSON-safe description, for a job summary or a log line."""
        return {
            "rotation_deg": round(self.rotation_deg, 4),
            "scale": round(self.scale, 6),
            "n_matched": self.n_matched,
            "residual_px": round(self.residual_px, 4),
            "centre_shift_px": [round(v, 3) for v in self.centre_shift_px],
        }


def _raise_sep_deblend_limit() -> None:
    """Lift ``sep``'s sub-object cap off its default — see :data:`SEP_SUB_OBJECT_LIMIT`.

    Idempotent and process-global (it is a module setting in ``sep``), so it is
    simply re-asserted before each match rather than tracked. A ``sep`` that cannot
    be imported or does not offer the setter is left alone: astroalign would not be
    working at all without it, and a failure *here* must never be the thing that
    turns a match that would have succeeded into an exception.
    """
    try:
        import sep

        sep.set_sub_object_limit(SEP_SUB_OBJECT_LIMIT)
    except Exception as exc:  # noqa: BLE001 — a best-effort widening, never fatal
        log.debug("star match: could not raise sep's sub-object limit: %s", exc)


def _similarity_parts(a: np.ndarray) -> tuple[float, float] | None:
    """``(scale, rotation_deg)`` of a 2×2 matrix that is a rotation times a scale.

    ``None`` when it is not one: a mirrored matrix (negative determinant — a
    camera cannot flip its field between two subs), a degenerate one, or one whose
    two axes disagree about scale or angle, which is a shear and means the fit is
    not the rigid thing it claims to be.
    """
    det = float(np.linalg.det(a))
    if not math.isfinite(det) or det <= 0.0:
        return None
    scale = math.sqrt(det)
    if scale <= 0.0:
        return None
    # A scaled rotation satisfies AᵀA = s²I exactly; allow a hair for the fit's
    # own arithmetic, relative to s² so the check means the same at any scale.
    gram = a.T @ a
    if not np.allclose(gram, (scale ** 2) * np.eye(2), rtol=1e-6, atol=1e-9 * scale ** 2):
        return None
    return scale, math.degrees(math.atan2(float(a[1, 0]), float(a[0, 0])))


def find_star_transform(
    reference: np.ndarray | None,
    moving: np.ndarray | None,
    *,
    max_shift_px: float = DEFAULT_MAX_SHIFT_PX,
    max_rotation_deg: float = DEFAULT_MAX_ROTATION_DEG,
    max_scale_deviation: float = DEFAULT_MAX_SCALE_DEVIATION,
    min_control_points: int = DEFAULT_MIN_CONTROL_POINTS,
    max_control_points: int = DEFAULT_MAX_CONTROL_POINTS,
    max_residual_px: float = DEFAULT_MAX_RESIDUAL_PX,
    detection_sigma: float = DEFAULT_DETECTION_SIGMA,
    min_area: int = DEFAULT_MIN_AREA,
) -> StarTransform | None:
    """Match ``moving``'s stars onto ``reference``'s, or return ``None``.

    Both are single-plane, sky-subtracted luminance images (what
    :func:`registration_gray` produces); they need not
    be the same shape. ``max_shift_px`` bounds how far this frame's **own centre**
    may have moved on the reference's grid — the honest measure of "did the
    pointing change", since with a rotation the transform's raw translation is not
    a displacement of anything in particular.

    ``None`` means "this frame was not placed", for every reason: no astroalign,
    too few stars, no match, a match that does not survive the checks above. The
    caller leaves the frame exactly as unsolved as it found it.
    """
    if reference is None or moving is None:
        return None
    ref = np.asarray(reference, dtype=np.float32)
    mov = np.asarray(moving, dtype=np.float32)
    if ref.ndim != 2 or mov.ndim != 2 or ref.size == 0 or mov.size == 0:
        return None
    try:
        import astroalign

        _raise_sep_deblend_limit()
        transform, (src_pos, dst_pos) = astroalign.find_transform(
            mov, ref,
            max_control_points=int(max_control_points),
            detection_sigma=detection_sigma,
            min_area=int(min_area),
        )
    except Exception as exc:  # noqa: BLE001 — a sub that won't match is skipped, never fatal
        log.debug("star match: no transform (%s: %s)", type(exc).__name__, exc)
        return None

    params = np.asarray(getattr(transform, "params", None), dtype=float)
    if params.shape != (3, 3) or not np.isfinite(params).all():
        return None
    a = params[:2, :2]
    b = params[:2, 2]
    parts = _similarity_parts(a)
    if parts is None:
        log.debug("star match: fitted matrix is not a similarity, refusing")
        return None
    scale, rotation_deg = parts
    if abs(scale - 1.0) > max_scale_deviation:
        log.debug("star match: scale %.5f outside tolerance, refusing", scale)
        return None
    if abs(rotation_deg) > max_rotation_deg:
        log.debug("star match: rotation %.2f° outside cap, refusing", rotation_deg)
        return None

    src = np.asarray(src_pos, dtype=float)
    dst = np.asarray(dst_pos, dtype=float)
    if src.ndim != 2 or src.shape != dst.shape or src.shape[1] != 2:
        return None
    n_matched = int(src.shape[0])
    if n_matched < min_control_points:
        log.debug("star match: only %d control points, refusing", n_matched)
        return None
    residual = (a @ src.T).T + b - dst
    rms = float(np.sqrt(np.mean(np.sum(residual ** 2, axis=1))))
    if not math.isfinite(rms) or rms > max_residual_px:
        log.debug("star match: residual %.3f px over %.3f, refusing", rms, max_residual_px)
        return None

    h, w = mov.shape
    centre = np.array([(w - 1) / 2.0, (h - 1) / 2.0], dtype=float)
    moved = a @ centre + b - centre
    if abs(float(moved[0])) > max_shift_px or abs(float(moved[1])) > max_shift_px:
        log.debug("star match: centre moved %s px, over the cap, refusing", moved)
        return None

    return StarTransform(
        matrix=((float(a[0, 0]), float(a[0, 1])), (float(a[1, 0]), float(a[1, 1]))),
        translation=(float(b[0]), float(b[1])),
        rotation_deg=rotation_deg,
        scale=scale,
        n_matched=n_matched,
        residual_px=rms,
        centre_shift_px=(float(moved[0]), float(moved[1])),
    )
