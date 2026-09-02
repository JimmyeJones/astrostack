"""The full-res PNG download of an **Adjusted** run must be rendered through the
same tone curve as the 1024 px preview the user actually tuned.

Regression (Scout QA audit 2026-09-02): both paths call :func:`asinh_stretch`, but
that function derives its *entire* curve from the statistics of whatever array it
is handed — ``lo = nanmin``, ``hi`` = the 99.5th percentile, and each channel's
robust ``(median, sigma)``, which sets the black point. The saved preview is
stretched on a 1024 px area-averaged array; the download is stretched at near
native size. Area-averaging lifts the min, lowers the percentile peak and shrinks
σ, so the *same* slider values produced a different normalisation **and** a
different black point at the two resolutions: the downloaded (framed, printed,
shared) picture was rendered by a curve the user never approved, and the effect
grows with canvas width — worst on exactly the wide mosaics the app is built for.

Two things are worth knowing about how this is tested, because they shaped it:

* The right assertion is about the **curve**, not about pixel-for-pixel equality.
  The download genuinely holds different data (native pixels, not area-averaged
  ones), and asinh is steep near the black point, so a 0.8 % difference in the
  arrays' own medians is several 8-bit levels of output no matter what curve is
  used. Resampling the export back onto the preview grid to compare mixes that
  irreducible difference — and the noise/nonlinearity commutation error on top of
  it — into any per-pixel metric, which is why one isn't used here.
* The **sky level** is the honest end-to-end figure: a median commutes exactly
  with a monotonic tone curve, so comparing the two renders' sky medians isolates
  the curve difference from the noise. It halves under the fix (measured below).
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from seestack.render.thumbnail import (
    PREVIEW_MAX_WIDTH,
    asinh_stretch,
    load_stack_rgb,
    measure_asinh_stats,
    render_preview_png_full_res,
    render_stack_png,
)

#: Slider pairs whose black point leaves the sky *visible* (an unclipped median),
#: so the sky-level comparison below has something to measure. A high ``black``
#: crushes the sky to 0 in both renders, which agrees trivially.
_SLIDERS = [(0.3, 0.2), (0.4, 0.15), (0.5, 0.1)]


def _linear_master(tmp_path, *, w: int = 1600, h: int = 1000, name: str = "master_wide"):
    """A wide synthetic linear master: a faint noisy sky, a soft nebula and a few
    hundred barely-sampled stars.

    The pixel noise and the single-pixel star peaks are the point — they are what
    makes ``asinh_stretch``'s statistics resolution-dependent in the first place
    (a perfectly smooth scene measures almost identically at both grids and would
    make this whole file vacuous; that was checked).
    """
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nebula = 0.010 * np.exp(-(((xx - w * 0.45) / (w * 0.22)) ** 2
                              + ((yy - h * 0.55) / (h * 0.25)) ** 2))
    cube = np.empty((3, h, w), dtype=np.float32)
    for c, gain in enumerate((1.0, 0.92, 0.78)):
        sky = 0.020 + rng.normal(0.0, 0.0016, size=(h, w)).astype(np.float32)
        cube[c] = (sky + nebula * gain).astype(np.float32)
    for _ in range(400):
        sy = int(rng.integers(3, h - 3))
        sx = int(rng.integers(3, w - 3))
        peak = float(rng.random() ** 6 * 0.9 + 0.02)
        cube[:, sy - 1:sy + 2, sx - 1:sx + 2] += peak * 0.35
        cube[:, sy, sx] += peak
    path = tmp_path / f"{name}.fits"
    fits.PrimaryHDU(data=cube).writeto(path, overwrite=True)
    return path, w, h


def _png_rgb(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as im:
        return np.asarray(im.convert("RGB"))


def _to_u8(stretched: np.ndarray) -> np.ndarray:
    return (np.clip(np.nan_to_num(stretched), 0.0, 1.0) * 255).astype(np.uint8)


def _sky_levels(img: np.ndarray) -> list[float]:
    """Each channel's median — the sky, on a sky-dominated frame. Exactly
    commutes with a monotonic tone curve, so it compares *curves*, not noise."""
    return [float(np.median(img[..., c])) for c in range(3)]


@pytest.mark.parametrize("stretch,black", _SLIDERS)
def test_full_res_download_is_rendered_with_the_preview_grid_curve(
    tmp_path, stretch, black,
):
    """The download is the native pixels through the **preview's** curve — and
    that is materially not what stretching them on their own statistics gives.

    Fails before the fix: the download was ``asinh_stretch(native)``, i.e. the
    "unpinned" render this asserts it is *different* from.
    """
    path, w, h = _linear_master(tmp_path)
    native, _ds = load_stack_rgb(str(path), max_width=8000)
    preview_rgb, _ds2 = load_stack_rgb(str(path), max_width=PREVIEW_MAX_WIDTH)
    assert native.shape[1] == w > PREVIEW_MAX_WIDTH == preview_rgb.shape[1]

    got = _png_rgb(render_preview_png_full_res(
        str(path), max_long_edge=8000, stretch=stretch, black=black))
    assert got.shape[:2] == (h, w)                  # still native resolution

    pinned = _to_u8(asinh_stretch(
        native, stretch=stretch, black=black,
        stats=measure_asinh_stats(preview_rgb)))
    assert np.array_equal(got, pinned)

    unpinned = _to_u8(asinh_stretch(native, stretch=stretch, black=black))
    moved = np.abs(got.astype(int) - unpinned.astype(int))
    assert moved.mean() > 2.0, (
        f"the two curves barely differ (mean {moved.mean():.2f}/255) — this scene "
        "no longer exercises the bug")


@pytest.mark.parametrize("stretch,black", _SLIDERS)
def test_full_res_download_sky_matches_the_preview_far_more_closely(
    tmp_path, stretch, black,
):
    """End-to-end and user-visible: the downloaded picture's sky sits at the
    brightness the user tuned on the preview, not several levels above it.

    Measured on this scene, the per-channel sky level of the download was **11–13
    of 255 brighter** than the preview it was tuned against; pinning the curve
    roughly halves that to 5–7, and the remainder is the two arrays' own (real)
    difference rather than a curve the user never chose.
    """
    path, _w, _h = _linear_master(tmp_path)
    native, _ds = load_stack_rgb(str(path), max_width=8000)

    preview = _png_rgb(render_stack_png(
        str(path), stretch=stretch, black=black, max_width=PREVIEW_MAX_WIDTH))
    want = _sky_levels(preview)
    assert min(want) > 20, "sliders must leave the sky unclipped for this to mean anything"

    got = _sky_levels(_png_rgb(render_preview_png_full_res(
        str(path), max_long_edge=8000, stretch=stretch, black=black)))
    before = _sky_levels(_to_u8(asinh_stretch(native, stretch=stretch, black=black)))

    for c in range(3):
        old_err = abs(before[c] - want[c])
        new_err = abs(got[c] - want[c])
        assert old_err >= 8.0, f"ch{c}: bug not reproduced (old error {old_err})"
        assert new_err <= 0.65 * old_err, f"ch{c}: {new_err} vs {old_err}"


def test_the_lightbox_render_uses_the_same_curve_as_the_sliders_preview(tmp_path):
    """The same defect at its second site: History's lightbox re-renders the run
    at ``size=2048`` while the Adjust sliders' own preview renders at the 1024 px
    default, so clicking to enlarge what you just tuned used to change the tone
    curve under you. One pair of sliders must mean one picture at every size.
    """
    path, _w, _h = _linear_master(tmp_path)
    stretch, black = 0.4, 0.15

    preview_rgb, _ = load_stack_rgb(str(path), max_width=PREVIEW_MAX_WIDTH)
    anchor = measure_asinh_stats(preview_rgb)
    big_rgb, _ = load_stack_rgb(str(path), max_width=2048)

    got = _png_rgb(render_stack_png(
        str(path), stretch=stretch, black=black, max_width=2048))
    assert np.array_equal(got, _to_u8(asinh_stretch(
        big_rgb, stretch=stretch, black=black, stats=anchor)))

    # …and it is not what measuring the 2048 px array for itself would have given.
    drifted = _to_u8(asinh_stretch(big_rgb, stretch=stretch, black=black))
    assert np.abs(got.astype(int) - drifted.astype(int)).mean() > 2.0


def test_the_stored_preview_render_is_bit_for_bit_unchanged(tmp_path):
    """The ``max_width=PREVIEW_MAX_WIDTH`` render is what bakes the *stored*
    preview PNG. It is the anchor, so it must measure itself exactly as it always
    has — no re-baking of an existing install's pictures, and no extra FITS read.
    """
    path, _w, _h = _linear_master(tmp_path)
    rgb, _ = load_stack_rgb(str(path), max_width=PREVIEW_MAX_WIDTH)
    got = _png_rgb(render_stack_png(
        str(path), stretch=0.55, black=0.3, max_width=PREVIEW_MAX_WIDTH))
    assert np.array_equal(got, _to_u8(asinh_stretch(rgb, stretch=0.55, black=0.3)))


def test_a_display_space_export_is_never_stretched_or_anchored(tmp_path):
    """An editor export is already tone-mapped: it is written verbatim at every
    size, and the anchoring must not creep onto that path."""
    from seestack.stack.output import DISPLAY_SPACE_CARD

    rng = np.random.default_rng(4)
    cube = rng.random((3, 700, 1400), dtype=np.float32)
    hdu = fits.PrimaryHDU(data=cube)
    hdu.header[DISPLAY_SPACE_CARD] = True
    path = tmp_path / "edited.fits"
    hdu.writeto(path)

    rgb, display_space = load_stack_rgb(str(path), max_width=8000)
    assert display_space
    assert np.array_equal(
        _png_rgb(render_stack_png(str(path), stretch=0.9, black=0.9, max_width=8000)),
        _to_u8(rgb))
    assert np.array_equal(
        _png_rgb(render_preview_png_full_res(
            str(path), max_long_edge=8000, stretch=0.9, black=0.9)),
        _to_u8(rgb))


def test_preview_grid_stats_really_do_differ_from_native_stats(tmp_path):
    """The driver, isolated: the same picture measured at 1024 px and at native
    size yields a different normalisation *and* a different per-channel black
    point. (If this ever stops holding, the tests above have gone vacuous.)"""
    path, _w, _h = _linear_master(tmp_path)
    small, _ = load_stack_rgb(str(path), max_width=PREVIEW_MAX_WIDTH)
    native, _ = load_stack_rgb(str(path), max_width=8000)

    a = measure_asinh_stats(small)
    b = measure_asinh_stats(native)
    assert a is not None and b is not None
    assert a.lo > b.lo                    # area-averaging lifts the floor
    for (med_a, sig_a), (med_b, sig_b) in zip(a.channels, b.channels, strict=True):
        assert sig_a < sig_b * 0.95       # …and shrinks the noise σ
        # …which moves the black point `med + (black*6 - 2)*sigma` for any slider.
        shadows_a = med_a + (0.4 * 6.0 - 2.0) * sig_a
        shadows_b = med_b + (0.4 * 6.0 - 2.0) * sig_b
        assert abs(shadows_a - shadows_b) > 0.01


def test_measured_stats_reproduce_the_unpinned_stretch_byte_for_byte(tmp_path):
    """``asinh_stretch(x, stats=measure_asinh_stats(x))`` is ``asinh_stretch(x)``.

    This is what stops the two measurement sites drifting apart, and it is why
    every existing caller (none of which passes ``stats``) is unaffected.
    """
    path, _w, _h = _linear_master(tmp_path, w=300, h=200, name="small")
    rgb, _ = load_stack_rgb(str(path), max_width=8000)
    rgb[5:20, 5:20, :] = np.nan           # an uncovered patch, as a mosaic has

    for kwargs in ({"stretch": 0.6, "black": 0.4},
                   {"highlight_protect": 0.8},
                   {"protect_highlights": False},
                   {}):
        assert np.array_equal(
            asinh_stretch(rgb, **kwargs),
            asinh_stretch(rgb, stats=measure_asinh_stats(rgb), **kwargs)), kwargs


def test_a_canvas_no_wider_than_the_preview_cap_is_untouched(tmp_path):
    """A stack narrower than 1024 px already stretched on the preview's own grid,
    so its download must be byte-for-byte what it always was — the fix must not
    move the ordinary small-target case at all, and must not re-read the FITS."""
    path, w, _h = _linear_master(tmp_path, w=800, h=600, name="narrow")
    rgb, _ = load_stack_rgb(str(path), max_width=8000)
    assert rgb.shape[1] == w <= PREVIEW_MAX_WIDTH

    got = _png_rgb(render_preview_png_full_res(
        str(path), max_long_edge=8000, stretch=0.7, black=0.5))
    assert np.array_equal(got, _to_u8(asinh_stretch(rgb, stretch=0.7, black=0.5)))


def test_an_unadjusted_run_still_takes_the_stf_path(tmp_path):
    """No saved Adjust → the STF export, byte-for-byte as before. The STF path
    never had this bug (`_write_preview_png` stretches full-res then downsizes),
    and the fix must not touch it."""
    from seestack.stack.output import _autostretch_for_export

    path, _w, _h = _linear_master(tmp_path, name="unadjusted")
    rgb, _ = load_stack_rgb(str(path), max_width=8000)
    got = _png_rgb(render_preview_png_full_res(str(path), max_long_edge=8000))
    assert np.array_equal(got, _to_u8(_autostretch_for_export(rgb)))


def test_a_degenerate_master_still_renders_black_rather_than_failing(tmp_path):
    """A flat master has no curve to measure; the stretch must fall back to its own
    (black) answer rather than the download erroring."""
    path = tmp_path / "flat.fits"
    fits.PrimaryHDU(data=np.full((3, 400, 1600), 0.5, dtype=np.float32)).writeto(path)
    assert measure_asinh_stats(load_stack_rgb(str(path), max_width=8000)[0]) is None
    got = _png_rgb(render_preview_png_full_res(
        str(path), max_long_edge=8000, stretch=0.5, black=0.35))
    assert got.shape == (400, 1600, 3)
    assert not got.any()                  # degenerate → black, exactly as before
