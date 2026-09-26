"""The matched-crop "did it get better?" endpoints.

The engine side is covered in ``tests/test_noise_delta_patch.py``; this pins the
web contract: what the info endpoint promises, that the PNG 404s on exactly the
cases the info endpoint calls unavailable, and that neither can be pointed at a
run (or a file) the target does not own.
"""

from __future__ import annotations

import io

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from seestack.stack.output import DISPLAY_SPACE_CARD
from webapp import noise_delta_cache


def _add_stack(root, safe: str, name: str, *, subs: int, when: str,
               noise: float, seed: int, size: int = 300,
               display_space: bool = False, write_fits: bool = True) -> int:
    """Write a synthetic linear master and register a stack run for it."""
    lib = Library.open_or_create(root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        h = w = size
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:h, 0:w]
        r2 = (xx - w / 2) ** 2 + (yy - h / 2) ** 2
        glow = 0.12 * np.exp(-r2 / (0.06 * h * w))
        chan = (0.10 + glow + noise * rng.standard_normal((h, w))).astype(np.float32)
        cube = np.stack([chan, chan * 0.8, chan * 0.6]).astype(np.float32)
        fp = tdir / f"{name}.fits"
        if write_fits:
            hdu = fits.PrimaryHDU(data=cube)
            if display_space:
                hdu.header[DISPLAY_SPACE_CARD] = True
            hdu.writeto(fp, overwrite=True)
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=when, output_basename=name,
                fits_path=str(fp), tiff_path=None, preview_path=None,
                n_frames_used=subs, canvas_h=h, canvas_w=w,
                coverage_min=1, coverage_max=3, options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def test_info_and_png_describe_the_same_picture(client, solved_library):
    noise_delta_cache.clear()
    safe = _safe(client)
    old = _add_stack(solved_library, safe, "s1", subs=120,
                     when="2026-05-12T00:00:00Z", noise=0.030, seed=1)
    new = _add_stack(solved_library, safe, "s2", subs=505,
                     when="2026-05-20T00:00:00Z", noise=0.005, seed=2)

    body = client.get(f"/api/targets/{safe}/noise-delta/info?a={new}&b={old}").json()
    assert body["available"] is True
    # Same canvas → the same pixel rectangle out of both, so the number is offered
    # and points the right way (the deeper master is the cleaner one).
    assert body["pixel_exact"] is True
    assert body["noise_ratio"] is not None and body["noise_ratio"] > 1.5
    assert body["patch_px"] >= 96

    r = client.get(f"/api/targets/{safe}/noise-delta?a={new}&b={old}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # Two squares plus the hairline divider, exactly as the composer builds them.
    from PIL import Image

    im = Image.open(io.BytesIO(r.content))
    assert im.height == body["patch_px"]
    assert im.width == body["patch_px"] * 2 + 2


def test_an_editor_export_gets_no_picture_and_the_png_404s(client, solved_library):
    # A display-space export is tone-mapped by a bespoke recipe; nothing can be
    # honestly matched to it. `available: false`, not an error — and the PNG must
    # agree, so the card can never ask for a picture it was told it can't have.
    noise_delta_cache.clear()
    safe = _safe(client)
    old = _add_stack(solved_library, safe, "s1", subs=120,
                     when="2026-05-12T00:00:00Z", noise=0.030, seed=3)
    baked = _add_stack(solved_library, safe, "s2", subs=505,
                       when="2026-05-20T00:00:00Z", noise=0.005, seed=4,
                       display_space=True)

    body = client.get(f"/api/targets/{safe}/noise-delta/info?a={baked}&b={old}").json()
    assert body["available"] is False
    assert client.get(
        f"/api/targets/{safe}/noise-delta?a={baked}&b={old}").status_code == 404


def test_a_missing_master_self_hides_rather_than_erroring(client, solved_library):
    noise_delta_cache.clear()
    safe = _safe(client)
    gone = _add_stack(solved_library, safe, "s1", subs=120,
                      when="2026-05-12T00:00:00Z", noise=0.030, seed=5,
                      write_fits=False)
    new = _add_stack(solved_library, safe, "s2", subs=505,
                     when="2026-05-20T00:00:00Z", noise=0.005, seed=6)

    body = client.get(f"/api/targets/{safe}/noise-delta/info?a={new}&b={gone}").json()
    assert body["available"] is False


def test_one_run_against_itself_is_not_a_comparison(client, solved_library):
    noise_delta_cache.clear()
    safe = _safe(client)
    only = _add_stack(solved_library, safe, "s1", subs=120,
                      when="2026-05-12T00:00:00Z", noise=0.030, seed=7)
    body = client.get(f"/api/targets/{safe}/noise-delta/info?a={only}&b={only}").json()
    assert body["available"] is False


def test_an_unknown_run_is_a_404_on_both_endpoints(client, solved_library):
    noise_delta_cache.clear()
    safe = _safe(client)
    real = _add_stack(solved_library, safe, "s1", subs=120,
                      when="2026-05-12T00:00:00Z", noise=0.030, seed=8)
    assert client.get(
        f"/api/targets/{safe}/noise-delta/info?a=999999&b={real}").status_code == 404
    assert client.get(
        f"/api/targets/{safe}/noise-delta?a={real}&b=999999").status_code == 404


def test_a_grown_canvas_still_draws_but_withholds_the_number(client, solved_library):
    # A mosaic that widened (or a drizzled restack) gives two different canvas
    # shapes, so one crop has to be resized to sit beside the other. The picture is
    # still fair; the sigma ratio would not be, and must be null.
    noise_delta_cache.clear()
    safe = _safe(client)
    old = _add_stack(solved_library, safe, "s1", subs=120,
                     when="2026-05-12T00:00:00Z", noise=0.030, seed=9, size=300)
    new = _add_stack(solved_library, safe, "s2", subs=505,
                     when="2026-05-20T00:00:00Z", noise=0.005, seed=10, size=420)

    body = client.get(f"/api/targets/{safe}/noise-delta/info?a={new}&b={old}").json()
    assert body["available"] is True
    assert body["pixel_exact"] is False
    assert body["noise_ratio"] is None
    assert client.get(
        f"/api/targets/{safe}/noise-delta?a={new}&b={old}").status_code == 200


def test_the_cache_is_invalidated_when_a_master_is_rewritten(client, solved_library):
    # A re-stack rewrites the master in place. A cache keyed on the path alone
    # would then serve last week's crop for this week's pixels, which is exactly
    # the kind of silently-stale picture this card exists to avoid.
    noise_delta_cache.clear()
    safe = _safe(client)
    old = _add_stack(solved_library, safe, "s1", subs=120,
                     when="2026-05-12T00:00:00Z", noise=0.030, seed=11)
    new = _add_stack(solved_library, safe, "s2", subs=505,
                     when="2026-05-20T00:00:00Z", noise=0.005, seed=12)
    url = f"/api/targets/{safe}/noise-delta?a={new}&b={old}"
    first = client.get(url).content
    assert client.get(url).content == first        # cached: identical bytes

    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        proj = lib.open_target(safe)
        try:
            row = next(r for r in proj.iter_stack_runs() if r.id == new)
        finally:
            proj.close()
        rng = np.random.default_rng(99)
        h = w = 300
        chan = (0.10 + 0.020 * rng.standard_normal((h, w))).astype(np.float32)
        cube = np.stack([chan, chan * 0.8, chan * 0.6]).astype(np.float32)
        fits.PrimaryHDU(data=cube).writeto(row.fits_path, overwrite=True)
        assert tdir.exists()
    finally:
        lib.close()

    assert client.get(url).content != first
