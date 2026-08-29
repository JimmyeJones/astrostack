"""``GET /api/sky/my-map.png`` — the all-sky map built from the owner's own data.

The endpoint's job is to collect each target's newest finished picture, mask it
down to the pixels enough frames actually reached, and render one Aitoff PNG —
cached so drawing the whole sky isn't paid for on every page load.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

pytest.importorskip("matplotlib")
pytest.importorskip("PIL")

_H, _W = 24, 32


def _make_run(data_root, safe: str, *, with_framecov: bool = True) -> int:
    """A plate-solved mosaic run with a picture, a ragged fringe, and (usually) a
    per-pixel frame count so the mask has something to say."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        cube = np.full((3, _H, _W), 0.3, dtype=np.float32)
        cube[:, :, :4] = np.nan                       # genuinely uncovered edge

        hdr = fits.Header()
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = (_W - 1) / 2 + 1
        hdr["CRPIX2"] = (_H - 1) / 2 + 1
        hdr["CRVAL1"] = 150.0
        hdr["CRVAL2"] = 20.0
        hdr["CD1_1"] = -0.001
        hdr["CD1_2"] = 0.0
        hdr["CD2_1"] = 0.0
        hdr["CD2_2"] = 0.001
        fits_path = tdir / "m.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)

        if with_framecov:
            counts = np.full((_H, _W), 9.0, dtype=np.float32)
            counts[:, 4:9] = 1.0                      # thin, badly-covered fringe
            fits.PrimaryHDU(data=counts).writeto(
                fits_path.with_name("m_framecov.fits"), overwrite=True)

        preview_path = tdir / "m_preview.png"
        from seestack.stack.output import _write_preview_png
        _write_preview_png(preview_path, np.moveaxis(cube, 0, -1))

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="m", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=9,
                canvas_h=_H, canvas_w=_W, coverage_min=0, coverage_max=9,
                options_json="{}", is_mosaic=True,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return int(run_id)
    finally:
        lib.close()


def test_my_map_renders_a_png(client, solved_library):
    from io import BytesIO

    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe)

    r = client.get("/api/sky/my-map.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    im = Image.open(BytesIO(r.content))
    assert im.width > 400 and im.height > 200


def test_my_map_works_on_a_fresh_install(client, solved_library):
    """No stacked pictures yet must still give a valid (empty) sky, not a 500 —
    the map is the first thing a curious beginner clicks."""
    r = client.get("/api/sky/my-map.png")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_render_is_cached_until_a_picture_changes(client, solved_library, data_root):
    """Drawing the whole sky isn't free; a second request must reuse the file."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe)

    first = client.get("/api/sky/my-map.png")
    assert first.status_code == 200
    cache = data_root / "state" / "my_map.png"
    fingerprint = data_root / "state" / "my_map.json"
    assert cache.exists() and fingerprint.exists()
    assert json.loads(fingerprint.read_text())["runs"]

    # Poison the cached bytes: a second request that re-rendered would replace
    # them, one that used the cache hands them straight back.
    cache.write_bytes(b"\x89PNG\r\n\x1a\nCACHED")
    again = client.get("/api/sky/my-map.png")
    assert again.content == b"\x89PNG\r\n\x1a\nCACHED"

    # …and a changed picture invalidates it rather than serving a stale sky.
    fingerprint.write_text(json.dumps({"v": 1, "runs": []}))
    fresh = client.get("/api/sky/my-map.png")
    assert fresh.content != b"\x89PNG\r\n\x1a\nCACHED"
    assert fresh.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_only_well_covered_pixels_are_drawn(client, solved_library):
    """The owner's rule: don't paste the whole rectangle on the map. The alpha
    handed to the renderer must exclude the thin single-frame fringe."""
    from webapp.routers import sky as sky_router

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe)

    seen: list = []
    lib = Library.open_or_create(solved_library / "library")
    try:
        pictures, fingerprint = sky_router._my_map_pictures(lib)
    finally:
        lib.close()
    seen.extend(pictures)
    assert len(seen) == 1
    alpha = seen[0].rgba[..., 3]
    assert alpha.max() == 255 and alpha.min() == 0     # genuinely masked
    # The left ~28 % of the picture is NaN edge + single-frame fringe.
    cut = int(round(alpha.shape[1] * 9 / _W))
    assert not alpha[:, :cut].any()
    assert alpha[:, cut:].all()
    assert fingerprint["runs"][0][0] == safe


def test_a_run_without_a_frame_count_still_appears(client, solved_library):
    """An older run has no ``_framecov`` sibling — it maps its has-data footprint
    rather than dropping off the map."""
    from webapp.routers import sky as sky_router

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe, with_framecov=False)

    lib = Library.open_or_create(solved_library / "library")
    try:
        pictures, _fp = sky_router._my_map_pictures(lib)
    finally:
        lib.close()
    assert len(pictures) == 1
    alpha = pictures[0].rgba[..., 3]
    # Only the truly-uncovered (NaN) left edge is transparent this time.
    cut = int(round(alpha.shape[1] * 4 / _W))
    assert not alpha[:, :cut].any()
    assert alpha[:, cut:].all()


def test_a_picture_with_unreconcilable_geometry_is_left_off(client, solved_library):
    """If we can't line the mask up with the stored bytes there is no honest way
    to place it — skip it rather than smear a mis-registered footprint."""
    from seestack.previewcrop import UNKNOWN, preview_crop_json
    from webapp.routers import sky as sky_router

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_stack_preview_crop(
                run_id, preview_crop_json(UNKNOWN)) is True
        finally:
            proj.close()
        pictures, fingerprint = sky_router._my_map_pictures(lib)
    finally:
        lib.close()
    assert pictures == []
    # …but it still counts toward the cache fingerprint, so the map re-renders
    # once that run's geometry becomes placeable again.
    assert len(fingerprint["runs"]) == 1
