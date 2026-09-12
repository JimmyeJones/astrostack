"""\"My Messier grid\" — the life list composed into one shareable poster.

Pure and offline (Pillow only), so every case here is a real render whose pixels
are read back rather than a shape assertion.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from seestack.lifelistcard import (
    MAX_COLUMNS,
    GridCell,
    build_life_list_grid,
    grid_columns,
    grid_subtitle,
    grid_title,
)


def _picture(colour: tuple[int, int, int], size: tuple[int, int] = (200, 150)):
    """A flat, unmistakable stand-in for one of the owner's previews."""
    return Image.new("RGB", size, colour)


def _messier_cells(captured: set[int], *, picture: bool = True) -> list[GridCell]:
    """All 110 squares, with the given ones captured."""
    return [
        GridCell(
            label=f"M{n}",
            captured=(n in captured),
            image=(_picture((0, 180, 0)) if (n in captured and picture) else None),
        )
        for n in range(1, 111)
    ]


def _cell_geometry(width: int, cols: int) -> tuple[int, int, int]:
    """``(pad, gap, cell_px)`` — the same arithmetic the builder does, so a test
    can look at a named square rather than eyeballing a coordinate."""
    gap = max(2, round(width * 0.004))
    pad = max(gap, round(width * 0.012))
    return pad, gap, max(1, (width - pad * 2 - gap * (cols - 1)) // cols)


def _square(img, index: int, *, width: int, cols: int, head_h: int):
    """Crop the tile at ``index`` out of a finished grid."""
    pad, gap, cell = _cell_geometry(width, cols)
    row, col = divmod(index, cols)
    x = pad + col * (cell + gap)
    y = head_h + pad + row * (cell + gap)
    return img.crop((x, y, x + cell, y + cell))


def test_the_classic_list_lands_on_a_tidy_eleven_by_ten():
    """110 is the number a beginner is counting, so it must not come out ragged."""
    assert grid_columns(110) == 11


def test_a_bigger_catalog_grows_downward_rather_than_shrinking_every_tile():
    # The bundled catalog is ~157 objects with the popular NGC/IC included; past
    # eleven columns a galaxy is unrecognisable at the poster width.
    assert grid_columns(157) == MAX_COLUMNS
    assert grid_columns(0) == 0
    assert grid_columns(4) == 2


def test_the_title_says_how_far_along_you_are():
    assert grid_title(42, 110) == "My Messier list · 42 of 110 captured"
    # An em dash renders as a tofu box in Pillow's built-in font, which is why
    # every drawn string in this app uses the middle dot.
    assert "—" not in grid_title(42, 110)


def test_the_subtitle_changes_with_how_far_along_you_are():
    assert grid_subtitle(0, 110) == "All still to shoot."
    assert grid_subtitle(42, 110) == "The dim squares are the 68 still to shoot."
    assert grid_subtitle(110, 110) == "The whole list: every one of them."
    assert grid_subtitle(0, 0) == ""


def test_a_list_with_nothing_captured_is_not_a_poster():
    """A grid of grey squares is a picture of Messier's catalogue, not of the
    owner's sky — the caller renders nothing and the endpoint 404s."""
    assert build_life_list_grid(_messier_cells(set()), title="x") is None
    assert build_life_list_grid([], title="x") is None


def test_one_capture_is_enough_to_share():
    grid = build_life_list_grid(_messier_cells({31}), title=grid_title(1, 110))
    assert grid is not None
    assert grid.size[0] == 1320


def test_every_object_is_drawn_captured_or_not():
    """The empty squares are the point — a life list that showed only what you
    have would just be the gallery."""
    width = 1320
    grid = build_life_list_grid(_messier_cells({31}), width=width)
    pad, gap, cell = _cell_geometry(width, 11)
    # No title strip was asked for, so the grid is exactly ten rows of squares.
    assert grid.size == (width, pad * 2 + 10 * cell + 9 * gap)


def test_the_squares_stay_in_catalog_order_so_the_counting_works():
    """M1 is top-left and M110 is bottom-right: a beginner reads the grid as
    M1, M2, M3…, so re-ordering by "captured first" would break it."""
    width = 1320
    grid = build_life_list_grid(
        [GridCell(label=f"M{n}", captured=n in (1, 110),
                  image=_picture((255, 0, 0) if n == 1 else (0, 0, 255)))
         for n in range(1, 111)],
        width=width,
    )
    first = np.asarray(_square(grid, 0, width=width, cols=11, head_h=0)).reshape(-1, 3)
    last = np.asarray(_square(grid, 109, width=width, cols=11, head_h=0)).reshape(-1, 3)
    # The centre of each square is the owner's picture, unlabelled (the id chip
    # sits in the bottom-left corner).
    assert first[first.shape[0] // 2].tolist() == [255, 0, 0]
    assert last[last.shape[0] // 2].tolist() == [0, 0, 255]


def test_a_captured_square_shows_the_picture_and_a_to_shoot_square_does_not():
    width = 1320
    grid = build_life_list_grid(_messier_cells({1}), width=width)
    got = np.asarray(_square(grid, 0, width=width, cols=11, head_h=0))
    todo = np.asarray(_square(grid, 1, width=width, cols=11, head_h=0))
    # The captured square is the owner's (green) picture edge to edge; the next
    # one is the app's dim to-shoot tile with its id in it and no picture.
    assert got[got.shape[0] // 2, got.shape[1] // 2].tolist() == [0, 180, 0]
    assert todo[2, 2].tolist() == [26, 29, 40]
    assert not (todo == np.array([0, 180, 0])).all(axis=-1).any()


def test_a_capture_with_no_picture_yet_still_reads_as_captured():
    """Captured but not stacked is a real state — the tile lights up, it just
    has no picture in it — and it must not look like a square still to shoot."""
    width = 1320
    grid = build_life_list_grid(
        _messier_cells({1}, picture=False) , width=width)
    lit = np.asarray(_square(grid, 0, width=width, cols=11, head_h=0))
    todo = np.asarray(_square(grid, 1, width=width, cols=11, head_h=0))
    assert lit.mean() != pytest.approx(todo.mean(), abs=1.0)


def test_the_id_is_burned_onto_a_captured_square_too():
    """Both halves of the grid must label at the same weight, or the empty half
    shouts over the half the owner is proud of."""
    width = 1320
    grid = build_life_list_grid(_messier_cells({1}), width=width)
    got = np.asarray(_square(grid, 0, width=width, cols=11, head_h=0))
    # Bottom-left corner: the dark chip and its white text over the flat green.
    corner = got[got.shape[0] // 2:, : got.shape[1] // 2]
    assert corner.min() < 40      # the chip
    assert corner.max() > 200     # the text


def test_a_picture_that_cannot_be_decoded_falls_back_rather_than_sinking_the_grid():
    class _Broken:
        def convert(self, _mode):  # noqa: ANN001, ANN202
            raise OSError("truncated preview")

    width = 1320
    cells = _messier_cells({1, 2})
    cells[0] = GridCell(label="M1", captured=True, image=_Broken())
    grid = build_life_list_grid(cells, width=width)
    assert grid is not None
    broken = np.asarray(_square(grid, 0, width=width, cols=11, head_h=0))
    good = np.asarray(_square(grid, 1, width=width, cols=11, head_h=0))
    # The unreadable one falls back to the lit "captured, no picture" placeholder;
    # its neighbour still shows its picture, so one bad file costs one square and
    # not the poster.
    assert broken[2, 2].tolist() == [17, 48, 47]
    assert good[good.shape[0] // 2, good.shape[1] // 2].tolist() == [0, 180, 0]


def test_the_title_strip_only_takes_room_when_there_is_a_title():
    plain = build_life_list_grid(_messier_cells({1}))
    titled = build_life_list_grid(_messier_cells({1}), title=grid_title(1, 110))
    both = build_life_list_grid(
        _messier_cells({1}), title=grid_title(1, 110), subtitle=grid_subtitle(1, 110))
    assert plain.size[1] < titled.size[1] < both.size[1]
