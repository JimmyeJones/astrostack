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

from fastapi import APIRouter, Request
from pydantic import BaseModel

from seestack.post.skymap import bright_star_catalog
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


class SkyResponse(BaseModel):
    stars: list[SkyStar]
    images: list[SkyImage]


def _representative_pixscale_rotation(proj) -> tuple[float | None, float | None]:  # noqa: ANN001
    """Pixel scale (arcsec/px) + rotation (deg) from a solved frame, if any."""
    for f in proj.iter_frames():
        if f.pixscale_arcsec:
            return f.pixscale_arcsec, (f.rotation_deg or 0.0)
    return None, None


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
                # Latest stack run that actually has a preview on disk.
                run = next(
                    (r for r in proj.iter_stack_runs()
                     if r.preview_path and r.canvas_w and r.canvas_h),
                    None,
                )
                if run is None:
                    continue
                pixscale, rotation = _representative_pixscale_rotation(proj)
                if not pixscale:
                    # No plate-solved frame → we can't size it on the sky. Skip.
                    continue
                width_deg = run.canvas_w * pixscale / 3600.0
                height_deg = run.canvas_h * pixscale / 3600.0
                images.append(SkyImage(
                    safe=t.safe_name,
                    name=t.name,
                    ra_deg=float(t.ra_deg),
                    dec_deg=float(t.dec_deg),
                    width_deg=width_deg,
                    height_deg=height_deg,
                    rotation_deg=rotation or 0.0,
                    preview_url=f"/api/targets/{t.safe_name}/stack-runs/{run.id}/preview",
                    timestamp_utc=run.timestamp_utc,
                    run_id=run.id,
                ))
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()

    # Oldest first so the frontend can paint newest last (on top of overlaps).
    images.sort(key=lambda im: im.timestamp_utc or "")
    return SkyResponse(stars=stars, images=images)
