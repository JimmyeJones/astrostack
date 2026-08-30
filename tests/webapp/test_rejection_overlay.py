""""See what stacking removed" — the overlay endpoint and its run-info flag.

The stack writes *where* rejection dropped samples as a ``{base}_rejected.fits``
sibling (``StackOptions.record_rejection_map``). These tests cover the server
half: the run tells History whether it has one, and the overlay lands on the
*stored preview's* grid — through the same crop and North-up rotation every
other consumer of that preview has to compose (the map comes off the un-cropped,
un-rotated canvas, so without it the highlighted trail lands where the trail
isn't).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

pytest.importorskip("PIL")

_H, _W = 40, 60
#: A "satellite trail": a solid diagonal of drops through an otherwise clean map.
_TRAIL = [(y, y + 5) for y in range(6, 34)]


def _make_run(data_root, safe: str, *, with_map: bool = True,
              rejmap_header: bool | None = True) -> tuple[int, Path, Path]:
    """A stack run with (optionally) a rejection-map sibling. Returns
    ``(run_id, fits_path, preview_path)``."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        rng = np.random.default_rng(3)
        cube = rng.normal(0.25, 0.02, size=(3, _H, _W)).astype(np.float32)
        # A deliberately *rotated* WCS (~35° off North), so the North-up test
        # below actually moves the map instead of passing on a no-op.
        hdr = fits.Header()
        cdelt, rot = 0.001, np.deg2rad(35.0)
        hdr["CTYPE1"], hdr["CTYPE2"] = "RA---TAN", "DEC--TAN"
        hdr["CRPIX1"], hdr["CRPIX2"] = (_W - 1) / 2 + 1, (_H - 1) / 2 + 1
        hdr["CRVAL1"], hdr["CRVAL2"] = 150.0, 20.0
        hdr["CD1_1"] = -cdelt * np.cos(rot)
        hdr["CD1_2"] = cdelt * np.sin(rot)
        hdr["CD2_1"] = cdelt * np.sin(rot)
        hdr["CD2_2"] = cdelt * np.cos(rot)
        if rejmap_header is not None:
            hdr["REJMODE"] = "sigma-clip"
            hdr["REJNREJ"] = 412
            hdr["REJNTOT"] = 120000
            hdr["REJFRAC"] = 0.0034
            hdr["REJMAP"] = bool(rejmap_header)
        fits_path = tdir / "rej.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)

        if with_map:
            rej = np.zeros((_H, _W), dtype=np.uint16)
            for y, x in _TRAIL:
                rej[y, x] = 1
            fits.PrimaryHDU(data=rej).writeto(
                fits_path.with_name("rej_rejected.fits"), overwrite=True)

        preview_path = tdir / "rej_preview.png"
        from seestack.stack.output import _write_preview_png
        _write_preview_png(preview_path, np.moveaxis(cube, 0, -1))

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="rej", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=16,
                canvas_h=_H, canvas_w=_W, coverage_min=16, coverage_max=16,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return int(run_id), fits_path, preview_path
    finally:
        lib.close()


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


# ---- the run says whether it has one ------------------------------------

def test_run_info_reports_the_map_when_it_is_there(client, solved_library):
    safe = _safe(client)
    run_id, _f, _p = _make_run(solved_library, safe)
    info = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert info["rejection"]["has_map"] is True
    # …without disturbing the trust line it sits beside.
    assert info["rejection"]["mode"] == "sigma-clip"
    assert info["rejection"]["n_rejected"] == 412


def test_run_info_says_no_when_the_sibling_is_gone(client, solved_library):
    """The header claims a map but the file isn't there — a hand-tidied output
    directory, a run restored without its siblings. Offering a toggle that 404s
    is worse than not offering one."""
    safe = _safe(client)
    run_id, _f, _p = _make_run(solved_library, safe, with_map=False)
    info = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert info["rejection"]["has_map"] is False


def test_run_info_omits_the_flag_on_a_run_that_never_recorded(client, solved_library):
    """Every run recorded before this feature — absent, not False, so nothing
    reads it as "this run refused to record one"."""
    safe = _safe(client)
    run_id, _f, _p = _make_run(solved_library, safe, with_map=False,
                               rejmap_header=None)
    info = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert "has_map" not in (info.get("rejection") or {})


# ---- the overlay ---------------------------------------------------------

def _alpha(resp) -> np.ndarray:
    from PIL import Image

    im = Image.open(BytesIO(resp.content))
    assert im.mode == "RGBA"
    return np.asarray(im)[:, :, 3]


def test_overlay_tints_the_trail_and_nothing_else(client, solved_library):
    from PIL import Image

    safe = _safe(client)
    run_id, _f, preview_path = _make_run(solved_library, safe)
    resp = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    with Image.open(preview_path) as pv:
        size = pv.size
    alpha = _alpha(resp)
    assert alpha.shape == (size[1], size[0]), "must land on the preview's grid"

    on = [alpha[y, x] for y, x in _TRAIL]
    assert min(on) > 200, f"the trail should be plainly visible, got {min(on)}"
    # Everything off the trail (and not adjacent to it) is fully transparent, so
    # this is an overlay over the picture, not a wash across it.
    off = alpha.copy()
    for y, x in _TRAIL:
        off[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = 0
    assert off.max() == 0


def test_a_run_without_a_map_serves_no_overlay(client, solved_library):
    """404, which the History card reads as "no overlay for this one" — the
    ordinary case on every run recorded before the feature."""
    safe = _safe(client)
    run_id, _f, _p = _make_run(solved_library, safe, with_map=False)
    resp = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay")
    assert resp.status_code == 404


def test_overlay_follows_a_north_up_preview(client, solved_library):
    """The stored preview was saved rotated; the map comes off the un-rotated
    canvas, so it has to make the same journey or it highlights empty sky."""
    from PIL import Image

    safe = _safe(client)
    run_id, _f, preview_path = _make_run(solved_library, safe)
    # Re-render the preview North-up through the endpoint that bakes the rotation
    # and records it on the run, exactly as History's "Adjust" does.
    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.5, "black": 0.0, "north_up": True})
    assert r.status_code == 200

    resp = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay")
    assert resp.status_code == 200
    alpha = _alpha(resp)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    with Image.open(row.preview_path) as pv:
        size = pv.size
    assert alpha.shape == (size[1], size[0])

    from seestack.render.orient import rotate_plane_north_up
    from webapp.preview_orient import baked_north_up_deg

    deg = baked_north_up_deg(row)
    assert abs(deg) > 1.0, "the fixture's WCS must really be turned, or this proves nothing"
    src = np.zeros((_H, _W), dtype=np.float32)
    for y, x in _TRAIL:
        src[y, x] = 1.0
    expected = rotate_plane_north_up(src, deg) if deg else src
    # The trail's tinted pixels must sit where the *rotated* trail is, which is a
    # different set of pixels from the un-rotated one whenever the run is turned.
    hit = np.asarray(
        Image.fromarray(expected, mode="F").resize(size, Image.BOX)) > 0
    assert hit.sum() > 0
    assert (alpha[hit] > 0).all()
    assert alpha[~hit].max() == 0


def test_the_run_listing_says_which_runs_have_a_map(client, solved_library):
    """The History card decides whether to offer the overlay from the listing row
    it already has — one stat() beside the has_fits/has_preview ones — rather than
    a per-run header read on every page load."""
    safe = _safe(client)
    with_id, _f, _p = _make_run(solved_library, safe)
    rows = {r["id"]: r for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert rows[with_id]["has_rejection_map"] is True

    # …and a run that recorded nothing says so, rather than omitting the key and
    # leaving an older client to guess.
    lib = Library.open_or_create(solved_library / "library")
    try:
        (lib.target_dir(lib.find_target(safe)) / "rej_rejected.fits").unlink()
    finally:
        lib.close()
    rows = {r["id"]: r for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert rows[with_id]["has_rejection_map"] is False


def test_overlay_can_follow_an_on_the_fly_north_up_view(client, solved_library):
    """``?north_up=true`` composes the same turn ``…/preview?north_up=true``
    applies to the stored bytes, so a viewer looking at their picture North-up
    still sees the trail highlighted *on the trail* — instead of the tint having
    to step aside because the picture moved out from under it."""
    from PIL import Image

    safe = _safe(client)
    run_id, fits_path, preview_path = _make_run(solved_library, safe)
    plain = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay")
    turned = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay?north_up=true")
    assert turned.status_code == 200

    from seestack.render.orient import rotate_plane_north_up
    from seestack.render.thumbnail import (
        orient_preview_north_up,
        preview_north_up_remainder_deg,
    )

    # The picture this overlay has to lay over: the *stored* bytes turned on the
    # way out, which is exactly what the preview endpoint serves.
    rotated = orient_preview_north_up(Path(preview_path).read_bytes(), fits_path)
    with Image.open(BytesIO(rotated)) as im:
        size = im.size
    alpha = _alpha(turned)
    assert alpha.shape == (size[1], size[0]), "must land on the turned picture's grid"
    assert alpha.shape != _alpha(plain).shape, (
        "the fixture's WCS must really turn the picture, or this proves nothing")

    deg = preview_north_up_remainder_deg(fits_path)
    assert abs(deg) > 1.0
    src = np.zeros((_H, _W), dtype=np.float32)
    for y, x in _TRAIL:
        src[y, x] = 1.0
    hit = np.asarray(Image.fromarray(rotate_plane_north_up(src, deg), mode="F")
                     .resize(size, Image.BOX)) > 0
    assert hit.sum() > 0
    assert (alpha[hit] > 0).all()
    assert alpha[~hit].max() == 0


def test_a_preview_already_saved_north_up_is_not_turned_twice(client, solved_library):
    """The remainder, not the whole correction: a run whose stored bytes a past
    "Adjust → North up → Save" already rotated is exactly as North-up as it can
    get, so asking for the view turn on it must be a no-op — the same bytes the
    bare URL serves, not a picture 2× the angle round."""
    safe = _safe(client)
    run_id, _f, _p = _make_run(solved_library, safe)
    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.5, "black": 0.0, "north_up": True})
    assert r.status_code == 200

    base = f"/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay"
    plain = client.get(base)
    turned = client.get(f"{base}?north_up=true")
    assert plain.status_code == turned.status_code == 200
    assert turned.content == plain.content


def test_the_bare_overlay_url_is_unchanged_by_the_new_parameter(client, solved_library):
    """`north_up` defaults off, so every surface that already embeds the bare URL
    gets byte-for-byte what it got before."""
    safe = _safe(client)
    run_id, _f, _p = _make_run(solved_library, safe)
    base = f"/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay"
    assert client.get(base).content == client.get(f"{base}?north_up=false").content


def test_the_gallery_listing_says_which_runs_have_a_map(client, solved_library):
    """The full-screen viewer the Gallery opens decides whether to offer the tint
    from the listing row it already drew the card from — the same one stat() the
    run listing does, so the two surfaces can't disagree about one run, and
    opening a picture costs no extra request."""
    safe = _safe(client)
    with_id, _f, _p = _make_run(solved_library, safe)
    rows = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert rows[with_id]["has_rejection_map"] is True

    # …and it agrees with the answer the History card reads, on the same run.
    runs = {r["id"]: r for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs[with_id]["has_rejection_map"] is True

    lib = Library.open_or_create(solved_library / "library")
    try:
        (lib.target_dir(lib.find_target(safe)) / "rej_rejected.fits").unlink()
    finally:
        lib.close()
    rows = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert rows[with_id]["has_rejection_map"] is False
