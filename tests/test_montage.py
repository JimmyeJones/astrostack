"""\"My deep-sky wall\" — the pure montage layout helper (seestack/montage.py)."""

from __future__ import annotations

import pytest

from seestack.montage import (
    MIN_TILES,
    MontageTile,
    build_montage,
    montage_caption,
    montage_grid,
    montage_title,
)

Image = pytest.importorskip("PIL.Image")


def _tile(w: int, h: int, colour=(40, 60, 90), caption: str = "") -> MontageTile:
    return MontageTile(image=Image.new("RGB", (w, h), colour), caption=caption)


@pytest.mark.parametrize(("n", "expected"), [
    (1, (1, 1)), (2, (2, 1)), (3, (3, 1)),   # a short row reads better than a hole
    (4, (2, 2)), (5, (3, 2)), (6, (3, 2)),
    (7, (3, 3)), (9, (3, 3)), (10, (4, 3)),
])
def test_grid_is_as_square_as_it_can_fill(n, expected):
    assert montage_grid(n) == expected


def test_grid_never_leaves_more_than_one_short_row():
    for n in range(1, 17):
        cols, rows = montage_grid(n)
        assert cols * rows >= n
        assert (cols * rows) - n < cols  # at most one row is partly empty


def test_grid_honours_and_clamps_an_explicit_column_count():
    assert montage_grid(6, columns=2) == (2, 3)
    assert montage_grid(3, columns=99) == (3, 1)   # never wider than the tiles
    assert montage_grid(3, columns=0) == (1, 3)
    assert montage_grid(0) == (0, 0)


def test_caption_names_the_target_and_its_integration():
    assert montage_caption("M 42", 11520) == "M 42 · 3.2 h"
    # No integration yet → the name alone, never a dangling separator or "0s".
    assert montage_caption("M 42", None) == "M 42"
    assert montage_caption("M 42", 0) == "M 42"
    # No name at all → no label (the label drawer treats "" as a no-op).
    assert montage_caption("  ", 3600) == ""


def test_title_says_what_the_wall_holds():
    assert montage_title(14, 136800) == "My deep-sky wall · 14 targets, 38 h of light"
    assert montage_title(1, 3600) == "My deep-sky wall · 1 target, 1.0 h of light"
    # Nothing to report about integration → the count alone, not a hole.
    assert montage_title(3, None) == "My deep-sky wall · 3 targets"


def test_one_picture_is_not_a_wall():
    """The offer must self-hide rather than dress a single picture up as a
    montage — that is the same picture the gallery already shows."""
    assert build_montage([_tile(80, 60)]) is None
    assert build_montage([]) is None
    assert MIN_TILES == 2


def test_a_landscape_and_a_portrait_tile_are_both_undistorted():
    """A single-field stack and a tall mosaic must sit together without either
    being squashed — round stars stay round. Letterboxed, so each tile's own
    pixels keep their aspect ratio and the pad is background, not stretch."""
    wide = _tile(200, 100, colour=(255, 0, 0))
    tall = _tile(100, 200, colour=(0, 255, 0))
    img = build_montage([wide, tall], width=800)
    assert img is not None
    assert img.size[0] == 800
    colours = {c for _, c in img.getcolors(maxcolors=1 << 20)}
    # Both pictures made it on, and neither filled its whole cell (a squashed
    # tile would have left no black letterbox at all).
    assert (255, 0, 0) in colours and (0, 255, 0) in colours
    assert (0, 0, 0) in colours


def test_the_grid_grows_with_the_tile_count_not_the_width():
    """Six pictures make a taller montage than two of the same shape, at the
    same width — the wall grows downwards, so it stays postable."""
    two = build_montage([_tile(160, 120) for _ in range(2)], width=900)
    six = build_montage([_tile(160, 120) for _ in range(6)], width=900)
    assert two is not None and six is not None
    assert two.size[0] == six.size[0] == 900
    assert six.size[1] > two.size[1]


def test_extra_tiles_past_the_cap_are_dropped_not_shrunk():
    """The best pictures are first, so the cap simply keeps the leading ones —
    the wall stays enjoyable at social sizes instead of becoming a contact sheet
    of thumbnails. Capping at N must give exactly the wall the first N make."""
    tiles = [_tile(160, 120, colour=(i * 20, 30, 40)) for i in range(12)]
    capped = build_montage(tiles, max_tiles=4, width=800)
    first_four = build_montage(tiles[:4], width=800)
    assert capped is not None and first_four is not None
    assert capped.size == first_four.size
    assert capped.tobytes() == first_four.tobytes()
    # …and the cap can't be talked below the "one picture is not a wall" floor.
    assert build_montage(tiles, max_tiles=1, width=800) is not None


def test_a_title_adds_a_strip_and_no_title_leaves_none():
    with_title = build_montage([_tile(160, 120), _tile(160, 120)],
                               width=800, title="My deep-sky wall — 2 targets")
    without = build_montage([_tile(160, 120), _tile(160, 120)], width=800)
    assert with_title is not None and without is not None
    assert with_title.size[1] > without.size[1]


def test_captions_are_burned_onto_their_own_tiles():
    """The label is what makes the wall readable ("which one is which?"), and it
    must land on the picture, not on the background between them."""
    labelled = build_montage(
        [_tile(200, 150, caption="M 42 · 3.2 h"), _tile(200, 150, caption="M 31")],
        width=800)
    plain = build_montage([_tile(200, 150), _tile(200, 150)], width=800)
    assert labelled is not None and plain is not None
    assert labelled.size == plain.size          # labels never resize the wall
    assert labelled.tobytes() != plain.tobytes()


def test_the_title_avoids_glyphs_the_built_in_font_cannot_draw():
    """Pillow's built-in font renders an em dash as a tofu box, and this strip
    sits across the top of an image the user is about to post."""
    title = montage_title(4, 7200)
    assert "\u2014" not in title
    assert all(ord(c) < 0x2500 for c in title)


def test_a_short_last_row_is_centred_not_left_aligned():
    """Seven pictures in a 3-wide grid otherwise leave a conspicuous hole in the
    bottom-right corner, which reads as "something failed to load"."""
    tiles = [_tile(200, 150, colour=(255, 0, 0)) for _ in range(7)]
    img = build_montage(tiles, width=900)
    assert img is not None
    w, h = img.size
    bottom = img.crop((0, round(h * 0.72), w, h))
    # The lone last-row tile straddles the horizontal centre of the wall.
    assert bottom.getpixel((w // 2, bottom.size[1] // 2)) == (255, 0, 0)


def test_the_cell_shape_follows_the_pictures():
    """A library of tall pictures gets tall cells, so it isn't rendered into a
    sea of black bars — the montage takes its shape from the user's own data."""
    wide = build_montage([_tile(200, 100) for _ in range(2)], width=800)
    tall = build_montage([_tile(100, 200) for _ in range(2)], width=800)
    assert wide is not None and tall is not None
    assert tall.size[1] > wide.size[1]
