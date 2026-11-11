"""An unedited canvas **wider than the Full-res PNG's cap** keeps its true size
once its border is trimmed (Scout 2026-11-11, QA rotation sweep (1)).

``render_preview_png_full_res`` used to area-average the *canvas* to the cap
and only then cut ``crop``, so a 9000 px canvas trimmed to a true 7200 px came
out 6400 px — shrunk for no reason, while every caller (the menu's size, the
full-size archive) believed it was at its true size. The load now targets the
*trimmed* width (:func:`full_res_load_width`), so the trimmed picture lands at
its true size when that fits under the cap, and at the cap when it doesn't.
These run the real renderer at a small cap so the canvas stays cheap.
"""

from __future__ import annotations

import io

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.edit.ops.geometry import crop_bounds
from seestack.render.thumbnail import full_res_load_width, render_preview_png_full_res
from seestack.stack.output import DISPLAY_SPACE_CARD

CAP = 200


def _write(path, w: int, h: int, *, display_space: bool = False) -> None:
    rng = np.random.default_rng(11)
    cube = (rng.random((3, h, w), dtype=np.float32) * 100.0) + 20.0
    hdu = fits.PrimaryHDU(data=cube)
    if display_space:
        cube /= cube.max()
        hdu = fits.PrimaryHDU(data=cube)
        hdu.header[DISPLAY_SPACE_CARD] = (True, "tone-mapped display-space image")
    hdu.writeto(path, overwrite=True)


def _size(png: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(png)) as im:
        return im.size


def _true_trim(w: int, h: int, crop) -> tuple[int, int]:
    x0, x1, y0, y1 = crop_bounds(h, w, {"x0": crop[0], "y0": crop[1],
                                        "x1": crop[2], "y1": crop[3]})
    return x1 - x0, y1 - y0


def test_a_trim_that_fits_under_the_cap_comes_out_at_its_true_size(tmp_path):
    """The Scout's repro, scaled: a canvas 1.125× the cap trimmed to 80 % of its
    width is 0.9× the cap — it fits, so it is not shrunk at all. Before the fix
    it came out at 0.8× the cap (the canvas shrunk to the cap, then trimmed)."""
    w, h = 225, 40          # 9000 × … at the real 8000 px cap
    crop = (0.1, 0.0, 0.9, 1.0)
    fp = tmp_path / "wide.fits"
    _write(fp, w, h)
    got = _size(render_preview_png_full_res(fp, max_long_edge=CAP, crop=crop))
    assert got == _true_trim(w, h, crop) == (180, 40)


def test_a_trim_still_wider_than_the_cap_comes_out_at_the_cap(tmp_path):
    """A trim that leaves more than the cap is shrunk to the cap — to it, not
    under it (before: 0.89× the cap, ``…_reduced_size.txt`` naming a file
    smaller than the cap it cites)."""
    w, h = 250, 60
    crop = (0.0, 0.0, 0.85, 1.0)  # true 212 px > CAP
    fp = tmp_path / "wider.fits"
    _write(fp, w, h)
    got = _size(render_preview_png_full_res(fp, max_long_edge=CAP, crop=crop))
    assert got[0] == CAP
    tw, th = _true_trim(w, h, crop)
    assert abs(got[1] - round(th * CAP / tw)) <= 1


def test_no_crop_and_display_space_still_load_at_the_cap(tmp_path):
    """Nothing to trim — or a finished edit, which ignores ``crop`` — keeps the
    old load (and so the old bytes): the widened load is only for a trim."""
    assert full_res_load_width(400, None, CAP) == CAP
    assert full_res_load_width(400, (0.1, 0.0, 0.9, 1.0), CAP,
                               display_space=True) == CAP
    fp = tmp_path / "edit.fits"
    _write(fp, 300, 40, display_space=True)
    plain = render_preview_png_full_res(fp, max_long_edge=CAP)
    cropped = render_preview_png_full_res(fp, max_long_edge=CAP,
                                          crop=(0.1, 0.0, 0.9, 1.0))
    assert plain == cropped and _size(plain) == (CAP, 27)


def test_the_load_never_exceeds_the_canvas_nor_twice_the_cap():
    """The memory bound: never wider than the canvas (a narrower one is read at
    native size anyway), and never more than 2× the cap however deep the trim —
    Auto's own rule refuses a rectangle that keeps under half the canvas."""
    assert full_res_load_width(225, (0.1, 0.0, 0.9, 1.0), CAP) == 225
    assert full_res_load_width(10_000, (0.1, 0.0, 0.9, 1.0), CAP) == 250
    assert full_res_load_width(10_000, (0.0, 0.0, 0.2, 1.0), CAP) == 2 * CAP
    # A canvas under the cap keeps the cap: it is read at native size anyway.
    assert full_res_load_width(150, (0.1, 0.0, 0.9, 1.0), CAP) == CAP
