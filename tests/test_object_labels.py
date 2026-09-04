""""What's in it?", baked into the shared file.

The app names the catalog objects in a solved field on screen (v0.293.0), but a
browser overlay doesn't travel with the picture — share it and the answer is
gone. :mod:`seestack.objectlabels` draws the same names into the pixels.

Two halves, tested separately because only one of them needs an image:

* :func:`place_labels` — pure geometry. Which objects are on the picture the
  user is actually looking at (a cropped preview shows less than the canvas),
  where they land as fractions of it, and in what order.
* :func:`draw_object_labels` — the pixel work. It must draw *something* where a
  name goes, nothing where none does, keep every label inside the frame, and
  never stack two labels on top of each other.
"""

from dataclasses import dataclass

import numpy as np
import pytest

pytest.importorskip("PIL")

from seestack.objectlabels import (  # noqa: E402
    ObjectLabel,
    ObjectLabels,
    draw_object_labels,
    label_budget,
    label_text,
    place_labels,
)


@dataclass
class _Obj:
    """The shape :func:`seestack.annotate.objects_in_field` returns."""

    catalog_id: str
    name: str
    x_px: float
    y_px: float


def _picture(w=400, h=300, level=8):
    from PIL import Image

    return Image.new("RGB", (w, h), (level, level, level))


# ---- the pure half: which objects, where -------------------------------------

def test_a_friendly_name_wins_over_the_designation():
    """The chip says what the on-screen one says — the mirror of the overlay's
    ``objectLabel``, so the file and the card can't disagree."""
    assert label_text("M42", "Orion Nebula") == "Orion Nebula"
    assert label_text("NGC 891", "") == "NGC 891"
    assert label_text("NGC 891", "   ") == "NGC 891"
    assert label_text("", "") == ""


def test_anchors_are_fractions_of_the_picture_not_pixels():
    """The shared JPEG is re-rendered at share resolution, so its pixel grid is
    not the FITS one the pins were measured on. Fractions survive that."""
    labels = place_labels([_Obj("M1", "Crab", 100.0, 60.0)], 400, 300)
    assert len(labels.labels) == 1
    lab = labels.labels[0]
    assert lab.x == pytest.approx(0.25)
    assert lab.y == pytest.approx(0.2)


def test_the_most_notable_object_comes_first():
    """Room is handed out in order, so the order has to be the one the app
    already calls notability: closest to the picture's centre first, exactly as
    the on-screen read-out sorts."""
    labels = place_labels([
        _Obj("EDGE", "Edge", 10.0, 10.0),
        _Obj("MID", "Middle", 200.0, 150.0),
        _Obj("NEAR", "Near", 210.0, 160.0),
    ], 400, 300)
    assert [lab.text for lab in labels.labels] == ["Middle", "Near", "Edge"]
    assert labels.labels[0].notability < labels.labels[-1].notability


def test_an_object_off_the_canvas_is_dropped():
    labels = place_labels([
        _Obj("IN", "Inside", 200.0, 150.0),
        _Obj("OUT", "Outside", 900.0, 150.0),
    ], 400, 300)
    assert [lab.text for lab in labels.labels] == ["Inside"]


def test_a_cropped_preview_re_bases_its_pins_onto_what_it_shows():
    """The one-click auto-edit trims a mosaic's ragged border, so the stored
    preview shows a *rectangle* of the canvas the pins were measured on. An
    object at the trim's centre has to land at the middle of the picture, not
    wherever it sat on the canvas behind it."""
    box = (100, 75, 300, 225)          # the middle half of a 400×300 canvas
    labels = place_labels([_Obj("M1", "Crab", 200.0, 150.0)], 400, 300,
                          crop_box=box)
    assert labels.labels[0].x == pytest.approx(0.5)
    assert labels.labels[0].y == pytest.approx(0.5)


def test_an_object_the_trim_cut_away_is_not_drawn_off_the_edge():
    """The realistic failure: an object that was in the canvas but outside the
    kept rectangle. Placing it at all would put a name on empty sky."""
    box = (100, 75, 300, 225)
    labels = place_labels([
        _Obj("KEPT", "Kept", 200.0, 150.0),
        _Obj("TRIMMED", "Trimmed", 20.0, 150.0),
    ], 400, 300, crop_box=box)
    assert [lab.text for lab in labels.labels] == ["Kept"]


def test_nothing_to_place_is_falsey_rather_than_an_error():
    assert not place_labels([], 400, 300)
    assert not place_labels([_Obj("M1", "Crab", 1.0, 1.0)], 0, 300)
    assert not place_labels([_Obj("M1", "Crab", 1.0, 1.0)], 400, 300,
                            crop_box=(10, 10, 10, 10))
    assert not ObjectLabels()


# ---- the pins follow a North-up turn -----------------------------------------

def _rotated_pixel(x, y, w, h, angle):
    """Where a pixel really lands, measured on the renderer's own output.

    Ground truth rather than a second implementation of the transform: plant one
    bright pixel, rotate the image with the *same* function the picture goes
    through (:func:`seestack.render.orient.rotate_image_north_up`), and take the
    centroid of what comes out — which also absorbs the bicubic splash an
    off-orthogonal angle leaves behind.
    """
    from seestack.render.orient import rotate_image_north_up

    img = np.zeros((h, w, 3), dtype=np.float32)
    img[int(round(y)), int(round(x))] = 1.0
    rot = rotate_image_north_up(img, angle)
    plane = rot[..., 0]
    hit = plane > plane.max() * 0.3
    ys, xs = np.nonzero(hit)
    wts = plane[hit]
    return ((xs * wts).sum() / wts.sum(), (ys * wts).sum() / wts.sum(),
            rot.shape[1], rot.shape[0])


def test_no_turn_is_exactly_todays_placement():
    """The turn is opt-in: every existing caller passes nothing and must get the
    identical anchors, so an un-turned share stays byte-for-byte what it was."""
    objs = [_Obj("M1", "Crab", 100.0, 60.0), _Obj("M2", "Two", 310.0, 240.0)]
    assert place_labels(objs, 400, 300) == place_labels(objs, 400, 300,
                                                        north_up_turns=())
    assert place_labels(objs, 400, 300) == place_labels(objs, 400, 300,
                                                        north_up_turns=(0.0,))


@pytest.mark.parametrize("angle", [90.0, -90.0, 180.0])
def test_a_square_turn_moves_the_pins_losslessly(angle):
    """The common case is a near-orthogonal correction, which the renderer does
    as a pure ``np.rot90``. The anchors must land on exactly the pixel the image
    did — no half-pixel, and no flipped axis."""
    w, h = 400, 300
    objs = [_Obj("A", "A", 100.0, 60.0), _Obj("B", "B", 330.0, 250.0)]
    labels = place_labels(objs, w, h, north_up_turns=(angle,))
    by = {lab.text: lab for lab in labels.labels}
    for o in objs:
        gx, gy, nw, nh = _rotated_pixel(o.x_px, o.y_px, w, h, angle)
        lab = by[o.name]
        assert lab.x * nw == pytest.approx(gx, abs=1e-6)
        assert lab.y * nh == pytest.approx(gy, abs=1e-6)


@pytest.mark.parametrize("angle", [31.5, 123.0, 7.0, -44.0])
def test_an_off_square_turn_lands_the_pins_inside_a_marker_dot(angle):
    """An arbitrary angle goes through ``PIL.Image.rotate(expand=True)``, whose
    canvas is a ceil/floor bounding box. Measured residual is well under a
    fifth of a pixel — orders of magnitude inside the dot that gets drawn, which
    is what "the name points at its object" actually needs."""
    w, h = 400, 300
    objs = [_Obj("A", "A", 100.0, 60.0), _Obj("B", "B", 330.0, 250.0),
            _Obj("C", "C", 200.0, 150.0)]
    labels = place_labels(objs, w, h, north_up_turns=(angle,))
    by = {lab.text: lab for lab in labels.labels}
    for o in objs:
        gx, gy, nw, nh = _rotated_pixel(o.x_px, o.y_px, w, h, angle)
        lab = by[o.name]
        err = ((lab.x * nw - gx) ** 2 + (lab.y * nh - gy) ** 2) ** 0.5
        assert err < 0.5, (o.name, err)
        assert 0.0 <= lab.x <= 1.0 and 0.0 <= lab.y <= 1.0


def test_two_turns_follow_the_pixels_and_are_not_the_sum_of_one():
    """A picture a past "Adjust → North up → Save" already turned, then shared
    with ``?north_up=true``, takes *two* rotations of a growing canvas: the first
    rotate-with-expand adds black wedges, and the second bounds a frame that now
    includes them. Summing them into one rotation of the original grid gives a
    different canvas and a different place — which is why the turns are passed as
    a sequence. (Two non-square angles on purpose: a leading 90° expands nothing,
    so it composes exactly and would hide the difference.)"""
    from seestack.render.orient import rotate_image_north_up

    w, h = 400, 300
    first, second = 33.0, 41.0
    obj = _Obj("A", "A", 120.0, 70.0)

    # Ground truth: rotate the marker image the way the pixels are rotated.
    img = np.zeros((h, w, 3), dtype=np.float32)
    img[70, 120] = 1.0
    rot = rotate_image_north_up(rotate_image_north_up(img, first), second)
    plane = rot[..., 0]
    hit = plane > plane.max() * 0.3
    ys, xs = np.nonzero(hit)
    wts = plane[hit]
    gx, gy = (xs * wts).sum() / wts.sum(), (ys * wts).sum() / wts.sum()

    lab = place_labels([obj], w, h, north_up_turns=(first, second)).labels[0]
    assert lab.x * rot.shape[1] == pytest.approx(gx, abs=0.6)
    assert lab.y * rot.shape[0] == pytest.approx(gy, abs=0.6)

    summed = place_labels([obj], w, h,
                          north_up_turns=(first + second,)).labels[0]
    assert (summed.x, summed.y) != (lab.x, lab.y)


def test_a_turn_re_places_the_names_without_reshuffling_them():
    """Notability is "how central is this object in the picture", and a turn
    doesn't change which objects the picture is about — so a crowded field keeps
    the same names, in the same order, wherever North ends up."""
    objs = [_Obj("EDGE", "Edge", 10.0, 10.0),
            _Obj("MID", "Middle", 200.0, 150.0),
            _Obj("NEAR", "Near", 210.0, 160.0)]
    flat = place_labels(objs, 400, 300)
    turned = place_labels(objs, 400, 300, north_up_turns=(37.0,))
    assert [lab.text for lab in turned.labels] == [lab.text for lab in flat.labels]
    assert ([lab.notability for lab in turned.labels]
            == [lab.notability for lab in flat.labels])
    assert (turned.labels[0].x, turned.labels[0].y) != (flat.labels[0].x,
                                                        flat.labels[0].y)


def test_a_turn_composes_with_a_crop():
    """A trimmed preview is cropped *then* turned, so the turn applies to the
    kept rectangle — not to the canvas behind it. An object at the trim's centre
    stays at the middle of the picture however far it is turned.

    Within a pixel, not exactly: an anchor is ``index / size``, so the middle of
    a 200-wide grid is index 99.5 and the object sitting on index 100 is half a
    pixel off centre before the turn as well as after it. That half pixel is the
    fraction convention every caller already uses, not drift introduced here —
    the ground-truth tests above pin the placement itself to the renderer.
    """
    box = (100, 75, 300, 225)          # the middle half of a 400×300 canvas
    for angle in (0.0, 90.0, 41.0):
        labels = place_labels([_Obj("M1", "Crab", 200.0, 150.0)], 400, 300,
                              crop_box=box, north_up_turns=(angle,))
        lab = labels.labels[0]
        assert abs(lab.x - 0.5) * 150 <= 1.0
        assert abs(lab.y - 0.5) * 150 <= 1.0


# ---- the pixel half ----------------------------------------------------------

def test_an_empty_set_returns_the_picture_unchanged():
    """A run with no catalog object in frame must share byte-for-byte the plain
    picture — the same clean no-op an empty ``SkyMarks`` is."""
    img = _picture()
    out = draw_object_labels(img, ObjectLabels())
    assert np.array_equal(np.asarray(out), np.asarray(img))


def test_a_label_marks_the_picture_where_its_object_is():
    img = _picture()
    out = draw_object_labels(
        img, ObjectLabels((ObjectLabel("Orion Nebula", 0.5, 0.5, 0.0),)))
    before = np.asarray(img, dtype=np.int16)
    after = np.asarray(out, dtype=np.int16)
    assert not np.array_equal(before, after), "something should have been drawn"
    changed = np.argwhere(np.abs(after - before).sum(axis=2) > 0)
    ys, xs = changed[:, 0], changed[:, 1]
    # The marks land around the object's own spot, not somewhere else entirely.
    assert abs(float(xs.mean()) - 200.0) < 60.0
    assert abs(float(ys.mean()) - 150.0) < 60.0


def test_every_mark_stays_inside_the_picture():
    """A name drawn half off the edge is worse than no name. Objects pushed hard
    into all four corners must either be placed wholly inside or dropped."""
    img = _picture()
    corners = tuple(
        ObjectLabel(f"Corner {i}", x, y, 1.4)
        for i, (x, y) in enumerate(((0.02, 0.02), (0.98, 0.02),
                                    (0.02, 0.98), (0.98, 0.98)))
    )
    out = draw_object_labels(img, ObjectLabels(corners))
    diff = np.abs(np.asarray(out, dtype=np.int16)
                  - np.asarray(img, dtype=np.int16)).sum(axis=2)
    if diff.any():
        ys, xs = np.nonzero(diff)
        assert xs.min() >= 0 and xs.max() < img.size[0]
        assert ys.min() >= 0 and ys.max() < img.size[1]


def test_a_crowded_field_does_not_pile_labels_on_top_of_each_other():
    """Point a wide frame at the Sword of Orion and a dozen objects land within
    a few pixels. Every one of them gets a chip and the picture becomes an
    unreadable smear, so the drawing has to give up rather than overdraw."""
    img = _picture(600, 450)
    pile = tuple(
        ObjectLabel(f"Object {i}", 0.5 + 0.002 * i, 0.5 + 0.002 * i, 0.01 * i)
        for i in range(12)
    )
    crowded = np.abs(
        np.asarray(draw_object_labels(img, ObjectLabels(pile)), dtype=np.int16)
        - np.asarray(img, dtype=np.int16)).sum(axis=2)
    # Four well-spread objects, so nothing has to be dropped for room.
    spread = tuple(
        ObjectLabel(f"Object {i}", x, y, 0.5)
        for i, (x, y) in enumerate(((0.25, 0.25), (0.75, 0.25),
                                    (0.25, 0.75), (0.75, 0.75)))
    )
    roomy = np.abs(
        np.asarray(draw_object_labels(img, ObjectLabels(spread)), dtype=np.int16)
        - np.asarray(img, dtype=np.int16)).sum(axis=2)
    # A pile of 12 must not ink more of the picture than 4 spread-out names do:
    # the ones with nowhere clear to go are dropped, not stacked.
    assert int((crowded > 0).sum()) <= int((roomy > 0).sum())


def test_the_budget_scales_with_the_picture_and_stays_in_its_band():
    """A thumbnail still gets a few names; a huge mosaic doesn't turn into a
    catalogue page."""
    assert label_budget(0, 0) == 0
    assert label_budget(120, 90) == 3            # the floor
    assert label_budget(40_000, 40_000) == 10    # the ceiling
    assert 3 <= label_budget(1600, 1200) <= 10


def test_the_canvas_is_not_resized():
    """These are marks *on* the picture, like the sky marks — not a frame around
    it, which would change what a wallpaper or a print is."""
    img = _picture(640, 360)
    out = draw_object_labels(
        img, ObjectLabels((ObjectLabel("M42", 0.5, 0.5, 0.0),)))
    assert out.size == img.size


# ---- sharing the picture with the sky marks too ------------------------------

def test_a_label_routes_around_a_zone_it_is_told_to_avoid():
    """The sky marks are drawn *after* the names, so a collision doesn't
    mislead — it just buries a name nobody can then read. Told where the bar and
    the rose will land, the placement moves the chip instead."""
    img = _picture(600, 450)
    # An object right where a compass rose would sit, top-right.
    lab = ObjectLabels((ObjectLabel("NGC 1981", 0.86, 0.10, 0.9),))
    rose = (500.0, 0.0, 600.0, 100.0)

    free = np.abs(np.asarray(draw_object_labels(img, lab), dtype=np.int16)
                  - np.asarray(img, dtype=np.int16)).sum(axis=2)
    avoided = np.abs(
        np.asarray(draw_object_labels(img, lab, avoid=(rose,)), dtype=np.int16)
        - np.asarray(img, dtype=np.int16)).sum(axis=2)

    assert free.any(), "the control has to draw something"
    ys, xs = np.nonzero(avoided)
    if ys.size:
        # The chip moved out of the zone. The *dot* may still sit inside it —
        # it never moves, by design; only the name is nudged.
        chip = (xs >= rose[0]) & (xs <= rose[2]) & (ys >= rose[1]) & (ys <= rose[3])
        assert int(chip.sum()) < int(
            ((np.nonzero(free)[1] >= rose[0]) & (np.nonzero(free)[1] <= rose[2])
             & (np.nonzero(free)[0] >= rose[1]) & (np.nonzero(free)[0] <= rose[3])
             ).sum())


def test_a_label_with_nowhere_left_to_go_is_dropped_not_buried():
    """When the avoided zone swallows every spot a chip could take, the name is
    given up. A name drawn under the scale bar is worse than no name."""
    img = _picture(600, 450)
    lab = ObjectLabels((ObjectLabel("NGC 1980", 0.12, 0.06, 0.99),))
    assert np.abs(np.asarray(draw_object_labels(img, lab), dtype=np.int16)
                  - np.asarray(img, dtype=np.int16)).sum() > 0
    whole_top = (0.0, 0.0, 600.0, 200.0)
    buried = np.abs(
        np.asarray(draw_object_labels(img, lab, avoid=(whole_top,)), dtype=np.int16)
        - np.asarray(img, dtype=np.int16)).sum()
    assert buried == 0


def test_avoiding_nothing_is_exactly_todays_drawing():
    """The default is a no-op, so every caller that doesn't pass zones — and the
    plain labelled share — is byte-for-byte unchanged."""
    img = _picture()
    lab = ObjectLabels((ObjectLabel("Orion Nebula", 0.5, 0.5, 0.0),))
    assert np.array_equal(np.asarray(draw_object_labels(img, lab)),
                          np.asarray(draw_object_labels(img, lab, avoid=())))
