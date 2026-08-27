"""Framed keepsake — a matted, titled, print-and-share-ready picture.

The sibling of the nameplate: instead of a translucent bar drawn *over* the
picture, a dark matte *around* it with the object's name and acquisition data set
beneath. These pin the caption split, the framing geometry, the no-op, and the
one thing that made the nameplate ship a hollow box for months — that every
character it can draw actually has a glyph in the bundled font.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from seestack.keepsake import (
    EDGE_RGB,
    MATTE_RGB,
    _load_font,
    draw_keepsake,
    keepsake_caption,
)
from seestack.nameplate import NameplateFields

FULL = NameplateFields(
    target="M 31", integration_s=15150, n_frames=505, sub_exposure_s=30,
    date_iso="2026-07-19T21:03:00", camera="ZWO Seestar S50",
)


def _picture(w: int = 400, h: int = 300, rgb=(120, 130, 140)) -> Image.Image:
    return Image.new("RGB", (w, h), rgb)


def test_caption_splits_the_name_off_as_a_title():
    title, details = keepsake_caption(FULL)
    assert title == "M 31"
    # Everything the nameplate says, minus the name — same wording, same order,
    # because both go through `acquisition_parts`.
    assert details == "4h 12m (505x30s) · 19 Jul 2026 · ZWO Seestar S50"
    assert "M 31" not in details


def test_caption_degrades_to_one_half_or_neither():
    assert keepsake_caption(NameplateFields(target="NGC 7000")) == ("NGC 7000", "")
    title, details = keepsake_caption(NameplateFields(integration_s=3600))
    assert title == "" and details == "1h"
    assert keepsake_caption(NameplateFields()) == ("", "")


def test_draw_keepsake_frames_the_picture_and_keeps_its_pixels_exactly():
    img = _picture()
    out = draw_keepsake(img, FULL)

    assert out.mode == "RGB"
    # A matte on every side plus a caption foot, so the card is strictly larger.
    assert out.size[0] > 400 and out.size[1] > 300
    arr = np.asarray(out)
    # The picture itself is untouched — a keepsake never draws over the sky.
    src = np.asarray(img)
    matte = (out.size[0] - 400) // 2
    assert np.array_equal(arr[matte:matte + 300, matte:matte + 400], src)


def test_the_matte_is_the_matte_colour_and_the_foot_is_the_deep_side():
    """Even mount on three sides; the foot is deeper because it carries the
    caption — the proportion a physical photo mount uses."""
    out = draw_keepsake(_picture(), FULL)
    arr = np.asarray(out)
    w, h = out.size
    # Bare matte in the corners, top and bottom alike.
    assert tuple(arr[1, 1]) == MATTE_RGB
    assert tuple(arr[h - 2, 1]) == MATTE_RGB

    side = (w - 400) // 2            # the picture is centred left-to-right
    top = side                       # …and its head margin matches the sides
    assert tuple(arr[top, w // 2]) == (120, 130, 140)          # picture starts
    assert tuple(arr[top - 2, w // 2]) == MATTE_RGB            # matte above it
    bottom = h - (top + 300)
    assert bottom > top * 2, "the caption foot must be the deep side"


def test_the_caption_is_actually_drawn_beneath_the_picture():
    """Light type on a dark matte: the foot must contain pixels far brighter
    than the matte, and they must be below the picture, not on it."""
    out = draw_keepsake(_picture(rgb=(10, 10, 12)), FULL)
    arr = np.asarray(out)
    matte = (out.size[0] - 400) // 2
    foot = arr[matte + 300:]
    assert foot.max() > 200, "no light caption text found under the picture"


def test_a_hairline_separates_a_dark_picture_from_the_matte():
    """A black sky on a near-black card would read as a hole in the mount."""
    out = draw_keepsake(_picture(rgb=(0, 0, 0)), FULL)
    arr = np.asarray(out)
    matte = (out.size[0] - 400) // 2
    # The row just above the picture carries the edge line, not bare matte.
    assert tuple(arr[matte - 1, matte + 200]) == EDGE_RGB


def test_no_provenance_is_a_clean_no_op_rather_than_an_empty_mount():
    img = _picture()
    out = draw_keepsake(img, NameplateFields())
    assert out.size == img.size
    assert np.array_equal(np.asarray(img), np.asarray(out))


def test_a_title_only_run_still_frames_cleanly():
    out = draw_keepsake(_picture(), NameplateFields(target="M 42"))
    assert out.size[1] > 300  # framed, with room for the one line


def test_the_frame_scales_with_the_short_side_not_the_long_one():
    """A wide mosaic and a square crop should get proportionally the same mount,
    so the app never puts a hairline mount on a panorama."""
    wide = draw_keepsake(_picture(1200, 300), FULL)
    square = draw_keepsake(_picture(300, 300), FULL)
    assert (wide.size[0] - 1200) == (square.size[0] - 300)


def test_a_long_caption_shrinks_to_fit_a_narrow_share():
    out = draw_keepsake(_picture(96, 72), NameplateFields(
        target="A very long target designation that would overflow a narrow card",
        integration_s=11520, n_frames=152, sub_exposure_s=30,
        date_iso="2026-07-19", camera="ZWO Seestar S50",
    ))
    assert out.size[0] > 96 and out.size[1] > 72   # no crash, still a card


def test_a_non_rgb_source_is_converted_rather_than_rejected():
    grey = Image.new("L", (200, 150), 90)
    out = draw_keepsake(grey, FULL)
    assert out.mode == "RGB"


def test_every_keepsake_character_has_a_glyph_in_the_font_we_draw_with():
    """The same rule the nameplate learned the hard way (v0.281.1): a character
    the bundled Aileron face lacks bakes a hollow ``.notdef`` box into the
    picture. Pin it here too, since the keepsake is the *more* share-facing of
    the two."""
    font = _load_font(32)
    notdef = np.asarray(font.getmask(chr(0xE000), mode="L"))
    assert notdef.size, "reference .notdef glyph came back empty — re-pick it"

    def missing(text: str) -> list[str]:
        out = set()
        for ch in text:
            mask = np.asarray(font.getmask(ch, mode="L"))
            if mask.shape == notdef.shape and np.array_equal(mask, notdef):
                out.add(ch)
        return sorted(out)

    for fields in (
        FULL,
        NameplateFields(target="NGC 7000", integration_s=11520, n_frames=152),
        NameplateFields(target="M 42", n_frames=1),
        NameplateFields(integration_s=1.5, n_frames=3, sub_exposure_s=2.5,
                        date_iso="2026-01-05"),
    ):
        for part in keepsake_caption(fields):
            assert not missing(part), (
                f"{missing(part)!r} has no glyph in the bundled font, so it "
                f"bakes a hollow box into the keepsake: {part!r}"
            )
