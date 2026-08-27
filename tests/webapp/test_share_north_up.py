"""A picture that was *saved* North-up must not be turned North-up again.

History's "Adjust → North up → Save" bakes the whole rotation into the run's
stored preview PNG (and records it as ``stack_runs.preview_north_up_deg``). Every
surface that re-orients those **stored bytes** from the FITS — the share JPEG,
the wallpaper, the baked-on scale bar and North/East rose, the wallpaper's
target-centred crop — has to start from the rotation the bytes already carry, or
it applies the turn a second time and hands over a picture 180° from the one on
screen.

These tests pin each of those consumers: the share JPEG and the wallpaper stop at
the remainder, the rose follows the picture even when the download itself asks
for no rotation, the scale bar keeps measuring against the canvas width, and the
crop still centres on the object. The un-rotated run is asserted unchanged
throughout, because that is every ordinary install's path.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow

pytest.importorskip("PIL")

#: A canvas tilt whose North-up correction is an exact 90° step, so the rotation
#: is lossless (``np.rot90``) and every comparison below can be exact. The canvas
#: is deliberately non-square, so a save swaps the picture's width and height —
#: the shape a double-rotation is most obvious on.
_TILT_DEG = 90.0
_H, _W = 30, 40


def _make_run(data_root, safe: str, *, tilt_deg: float = _TILT_DEG) -> int:
    """Register a run with a real, tilted-WCS master and an off-centre blob, so
    the North-up correction is genuine and the crop has something to centre on."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        yy, xx = np.mgrid[0:_H, 0:_W]
        # An off-centre blob: a wrongly-placed crop centre shows up as a dimmer
        # wallpaper, and a doubled rotation moves it to the opposite corner.
        blob = np.exp(-(((xx - 8) ** 2 + (yy - 7) ** 2) / 12.0)).astype(np.float32)
        cube = np.stack([blob, blob, blob]).astype(np.float32)

        th = np.radians(tilt_deg)
        cdelt = 0.001
        hdr = fits.Header()
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = (_W - 1) / 2 + 1
        hdr["CRPIX2"] = (_H - 1) / 2 + 1
        hdr["CRVAL1"] = 150.0
        hdr["CRVAL2"] = 20.0
        hdr["CD1_1"] = -cdelt * np.cos(th)
        hdr["CD1_2"] = cdelt * np.sin(th)
        hdr["CD2_1"] = cdelt * np.sin(th)
        hdr["CD2_2"] = cdelt * np.cos(th)

        fits_path = tdir / "shared.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)
        preview_path = tdir / "shared_preview.png"
        Image.new("RGB", (_W, _H), (10, 20, 30)).save(preview_path)

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="shared", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=5,
                canvas_h=_H, canvas_w=_W, coverage_min=1, coverage_max=5,
                options_json=json.dumps({"output_name": "shared"}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _stored_preview(data_root, safe: str, run_id: int) -> bytes:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
            return Path(run.preview_path).read_bytes()
        finally:
            proj.close()
    finally:
        lib.close()


def _fits_of(data_root, safe: str, run_id: int) -> str:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(r for r in proj.iter_stack_runs() if r.id == run_id).fits_path
        finally:
            proj.close()
    finally:
        lib.close()


def _save_preview(client, safe: str, run_id: int, *, north_up: bool):
    r = client.post(
        f"/api/targets/{safe}/stack-runs/{run_id}/preview",
        json={"stretch": 0.5, "black": 0.0, "north_up": north_up},
    )
    assert r.status_code == 200, r.text
    return r


def _size(content: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(content)) as im:
        return im.size


def _jpeg(client, safe: str, run_id: int, **params) -> bytes:
    query = "&".join(f"{k}={str(v).lower()}" for k, v in params.items())
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    r = client.get(f"{url}?{query}" if query else url)
    assert r.status_code == 200, r.text
    return r.content


# --------------------------------------------------------------------------- #
# The share JPEG
# --------------------------------------------------------------------------- #

def test_share_jpeg_does_not_turn_a_north_up_saved_picture_twice(
        client, solved_library):
    """The filed bug: save North-up, then share with the North-up switch on.

    The switch is per-page-load state, so it genuinely reads "off" over a picture
    that is already turned — asking for North up again used to hand back a
    picture 180° from the one on screen (and, here, back at the canvas's own
    30×40 shape)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)

    _save_preview(client, safe, run_id, north_up=True)
    stored = _stored_preview(solved_library, safe, run_id)
    assert _size(stored) == (_H, _W)          # the save swapped 40×30 → 30×40

    plain = _jpeg(client, safe, run_id)
    asked = _jpeg(client, safe, run_id, north_up=True)
    # Already North-up, so asking for it is a no-op — same picture, same bytes.
    assert _size(asked) == _size(stored)
    assert asked == plain


def test_share_jpeg_still_orients_a_run_saved_without_north_up(
        client, solved_library):
    """No-regression half: nothing was baked in, so the full turn is still applied
    — and a re-save *without* the toggle clears an earlier rotation, so the share
    goes back to turning the picture itself."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)

    _save_preview(client, safe, run_id, north_up=True)
    _save_preview(client, safe, run_id, north_up=False)
    stored = _stored_preview(solved_library, safe, run_id)
    assert _size(stored) == (_W, _H)

    plain = _jpeg(client, safe, run_id)
    asked = _jpeg(client, safe, run_id, north_up=True)
    assert _size(plain) == (_W, _H)
    assert _size(asked) == (_H, _W)           # turned, as it always was
    assert asked != plain

    # …and byte-identical to rendering the same rotation the old code did.
    from seestack.render.thumbnail import orient_preview_north_up
    from seestack.stack.output import png_bytes_to_jpeg
    expected = png_bytes_to_jpeg(
        orient_preview_north_up(stored, _fits_of(solved_library, safe, run_id)))
    assert asked == expected


def test_share_jpeg_does_not_flip_a_north_up_saved_upside_down_field(
        client, solved_library):
    """The half-turn case — the sneakiest shape of this bug, and the one the
    report describes: a 180° correction leaves the picture's *size* alone, so
    nothing about the shared file looks wrong. It is simply upside down."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe, tilt_deg=0.0)   # North points down
    _save_preview(client, safe, run_id, north_up=True)

    stored = _stored_preview(solved_library, safe, run_id)
    with Image.open(BytesIO(stored)) as im:
        saved = np.asarray(im.convert("L"))
    assert _size(stored) == (_W, _H)          # a half-turn keeps the shape

    asked = _jpeg(client, safe, run_id, north_up=True)
    with Image.open(BytesIO(asked)) as im:
        shared = np.asarray(im.convert("L"), dtype=np.float32)
    # The shared picture is the saved one, not its 180° flip.
    assert np.abs(shared - saved).mean() < np.abs(
        shared - np.rot90(saved, k=2)).mean()
    assert asked == _jpeg(client, safe, run_id)


def test_share_jpeg_of_an_already_north_up_run_is_untouched(client, solved_library):
    """A run whose field is *already* North-up needs no correction at all, so both
    the plain and the North-up download are the plain transcode — the guard that
    a healthy, well-oriented install is bit-for-bit unaffected by any of this."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe, tilt_deg=180.0)
    _save_preview(client, safe, run_id, north_up=True)

    from seestack.stack.output import png_bytes_to_jpeg
    stored = _stored_preview(solved_library, safe, run_id)
    assert _size(stored) == (_W, _H)          # nothing to turn
    assert _jpeg(client, safe, run_id) == png_bytes_to_jpeg(stored)
    assert _jpeg(client, safe, run_id, north_up=True) == png_bytes_to_jpeg(stored)


# --------------------------------------------------------------------------- #
# The baked-on scale bar + North/East rose
# --------------------------------------------------------------------------- #

def _marks_for(client, safe: str, run_id: int, *, north_up: bool):
    """The `SkyMarks` the share path would bake on, via the router's own helper —
    so the assertions read the numbers the picture is actually drawn with."""
    from webapp.routers import stack as stack_router
    captured: dict = {}
    real = stack_router._sky_marks_for_run

    def spy(fits_path, preview_width, north_up_deg=0.0,  # noqa: ANN001, ANN202
            preview_height=0, saved_north_up_deg=0.0):
        marks = real(fits_path, preview_width, north_up_deg, preview_height,
                     saved_north_up_deg)
        captured["marks"] = marks
        captured["north_up_deg"] = north_up_deg
        captured["preview_width"] = preview_width
        captured["saved_north_up_deg"] = saved_north_up_deg
        return marks

    stack_router._sky_marks_for_run = spy
    try:
        _jpeg(client, safe, run_id, scale=True, north_up=north_up)
    finally:
        stack_router._sky_marks_for_run = real
    return captured


def test_sky_marks_follow_a_north_up_saved_picture(client, solved_library):
    """The rose and the bar are measured on the FITS canvas, so a saved rotation
    moves them too — even on a download that asks for *no* rotation of its own.

    Before the fix this download reported a 0° turn (the rose pointed at the
    canvas's North, not the picture's) and measured the bar against the rotated
    picture's width, which on a 90° save is the canvas's *height*."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)
    _save_preview(client, safe, run_id, north_up=True)

    saved = _marks_for(client, safe, run_id, north_up=False)
    assert saved["north_up_deg"] == pytest.approx(90.0, abs=1e-6)
    assert saved["saved_north_up_deg"] == pytest.approx(90.0, abs=1e-6)
    # North is up in the picture: the rose's North points at screen-up (+90°).
    assert saved["marks"].directions is not None
    assert saved["marks"].directions.north_deg == pytest.approx(90.0, abs=1.0)
    # The bar is a fraction of the *canvas* width (40); the rotated picture is
    # only 30 wide, so measuring against that would shorten it by a quarter.
    assert saved["preview_width"] == _H            # what was handed in…
    assert saved["marks"].bar_px is not None       # …and what came out of it

    # Turning the picture can't change the plate scale, so the bar keeps exactly
    # the pixel length it has on the same run saved un-rotated.
    _save_preview(client, safe, run_id, north_up=False)
    unrotated = _marks_for(client, safe, run_id, north_up=False)
    assert unrotated["preview_width"] == _W
    assert saved["marks"].bar_px == pytest.approx(
        unrotated["marks"].bar_px, rel=1e-9)
    assert saved["marks"].bar_label == unrotated["marks"].bar_label


def test_sky_marks_unchanged_for_a_run_with_no_saved_rotation(
        client, solved_library):
    """No-regression half: with nothing baked in, the plain download reports no
    turn and the North-up one reports the full correction, exactly as before —
    and the bar is measured against the picture's own width, untouched."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)
    _save_preview(client, safe, run_id, north_up=False)

    plain = _marks_for(client, safe, run_id, north_up=False)
    assert plain["north_up_deg"] == 0.0
    assert plain["saved_north_up_deg"] == 0.0
    assert plain["preview_width"] == _W

    asked = _marks_for(client, safe, run_id, north_up=True)
    assert asked["north_up_deg"] == pytest.approx(90.0, abs=1e-6)
    assert asked["saved_north_up_deg"] == 0.0
    assert asked["preview_width"] == _W
    assert asked["marks"].bar_px == pytest.approx(plain["marks"].bar_px, rel=1e-9)


# --------------------------------------------------------------------------- #
# The wallpaper
# --------------------------------------------------------------------------- #

def _set_target_position(data_root, safe: str, ra: float, dec: float) -> None:
    lib = Library.open_or_create(data_root / "library")
    try:
        lib._upsert_target(name=safe, safe_name=safe, ra_deg=ra, dec_deg=dec)
    finally:
        lib.close()


def _blob_sky_position(data_root, safe: str, run_id: int) -> tuple[float, float]:
    """The RA/Dec of the synthetic blob, from the master's own WCS — so the crop
    has a real object to centre on rather than a made-up coordinate."""
    from astropy.wcs import WCS

    with fits.open(_fits_of(data_root, safe, run_id)) as hdul:
        wcs = WCS(hdul[0].header, naxis=2)
    ra, dec = wcs.all_pix2world(8.0, 7.0, 0)
    return float(ra), float(dec)


def _wallpaper(client, safe: str, run_id: int, **params) -> bytes:
    query = "&".join(f"{k}={str(v).lower()}" for k, v in params.items())
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=square&{query}")
    assert r.status_code == 200, r.text
    return r.content


def test_wallpaper_does_not_turn_a_north_up_saved_picture_twice(
        client, solved_library):
    """Same double-turn on the wallpaper endpoint: a North-up-saved picture asked
    for North up is already there, so the crop is the plain one."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)
    ra, dec = _blob_sky_position(solved_library, safe, run_id)
    _set_target_position(solved_library, safe, ra, dec)
    _save_preview(client, safe, run_id, north_up=True)

    assert _wallpaper(client, safe, run_id, north_up=True) == _wallpaper(
        client, safe, run_id)


def test_wallpaper_crop_centres_on_a_rotated_stored_preview(
        client, solved_library):
    """The companion defect: the target's pixel is measured on the FITS grid and
    applied to a preview a past save already rotated, so the crop re-centred on
    the wrong spot even with ``north_up`` off.

    The 90° save puts the blob near the *bottom* of the 30×40 stored preview
    (row 31). A square crop of that is 30×30 — it can only slide vertically — so
    reading the target's row off the un-rotated canvas (row 7) placed it at the
    top and cropped the object out of its own wallpaper entirely."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)
    ra, dec = _blob_sky_position(solved_library, safe, run_id)
    _set_target_position(solved_library, safe, ra, dec)
    _save_preview(client, safe, run_id, north_up=True)

    with Image.open(BytesIO(_stored_preview(solved_library, safe, run_id))) as im:
        stored = np.asarray(im.convert("L"))
    stored_y, stored_x = np.unravel_index(int(np.argmax(stored)), stored.shape)
    assert (stored_y, stored_x) == (31, 7)    # where the save actually put it

    with Image.open(BytesIO(_wallpaper(client, safe, run_id))) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float32)
    assert arr.shape == (30, 30)
    peak_y, peak_x = np.unravel_index(int(np.argmax(arr)), arr.shape)
    # The crop slid as far down as it can (rows 10–40), so the blob is inside it
    # at row 31−10. The un-rotated row would have cropped rows 0–30 — no blob.
    assert abs(int(peak_y) - (stored_y - 10)) <= 2
    assert abs(int(peak_x) - stored_x) <= 2


def test_wallpaper_of_an_unrotated_run_is_unchanged(client, solved_library):
    """No-regression half: with nothing baked in, the North-up wallpaper is still
    a genuinely different (turned) picture from the plain one."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe)
    ra, dec = _blob_sky_position(solved_library, safe, run_id)
    _set_target_position(solved_library, safe, ra, dec)
    _save_preview(client, safe, run_id, north_up=False)

    assert _wallpaper(client, safe, run_id, north_up=True) != _wallpaper(
        client, safe, run_id)
