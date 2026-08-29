"""The vocabulary for "what does the stored preview show of its canvas?".

A run's preview PNG is normally a plain downscale of the master FITS, and every
surface that lines up with it assumes so. The one-click "Process target"
auto-edit breaks that: Auto ends with a ``geometry.crop`` that trims a mosaic's
ragged border, so the stored picture becomes a *crop* of the canvas. These pin
the encoding (:mod:`seestack.previewcrop`) and the recipe → crop reduction that
records it.
"""

from __future__ import annotations

from seestack.edit.recipe import Recipe, preview_crop_of_recipe, recipe_from_dict
from seestack.previewcrop import (
    UNKNOWN,
    PreviewCrop,
    crop_pixel_box,
    make_crop,
    parse_preview_crop,
    preview_crop_json,
)


def _recipe(*ops) -> Recipe:
    return recipe_from_dict({"ops": [
        {"id": i, "params": p, "enabled": e} for i, p, e in ops]})


# ---- the encoding -------------------------------------------------------

def test_round_trip_keeps_the_bounds():
    crop = PreviewCrop(0.1, 0.2, 0.75, 0.9)
    back = parse_preview_crop(preview_crop_json(crop))
    assert isinstance(back, PreviewCrop)
    assert back.as_tuple() == crop.as_tuple()


def test_no_crop_and_a_full_crop_both_store_as_nothing():
    """A run whose render covers the whole canvas must clear the column, not
    leave a stale rectangle — the "always written, never left alone" rule."""
    assert preview_crop_json(None) is None
    assert preview_crop_json(PreviewCrop(0.0, 0.0, 1.0, 1.0)) is None
    assert parse_preview_crop(None) is None
    assert parse_preview_crop("") is None


def test_unreadable_values_read_as_no_crop():
    """An unparseable column must never be *more* alarming than an absent one."""
    for bad in ("not json", "[]", "null", '{"x0": 0.1}', '{"x0": "a", "y0": 0,'
                ' "x1": 1, "y1": 1}'):
        assert parse_preview_crop(bad) is None


def test_the_unknown_marker_round_trips():
    assert parse_preview_crop(preview_crop_json(UNKNOWN)) == UNKNOWN


def test_make_crop_clamps_orders_and_rejects_degenerate():
    assert make_crop(0.9, 0.8, 0.1, 0.2).as_tuple() == (0.1, 0.2, 0.9, 0.8)
    assert make_crop(-1.0, -1.0, 2.0, 2.0).as_tuple() == (0.0, 0.0, 1.0, 1.0)
    assert make_crop(0.5, 0.0, 0.5, 1.0) is None       # zero width
    assert make_crop(float("nan"), 0.0, 1.0, 1.0) is None


def test_compose_nests_two_crops():
    """A crop of a crop is one crop of the original canvas."""
    outer = PreviewCrop(0.2, 0.0, 0.6, 1.0)            # 40 % of the width
    inner = PreviewCrop(0.5, 0.0, 1.0, 1.0)            # right half of *that*
    assert outer.compose(inner).as_tuple() == (0.4, 0.0, 0.6, 1.0)


def test_crop_pixel_box_is_the_whole_grid_without_a_crop():
    assert crop_pixel_box(None, 40, 30) == (0, 0, 40, 30)
    assert crop_pixel_box(PreviewCrop(0.25, 0.0, 0.75, 0.5), 40, 30) == (
        10, 0, 30, 15)


def test_crop_pixel_box_keeps_at_least_one_pixel_per_axis():
    """A sliver crop of a small grid must never produce an empty slice."""
    x0, y0, x1, y1 = crop_pixel_box(PreviewCrop(0.999, 0.999, 1.0, 1.0), 8, 8)
    assert x1 > x0 and y1 > y0
    assert 0 <= x0 < x1 <= 8 and 0 <= y0 < y1 <= 8


# ---- reducing a recipe to a crop ---------------------------------------

def test_a_tone_only_recipe_crops_nothing():
    assert preview_crop_of_recipe(_recipe(
        ("tone.curves", {"auto": True}, True))) is None


def test_the_auto_border_trim_is_read_off_the_recipe():
    crop = preview_crop_of_recipe(_recipe(
        ("tone.curves", {"auto": True}, True),
        ("geometry.crop", {"x0": 0.1, "y0": 0.05, "x1": 0.9, "y1": 0.95}, True)))
    assert isinstance(crop, PreviewCrop)
    assert crop.as_tuple() == (0.1, 0.05, 0.9, 0.95)


def test_a_disabled_crop_is_not_recorded():
    """A disabled op doesn't render, so it can't have moved the pixels."""
    assert preview_crop_of_recipe(_recipe(
        ("geometry.crop", {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}, False),
    )) is None


def test_two_crops_compose():
    crop = preview_crop_of_recipe(_recipe(
        ("geometry.crop", {"x0": 0.2, "y0": 0.0, "x1": 0.6, "y1": 1.0}, True),
        ("geometry.crop", {"x0": 0.5, "y0": 0.0, "x1": 1.0, "y1": 1.0}, True)))
    assert isinstance(crop, PreviewCrop)
    assert crop.as_tuple() == (0.4, 0.0, 0.6, 1.0)


def test_a_rotate_makes_the_geometry_unknown():
    """A rotated render is not a crop of the canvas at all — callers must decline
    to place geometry rather than confidently misplace it."""
    assert preview_crop_of_recipe(_recipe(
        ("geometry.rotate", {"angle": 12.0}, True),
        ("geometry.crop", {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}, True),
    )) == UNKNOWN


def test_a_no_op_rotate_is_not_unknown():
    """``geometry.rotate`` ignores a sub-milli-degree angle, so it left the
    pixels exactly where they were."""
    assert preview_crop_of_recipe(_recipe(
        ("geometry.rotate", {"angle": 0.0}, True))) is None


def test_a_disabled_rotate_is_not_unknown():
    crop = preview_crop_of_recipe(_recipe(
        ("geometry.rotate", {"angle": 30.0}, False),
        ("geometry.crop", {"x0": 0.0, "y0": 0.0, "x1": 0.5, "y1": 1.0}, True)))
    assert isinstance(crop, PreviewCrop)
    assert crop.as_tuple() == (0.0, 0.0, 0.5, 1.0)


def test_a_resize_does_not_change_the_mapping():
    """A uniform rescale is exactly what the consumers already handle — they work
    in fractions of the picture — so it is not a crop and not unknown."""
    assert preview_crop_of_recipe(_recipe(
        ("geometry.resize", {"scale": 0.5}, True))) is None
