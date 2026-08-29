"""Print-ready export sizing (``seestack.printexport``).

The promise is narrow and load-bearing: every size offered must be one the
picture can fill **without being upscaled** past the sharpness floor, so a
beginner who orders the recommended print gets a sharp one. These tests pin the
arithmetic at the edges (a picture exactly on the floor, one pixel under it), the
orientation rule, the no-distortion guarantee, and the self-hiding behaviour for
a picture too small to print well.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.printexport import (
    BIGGER_PRINT_MAX_SCALE,
    DEFAULT_MIN_DPI,
    DRIZZLE_MAX_USEFUL_SCALE,
    MAX_DPI,
    PAPER_SIZES,
    bigger_print,
    print_advice,
    print_options,
    render_print,
)


def _names(options):
    return [o.name for o in options]


def test_largest_printable_size_leads_and_every_offer_is_honest():
    # A ~3000×2000 stack (a modest drizzled Seestar field).
    options = print_options(3000, 2000)
    assert options, "a 6 MP picture must be printable at *something*"
    # Largest first, so the caller's default is "the biggest print you can make".
    areas = [o.width_in * o.height_in for o in options]
    assert areas == sorted(areas, reverse=True)
    # Every offer clears the sharpness floor and needs no upscaling: the canvas
    # never exceeds the picture in either axis.
    for o in options:
        assert o.dpi >= DEFAULT_MIN_DPI
        assert o.width_px <= 3000 and o.height_px <= 2000


def test_a_size_qualifies_exactly_at_the_floor_and_not_one_pixel_below():
    """The boundary is where a wrong ``<`` vs ``<=`` would silently offer a soft
    print, so pin it against a real paper size rather than a round number."""
    a4 = next(p for p in PAPER_SIZES if p.name == "A4")
    # Landscape picture → landscape A4: long edge across.
    w = int(np.ceil(a4.long_in * DEFAULT_MIN_DPI))
    h = int(np.ceil(a4.short_in * DEFAULT_MIN_DPI))
    assert "A4" in _names(print_options(w, h))
    assert "A4" not in _names(print_options(w - 2, h))
    assert "A4" not in _names(print_options(w, h - 2))


def test_paper_is_oriented_to_match_the_picture():
    """Landscape paper for a landscape picture and portrait for a portrait one —
    otherwise the letterbox bars are the aspect mismatch *plus* the rotation."""
    landscape = next(o for o in print_options(3000, 2000) if o.name == "A4")
    assert landscape.width_in > landscape.height_in
    assert landscape.width_px > landscape.height_px
    portrait = next(o for o in print_options(2000, 3000) if o.name == "A4")
    assert portrait.height_in > portrait.width_in
    assert portrait.height_px > portrait.width_px
    # Same paper either way — only the orientation differs.
    assert {landscape.width_in, landscape.height_in} == {portrait.width_in,
                                                         portrait.height_in}


def test_dpi_is_capped_so_a_huge_mosaic_does_not_render_a_pointless_canvas():
    huge = print_options(30000, 20000)
    assert huge and all(o.dpi <= MAX_DPI for o in huge)
    assert huge[0].dpi == MAX_DPI


def test_a_small_picture_offers_only_what_it_can_actually_print():
    small = print_options(900, 600)          # 0.54 MP
    assert _names(small) == ["6×4 in"]       # …and nothing bigger
    assert small[0].dpi == 150


def test_a_picture_too_small_to_print_well_offers_nothing():
    assert print_options(300, 200) == []
    # …and says so kindly rather than silently vanishing. (It used to promise
    # "another night or two of subs will get it there", which is false — subs add
    # signal, not pixels. `bigger_print` now names the lever that really works.)
    advice = print_advice(print_options(300, 200))
    assert "doesn't have enough detail" in advice
    assert "pixels" in advice


def test_degenerate_inputs_are_refused_rather_than_guessed():
    assert print_options(0, 100) == []
    assert print_options(100, 0) == []
    assert print_options(-5, -5) == []
    assert print_options(3000, 2000, min_dpi=0) == []


def test_advice_names_the_size_not_the_arithmetic():
    advice = print_advice(print_options(3000, 2000))
    best = print_options(3000, 2000)[0]
    assert best.name in advice
    assert advice.endswith(".")
    # A beginner picks a size, so the size leads the label too.
    assert best.label.startswith(best.name)


def test_advice_never_claims_more_subs_unlock_a_print():
    """The honesty rule this whole nudge exists to keep: exposure adds signal,
    not pixels, so nothing here may suggest another night makes a print bigger."""
    too_small = print_advice(print_options(100, 80))
    assert "pixels" in too_small
    assert "night" not in too_small.lower()
    assert "subs" not in too_small.lower()


# --- "what would it take to print bigger?" --------------------------------

def test_the_next_size_up_is_named_with_the_gap_to_it():
    # A ~3 MP picture prints at A4 but not A3; the nudge names A3 and how far off.
    assert "A4" in _names(print_options(2000, 1500))
    assert "A3" not in _names(print_options(2000, 1500))
    nudge = bigger_print(2000, 1500)
    assert nudge is not None
    assert nudge.name == "A3"
    assert 1.0 < nudge.scale <= DRIZZLE_MAX_USEFUL_SCALE
    assert nudge.name in nudge.text
    # The pixel counts are the real bar, and the picture is genuinely short of it.
    assert nudge.width_px > 2000 or nudge.height_px > 1500


def test_a_picture_that_already_prints_at_the_largest_size_says_nothing():
    """Nothing to reach for — a nudge here would be noise on a great stack."""
    assert _names(print_options(5000, 3500))[0] == PAPER_SIZES[-1].name
    assert bigger_print(5000, 3500) is None


def test_a_picture_too_small_to_print_at_all_still_gets_the_next_step():
    """The case the size menu hides itself for: it must still say what it would
    take to get a first print, since that is the only useful thing left to say."""
    assert print_options(600, 400) == []
    nudge = bigger_print(600, 400)
    assert nudge is not None
    assert nudge.name == PAPER_SIZES[0].name          # the smallest size offered
    assert "smallest size" in nudge.text


def test_the_lever_is_resolution_and_never_more_exposure():
    """The one thing this must get right (see the module docstring): more subs
    make a picture cleaner, not bigger, so they may never be offered as the way
    to a larger print."""
    for w, h in [(2000, 1500), (1200, 900), (600, 400), (400, 300)]:
        nudge = bigger_print(w, h)
        assert nudge is not None, (w, h)
        assert "cleaner, not bigger" in nudge.text
        # Within reach of super-resolution → name drizzle; beyond it → a mosaic.
        if nudge.scale <= DRIZZLE_MAX_USEFUL_SCALE:
            assert "Drizzle" in nudge.text
            assert "mosaic" not in nudge.text
        else:
            assert "mosaic" in nudge.text
            assert "Drizzle" not in nudge.text


def test_an_unreachable_gap_stays_silent_rather_than_setting_a_daft_goal():
    tiny = bigger_print(100, 80)
    assert tiny is None
    # …and the boundary is the constant, not a coincidence: 300x200 needs exactly
    # 3x for a 6x4 in print at 150 DPI (900 px wide), which is the last one voiced.
    edge = bigger_print(300, 200)
    assert edge is not None and edge.scale == BIGGER_PRINT_MAX_SCALE
    assert bigger_print(290, 200) is None


def test_the_gap_is_rounded_up_so_the_nudge_never_promises_too_little():
    """Acting on the number must actually get there — a rounded-down scale would
    leave the picture just short of the size it was promised."""
    for w, h in [(2000, 1500), (1234, 987), (1001, 800), (777, 555)]:
        nudge = bigger_print(w, h)
        if nudge is None:
            continue
        grown = print_options(round(w * nudge.scale), round(h * nudge.scale))
        assert nudge.name in _names(grown), (w, h, nudge.scale)


def test_the_next_size_is_always_bigger_than_what_the_picture_already_prints():
    """Paper aspects differ (10x8 is 1.25, A4 is 1.41), so a very wide picture can
    clear A4 while missing the smaller 10x8 — the nudge must still point up."""
    for w, h in [(4000, 1000), (3000, 800), (1500, 1400), (900, 1600)]:
        nudge = bigger_print(w, h)
        if nudge is None:
            continue
        printable = _names(print_options(w, h))
        assert nudge.name not in printable
        by_name = {p.name: p for p in PAPER_SIZES}
        assert all(by_name[nudge.name].long_in > by_name[n].long_in
                   for n in printable), (w, h, nudge.name, printable)


def test_degenerate_sizes_get_no_nudge():
    assert bigger_print(0, 100) is None
    assert bigger_print(100, 0) is None
    assert bigger_print(-5, -5) is None
    assert bigger_print(1000, 800, min_dpi=0) is None


@pytest.mark.parametrize("shape", [(400, 400, 3), (400, 400)])
def test_render_letterboxes_rather_than_stretching_the_picture(shape):
    """A lab that prints a squashed M 31 has printed the wrong picture — so a
    square stack on 6×4 paper gets even black bars, not a stretch. Works for a
    mono stack too (the app can produce one, and a print must not crash on it).

    The 600×400 canvas (6×4 in at 100 DPI) is deliberately tiny: the geometry it
    exercises is the same at any size, and the render stays instant.
    """
    from PIL import Image

    rng = np.random.default_rng(3)
    rgb = np.clip(rng.random(shape, dtype=np.float32) * 0.5 + 0.5, 0.0, 1.0)
    option = print_options(600, 400, min_dpi=100)[0]
    img = render_print(rgb, option)
    assert isinstance(img, Image.Image)
    assert img.size == (option.width_px, option.height_px) == (600, 400)

    # The picture's own (square) aspect survives, and the bars are even.
    arr = np.asarray(img.convert("L"), dtype=np.uint8)
    cols = np.flatnonzero(arr.max(axis=0) > 0)
    rows = np.flatnonzero(arr.max(axis=1) > 0)
    content_w = cols[-1] - cols[0] + 1
    content_h = rows[-1] - rows[0] + 1
    assert content_w / content_h == pytest.approx(1.0, rel=0.02)
    assert content_h == 400                      # fills the short axis…
    assert cols[0] == pytest.approx((600 - content_w) / 2, abs=1)   # …centred
    assert 600 - 1 - cols[-1] == pytest.approx((600 - content_w) / 2, abs=1)


def test_render_paints_uncovered_pixels_black_not_grey():
    """NaN means "no coverage" everywhere else in the app; a print is no place to
    start guessing a value for it."""
    rgb = np.full((400, 600, 3), np.nan, dtype=np.float32)
    rgb[100:300, 200:400, :] = 1.0
    option = print_options(600, 400, min_dpi=100)[0]
    arr = np.asarray(render_print(rgb, option).convert("L"), dtype=np.uint8)
    assert arr.min() == 0
    assert arr.max() == 255
