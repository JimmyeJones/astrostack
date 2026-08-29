"""Interactive sky viewer data.

``GET /api/sky`` returns everything the frontend's 3D viewer needs in one call:

  * ``stars`` — a small built-in bright-star catalog (shared with the all-sky
    map), so the sphere has a recognisable backdrop with no external server.
  * ``images`` — one placement per target that has a stacked image: where it
    sits on the celestial sphere (RA/Dec), how big it is (degrees, from the
    stack canvas × pixel scale), its rotation, a preview URL, and a timestamp
    so the viewer can draw newer images on top of older overlapping ones.
"""

from __future__ import annotations

import math
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from seestack.io.wcs_io import (
    canvas_extent_from_fits,
    cropped_center_radec_from_fits,
    wcs_dict_rescaled_to_preview,
)
from seestack.post.skymap import bright_star_catalog
from seestack.previewcrop import UNKNOWN as CROP_UNKNOWN
from seestack.previewcrop import parse_preview_crop
from webapp import deps

router = APIRouter(tags=["sky"])


class SkyStar(BaseModel):
    name: str
    ra_deg: float
    dec_deg: float
    mag: float


class SkyImage(BaseModel):
    safe: str
    name: str
    ra_deg: float
    dec_deg: float
    width_deg: float
    height_deg: float
    rotation_deg: float
    preview_url: str
    timestamp_utc: str | None
    run_id: int
    # FITS WCS keywords matching the *preview PNG* pixel grid, so a sky atlas
    # (Aladin Lite) can place the PNG by WCS. None if the preview size is
    # unreadable; the built-in viewer uses ra/dec/width/height/rotation instead.
    wcs: dict | None = None


class SkyResponse(BaseModel):
    stars: list[SkyStar]
    images: list[SkyImage]


def _representative_pixscale_rotation(proj) -> tuple[float | None, float | None]:  # noqa: ANN001
    """Pixel scale (arcsec/px) + rotation (deg) from a solved frame, if any."""
    for f in proj.iter_frames():
        if f.pixscale_arcsec:
            return f.pixscale_arcsec, (f.rotation_deg or 0.0)
    return None, None


def _png_size(path: str) -> tuple[int, int] | None:
    """(width, height) of a PNG from its header, without decoding pixels."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return int(im.width), int(im.height)
    except Exception:  # noqa: BLE001 — missing/corrupt preview → no WCS
        return None


def _tan_wcs(
    ra_deg: float, dec_deg: float, width_deg: float,
    preview_w: int, preview_h: int, rotation_deg: float,
) -> dict:
    """A TAN-projection WCS dict (FITS keywords) for the preview PNG grid.

    Scale comes from the image's angular width spread across the preview's pixel
    width, so it matches the downscaled PNG exactly. RA increases to the left
    (negative on axis 1). Sign of the rotation is a best-effort starting point.
    """
    scale = width_deg / max(preview_w, 1)            # deg / preview-pixel
    theta = math.radians(rotation_deg or 0.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return {
        "NAXIS": 2, "NAXIS1": preview_w, "NAXIS2": preview_h,
        "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
        "CRPIX1": preview_w / 2 + 0.5, "CRPIX2": preview_h / 2 + 0.5,
        "CRVAL1": ra_deg, "CRVAL2": dec_deg,
        "CD1_1": -scale * cos_t, "CD1_2": scale * sin_t,
        "CD2_1": scale * sin_t, "CD2_2": scale * cos_t,
    }


@router.get("/api/sky", response_model=SkyResponse)
def get_sky(request: Request) -> SkyResponse:
    stars = [SkyStar(**s) for s in bright_star_catalog()]

    images: list[SkyImage] = []
    lib = deps.open_library(request)
    try:
        for t in lib.list_targets():
            if t.ra_deg is None or t.dec_deg is None:
                continue
            proj = None
            try:
                from seestack.io.project import Project
                proj = Project.open(lib.target_dir(t))
            except Exception:  # noqa: BLE001 — a broken project must not 500 the sky map
                # One unreadable/corrupt project DB — or one stamped with a newer
                # schema after an image rollback (Project.open raises RuntimeError)
                # — must not hide *every* target's placement. Skip it, like
                # stats.py / storage.py already do for the same call.
                if proj is not None:
                    proj.close()
                continue
            try:
                # Latest stack run that actually has a preview on disk. Guard the
                # file's existence (like gallery.py / stats.py do) — a run whose
                # preview PNG was deleted still carries a truthy preview_path, and
                # emitting it would place a sky tile whose image 404s.
                run = next(
                    (r for r in proj.iter_stack_runs()
                     if r.preview_path and Path(r.preview_path).exists()
                     and r.canvas_w and r.canvas_h),
                    None,
                )
                if run is None:
                    continue
                pixscale, rotation = _representative_pixscale_rotation(proj)
                # History's "Adjust" can save a preview rotated North-up. That
                # picture is no longer a plain downscale of the canvas, so both
                # the tile's geometry and its WCS have to be taken through the
                # same rotation — otherwise the map places the un-rotated canvas
                # under a rotated image. 0.0/NULL (every ordinary run) composes
                # nothing and is unchanged.
                north_up_deg = run.preview_north_up_deg or 0.0
                # The other way the stored bytes leave the canvas grid: the
                # one-click "Process target" auto-edit ends its recipe with a
                # border trim, so the picture is a *crop* of the canvas — placed
                # on the full footprint it is drawn stretched, off-centre by the
                # trim's offset. UNKNOWN means the geometry can't be reconciled
                # at all; the tile then falls back to the canvas footprint with
                # no WCS, because a confidently-misplaced tile is worse than an
                # approximate one.
                crop = parse_preview_crop(run.preview_crop_json)
                crop_ok = crop != CROP_UNKNOWN
                crop = crop if crop_ok else None
                # Prefer the stack's *stored* canvas WCS for the tile's size and
                # rotation too — that is the true union-canvas geometry the pixels
                # were reprojected onto, so a mosaic (or a rotated canvas) is sized
                # and oriented correctly instead of extrapolated from frame 0's
                # grid. Mirrors the `wcs`/Aladin path below (same fix, both viewers
                # now agree). Fall back to the single-frame pixscale/rotation when
                # the master FITS is missing/headerless (older/edited runs).
                extent = (
                    canvas_extent_from_fits(run.fits_path,
                                            north_up_deg=north_up_deg, crop=crop)
                    if run.fits_path else None
                )
                if extent is not None:
                    width_deg, height_deg, rotation = extent
                elif pixscale:
                    width_deg = run.canvas_w * pixscale / 3600.0
                    height_deg = run.canvas_h * pixscale / 3600.0
                else:
                    # No stored WCS and no plate-solved frame → can't size it. Skip.
                    continue
                wcs = None
                if run.preview_path and (size := _png_size(run.preview_path)):
                    # Prefer the stack's *stored* canvas WCS (master FITS header),
                    # rescaled to the preview grid — that is the true geometry the
                    # pixels were reprojected onto, so it places a mosaic at the
                    # correct RA/Dec *and* orientation (canvas geometry, not frame
                    # 0's) with no rotation-sign guesswork. Fall back to the
                    # single-frame TAN extrapolation only when the master FITS is
                    # missing/headerless (older/edited runs).
                    if run.fits_path and crop_ok:
                        wcs = wcs_dict_rescaled_to_preview(
                            run.fits_path, size[0], size[1],
                            north_up_deg=north_up_deg, crop=crop,
                        )
                    if wcs is None and not north_up_deg and crop is None and crop_ok:
                        wcs = _tan_wcs(
                            float(t.ra_deg), float(t.dec_deg), width_deg,
                            size[0], size[1], rotation or 0.0,
                        )
                # A tile is placed by its centre, and the target's own RA/Dec is
                # that centre only while the picture is the whole canvas. A trim
                # off one side moves it, so read the crop's own centre off the
                # canvas WCS; an un-cropped run keeps the target position exactly
                # as before.
                centre = (
                    cropped_center_radec_from_fits(run.fits_path, crop)
                    if run.fits_path and crop is not None else None
                ) or (float(t.ra_deg), float(t.dec_deg))
                images.append(SkyImage(
                    safe=t.safe_name,
                    name=t.name,
                    ra_deg=centre[0],
                    dec_deg=centre[1],
                    width_deg=width_deg,
                    height_deg=height_deg,
                    rotation_deg=rotation or 0.0,
                    # Transparent (RGBA) overlay: uncovered/NaN pixels are alpha=0
                    # so an irregular mosaic shows its true footprint on the sky,
                    # not the opaque black rectangle the plain `preview` PNG is.
                    # Same pixel grid as the preview, so `wcs` (built from the
                    # preview size above) still places it correctly — including
                    # a North-up-saved preview, whose coverage mask the overlay
                    # endpoint takes through the same rotation.
                    preview_url=f"/api/targets/{t.safe_name}/stack-runs/{run.id}/sky-overlay",
                    timestamp_utc=run.timestamp_utc,
                    run_id=run.id,
                    wcs=wcs,
                ))
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()

    # Oldest first so the frontend can paint newest last (on top of overlaps).
    images.sort(key=lambda im: im.timestamp_utc or "")
    return SkyResponse(stars=stars, images=images)
