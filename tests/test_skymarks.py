"""Tests for :mod:`seestack.skymarks` — the scale bar + sky compass baked onto
a shared picture.

Two things are pinned here that a string comparison could never catch: that the
compass points where *astropy itself* says North and East are (so an East/West
mirror can't creep in), and that every character the marks draw has a real glyph
in the font they're drawn with (the ``.notdef``-box class of defect v0.282.1
fixed in the nameplate — and the ′/″ prime marks the on-screen scale bar uses
are exactly the characters that trip it).
"""

from __future__ import annotations

import math

import numpy as np
from astropy.wcs import WCS
from PIL import Image, ImageFont

from seestack.scalebar import scale_bar_for
from seestack.skymarks import (
    HALO_RGB,
    MARK_RGB,
    SkyDirections,
    SkyMarks,
    draw_sky_marks,
    rotated,
    sky_directions,
)


def _tan_wcs(width: int, height: int, ra: float = 10.0, dec: float = 20.0,
             arcsec_per_px: float = 1.5, rotation_deg: float = 0.0) -> WCS:
    """A TAN WCS centred on the frame, optionally rotated via ``CROTA2``.

    The rotation is set the way astropy itself interprets it, so the tests below
    compare our answer against astropy's — they never assert a hand-rolled sign.
    """
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [width / 2 + 0.5, height / 2 + 0.5]
    w.wcs.crval = [ra, dec]
    w.wcs.cdelt = [-arcsec_per_px / 3600.0, arcsec_per_px / 3600.0]
    if rotation_deg:
        w.wcs.crota = [0.0, rotation_deg]
    return w


# --------------------------------------------------------------------------
# sky_directions — where North and East point
# --------------------------------------------------------------------------

def test_unrotated_sky_is_axis_aligned_with_east_a_quarter_turn_from_north():
    """An unrotated frame puts both marks on the axes, a quarter turn apart.

    Which way each one lands is a property of the grid the app draws on, not a
    free choice: astropy's pixel *y* is the FITS array row, and the renderer
    puts array row 0 at the **top** of the picture, so a step that increases Dec
    moves *down* the screen. The angles below are that fact, and they are the
    same fact :func:`~seestack.render.orient.north_up_rotation_deg` reads when
    it decides how far to turn a picture — so the rose and the North-up option
    can never disagree about which way North is."""
    d = sky_directions(_tan_wcs(400, 300), 400, 300)
    assert d is not None
    assert abs(d.north_deg - (-90.0)) < 0.5     # Dec increases down the screen
    assert abs(abs(d.east_deg) - 180.0) < 0.5   # RA increases to the left


def test_directions_track_a_rotated_field():
    """Rotating the field turns both marks together, keeping their 90° split."""
    d = sky_directions(_tan_wcs(400, 300, rotation_deg=30.0), 400, 300)
    assert d is not None
    # North moves off screen-up by the field rotation…
    assert abs(d.north_deg - 90.0) > 20.0
    # …and East stays exactly a quarter turn from it (the sky doesn't shear).
    split = (d.east_deg - d.north_deg + 180.0) % 360.0 - 180.0
    assert abs(abs(split) - 90.0) < 0.5


def test_compass_agrees_with_astropy_about_which_way_is_north():
    """Ground truth, not a hand-rolled convention: step North in *astropy's*
    world coordinates and check the pixel motion matches the angle we report.

    This is the test that would fail if a sign error mirrored the rose."""
    for rotation in (0.0, 30.0, -47.5, 115.0):
        wcs = _tan_wcs(400, 300, rotation_deg=rotation)
        d = sky_directions(wcs, 400, 300)
        assert d is not None
        cx, cy = (400 - 1) / 2.0, (300 - 1) / 2.0
        ra0, dec0 = (float(v) for v in wcs.all_pix2world(cx, cy, 0))
        for angle, (ra1, dec1) in (
            (d.north_deg, (ra0, dec0 + 0.02)),
            (d.east_deg, (ra0 + 0.02 / math.cos(math.radians(dec0)), dec0)),
        ):
            x1, y1 = (float(v) for v in wcs.all_world2pix(ra1, dec1, 0))
            truth = math.degrees(math.atan2(-(y1 - cy), x1 - cx))
            assert abs((truth - angle + 180.0) % 360.0 - 180.0) < 0.5


def test_a_flipped_field_draws_east_the_other_way_round():
    """Parity is shown, never silently corrected. A frame whose RA axis isn't
    flipped is a mirror of the ordinary sky, and its rose must say so — the two
    fields below share a North arm and point East in opposite directions."""
    ordinary = sky_directions(_tan_wcs(400, 300), 400, 300)
    flipped_wcs = _tan_wcs(400, 300)
    flipped_wcs.wcs.cdelt = [1.5 / 3600.0, 1.5 / 3600.0]  # no RA flip
    flipped = sky_directions(flipped_wcs, 400, 300)
    assert ordinary is not None and flipped is not None
    assert abs(ordinary.north_deg - flipped.north_deg) < 0.5
    split = abs((ordinary.east_deg - flipped.east_deg + 180.0) % 360.0 - 180.0)
    assert abs(split - 180.0) < 0.5


def test_no_wcs_or_degenerate_geometry_gives_no_directions():
    assert sky_directions(None, 400, 300) is None
    assert sky_directions(_tan_wcs(400, 300), 0, 300) is None
    assert sky_directions(_tan_wcs(400, 300), 400, 0) is None


def test_near_the_pole_both_arms_are_still_answered_honestly():
    """Dec 89.99° breaks both steps if they're taken naively: North would step
    *past* the pole, and East would need 57° of RA to travel 0.01° of sky. The
    first is flipped, the second capped — and the two arms still come out a
    quarter turn apart, which is the check that the capping didn't quietly
    corrupt the direction."""
    d = sky_directions(_tan_wcs(400, 300, dec=89.99), 400, 300)
    assert d is not None
    assert abs(d.north_deg - (-90.0)) < 1.0  # same answer as at low declination
    split = (d.east_deg - d.north_deg + 180.0) % 360.0 - 180.0
    assert abs(abs(split) - 90.0) < 1.0


def test_rotated_follows_the_pixels():
    d = SkyDirections(north_deg=30.0, east_deg=120.0)
    r = rotated(d, 60.0)
    assert r is not None
    assert abs(r.north_deg - 90.0) < 1e-9
    assert abs(r.east_deg - 180.0) < 1e-9
    # Wraps into (-180, 180] rather than running away.
    assert abs(rotated(d, 200.0).north_deg - (-130.0)) < 1e-9
    assert rotated(None, 90.0) is None


# --------------------------------------------------------------------------
# draw_sky_marks — the pixels
# --------------------------------------------------------------------------

def _picture(w: int = 400, h: int = 300, level: int = 0) -> Image.Image:
    return Image.new("RGB", (w, h), (level, level, level))


def _marked_columns(before: Image.Image, after: Image.Image) -> np.ndarray:
    """Which columns changed between two same-size images."""
    diff = np.abs(np.asarray(after, dtype=np.int16)
                  - np.asarray(before, dtype=np.int16)).sum(axis=(0, 2))
    return np.nonzero(diff)[0]


def test_nothing_to_draw_is_a_clean_no_op():
    src = _picture()
    out = draw_sky_marks(src, SkyMarks())
    assert out.size == src.size
    assert np.array_equal(np.asarray(out), np.asarray(src))
    # And it doesn't mutate the caller's image when it *does* draw.
    drawn = draw_sky_marks(src, SkyMarks(bar_px=100, bar_label="15'"))
    assert np.asarray(src).sum() == 0
    assert np.asarray(drawn).sum() > 0


def test_scale_bar_is_drawn_at_the_top_left_at_the_requested_length():
    src = _picture(400, 300)
    out = draw_sky_marks(src, SkyMarks(bar_px=100.0, bar_label="15'"))
    assert out.size == src.size  # marks go *on* the picture, never around it
    arr = np.asarray(out)
    # The bar lives in the top strip, not the bottom (the caption zone).
    top = np.abs(arr[: 300 // 3].astype(int)).sum()
    bottom = np.abs(arr[2 * 300 // 3:].astype(int)).sum()
    assert top > 0 and bottom == 0
    # Its span matches the length we asked for, within the end serifs' width.
    cols = _marked_columns(src, out)
    assert 90 <= (cols.max() - cols.min()) <= 115


def test_a_bar_longer_than_the_picture_is_clamped_inside_it():
    src = _picture(200, 200)
    out = draw_sky_marks(src, SkyMarks(bar_px=10_000.0, bar_label="2°"))
    cols = _marked_columns(src, out)
    assert cols.max() < 200


def test_compass_arms_point_where_the_directions_say():
    """Draw a rose with North up and East left and check the marked pixels sit
    above and to the left of the rose centre — the geometric statement the whole
    feature rests on."""
    src = _picture(400, 400)
    marks = SkyMarks(directions=SkyDirections(north_deg=90.0, east_deg=180.0))
    out = draw_sky_marks(src, marks)
    changed = np.abs(np.asarray(out, dtype=np.int16)
                     - np.asarray(src, dtype=np.int16)).sum(axis=2)
    ys, xs = np.nonzero(changed)
    assert xs.size
    # The rose is in the top-right quadrant.
    assert xs.min() > 400 / 2 and ys.max() < 400 / 2
    # Its centre is the one point both arms share; the North arm reaches above
    # it and the East arm to its left.
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    assert ys.min() < cy - 5   # something drawn above the centre (North)
    assert xs.min() < cx - 5   # something drawn left of it (East)


def test_marks_are_readable_on_a_white_background():
    """Every mark is drawn over a dark halo, so it survives a bright nebula core
    as well as empty sky — check both colours land on a white picture."""
    src = _picture(400, 300, level=255)
    out = np.asarray(draw_sky_marks(
        src, SkyMarks(bar_px=120.0, bar_label="15'",
                      directions=SkyDirections(north_deg=90.0, east_deg=180.0))))
    assert (out == np.array(MARK_RGB, dtype=np.uint8)).all(axis=2).any()
    assert (out == np.array(HALO_RGB, dtype=np.uint8)).all(axis=2).any()


def test_marks_scale_with_a_small_picture_without_crashing():
    out = draw_sky_marks(
        _picture(60, 40),
        SkyMarks(bar_px=20.0, bar_label="30\"",
                 directions=SkyDirections(north_deg=-35.0, east_deg=55.0)))
    assert out.size == (60, 40)
    assert np.asarray(out).sum() > 0


def test_non_rgb_input_is_accepted():
    grey = Image.new("L", (200, 150), 0)
    out = draw_sky_marks(grey, SkyMarks(bar_px=40.0, bar_label="5'"))
    assert out.mode == "RGB"


# --------------------------------------------------------------------------
# The glyph rule — a mark whose characters have no glyph bakes a hollow box
# --------------------------------------------------------------------------

def test_every_character_the_marks_draw_has_a_glyph_in_the_font():
    """The scale bar's on-screen label uses the typographic primes ``′``/``″``,
    which Pillow's bundled Aileron face has **no glyph for** — baking one in
    would put a hollow ``.notdef`` box where the number should be, exactly the
    defect v0.282.1 fixed in the nameplate. So the baked bar asks for
    ``ScaleBar.ascii_label`` instead, and this pins that every rung of the
    ladder (plus the rose's letters) really is drawable."""
    font = ImageFont.load_default(size=28)
    # A codepoint in the Private Use Area is guaranteed unmapped, so its mask is
    # the font's .notdef box. Asserted non-empty first: a future Pillow that
    # rendered unmapped codepoints as *blank* would otherwise turn this into a
    # test that can never fail.
    notdef = np.asarray(font.getmask(chr(0xE000), mode="L"))
    assert notdef.size, "the reference .notdef glyph came back empty"

    def drawable(ch: str) -> bool:
        mask = np.asarray(font.getmask(ch, mode="L"))
        return mask.shape != notdef.shape or not np.array_equal(mask, notdef)

    # Every label the ladder can produce, across all three units, plus N/E.
    labels = {"N", "E"}
    for arcsec_per_px in (0.2, 1.5, 10.0, 60.0):
        for width in (500, 1920, 6000):
            bar = scale_bar_for(arcsec_per_px, width)
            if bar is not None:
                labels.add(bar.ascii_label)
    assert len(labels) > 4, "the ladder sweep produced too few distinct labels"
    for label in sorted(labels):
        for ch in label:
            assert drawable(ch), (
                f"{ch!r} (in {label!r}) has no glyph in the font the marks are "
                "drawn with — it would bake a hollow box into the picture"
            )
    # And the guard is real: the prime the *on-screen* label uses is not.
    assert not drawable("′")


# ---- telling another overlay where the marks will be ------------------------

def test_the_declared_mark_zones_really_do_cover_where_the_marks_land():
    """``mark_zones`` exists so a second overlay on the same picture (the object
    labels, v0.315.0) can route around the bar and the rose instead of being
    silently buried under them. It is derived from the drawing's own constants
    rather than measured, so the property that matters is that it doesn't
    *under*-claim: every pixel the drawing actually inks has to fall inside one
    of the declared boxes.
    """
    from seestack.skymarks import mark_zones

    src = _picture(640, 480)
    marks = SkyMarks(bar_px=150.0, bar_label="15'",
                     directions=SkyDirections(north_deg=104.0, east_deg=194.0))
    out = draw_sky_marks(src, marks)
    diff = np.abs(np.asarray(out, dtype=np.int16)
                  - np.asarray(src, dtype=np.int16)).sum(axis=2)
    ys, xs = np.nonzero(diff)
    assert ys.size, "the marks should have drawn something"
    zones = mark_zones(640, 480, marks)
    assert len(zones) == 2
    inside = np.zeros(ys.shape, dtype=bool)
    for x0, y0, x1, y1 in zones:
        inside |= (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
    assert inside.all(), (
        f"{int((~inside).sum())} inked pixels fell outside the declared zones")


def test_a_mark_that_is_not_drawn_claims_no_zone():
    """Half-present marks are the common case — a run with a scale but no usable
    orientation — so the boxes have to follow what will actually be drawn."""
    from seestack.skymarks import mark_zones

    assert mark_zones(640, 480, SkyMarks()) == ()
    assert len(mark_zones(640, 480, SkyMarks(bar_px=100.0, bar_label="15'"))) == 1
    assert len(mark_zones(640, 480, SkyMarks(
        directions=SkyDirections(north_deg=90.0, east_deg=180.0)))) == 1
    assert mark_zones(0, 0, SkyMarks(bar_px=100.0, bar_label="15'")) == ()
