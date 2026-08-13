"""The offline "will it fit in one Seestar frame?" framing hint."""

from __future__ import annotations

import pytest

from seestack.framing import (
    SEESTAR_FOV_LONG_ARCMIN,
    SEESTAR_FOV_SHORT_ARCMIN,
    framing_hint,
    framing_result_verdict,
)
from seestack.nightplan import load_catalog


def test_unknown_or_nonpositive_size_never_guesses():
    # Absent a vetted size, we emit no hint rather than guessing.
    assert framing_hint(None) is None
    assert framing_hint(0) is None
    assert framing_hint(-5) is None


def test_small_object_fits_one_frame():
    # A compact target (well inside the short frame edge) fits comfortably.
    h = framing_hint(20)
    assert h is not None
    assert h.level == "fits"
    assert "single Seestar frame" in h.text
    assert "no mosaic needed" in h.text  # reassuring, not a mosaic nudge


def test_mid_size_object_is_tight():
    # Between the short and long frame edges: only fits if favourably rotated.
    h = framing_hint(60)
    assert h is not None
    assert h.level == "tight"
    assert "mosaic mode" in h.text


def test_large_object_needs_mosaic():
    # Bigger than the long frame edge (e.g. M31 at ~178'): won't fit at all.
    h = framing_hint(178)
    assert h is not None
    assert h.level == "mosaic"
    assert "mosaic mode" in h.text


def test_boundaries_are_inclusive_at_the_short_and_long_edges():
    # Exactly the short edge still counts as "fits"; exactly the long edge as
    # "tight"; a hair past the long edge flips to "mosaic".
    assert framing_hint(SEESTAR_FOV_SHORT_ARCMIN).level == "fits"
    assert framing_hint(SEESTAR_FOV_SHORT_ARCMIN + 0.01).level == "tight"
    assert framing_hint(SEESTAR_FOV_LONG_ARCMIN).level == "tight"
    assert framing_hint(SEESTAR_FOV_LONG_ARCMIN + 0.01).level == "mosaic"


def test_custom_fov_overrides_are_honoured():
    # The helper compares against whatever field is passed (e.g. a solved frame's
    # real size), not only the Seestar default.
    assert framing_hint(30, fov_short_arcmin=20, fov_long_arcmin=40).level == "tight"
    assert framing_hint(50, fov_short_arcmin=20, fov_long_arcmin=40).level == "mosaic"


@pytest.mark.parametrize(
    "obj_id,expected_level",
    [
        ("M31", "mosaic"),   # Andromeda, ~3° — the classic doesn't-fit surprise
        ("M45", "mosaic"),   # Pleiades, ~110'
        ("M33", "tight"),    # Triangulum, ~71' — right at the frame edge
        ("M13", "fits"),     # Hercules globular, ~20'
        ("M57", "fits"),     # Ring Nebula, tiny
    ],
)
def test_popular_catalog_targets_get_sensible_verdicts(obj_id, expected_level):
    cat = {o.id: o for o in load_catalog()}
    obj = cat[obj_id]
    assert obj.size_arcmin is not None
    hint = framing_hint(obj.size_arcmin)
    assert hint is not None
    assert hint.level == expected_level


def test_catalog_sizes_are_sane_when_present():
    # Every catalog size we vetted must be a positive, plausible arcmin value
    # (nothing absurd like a whole-sky degree slipped in), and unsized objects
    # stay None (never coerced to 0).
    for obj in load_catalog():
        if obj.size_arcmin is None:
            continue
        assert 0 < obj.size_arcmin <= 600, obj.id


def test_every_catalog_object_now_carries_a_size():
    # The bundled catalog is fully sized, so every identified target gets a
    # framing hint (uniform "will it fit?" line — no silent gaps). A future
    # addition without a vetted size trips this, prompting the author to add one.
    unsized = [o.id for o in load_catalog() if o.size_arcmin is None]
    assert unsized == [], f"catalog objects missing a vetted size_arcmin: {unsized}"


# ---------------------------------------------------------------------------
# "Did I frame it well?" — the post-stack verdict on the finished picture.
# ---------------------------------------------------------------------------

# A stand-in for a finished Seestar stack: 1000 × 800 px at 5"/px, so the canvas
# spans ~83' × 67' and a 30' object is 360 px across — comfortably inside it.
FRAME = {"width_px": 1000, "height_px": 800, "arcsec_per_px": 5.0}


def verdict(x, y, size_arcmin, **over):
    return framing_result_verdict(
        x_px=x, y_px=y, size_arcmin=size_arcmin, **{**FRAME, **over},
    )


def test_a_centred_object_that_fits_reads_as_well_framed():
    v = verdict(500, 400, 30)
    assert v is not None
    assert v.level == "centred"
    assert v.coverage == pytest.approx(1.0)
    assert v.off_centre < 0.01
    assert "centred" in v.text


def test_an_object_pushed_to_a_corner_is_flagged_even_though_it_all_fits():
    v = verdict(900, 700, 10)
    assert v is not None
    assert v.level == "off_centre"
    assert v.coverage == pytest.approx(1.0)   # nothing is missing...
    assert v.off_centre > 0.34                # ...it just sits well out
    assert "off to one side" in v.text


def test_an_object_that_would_fit_but_runs_off_an_edge_says_re_centre():
    # 30' object (360 px across) centred only 60 px from the top: two thirds of it
    # made it in. It fits the canvas easily, so the fix is aim, not mosaic mode.
    v = verdict(500, 60, 30)
    assert v is not None
    assert v.level == "clipped"
    assert v.coverage == pytest.approx(2 / 3, abs=0.01)
    assert "re-centre it next session" in v.text
    assert "mosaic" not in v.text


def test_an_object_bigger_than_the_canvas_says_mosaic_not_re_centre():
    # M 31-sized (3°) on this canvas can never fit however well it is aimed.
    v = verdict(500, 400, 180)
    assert v is not None
    assert v.level == "partial"
    assert v.coverage < 0.5
    assert "mosaic mode" in v.text
    assert "re-centre" not in v.text


def test_the_reported_percentage_is_friendly_and_never_absurd():
    # Rounded to the nearest 5, and never "0%"/"100%" — either would contradict
    # the sentence it sits in ("only about 0% of it is in this picture").
    text = verdict(500, 400, 3000).text          # a sliver of a vast object
    assert "about 5% of it" in text
    text = verdict(500, 60, 30).text
    assert "about 65% of it" in text


def test_no_verdict_without_a_vetted_size():
    # We never guess: an unsized catalog object gets no card at all.
    assert verdict(500, 400, None) is None
    assert verdict(500, 400, 0) is None


def test_no_verdict_from_a_degenerate_frame_or_projection():
    assert verdict(500, 400, 30, width_px=0) is None
    assert verdict(500, 400, 30, height_px=0) is None
    assert verdict(500, 400, 30, arcsec_per_px=0.0) is None
    # An object behind the projection comes back non-finite from the WCS.
    assert verdict(float("nan"), 400, 30) is None
    assert verdict(500, float("inf"), 30) is None


def test_the_verdict_names_no_object_so_the_caller_can_prefix_it():
    # Same contract as framing_hint: the sentence starts with a verb, so the UI
    # renders "M 31 " + text and one voice covers both cards.
    for v in (verdict(500, 400, 30), verdict(900, 700, 10), verdict(500, 60, 30),
              verdict(500, 400, 180)):
        assert v is not None
        assert v.text[0].islower()
