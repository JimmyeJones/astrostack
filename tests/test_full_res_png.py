"""`render_preview_png_full_res` — the finished picture at native output
resolution, using the same stretch as the baked gallery/History preview.

This is the engine half of the "why is my downloaded picture low-res?" fix: the
FITS/TIFF already hold full-resolution pixels, but the only beginner-friendly
image download served the 1024 px preview PNG. This renders the *same look* at
full output resolution.
"""

from __future__ import annotations

import io

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.render.thumbnail import render_preview_png_full_res
from seestack.stack.output import DISPLAY_SPACE_CARD


def _write_linear_fits(path, rgb_chw: np.ndarray) -> None:
    fits.PrimaryHDU(data=rgb_chw.astype(np.float32)).writeto(path, overwrite=True)


def _write_display_space_fits(path, rgb_chw: np.ndarray) -> None:
    hdu = fits.PrimaryHDU(data=rgb_chw.astype(np.float32))
    hdu.header[DISPLAY_SPACE_CARD] = (True, "tone-mapped display-space image")
    hdu.writeto(path, overwrite=True)


def _png_size(png_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(png_bytes)) as im:
        return im.size  # (w, h)


def test_full_res_png_is_native_resolution_not_the_preview_cap(tmp_path):
    """A run wider than the 1024 px preview cap renders at its true native size —
    that is the whole point of the download."""
    w, h = 1600, 1200  # > the 1024 preview cap
    rng = np.random.default_rng(0)
    cube = rng.random((3, h, w), dtype=np.float32) * 100.0  # linear counts
    fp = tmp_path / "master.fits"
    _write_linear_fits(fp, cube)

    png = render_preview_png_full_res(fp)
    assert _png_size(png) == (w, h)  # native, not 1024-capped


def test_full_res_png_caps_an_enormous_mosaic_long_edge(tmp_path):
    """A giant mosaic is capped to ``max_long_edge`` so the render/response stays
    within a RAM-capped host's budget (the FITS/TIFF keep the true native pixels)."""
    w, h = 400, 200
    cube = np.ones((3, h, w), dtype=np.float32)
    fp = tmp_path / "big.fits"
    _write_linear_fits(fp, cube)

    png = render_preview_png_full_res(fp, max_long_edge=100)
    ow, oh = _png_size(png)
    assert max(ow, oh) == 100  # long edge capped
    assert ow == 100 and oh == 50  # aspect preserved


def test_display_space_fits_is_rendered_verbatim_not_autostretched(tmp_path):
    """A display-space editor export is served exactly as stored (matches its
    baked preview) — no second stretch. A mid-grey display image stays mid-grey,
    whereas a linear stack of the same values would be STF-stretched away from it."""
    w, h = 64, 48
    val = 0.4
    cube = np.full((3, h, w), val, dtype=np.float32)

    disp_fp = tmp_path / "display.fits"
    _write_display_space_fits(disp_fp, cube)
    disp_png = render_preview_png_full_res(disp_fp)
    with Image.open(io.BytesIO(disp_png)) as im:
        disp_px = np.asarray(im)
    # Verbatim: 0.4 → round(0.4*255) = 102, uniform across the frame.
    assert np.all(disp_px == round(val * 255))

    # The same pixel values as a *linear* stack are autostretched, so they do NOT
    # come out at the verbatim byte — proving the display-space branch really is a
    # distinct, no-restretch path.
    lin_fp = tmp_path / "linear.fits"
    _write_linear_fits(lin_fp, cube)
    lin_png = render_preview_png_full_res(lin_fp)
    with Image.open(io.BytesIO(lin_png)) as im:
        lin_px = np.asarray(im)
    assert lin_px.mean() != disp_px.mean()


def test_full_res_png_matches_the_baked_preview_look_at_full_size(tmp_path):
    """The full-res PNG uses the SAME stretch as ``_write_preview_png`` (STF for a
    linear stack), so downscaling it to the preview width reproduces the stored
    thumbnail — it is the same picture, just bigger."""
    from seestack.stack.output import _write_preview_png

    w, h = 1400, 1050
    rng = np.random.default_rng(7)
    cube = (rng.random((3, h, w), dtype=np.float32) * 500.0)
    fp = tmp_path / "m.fits"
    _write_linear_fits(fp, cube)

    # The baked preview (STF, capped at 1024 wide).
    prev_path = tmp_path / "m_preview.png"
    rgb_hwc = np.transpose(cube, (1, 2, 0))
    _write_preview_png(prev_path, rgb_hwc, max_width=1024)
    with Image.open(prev_path) as im:
        prev = np.asarray(im.convert("RGB"), dtype=np.float32)

    # The full-res PNG downscaled to the preview width should match closely.
    full_png = render_preview_png_full_res(fp)
    with Image.open(io.BytesIO(full_png)) as im:
        full_small = im.convert("RGB").resize(
            (prev.shape[1], prev.shape[0]), Image.BOX)
        full_small_arr = np.asarray(full_small, dtype=np.float32)

    # Both apply the identical STF; only the decimation grid differs slightly, so
    # the per-pixel byte difference is tiny.
    assert np.abs(full_small_arr - prev).mean() < 3.0
