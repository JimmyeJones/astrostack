"""What of a handed header reaches ``master.fits`` — the WCS, and nothing else.

``_write_fits`` copies a WCS into the master it writes. It used to copy the
header it was handed *wholesale*, inside one ``try`` around the whole loop, and
on the one branch of ``run_stack`` that hands it a **frame's entire header** — a
single field with drizzle off, which keeps the reference-frame canvas — that
merge died on the first ``COMMENT`` card and wrote the master with **no WCS at
all**. Observer issue #989 measured it on the owner's library: 6 of 6 runs with
that combination, 0 of the other 737, one of them a target's current picture
across six consecutive stacks. Every surface that reads a run's place on the sky
then failed toward silence — sky coverage, North-up, the scale bar and compass,
the baked catalog labels, framing advice, and an editor export's own header.

The fix is an allowlist rather than a tolerant loop, and the second half of this
file is why: the header that branch hands over also carries the
``SITELAT``/``SITELONG`` cards a Seestar stamps into every sub, which for a scope
used at home is the owner's address — in the very files that get exported and
shared (``AGENTS.md`` §10). A loop that skipped commentary cards and carried on
would have fixed the silence and started leaking those.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")

from astropy.io import fits  # noqa: E402

from seestack.io.wcs_io import celestial_wcs_from_fits  # noqa: E402
from seestack.stack.output import _is_wcs_keyword, write_stack_outputs  # noqa: E402
from tests.synth import make_synth_frame_header_text, make_synth_wcs_text  # noqa: E402

W, H = 480, 320
RA, DEC = 83.6, -5.4
PIXSCALE = 5.0


def _write_master(tmp_path, wcs_text, header_meta=None, basename="master"):
    project_dir = tmp_path / "project"
    project_dir.mkdir(exist_ok=True)
    paths = write_stack_outputs(
        project_dir=project_dir,
        rgb=np.zeros((H, W, 3), dtype=np.float32),
        coverage=np.ones((H, W), dtype=np.float32),
        wcs_text=wcs_text,
        out_basename=basename,
        header_meta=header_meta,
    )
    return paths["fits"]


def _header(path) -> fits.Header:
    with fits.open(path) as hdul:
        return hdul[0].header


# ---- the regression -------------------------------------------------------

def test_a_whole_frame_header_still_lands_a_readable_wcs_in_the_master(tmp_path):
    """The fail-before. Hand the writer what the reference-frame-canvas branch
    hands it — a solved sub's entire stored header — and the master must come
    back with a celestial WCS pointing at the same place on the sky.

    Before the fix this asserted ``None``: the merge raised on the ``COMMENT``
    card at index 5 and never reached ``CTYPE1``.
    """
    fits_path = _write_master(tmp_path, make_synth_frame_header_text(
        width=W, height=H, ra_center_deg=RA, dec_center_deg=DEC,
        pixscale_arcsec=PIXSCALE))

    wcs, width, height = celestial_wcs_from_fits(fits_path)
    assert wcs is not None, "the master must carry the WCS it was handed"
    assert (width, height) == (W, H)
    ra, dec = float(wcs.wcs.crval[0]), float(wcs.wcs.crval[1])
    assert ra == pytest.approx(RA, abs=1e-6)
    assert dec == pytest.approx(DEC, abs=1e-6)


def test_the_whole_frame_header_and_the_wcs_only_one_agree_on_the_sky(tmp_path):
    """The two shapes a caller can hand over must describe the same geometry.

    The mosaic and drizzle branches pass ``wcs_to_text(...)``; the
    reference-canvas branch passes the frame's whole header. That difference is
    the *only* thing #989 turned on, so the masters they produce must be
    indistinguishable to anything reading the sky off them.
    """
    whole = _write_master(tmp_path, make_synth_frame_header_text(
        width=W, height=H, ra_center_deg=RA, dec_center_deg=DEC,
        pixscale_arcsec=PIXSCALE), basename="whole")
    only = _write_master(tmp_path, make_synth_wcs_text(
        width=W, height=H, ra_center_deg=RA, dec_center_deg=DEC,
        pixscale_arcsec=PIXSCALE), basename="wcsonly")

    a, _, _ = celestial_wcs_from_fits(whole)
    b, _, _ = celestial_wcs_from_fits(only)
    assert a is not None and b is not None
    corners = [(0.0, 0.0), (W - 1.0, 0.0), (0.0, H - 1.0), (W - 1.0, H - 1.0)]
    for x, y in corners:
        ra_a, dec_a = a.all_pix2world(x, y, 0)
        ra_b, dec_b = b.all_pix2world(x, y, 0)
        assert float(ra_a) == pytest.approx(float(ra_b), abs=1e-9)
        assert float(dec_a) == pytest.approx(float(dec_b), abs=1e-9)


def test_a_wcs_only_header_still_lands_every_keyword_it_always_did(tmp_path):
    """The branches that already worked must be untouched: every keyword
    ``wcs_to_text`` emits is in the allowlist, so a mosaic or drizzle master's
    header keeps exactly the cards it had."""
    text = make_synth_wcs_text(width=W, height=H, ra_center_deg=RA,
                               dec_center_deg=DEC, pixscale_arcsec=PIXSCALE)
    handed = fits.Header.fromstring(text)
    written = _header(_write_master(tmp_path, text))

    assert list(handed), "the fixture must carry some WCS keywords"
    for key in handed:
        if key.startswith("NAXIS") or key in {"SIMPLE", "BITPIX", "EXTEND", ""}:
            continue
        assert key in written, f"{key} used to travel and must keep travelling"
        assert written[key] == handed[key]


# ---- the reason it is an allowlist (AGENTS.md §10) ------------------------

def test_the_master_never_carries_the_observing_site_out_of_a_subs_header(
    tmp_path,
):
    """A Seestar stamps the site it was used at into every sub. A master is what
    gets exported and shared, so those cards must not travel — the tolerant-loop
    fix would have started copying them the moment it stopped aborting."""
    written = _header(_write_master(tmp_path, make_synth_frame_header_text(
        width=W, height=H, site_lat=12.3456, site_lon=-65.4321)))

    for key in ("SITELAT", "SITELONG", "OBSGEO-X", "OBSGEO-Y", "OBSGEO-Z"):
        assert key not in written, f"{key} must never reach a master"
    text = str(written)
    assert "12.3456" not in text
    assert "-65.4321" not in text


def test_nothing_else_from_the_subs_header_travels_either(tmp_path):
    """Only the sky geometry is copied. A sub's own exposure, gain, temperature
    and optics describe *one frame*, not the stack — the stacker stamps the
    master's own versions of those itself, from every sub it combined."""
    written = _header(_write_master(tmp_path, make_synth_frame_header_text()))

    for key in ("BAYERPAT", "EXPTIME", "GAIN", "CCD-TEMP", "FOCALLEN",
                "XPIXSZ", "YPIXSZ"):
        assert key not in written, f"{key} belongs to a sub, not to the master"
    assert "HISTORY" not in written
    assert "CTYPE1" in written, "…while the WCS did travel"


def test_the_stacks_own_capture_window_survives_the_wcs_merge(tmp_path):
    """``DATE-OBS`` is deliberately outside the allowlist. The stacker stamps the
    window of *every* sub it combined, and this merge runs after that — so one
    reference frame's timestamp must not overwrite the whole stack's."""
    written = _header(_write_master(
        tmp_path,
        make_synth_frame_header_text(date_obs="2026-07-19T22:14:03"),
        header_meta={
            "DATE-OBS": ("2026-07-01T21:02:00", "start of the first sub combined"),
            "DATE-END": ("2026-07-19T23:58:00", "start of the last sub combined"),
        },
    ))

    assert written["DATE-OBS"] == "2026-07-01T21:02:00"
    assert written["DATE-END"] == "2026-07-19T23:58:00"


# ---- degrading, rather than losing the lot -------------------------------

def test_a_handed_header_with_no_wcs_writes_a_master_anyway(tmp_path):
    """A sub that never solved carries no geometry to copy. That is "no WCS",
    not "no master" — the write must still succeed, and must not smuggle the
    rest of the header in as a consolation prize."""
    text = make_synth_frame_header_text()
    stripped = fits.Header.fromstring(text)
    for key in ("CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2",
                "CDELT1", "CDELT2"):
        del stripped[key]

    fits_path = _write_master(tmp_path, str(stripped))
    written = _header(fits_path)
    assert written["CREATOR"] == "Seestack"
    assert "SITELAT" not in written
    assert celestial_wcs_from_fits(fits_path)[0] is None


def test_an_unparseable_wcs_blob_writes_a_master_anyway(tmp_path):
    """Same for a corrupt blob: the master is the point, the WCS is a bonus."""
    fits_path = _write_master(tmp_path, "this is not a FITS header at all")
    assert _header(fits_path)["CREATOR"] == "Seestack"


def test_one_card_the_writer_cannot_assign_costs_only_that_card(tmp_path):
    """The shape of the original bug, in miniature: a card that raises on
    assignment must cost *itself*, never the rest of the solution. Here the
    commentary cards are that card — they are skipped by name — and ``CTYPE1``,
    which sits below them in a real frame header, still lands."""
    written = _header(_write_master(tmp_path, make_synth_frame_header_text()))
    assert "COMMENT" not in written
    for key in ("CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2",
                "CDELT1", "CDELT2"):
        assert key in written


# ---- the predicate -------------------------------------------------------

@pytest.mark.parametrize("key", [
    "WCSAXES", "WCSNAME", "CTYPE1", "CTYPE2", "CUNIT1", "CRPIX1", "CRVAL2",
    "CDELT1", "CROTA2", "CD1_1", "CD2_1", "PC1_2", "PV2_10", "PS3_1",
    "CSYER1", "CRDER2", "LONPOLE", "LATPOLE", "RADESYS", "RADECSYS",
    "EQUINOX", "EPOCH", "MJDREF", "MJDREFI", "MJDREFF",
    "A_ORDER", "B_ORDER", "AP_ORDER", "BP_ORDER", "A_DMAX", "B_DMAX",
    "A_0_2", "B_2_0", "AP_1_1", "BP_0_1",
    "CTYPE1A", "CRVAL2A", "CD1_1A",  # an alternate WCS description
])
def test_sky_geometry_keywords_are_allowed(key):
    assert _is_wcs_keyword(key)


@pytest.mark.parametrize("key", [
    # commentary and structural
    "COMMENT", "HISTORY", "", "   ", "END", "SIMPLE", "BITPIX", "EXTEND",
    "NAXIS", "NAXIS1", "NAXIS2", "NAXIS3", "BSCALE", "BZERO",
    # the site — AGENTS.md §10
    "SITELAT", "SITELONG", "OBSGEO-X", "OBSGEO-Y", "OBSGEO-Z", "TELESCOP",
    # one frame's acquisition, not the stack's
    "DATE-OBS", "DATE-END", "MJD-OBS", "MJD-AVG", "BAYERPAT", "EXPTIME",
    "EXPOSURE", "GAIN", "CCD-TEMP", "FOCALLEN", "XPIXSZ", "YPIXSZ",
    "INSTRUME", "OBJECT", "CREATOR", "BUNIT", "FILTER", "XBINNING",
])
def test_everything_else_is_refused(key):
    assert not _is_wcs_keyword(key)


def test_the_predicate_is_case_and_whitespace_forgiving():
    assert _is_wcs_keyword("ctype1")
    assert _is_wcs_keyword(" CRVAL1 ")
    assert not _is_wcs_keyword(None)  # type: ignore[arg-type]


# ---- the real path, end to end -------------------------------------------

def test_a_single_field_drizzle_off_stack_keeps_its_place_on_the_sky(tmp_path):
    """The combination #989 is about, through the actual stacker.

    A single field with drizzle off is the one branch that keeps the
    reference-frame canvas, and so the one that hands the writer the reference
    sub's whole header. The frames here carry a *realistic* ``wcs_json`` —
    ``make_synth_frame_header_text``, not the WCS-only helper every other stacker
    fixture uses — which is the only reason this can see the bug at all.
    """
    pytest.importorskip("scipy")
    pytest.importorskip("photutils")
    pytest.importorskip("tifffile")
    pytest.importorskip("PIL")

    from seestack.io.project import FrameRow, Project
    from seestack.stack.stacker import StackOptions, run_stack
    from tests.synth import write_seestar_fits

    proj = Project.create(tmp_path / "p", name="single field")
    raws = tmp_path / "raws"
    raws.mkdir()
    try:
        for k in range(4):
            path = write_seestar_fits(
                raws / f"s{k}.fit", add_wcs=True, seed=10 + k, n_stars=40,
                width=W, height=H, ra_center_deg=RA, dec_center_deg=DEC,
                pixscale_arcsec=PIXSCALE,
            )
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                wcs_json=make_synth_frame_header_text(
                    width=W, height=H, ra_center_deg=RA, dec_center_deg=DEC,
                    pixscale_arcsec=PIXSCALE),
                ra_center_deg=RA, dec_center_deg=DEC,
            ))
        res = run_stack(proj, StackOptions(
            output_name="single", max_workers=1, sigma_clip=False, drizzle=False,
        ))
    finally:
        proj.close()

    # The tell that the reference-frame-canvas branch ran (rather than the union
    # one, which hands the writer a WCS-only header and was never affected):
    # the output canvas is the reference frame's own shape.
    assert res.canvas_shape == (H, W)
    wcs, width, height = celestial_wcs_from_fits(res.fits_path)
    assert wcs is not None, (
        "a single-field drizzle-off master must carry its WCS (observer #989)")
    assert (width, height) == (W, H)
    assert float(wcs.wcs.crval[0]) == pytest.approx(RA, abs=1e-6)
    assert float(wcs.wcs.crval[1]) == pytest.approx(DEC, abs=1e-6)

    written = _header(res.fits_path)
    assert "SITELAT" not in written and "SITELONG" not in written
