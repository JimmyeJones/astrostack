"""\"Share your glow-up\" — the pure before/after composer (seestack/beforeafter.py)."""

from __future__ import annotations

import pytest

from seestack.beforeafter import (
    DEFAULT_WIDTH,
    MAX_WIDTH,
    MIN_WIDTH,
    before_after_caption,
    build_before_after,
    panel_labels,
    sub_exposure_label,
)

Image = pytest.importorskip("PIL.Image")


def _img(w: int, h: int, colour=(40, 60, 90)):
    return Image.new("RGB", (w, h), colour)


# ---- captions ----------------------------------------------------------

def test_sub_exposure_label_matches_the_reveal_cards_wording():
    assert sub_exposure_label(30) == "30-second"
    assert sub_exposure_label(30.0) == "30-second"
    assert sub_exposure_label(2.5) == "2.5-second"


@pytest.mark.parametrize("bad", [None, 0, -5, float("nan"), float("inf"), "x"])
def test_sub_exposure_label_drops_a_datum_it_cannot_use(bad):
    assert sub_exposure_label(bad) == ""


def test_panel_labels_name_each_half():
    assert panel_labels(505, 30) == ("One 30-second frame", "505 frames stacked")


def test_panel_labels_degrade_one_field_at_a_time():
    assert panel_labels(505, None) == ("One frame", "505 frames stacked")
    # Never "None frames stacked" / "0 frames stacked" on a run with no count.
    assert panel_labels(None, 30) == ("One 30-second frame", "Stacked")
    assert panel_labels(0, None) == ("One frame", "Stacked")
    # A one-frame "stack" reads as one frame, not "1 frames".
    assert panel_labels(1, 10) == ("One 10-second frame", "1 frame stacked")


def test_caption_reads_as_one_plain_sentence():
    assert before_after_caption("M 42", 505, 30, 11520) == (
        "M 42 · one 30-second frame vs 505 frames stacked · 3.2 h of light")


def test_caption_drops_missing_clauses_rather_than_printing_blanks():
    # No name → the comparison and the integration alone.
    assert before_after_caption(None, 505, 30, 11520) == (
        "one 30-second frame vs 505 frames stacked · 3.2 h of light")
    # No frame count → no comparison clause (it would say "vs Stacked").
    assert before_after_caption("M 42", None, 30, 11520) == "M 42 · 3.2 h of light"
    # No integration → no dangling "of light".
    assert before_after_caption("M 42", 505, 30, None) == (
        "M 42 · one 30-second frame vs 505 frames stacked")
    # Nothing at all to say → an empty caption (the bar is then omitted).
    assert before_after_caption(None, None, None, None) == ""


def test_caption_survives_a_non_finite_integration():
    # A NaN header must cost the clause, never the whole picture.
    assert before_after_caption("M 42", None, None, float("nan")) == "M 42"
    assert before_after_caption("M 42", None, None, float("inf")) == "M 42"


def test_caption_uses_no_glyph_the_built_in_font_lacks():
    # An em dash / arrow renders as a tofu box on the one image the user posts,
    # so the caption must separate with "·" (which the built-in face has).
    caption = before_after_caption("M 42", 505, 30, 11520)
    for bad in ("—", "→", "×", "–"):
        assert bad not in caption


# ---- layout ------------------------------------------------------------

def test_composes_the_two_halves_side_by_side_at_the_asked_width():
    out = build_before_after(_img(400, 300), _img(400, 300), caption="M 42")
    assert out is not None
    assert out.size[0] == DEFAULT_WIDTH
    # Two half-cells plus padding and a caption bar: taller than one half-cell,
    # and nowhere near as tall as it is wide for two landscape halves.
    assert 0 < out.size[1] < out.size[0]


def test_a_missing_half_yields_no_picture_rather_than_a_lopsided_one():
    assert build_before_after(None, _img(400, 300)) is None
    assert build_before_after(_img(400, 300), None) is None
    assert build_before_after(None, None) is None


def test_width_is_clamped_to_a_postable_range():
    assert build_before_after(_img(40, 30), _img(40, 30), width=10).size[0] == MIN_WIDTH
    assert build_before_after(
        _img(40, 30), _img(40, 30), width=99999).size[0] == MAX_WIDTH


def test_neither_half_is_squashed_when_the_two_shapes_disagree():
    # A portrait sub beside a wide mosaic master: the composed cell follows the
    # *taller* aspect, so the portrait half is the one shown whole.
    portrait = build_before_after(_img(300, 600), _img(1200, 400))
    wide_only = build_before_after(_img(1200, 400), _img(1200, 400))
    assert portrait.size[1] > wide_only.size[1]


def test_the_caption_bar_only_exists_when_there_is_something_to_say():
    with_caption = build_before_after(_img(400, 300), _img(400, 300), caption="M 42")
    without = build_before_after(_img(400, 300), _img(400, 300), caption="")
    assert with_caption.size[1] > without.size[1]


def test_the_two_halves_land_in_their_own_sides_of_the_canvas():
    # Distinct flat colours: the composed picture must carry the "before" on the
    # left and the "after" on the right (a swap would sell the reveal backwards).
    out = build_before_after(_img(400, 300, (200, 20, 20)),
                             _img(400, 300, (20, 20, 200)), caption="")
    w, h = out.size
    left = out.getpixel((w // 4, h // 2))
    right = out.getpixel((3 * w // 4, h // 2))
    assert left[0] > left[2]     # red-dominant
    assert right[2] > right[0]   # blue-dominant


def test_pixels_are_never_brightened_or_stretched_by_the_composer():
    # Honesty: matching the two tone curves is the caller's job, so a flat
    # mid-grey half must come out the same mid-grey it went in as.
    grey = (90, 90, 90)
    out = build_before_after(_img(800, 600, grey), _img(800, 600, grey), caption="")
    w, h = out.size
    assert out.getpixel((w // 4, h // 2)) == grey


def test_a_half_that_cannot_be_read_yields_nothing_rather_than_raising():
    class Broken:
        def convert(self, mode):  # noqa: ANN001, ANN201
            raise OSError("truncated")

    assert build_before_after(Broken(), _img(400, 300)) is None
