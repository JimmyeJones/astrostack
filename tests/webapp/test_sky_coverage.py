"""``GET /api/sky/coverage`` — how much of the sky the owner's pictures cover.

The number beside "My map". It must be measured off each run's **own WCS**, not
by counting pixels on the map: that map is Aitoff (not equal-area, so a pixel
near the rim is worth less sky than one at the centre) *and* it deliberately
draws every picture several times life size so the pictures stay visible. A
count taken off it would be wrong twice over, and a stat that silently disagrees
with the picture beside it is worse than no stat at all.

So these tests pin the measurement against hand-computed square degrees, and pin
that the well-covered mask — the same one that keeps a mosaic's ragged fringe
off the map — is what decides which pixels count.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

pytest.importorskip("PIL")

_H, _W = 40, 60
_SCALE_DEG = 0.001                      # 3.6 arcsec/px, Seestar-ish
_PX_DEG2 = _SCALE_DEG * _SCALE_DEG      # solid angle of one pixel


def _make_run(data_root, safe: str, *, n_uncovered_cols: int = 0,
              n_thin_cols: int = 0, with_wcs: bool = True,
              name: str = "m") -> int:
    """A run whose canvas has a known number of well-covered pixels.

    ``n_uncovered_cols`` are NaN (no data at all); ``n_thin_cols`` carry data but
    only one frame's worth, so the well-covered mask should exclude them too.
    """
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        cube = np.full((3, _H, _W), 0.3, dtype=np.float32)
        if n_uncovered_cols:
            cube[:, :, :n_uncovered_cols] = np.nan

        hdr = fits.Header()
        if with_wcs:
            hdr["CTYPE1"] = "RA---TAN"
            hdr["CTYPE2"] = "DEC--TAN"
            hdr["CRPIX1"] = (_W - 1) / 2 + 1
            hdr["CRPIX2"] = (_H - 1) / 2 + 1
            hdr["CRVAL1"] = 150.0
            hdr["CRVAL2"] = 20.0
            hdr["CD1_1"] = -_SCALE_DEG
            hdr["CD1_2"] = 0.0
            hdr["CD2_1"] = 0.0
            hdr["CD2_2"] = _SCALE_DEG
        fits_path = tdir / f"{name}.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)

        if n_thin_cols:
            counts = np.full((_H, _W), 9.0, dtype=np.float32)
            lo = n_uncovered_cols
            counts[:, lo:lo + n_thin_cols] = 1.0
            fits.PrimaryHDU(data=counts).writeto(
                fits_path.with_name(f"{name}_framecov.fits"), overwrite=True)

        preview_path = tdir / f"{name}_preview.png"
        from seestack.stack.output import _write_preview_png
        _write_preview_png(preview_path, np.moveaxis(cube, 0, -1))

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=name, fits_path=str(fits_path), tiff_path=None,
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


# ---- the measurement -----------------------------------------------------

def test_a_full_canvas_measures_its_own_wcs_area(client, solved_library):
    """Every pixel covered ⇒ the canvas's own solid angle, exactly."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe)

    body = client.get("/api/sky/coverage").json()
    assert body["n_pictures"] == 1
    assert body["deg2"] == pytest.approx(_H * _W * _PX_DEG2, rel=1e-6)
    assert body["sky_fraction"] == pytest.approx(
        body["deg2"] / body["whole_sky_deg2"], rel=1e-9)


def test_uncovered_and_thinly_covered_pixels_do_not_count(client, solved_library):
    """The owner's own rule for the map, applied to the number: a mosaic's
    ragged, one-frame fringe is not sky you have photographed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe, n_uncovered_cols=6, n_thin_cols=5)

    body = client.get("/api/sky/coverage").json()
    expected = _H * (_W - 6 - 5) * _PX_DEG2
    assert body["deg2"] == pytest.approx(expected, rel=1e-6)
    # …and it really is smaller than the whole canvas, so the assertion above
    # isn't passing by both sides being the same thing.
    assert body["deg2"] < _H * _W * _PX_DEG2


def test_a_run_without_a_wcs_contributes_nothing_rather_than_a_guess(
        client, solved_library):
    """No solve ⇒ no honest area. Inventing one from a nominal field would
    quietly claim sky the owner never pointed at."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe, with_wcs=False)

    body = client.get("/api/sky/coverage").json()
    assert body["n_pictures"] == 0
    assert body["deg2"] == 0.0
    assert body["sky_fraction"] == 0.0


def test_a_fresh_install_answers_zero_not_an_error(client, solved_library):
    """The map is the first thing a curious beginner clicks; the stat under it
    must survive having nothing to count."""
    r = client.get("/api/sky/coverage")
    assert r.status_code == 200
    assert r.json()["deg2"] == 0.0
    assert r.json()["n_pictures"] == 0


def test_the_answer_is_cached_until_a_picture_changes(
        client, solved_library, data_root):
    """Reading every target's coverage map is not free, so it happens once per
    change rather than once per page view — and a change must invalidate it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe)

    first = client.get("/api/sky/coverage").json()
    cache = data_root / "state" / "my_map_area.json"
    assert cache.exists()
    stored = json.loads(cache.read_text())
    assert stored["value"]["deg2"] == pytest.approx(first["deg2"])

    # Poison the cached value: a request that re-measured would overwrite it.
    stored["value"]["deg2"] = 123.5
    cache.write_text(json.dumps(stored))
    assert client.get("/api/sky/coverage").json()["deg2"] == pytest.approx(123.5)

    # A changed fingerprint re-measures rather than serving a stale number.
    stored["fingerprint"] = json.dumps({"v": 1, "runs": []})
    cache.write_text(json.dumps(stored))
    assert client.get("/api/sky/coverage").json()["deg2"] == pytest.approx(
        first["deg2"])


def test_the_stat_is_blind_to_how_the_map_draws_it(client, solved_library):
    """The trap this feature exists to avoid: the map exaggerates every picture
    (so it stays visible) and projects it through a non-equal-area Aitoff. The
    number must come from the WCS, so rendering the map cannot move it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe)

    before = client.get("/api/sky/coverage").json()["deg2"]
    assert client.get("/api/sky/my-map.png").status_code == 200
    assert client.get("/api/sky/coverage").json()["deg2"] == pytest.approx(before)
    # And it is the true canvas area, not the several-times-life-size one drawn.
    assert before == pytest.approx(_H * _W * _PX_DEG2, rel=1e-6)


def test_two_targets_are_summed(client, solved_library, data_root):
    """Each target's newest picture contributes; the total is what the owner is
    told they have seen."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        _entry, proj = lib.create_target("NGC 7000", ra_deg=314.0, dec_deg=44.0)
        proj.close()
    finally:
        lib.close()
    safes = [t["safe_name"] for t in client.get("/api/targets").json()]
    assert len(safes) >= 2
    for s in safes[:2]:
        _make_run(solved_library, s)

    body = client.get("/api/sky/coverage").json()
    assert body["n_pictures"] == 2
    assert body["deg2"] == pytest.approx(2 * _H * _W * _PX_DEG2, rel=1e-6)
