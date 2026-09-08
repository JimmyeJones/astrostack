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


# --- memory: the same pixels, a third of the footprint ----------------------
#
# The full-res render owns every array it touches — `load_stack_rgb` hands it a
# fresh one and nothing else can see it — but it used to *copy* at every step:
# the stretch copied its input, normalised it out-of-place (two more temporaries
# live at once), and the clip and the uint8 pack each allocated another. On the
# owner's 3494×2470 mosaic the decimated array is ~104 MB, so pressing "Full-res
# PNG" (or rendering the "Full-size versions" archive, which runs every target
# through this same call) peaked at roughly four of them, possibly while a stack
# job was holding its own canvases on a RAM-capped NAS.
#
# The fix consumes instead of copying: `autostretch(copy=False)`, an in-place
# normalise, `nan_to_num(copy=False)`, `clip(out=)` and `pack_unit(copy=False)`.
# It is a bit-parity change — these two tests pin *both* halves, because a
# memory win that moved a pixel would be a bug, not a win.


def _reference_full_res_png(fp, **kw) -> bytes:
    """The same render written the old, copy-at-every-step way.

    Deliberately independent of the code under test: it calls the same public
    pieces out-of-place, so "identical bytes" means the in-place path really is
    the same arithmetic and not just self-consistent.
    """
    from seestack.render.thumbnail import (
        _apply_north_up,
        _preview_grid_asinh_stats,
        asinh_stretch,
        load_stack_rgb,
    )
    from seestack.stack.output import _autostretch_for_export, pack_unit

    max_long_edge = kw.get("max_long_edge", 8000)
    rgb, display_space = load_stack_rgb(fp, max_width=max_long_edge)
    stretch, black = kw.get("stretch"), kw.get("black")
    if display_space:
        stretched = np.nan_to_num(rgb, nan=0.0)
    elif stretch is not None and black is not None:
        stretched = asinh_stretch(
            rgb, stretch=float(stretch), black=float(black),
            stats=_preview_grid_asinh_stats(fp, rgb, rendered_max_width=max_long_edge))
    else:
        stretched = _autostretch_for_export(rgb)
    disp = np.clip(np.nan_to_num(stretched), 0.0, 1.0)
    if kw.get("north_up"):
        disp = _apply_north_up(disp, fp)
    u8 = pack_unit(disp)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def _star_master(w: int, h: int, *, seed: int = 3) -> np.ndarray:
    """A small linear master with a sky, some stars and an uncovered corner."""
    rng = np.random.default_rng(seed)
    cube = rng.normal(0.02, 0.004, size=(3, h, w)).astype(np.float32)
    for _ in range(25):
        y = int(rng.integers(5, h - 5))
        x = int(rng.integers(5, w - 5))
        cube[:, y - 2:y + 3, x - 2:x + 3] += float(rng.uniform(0.5, 6.0))
    cube[:, : h // 20, : w // 20] = np.nan  # NaN = no coverage
    return cube


def test_the_in_place_full_res_render_is_byte_identical(tmp_path):
    """Linear, display-space and Adjust-stretched masters all render to exactly
    the bytes the old copy-at-every-step path produced."""
    cube = _star_master(300, 200)

    linear = tmp_path / "linear.fits"
    _write_linear_fits(linear, cube)
    assert render_preview_png_full_res(linear) == _reference_full_res_png(linear)

    display = tmp_path / "display.fits"
    _write_display_space_fits(display, np.clip(cube * 8.0, 0.0, 1.0))
    assert render_preview_png_full_res(display) == _reference_full_res_png(display)

    # The Adjust path (History's saved stretch/black) — a different curve, and
    # the one branch that does not consume its input.
    assert (render_preview_png_full_res(linear, stretch=0.5, black=0.35)
            == _reference_full_res_png(linear, stretch=0.5, black=0.35))


def test_full_res_render_no_longer_holds_five_copies_of_the_picture(tmp_path):
    """Peak allocation drops by about a fifth — measured, not estimated.

    NumPy reports its allocations to ``tracemalloc``, so this measures the real
    thing. On this fixture the render peaked at **5.00×** the decimated array
    before the change and **3.83×** after; the threshold sits between them with
    room either side. The **ratio** is what is pinned, not an absolute: the same
    code on the owner's 3494×2470 mosaic is the same multiple of a ~104 MB array
    (≈ 520 MB → ≈ 400 MB), and at the 8000 px cap ≈ 2.9 GB → ≈ 2.2 GB.

    What is left is inherent to the stretch rather than copying: the robust
    percentile that sets the normalisation ceiling (deliberately exact — a
    strided sample would move pixels), the zeroed output array, and the
    per-channel covered-pixel temporaries.
    """
    import tracemalloc

    w, h = 900, 700
    cube = _star_master(w, h, seed=5)
    fp = tmp_path / "master.fits"
    _write_linear_fits(fp, cube)
    one_copy = w * h * 3 * 4  # float32 RGB

    render_preview_png_full_res(fp)  # warm the imports/caches out of the count
    tracemalloc.start()
    try:
        render_preview_png_full_res(fp)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 4.4 * one_copy, f"peak {peak / one_copy:.2f}× the picture"
