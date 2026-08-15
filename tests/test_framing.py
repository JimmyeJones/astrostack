"""The offline "will it fit in one Seestar frame?" framing hint."""

from __future__ import annotations

import pytest

from seestack.framing import (
    SEESTAR_FOV_LONG_ARCMIN,
    SEESTAR_FOV_SHORT_ARCMIN,
    framing_hint,
    framing_result_verdict,
    recentre_crop,
    recentre_outcome,
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


# ---------------------------------------------------------------------------
# "Re-centre this picture" — the crop offered on an off-centre verdict.
# ---------------------------------------------------------------------------


def recentre(x, y, size_arcmin, **over):
    return recentre_crop(
        x_px=x, y_px=y, size_arcmin=size_arcmin, **{**FRAME, **over},
    )


def _reverdict(crop, x, y, size_arcmin):
    """The verdict a *cropped* picture would get — the contract the offer makes."""
    w = int(round((crop.x1 - crop.x0) * FRAME["width_px"]))
    h = int(round((crop.y1 - crop.y0) * FRAME["height_px"]))
    return framing_result_verdict(
        x_px=x - crop.x0 * FRAME["width_px"], y_px=y - crop.y0 * FRAME["height_px"],
        width_px=w, height_px=h, arcsec_per_px=FRAME["arcsec_per_px"],
        size_arcmin=size_arcmin,
    )


def test_the_offered_crop_turns_an_off_centre_picture_into_a_well_framed_one():
    # A 10' object halfway out to the right edge: the verdict flags it, and the
    # crop it offers is a picture the *same verdict* calls well framed — that
    # equivalence is the whole promise of the button.
    assert verdict(750, 400, 10).level == "off_centre"
    c = recentre(750, 400, 10)
    assert c is not None
    after = _reverdict(c, 750, 400, 10)
    assert after.level == "centred"
    assert after.coverage == pytest.approx(1.0)   # nothing of it is cropped away


def test_the_offered_crop_keeps_the_frame_shape_and_most_of_the_picture():
    c = recentre(750, 400, 10)
    assert c is not None
    frame_aspect = FRAME["width_px"] / FRAME["height_px"]
    crop_aspect = ((c.x1 - c.x0) * FRAME["width_px"]) / ((c.y1 - c.y0) * FRAME["height_px"])
    assert crop_aspect == pytest.approx(frame_aspect, rel=0.01)
    assert c.kept == pytest.approx((c.x1 - c.x0) * (c.y1 - c.y0))
    assert c.kept > 0.4
    # Fractional bounds, in range and ordered — the editor's crop-op contract.
    assert 0.0 <= c.x0 < c.x1 <= 1.0
    assert 0.0 <= c.y0 < c.y1 <= 1.0


def test_no_offer_when_the_picture_is_already_well_centred():
    # Nothing to fix: a centred object must never be offered a crop (the button
    # would take field away for no gain).
    assert verdict(500, 400, 10).level == "centred"
    assert recentre(500, 400, 10) is None


def test_no_offer_when_re_centring_would_gut_the_picture():
    # Pushed right into a corner, a crop that centres it keeps a tenth of the
    # frame — the cure is worse than the off-centre framing, so no offer at all.
    assert verdict(900, 700, 10).level == "off_centre"
    assert recentre(900, 700, 10) is None


def test_no_offer_for_a_clipped_or_oversized_object():
    # Cropping cannot un-clip what was never captured, and on an object bigger
    # than the frame it just throws away more of it.
    assert verdict(500, 60, 30).level == "clipped"
    assert recentre(500, 60, 30) is None
    assert verdict(500, 400, 180).level == "partial"
    assert recentre(500, 400, 180) is None


def test_the_crop_leaves_clear_space_around_the_object():
    # A big (60') object halfway out has no room to be re-framed without hugging
    # it — a cramped crop is worse than the off-centre picture.
    assert recentre(750, 400, 60) is None
    # ...and where a crop *is* offered, the object's own box sits comfortably
    # inside it with margin to spare.
    c = recentre(750, 400, 10)
    assert c is not None
    radius_px = (10 * 60.0 / FRAME["arcsec_per_px"]) / 2.0
    assert 750 - radius_px > c.x0 * FRAME["width_px"] + 0.5 * radius_px
    assert 750 + radius_px < c.x1 * FRAME["width_px"] - 0.5 * radius_px


def test_the_offer_works_off_either_axis_and_in_either_direction():
    for x, y in ((750, 400), (250, 400), (500, 600), (500, 200), (700, 600)):
        c = recentre(x, y, 10)
        assert c is not None, (x, y)
        assert _reverdict(c, x, y, 10).level == "centred", (x, y)


def test_no_offer_without_a_vetted_size_or_from_a_degenerate_frame():
    # Same "never guess" contract as the verdict itself.
    assert recentre(750, 400, None) is None
    assert recentre(750, 400, 0) is None
    assert recentre(750, 400, 10, width_px=0) is None
    assert recentre(750, 400, 10, height_px=0) is None
    assert recentre(750, 400, 10, width_px=1) is None
    assert recentre(750, 400, 10, arcsec_per_px=0.0) is None
    assert recentre(float("nan"), 400, 10) is None
    assert recentre(750, float("inf"), 10) is None


# ---------------------------------------------------------------------------
# Why there's no offer — the refusal reason, so the worst-framed pictures don't
# get *less* help than the mildly off-centre ones.
# ---------------------------------------------------------------------------


def outcome(x, y, size_arcmin, **over):
    return recentre_outcome(
        x_px=x, y_px=y, size_arcmin=size_arcmin, **{**FRAME, **over},
    )


def test_the_too_destructive_refusal_says_how_little_the_crop_would_keep():
    # The case the app used to go quiet on: pushed into a corner, the crop that
    # would centre it exists and is measurable — it just isn't worth taking. That
    # number is what makes "better to re-point next session" an honest sentence.
    o = outcome(900, 700, 10)
    assert o.crop is None
    assert o.reason == "too_destructive"
    assert o.kept is not None and 0.0 < o.kept < 0.4


def test_each_other_refusal_carries_its_own_reason():
    assert outcome(500, 400, 10).reason == "centred"        # nothing to fix
    assert outcome(750, 400, 60).reason == "cramped"        # no room around it
    assert outcome(750, 400, None).reason == "unknown_size"  # never guess
    assert outcome(750, 400, 10, width_px=0).reason == "degenerate"
    assert outcome(float("nan"), 400, 10).reason == "degenerate"


def test_an_offer_reports_no_reason_and_the_kept_fraction_it_chose():
    o = outcome(750, 400, 10)
    assert o.crop is not None
    assert o.reason is None
    assert o.kept == pytest.approx(o.crop.kept)


def test_the_two_views_of_the_same_answer_can_never_disagree():
    # `recentre_crop` is a thin view over `recentre_outcome`, so every case the
    # offer covers must agree with the outcome's crop — one implementation.
    for x, y, size in (
        (750, 400, 10), (900, 700, 10), (500, 400, 10), (750, 400, 60),
        (250, 400, 10), (500, 600, 10), (500, 60, 30), (500, 400, 180),
    ):
        assert recentre(x, y, size) == outcome(x, y, size).crop, (x, y, size)
