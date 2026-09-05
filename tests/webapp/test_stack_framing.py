""""Did I frame it well?" — `GET …/stack-runs/{id}/framing`.

The post-stack counterpart to the pre-shoot "will it fit in one frame?" hint:
the verdict is computed from the run's *own* solved WCS and the catalog object's
size, so it answers what actually happened rather than what was intended.
"""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

# M 42 (the fixture's first target) in the bundled catalog: ~85′ across.
M42_RA, M42_DEC, M42_SIZE_ARCMIN = 83.822, -5.391, 85.0


def _add_run(data_root, safe: str, *, ra: float, dec: float, w: int, h: int,
             arcsec_per_px: float, with_wcs: bool = True,
             is_mosaic: bool | None = None) -> int:
    """Register a stack run backed by a real 3-channel master FITS whose header
    carries a TAN WCS centred on (ra, dec) — exactly as the stacker merges the
    canvas WCS into ``master.fits`` — so the endpoint reads the field geometry
    from the file, as in production."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = tdir / f"framing_{ra}_{dec}_{w}x{h}_{is_mosaic}.fits"
        hdu = fits.PrimaryHDU(data=np.zeros((3, h, w), dtype=np.float32))
        if with_wcs:
            hdr = hdu.header
            hdr["CTYPE1"] = "RA---TAN"
            hdr["CTYPE2"] = "DEC--TAN"
            hdr["CRPIX1"] = w / 2 + 0.5
            hdr["CRPIX2"] = h / 2 + 0.5
            hdr["CRVAL1"] = ra
            hdr["CRVAL2"] = dec
            hdr["CD1_1"] = -arcsec_per_px / 3600.0
            hdr["CD1_2"] = 0.0
            hdr["CD2_1"] = 0.0
            hdr["CD2_2"] = arcsec_per_px / 3600.0
        hdu.writeto(fits_path, overwrite=True)

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path), tiff_path=None,
                preview_path=None, n_frames_used=3,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=3,
                options_json="{}", is_mosaic=is_mosaic,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _m42(client) -> str:
    safe = next(t["safe_name"] for t in client.get("/api/targets").json()
                if t["safe_name"] == "M_42")
    return safe


def test_a_well_pointed_stack_reads_as_nicely_framed(client, solved_library):
    safe = _m42(client)
    # 4000 × 3000 at 3″/px = 3.3° × 2.5°, centred on M 42 (85′): all of it, centred.
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                      w=4000, h=3000, arcsec_per_px=3.0)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing")
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == "centred"
    assert body["coverage"] == 1.0
    assert body["off_centre"] < 0.05
    assert body["object_name"] == "Orion Nebula"
    assert body["size_arcmin"] == M42_SIZE_ARCMIN
    assert body["text"].startswith("is ")  # the caller prefixes the object's name


def test_a_target_that_ran_off_an_edge_is_reported_from_the_result(client,
                                                                  solved_library):
    safe = _m42(client)
    # Same canvas, but pointed 1° north of M 42 — so the nebula sits well down
    # the frame and part of it is outside it. This is precisely the surprise a
    # beginner cannot see until the picture exists.
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 1.0,
                      w=4000, h=3000, arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "clipped"
    assert 0.5 < body["coverage"] < 0.95
    assert "re-centre it next session" in body["text"]


def test_an_object_bigger_than_the_canvas_is_told_to_use_mosaic_mode(client,
                                                                    solved_library):
    safe = _m42(client)
    # A single Seestar frame (~1.3° × 0.7°) can't hold an 85′ nebula at all.
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                      w=1080, h=1920, arcsec_per_px=2.4)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "partial"
    assert "mosaic mode" in body["text"]


def test_an_off_centre_picture_is_offered_a_re_centring_crop(client, solved_library):
    safe = _m42(client)
    # A generous 5° × 3.75° canvas pointed 0.7° north of M 42: the whole nebula is
    # in frame, but well down the picture — the one case cropping can actually fix.
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 0.7,
                      w=6000, h=4500, arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "off_centre"
    rc = body["recentre"]
    assert rc is not None
    # Fractional bounds in the editor's crop convention, keeping most of the frame
    # and the frame's own shape.
    assert 0.0 <= rc["x0"] < rc["x1"] <= 1.0
    assert 0.0 <= rc["y0"] < rc["y1"] <= 1.0
    assert rc["kept"] > 0.4
    # Not a symmetric trim: the kept band is offset toward the object. Pointing
    # north of M 42 puts the nebula at *low* y on this WCS (dec grows with y), so
    # the crop hugs that edge.
    assert (rc["y0"] + rc["y1"]) / 2.0 < 0.45
    assert (rc["x0"] + rc["x1"]) / 2.0 == pytest.approx(0.5, abs=0.02)  # centred in x


def test_no_re_centring_offer_when_cropping_could_not_help(client, solved_library):
    safe = _m42(client)
    # Already well framed: nothing to gain, so no offer (the button would just
    # take field away).
    centred = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                       w=4000, h=3000, arcsec_per_px=3.0)
    body = client.get(f"/api/targets/{safe}/stack-runs/{centred}/framing").json()
    assert body["level"] == "centred"
    assert body["recentre"] is None

    # Ran off an edge: cropping cannot un-clip what was never captured.
    clipped = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 1.0,
                       w=4000, h=3000, arcsec_per_px=3.0)
    body = client.get(f"/api/targets/{safe}/stack-runs/{clipped}/framing").json()
    assert body["level"] == "clipped"
    assert body["recentre"] is None


def test_no_verdict_when_the_run_has_no_usable_wcs(client, solved_library):
    safe = _m42(client)
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                      w=512, h=512, arcsec_per_px=3.0, with_wcs=False)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing")
    assert r.status_code == 200  # never a 404 where the run exists
    assert r.json() is None      # ...and never a guess


def test_framing_404s_for_an_unknown_run(client, solved_library):
    safe = _m42(client)
    assert client.get(
        f"/api/targets/{safe}/stack-runs/999999/framing").status_code == 404


def test_a_picture_too_far_off_centre_to_rescue_says_why_not(client, solved_library):
    """The worst-framed pictures used to get *less* help than the mildly
    off-centre ones: no crop, and no explanation either. The endpoint now returns
    the refusal reason and how little that crop would have kept, so the caller can
    say "better to re-point next session" instead of going quiet."""
    # A small object (M 57, 1.4′) so the "no room around it" refusal can't fire
    # first, pushed right into a corner of a 2° × 1.3° mosaic canvas at the
    # Seestar's own sampling: cropping it back to the middle is *possible* and
    # keeps under a tenth of the picture, which is the case worth explaining.
    lib = Library.open_or_create(solved_library / "library")
    try:
        entry, proj = lib.create_target("M 57", ra_deg=283.396, dec_deg=33.029)
        proj.close()
    finally:
        lib.close()
    safe = entry.safe_name
    # Pointed up and to the left of the nebula so it lands ~80 % of the way out
    # toward the bottom-right corner (dec grows with y, RA falls with x here).
    run_id = _add_run(solved_library, safe, ra=284.350, dec=32.495,
                      w=3000, h=2000, arcsec_per_px=2.4)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "off_centre"
    assert body["coverage"] == pytest.approx(1.0)   # all of it is in frame
    assert body["recentre"] is None                 # ...but no crop is offered
    refused = body["recentre_refused"]
    assert refused is not None
    assert refused["reason"] == "too_destructive"
    assert 0.0 < refused["kept"] < 0.4              # the number the copy needs


def test_an_offered_crop_carries_no_refusal(client, solved_library):
    safe = _m42(client)
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 0.7,
                      w=6000, h=4500, arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["recentre"] is not None
    assert body["recentre_refused"] is None

    # And a verdict that cropping can't address at all reports neither — the
    # refusal is only ever about an off-centre picture.
    centred = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                       w=4000, h=3000, arcsec_per_px=3.0)
    body = client.get(f"/api/targets/{safe}/stack-runs/{centred}/framing").json()
    assert body["level"] == "centred"
    assert body["recentre"] is None
    assert body["recentre_refused"] is None


def test_a_re_centre_verdict_says_which_way_to_nudge_the_mount(client, solved_library):
    """"Re-centre it next session" is only advice a beginner can act on once it
    names a direction. The picture was pointed 1° *north* of M 42, so the nebula
    is south of the frame's middle and the mount has to move south to catch it."""
    safe = _m42(client)
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 1.0,
                      w=4000, h=3000, arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "clipped"
    nudge = body["nudge"]
    assert nudge is not None
    assert nudge["direction"] == "south"
    assert nudge["degrees"] == pytest.approx(1.0, abs=0.02)
    assert "1.0°" in nudge["text"] and "south" in nudge["text"]


def test_the_nudge_names_an_east_west_correction_too(client, solved_library):
    safe = _m42(client)
    # Pointed 1° east of M 42 in RA (≈1.0° of sky at Dec −5°): the nebula is all
    # in frame but well off to one side, and the fix is a westward re-point.
    run_id = _add_run(solved_library, safe, ra=M42_RA + 1.0, dec=M42_DEC,
                      w=6000, h=4500, arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "off_centre"
    assert body["nudge"]["direction"] == "west"
    assert body["nudge"]["degrees"] == pytest.approx(1.0, abs=0.02)


def test_a_well_framed_or_oversized_picture_gets_no_nudge(client, solved_library):
    """No nudge where a better pointing isn't the fix: a centred picture needs
    nothing, and an object bigger than the frame needs mosaic mode."""
    safe = _m42(client)
    centred = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                       w=4000, h=3000, arcsec_per_px=3.0)
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{centred}/framing").json()["nudge"] is None

    oversized = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                         w=1080, h=1920, arcsec_per_px=2.4)
    body = client.get(f"/api/targets/{safe}/stack-runs/{oversized}/framing").json()
    assert body["level"] == "partial"
    assert body["nudge"] is None


# ---------------------------------------------------------------------------
# A MOSAIC picture. The owner is a heavy mosaic user (AGENTS.md §1), and every
# number here is measured against the run's *canvas* — which on a mosaic is
# several frames of sky. Calling that canvas "your frame", or telling them to go
# and shoot the mosaic they already shot, is the bug.
# ---------------------------------------------------------------------------


def test_a_mosaic_is_not_told_to_go_and_shoot_a_mosaic(client, solved_library):
    safe = _m42(client)
    # A 2×2-ish mosaic canvas that still can't hold all of an 85′ nebula.
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                      w=2160, h=3840, arcsec_per_px=1.2, is_mosaic=True)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "partial"
    assert body["canvas"] == "mosaic"
    assert "your frame" not in body["text"]
    assert "Shoot it in mosaic mode" not in body["text"]
    assert "bigger than this mosaic" in body["text"]
    assert "Adding more panels" in body["text"]


def test_a_single_field_run_keeps_the_frame_wording_it_always_had(client,
                                                                 solved_library):
    """The same geometry recorded as a single field is unchanged — this is a
    wording fix for mosaics, not a rewrite of the verdict everyone else sees."""
    safe = _m42(client)
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                      w=1080, h=1920, arcsec_per_px=2.4, is_mosaic=False)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "partial"
    assert body["canvas"] == "frame"
    assert "is bigger than your frame" in body["text"]
    assert "Shoot it in mosaic mode" in body["text"]


def test_a_run_from_before_is_mosaic_existed_reads_as_a_single_frame(client,
                                                                    solved_library):
    """Upgrade safety (§9): `is_mosaic` is NULL for runs recorded before schema 8,
    and those must keep the exact sentences they have always been given rather
    than being guessed into the mosaic voice."""
    safe = _m42(client)
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC,
                      w=1080, h=1920, arcsec_per_px=2.4, is_mosaic=None)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["canvas"] == "frame"
    assert "is bigger than your frame" in body["text"]


def test_a_mosaic_that_clipped_its_target_talks_about_the_mosaic(client,
                                                                solved_library):
    safe = _m42(client)
    # Big enough to hold M 42 whole, but pointed 1° north of it.
    run_id = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 1.0,
                      w=4000, h=3000, arcsec_per_px=3.0, is_mosaic=True)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/framing").json()
    assert body["level"] == "clipped"
    assert body["canvas"] == "mosaic"
    assert "edge of this mosaic" in body["text"]
    assert "re-centre the mosaic next session" in body["text"]
    # The "which way" half is unaffected — a clipped mosaic is still re-pointed.
    assert body["nudge"]["direction"] == "south"


def test_the_mosaic_verdict_changes_only_the_words_not_the_measurements(
        client, solved_library):
    """One canvas, two `is_mosaic` records: the coverage figures must be
    identical, because they were never a claim about a single frame."""
    safe = _m42(client)
    as_frame = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 1.0,
                        w=4000, h=3000, arcsec_per_px=3.0, is_mosaic=False)
    as_mosaic = _add_run(solved_library, safe, ra=M42_RA, dec=M42_DEC + 1.0,
                         w=4000, h=3000, arcsec_per_px=3.0, is_mosaic=True)

    a = client.get(f"/api/targets/{safe}/stack-runs/{as_frame}/framing").json()
    b = client.get(f"/api/targets/{safe}/stack-runs/{as_mosaic}/framing").json()
    for key in ("level", "coverage", "off_centre", "object_name", "size_arcmin"):
        assert a[key] == b[key], key
    assert a["text"] != b["text"]
