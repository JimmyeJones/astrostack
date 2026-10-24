"""Where one run's preview sits on another's, **by sky** — for Compare's Split and
Blink.

Split lays picture A over picture B under one divider, and Blink swaps them in
one frame; both only mean anything if a star is at the same place in both. On
two runs of one canvas that is free — the two previews are the same grid. On a
mosaic that grew (the Target page's "How far you've come" is first-ever against
now, which on a mosaic shooter's target is almost always a grown canvas) the
two canvases are different pieces of sky at different sizes, and drawing both
"contain" in one box put the same star ~94 px apart.

So this answers, from both masters' WCS, the one affine that takes a pixel of
A's *displayed* preview to the pixel of B's displayed preview showing the same
sky, and a frame — the bounding box of both, in B's pixels — that holds the two
without clipping either. "Displayed" is the bytes a viewer actually gets: the
stored preview (which a past North-up save may have turned, and an auto-edit's
border trim may have cropped — :mod:`webapp.preview_orient` recovers both), plus
the on-the-fly North-up view turn when that is on. Pixel conventions follow
:func:`seestack.render.deepening._sky_affine`: continuous ``u`` on a picture is
0-based pixel index ``u − 0.5``.

``None`` — never a guess — when either master has no usable celestial WCS, a
point does not project, or the two pictures share no sky; the caller then says
so in a sentence and shows them side by side. Pure and read-only: no webapp
import, nothing written.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

#: The smaller picture must have at least this share of its own area on the other
#: one's sky before the pair is "the same sky": a sliver of overlap at one corner
#: is two different pictures, not a comparison.
MIN_SHARED_FRACTION = 0.05

#: The frame may not be more than this many times the larger picture's long edge:
#: past it the two are drawn so far apart (or one so tiny) that an overlay
#: answers nothing a side-by-side wouldn't.
_MAX_FRAME_FACTOR = 6.0


@dataclass(frozen=True)
class PreviewSide:
    """What one side of a comparison is actually showing."""

    #: The run's master FITS — the WCS the stored preview is a picture of.
    fits_path: str | Path
    #: ``(width, height)`` of the stored preview PNG.
    stored_size: tuple[int, int]
    #: Rotation the stored bytes already carry (a past North-up save).
    baked_deg: float = 0.0
    #: The border trim the stored preview shows, or ``None`` for the whole canvas.
    crop: object | None = None    # seestack.previewcrop.PreviewCrop | None
    #: The extra turn the North-up *view* applies on the way out, or ``0.0``.
    view_deg: float = 0.0


@dataclass(frozen=True)
class SkyPlacement:
    """A over B by sky, in one frame measured in B's displayed pixels."""

    frame_w: float
    frame_h: float
    #: ``(a, b, c, d, e, f)`` in SVG/CSS ``matrix()`` order — frame
    #: ``x = a·u + c·v + e``, ``y = b·u + d·v + f`` for continuous ``(u, v)`` on
    #: A's displayed preview.
    a_matrix: tuple[float, float, float, float, float, float]
    a_size: tuple[int, int]
    #: Where B's displayed preview's top-left corner sits in the frame (B is drawn
    #: unscaled — the frame *is* its pixel grid, extended).
    b_offset: tuple[float, float]
    b_size: tuple[int, int]

    def as_json(self) -> dict[str, object]:
        return {
            "frame_w": round(self.frame_w, 3), "frame_h": round(self.frame_h, 3),
            "a": {"width": self.a_size[0], "height": self.a_size[1],
                  "matrix": [round(x, 6) for x in self.a_matrix]},
            "b": {"width": self.b_size[0], "height": self.b_size[1],
                  "x": round(self.b_offset[0], 3), "y": round(self.b_offset[1], 3)},
        }


class _Displayed:
    """One side's displayed-pixel ↔ sky mapping (0-based pixel indices)."""

    def __init__(self, side: PreviewSide) -> None:
        from astropy.io import fits as _fits
        from astropy.wcs import WCS

        from seestack.io.wcs_io import wcs_dict_rescaled_to_preview
        from seestack.render.orient import north_up_pixel_transform

        sw, sh = (int(side.stored_size[0]), int(side.stored_size[1]))
        wcs_dict = wcs_dict_rescaled_to_preview(
            side.fits_path, sw, sh,
            north_up_deg=float(side.baked_deg or 0.0), crop=side.crop)
        if wcs_dict is None:
            raise ValueError("no celestial WCS")
        header = _fits.Header()
        for key, value in wcs_dict.items():
            header[key] = value
        self.wcs = WCS(header)
        self.m = np.eye(2)
        self.t = np.zeros(2)
        self.size = (sw, sh)
        if side.view_deg:
            transform = north_up_pixel_transform(sw, sh, float(side.view_deg))
            if transform is None:
                raise ValueError("degenerate view turn")
            m, t, nw, nh = transform
            self.m, self.t = np.asarray(m, float), np.asarray(t, float)
            self.size = (int(nw), int(nh))
        self.m_inv = np.linalg.inv(self.m)

    def to_sky(self, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        stored = idx @ self.m.T + self.t
        return self.wcs.all_pix2world(stored[:, 0], stored[:, 1], 0)

    def from_sky(self, ra: np.ndarray, dec: np.ndarray) -> np.ndarray:
        sx, sy = self.wcs.all_world2pix(ra, dec, 0)
        stored = np.column_stack([np.asarray(sx, float), np.asarray(sy, float)])
        return (stored - self.t) @ self.m_inv.T


def _overlap_area(quad: np.ndarray, w: float, h: float) -> float:
    """Area of the bounding box of ``quad`` (4×2) clipped to ``[0,w]×[0,h]`` —
    generous for a turned quad, which is the safe direction for a guard whose job
    is only to catch two pictures that share (almost) no sky at all."""
    x0, y0 = np.clip(quad.min(axis=0), 0, [w, h])
    x1, y1 = np.clip(quad.max(axis=0), 0, [w, h])
    return float(max(0.0, x1 - x0) * max(0.0, y1 - y0))


def place_a_on_b(a: PreviewSide, b: PreviewSide) -> SkyPlacement | None:
    """A's displayed preview placed on B's by both masters' WCS, or ``None``."""
    try:
        da, db = _Displayed(a), _Displayed(b)
    except Exception as exc:  # noqa: BLE001 — no usable WCS just means "can't place"
        log.debug("compare placement: %s", exc)
        return None
    aw, ah = da.size
    bw, bh = db.size
    if min(aw, ah, bw, bh) <= 0:
        return None
    t = np.array([0.0, 0.5, 1.0])
    u, v = np.meshgrid(t * aw, t * ah)
    u, v = u.ravel(), v.ravel()
    try:
        ra, dec = da.to_sky(np.column_stack([u - 0.5, v - 0.5]))
        on_b = db.from_sky(ra, dec) + 0.5
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "can't place"
        log.warning("compare placement failed (%s → %s): %s",
                    a.fits_path, b.fits_path, exc)
        return None
    if not np.all(np.isfinite(on_b)):
        return None
    design = np.column_stack([u, v, np.ones_like(u)])
    (pa, pc, pe), *_ = np.linalg.lstsq(design, on_b[:, 0], rcond=None)
    (pb, pd, pf), *_ = np.linalg.lstsq(design, on_b[:, 1], rcond=None)
    coeffs = np.array([pa, pb, pc, pd, pe, pf], dtype=float)
    det = pa * pd - pb * pc
    if not np.all(np.isfinite(coeffs)) or abs(det) < 1e-9:
        return None

    corners = np.array([[0, 0], [aw, 0], [0, ah], [aw, ah]], dtype=float)
    quad = np.column_stack([pa * corners[:, 0] + pc * corners[:, 1] + pe,
                            pb * corners[:, 0] + pd * corners[:, 1] + pf])
    a_area_on_b = abs(det) * aw * ah
    shared = _overlap_area(quad, bw, bh)
    if shared < MIN_SHARED_FRACTION * min(a_area_on_b, float(bw * bh)):
        return None                       # two different pieces of sky

    x0 = min(0.0, float(quad[:, 0].min()))
    y0 = min(0.0, float(quad[:, 1].min()))
    x1 = max(float(bw), float(quad[:, 0].max()))
    y1 = max(float(bh), float(quad[:, 1].max()))
    frame_w, frame_h = x1 - x0, y1 - y0
    a_extent = float((quad.max(axis=0) - quad.min(axis=0)).max())
    if max(frame_w, frame_h) > _MAX_FRAME_FACTOR * max(bw, bh, a_extent):
        return None
    return SkyPlacement(
        frame_w=frame_w, frame_h=frame_h,
        a_matrix=(float(pa), float(pb), float(pc), float(pd),
                  float(pe - x0), float(pf - y0)),
        a_size=(int(aw), int(ah)),
        b_offset=(-x0, -y0), b_size=(int(bw), int(bh)),
    )
