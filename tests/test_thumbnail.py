"""Thumbnail generation produces a valid PNG."""

import pytest

pytest.importorskip("astropy")
pytest.importorskip("PIL")

import numpy as np  # noqa: E402

from seestack.gui.thumbnail import generate_thumbnail  # noqa: E402
from seestack.render.thumbnail import (  # noqa: E402
    _downsample_rgb,
    overlay_rgba_png,
    stack_coverage_mask,
)
from tests.synth import write_seestar_fits  # noqa: E402


def test_downsample_rgb_survives_nan_input():
    """A NaN=no-coverage pixel must not collapse the whole frame to black.

    Regression: `_downsample_rgb` used plain `rgb.min()`/`.max()`, so a single
    NaN made both NaN, the `hi <= lo` guard was False (NaN comparisons), and the
    frame downsampled to all-black. It now reduces NaN-aware like its siblings.
    """
    rgb = np.zeros((16, 16, 3), dtype=np.float32)
    rgb[:8] = np.linspace(0.1, 0.9, 8)[:, None, None]  # a finite region with range
    rgb[8:] = np.nan                                    # no-coverage region

    out = _downsample_rgb(rgb, 8, 8)

    assert np.isfinite(out).all()
    # The bright finite region must survive (before the fix everything was 0).
    assert out.max() > 0.5


def test_downsample_rgb_preserves_colour_ratios():
    """The float-mode resize must keep per-channel colour balance exactly.

    Box downsampling is a per-channel linear average, so a flat coloured input
    must come back with its R:G:B ratios intact (no shared normalisation needed
    now that there is no uint8 round-trip)."""
    rgb = np.zeros((100, 120, 3), dtype=np.float32)
    rgb[..., 0] = 1000.0
    rgb[..., 1] = 2000.0
    rgb[..., 2] = 4000.0

    out = _downsample_rgb(rgb, 50, 60)

    assert out.shape == (50, 60, 3)
    np.testing.assert_allclose(out[..., 0], 1000.0, rtol=0, atol=1e-3)
    np.testing.assert_allclose(out[..., 1], 2000.0, rtol=0, atol=1e-3)
    np.testing.assert_allclose(out[..., 2], 4000.0, rtol=0, atol=1e-3)


def test_downsample_rgb_keeps_faint_sky_texture_below_a_saturated_ceiling():
    """A faint noisy sky must survive downsampling even when a saturated star
    sets the global max — the bug that flattened the "one frame vs your stack"
    reveal.

    Before the fix, ``_downsample_rgb`` normalised to ``[0, 1]`` against the
    saturated ceiling (~65535) and quantised to uint8, so the ~80-ADU sky noise
    (a few thousand ADU up) collapsed into ~1 uint8 level. The downstream export
    stretch then had almost no tonal variation left to reveal — the displayed
    sky showed ~2 grey levels where the true single-sub noise spans dozens. The
    symptom is measured through the real display pipeline (downsample → export
    STF), exactly what ``render_sub_preview`` shows.
    """
    from seestack.stack.output import _autostretch_for_export

    rng = np.random.default_rng(3)
    h, w = 400, 600
    rgb = (3000.0 + rng.normal(0.0, 80.0, size=(h, w, 3))).astype(np.float32)
    # A saturated star in the right half sets the global max; the left half is
    # star-free sky whose noise texture must survive to the displayed image.
    rgb[100:110, 460:470, :] = 65535.0

    out = _downsample_rgb(rgb, h // 2, w // 2)
    displayed = np.clip(np.nan_to_num(_autostretch_for_export(out)), 0.0, 1.0)
    displayed_u8 = (displayed * 255).astype(np.uint8)

    # Star-free displayed sky patch (left region, clear of the star).
    sky_levels = np.unique(displayed_u8[5:80, 5:120, 0])
    # Fixed keeps dozens of tonal levels (real single-sub noise); the buggy uint8
    # path crushed the sky to ~2 levels. A generous floor separates them.
    assert sky_levels.size > 20
    # And the saturated star kept its true peak (not clipped to a percentile),
    # so the downstream percentile-robust stretch still sees it.
    assert float(out.max()) > 60000.0


def test_generate_thumbnail(tmp_path):
    fits_path = write_seestar_fits(tmp_path / "in.fit")
    out = tmp_path / "thumb.png"
    result = generate_thumbnail(fits_path, out)
    assert result.exists()
    # Should be a small PNG, definitely under 1 MB.
    assert 0 < result.stat().st_size < 1_000_000

    # Pillow should be able to open it.
    from PIL import Image

    with Image.open(result) as im:
        assert im.format == "PNG"
        assert max(im.size) <= 256


def test_render_sub_preview_debayers_and_stretches_to_png(tmp_path):
    """A single raw sub renders to a real, non-trivial PNG at the requested width.

    Powers the "one frame vs your stack" reveal: the sub is debayered and put
    through the same export autostretch as the stack preview so the comparison is
    a fair before/after.
    """
    from io import BytesIO

    from PIL import Image

    from seestack.render.thumbnail import render_sub_preview

    fits_path = write_seestar_fits(tmp_path / "in.fit", width=480, height=320,
                                   n_stars=40, seed=7)
    png = render_sub_preview(fits_path, bayer_pattern="RGGB", max_width=240)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(BytesIO(png)) as im:
        assert im.format == "PNG"
        assert im.mode == "RGB"
        # Decimated to max_width and not a black frame (the stretch revealed data).
        assert im.width == 240
        assert np.asarray(im).max() > 0


def test_render_sub_preview_matches_the_export_preview_stretch(tmp_path):
    """The sub is stretched with the *same* export STF as the stored stack preview,
    so the two halves of the reveal differ only in noise/detail, not brightness."""
    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw
    from seestack.render.thumbnail import _downsample_rgb, render_sub_preview
    from seestack.stack.output import _autostretch_for_export

    fits_path = write_seestar_fits(tmp_path / "in.fit", width=480, height=320,
                                   n_stars=40, seed=7)
    png = render_sub_preview(fits_path, bayer_pattern="RGGB", max_width=240)

    # Reproduce the expected pixels independently through the same pipeline.
    rgb, _ = load_seestar_raw(fits_path, debayer=False, out_dtype=np.float32)
    rgb = bilinear_debayer(rgb, pattern="RGGB")
    h, w = rgb.shape[:2]
    rgb = _downsample_rgb(rgb, max(1, round(h * (240 / w))), 240)
    expected = (np.clip(np.nan_to_num(_autostretch_for_export(rgb)), 0, 1) * 255).astype(
        np.uint8)

    from io import BytesIO

    from PIL import Image
    got = np.asarray(Image.open(BytesIO(png)))
    assert got.shape == expected.shape
    assert np.array_equal(got, expected)


def test_stack_coverage_mask_marks_nan_uncovered(tmp_path):
    """The coverage mask is True on covered pixels and False on NaN (mosaic gaps)."""
    from astropy.io import fits

    h = w = 16
    cube = np.ones((3, h, w), dtype=np.float32)
    cube[:, :, w // 2:] = np.nan            # right half uncovered
    fp = tmp_path / "m.fits"
    fits.PrimaryHDU(data=cube).writeto(fp)

    mask = stack_coverage_mask(fp)
    assert mask.shape == (h, w)
    assert mask[:, : w // 2].all()          # left half covered
    assert not mask[:, w // 2:].any()       # right half uncovered

    # A pixel finite in *any* channel counts as covered (per-channel κ-σ can drop
    # one channel at a pixel without meaning "no data there").
    cube2 = np.full((3, 4, 4), np.nan, dtype=np.float32)
    cube2[0, 1, 1] = 0.5
    fp2 = tmp_path / "m2.fits"
    fits.PrimaryHDU(data=cube2).writeto(fp2)
    assert stack_coverage_mask(fp2)[1, 1]
    assert not stack_coverage_mask(fp2)[0, 0]


def test_overlay_rgba_png_makes_uncovered_transparent():
    """overlay_rgba_png keeps the preview RGB verbatim and punches alpha=0 on
    uncovered pixels (so a mosaic shows its footprint, not a black box)."""
    from io import BytesIO

    from PIL import Image

    # A tiny 4×4 opaque "preview": left half red, right half black.
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[:, :2] = (200, 30, 30)
    buf = BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buf, format="PNG")
    preview_png = buf.getvalue()

    # Coverage: only the left half is real data.
    mask = np.zeros((4, 4), dtype=bool)
    mask[:, :2] = True

    out = overlay_rgba_png(preview_png, mask)
    im = Image.open(BytesIO(out))
    assert im.mode == "RGBA"
    arr = np.asarray(im)
    assert arr.shape == (4, 4, 4)
    # RGB preserved on the covered half; alpha opaque there, transparent elsewhere.
    assert (arr[:, :2, :3] == (200, 30, 30)).all()
    assert (arr[:, :2, 3] == 255).all()
    assert (arr[:, 2:, 3] == 0).all()


def test_overlay_rgba_png_resizes_mask_to_preview_grid():
    """A full-res coverage mask is resized (nearest) to the preview's dimensions,
    so a decimated preview and a full-size FITS mask still line up."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.fromarray(np.full((8, 8, 3), 120, np.uint8), mode="RGB").save(buf, format="PNG")
    preview_png = buf.getvalue()          # 8×8 preview

    mask = np.ones((16, 16), dtype=bool)  # 16×16 full-res mask, bottom uncovered
    mask[8:, :] = False

    out = Image.open(BytesIO(overlay_rgba_png(preview_png, mask)))
    assert out.size == (8, 8)             # matches the preview, not the mask
    alpha = np.asarray(out)[..., 3]
    assert (alpha[:4, :] == 255).all()    # top (covered) opaque
    assert (alpha[4:, :] == 0).all()      # bottom (uncovered) transparent


def test_overlay_rgba_png_all_covered_is_fully_opaque():
    """A fully-covered stack (no NaN) is unchanged — every pixel opaque."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.fromarray(np.full((5, 5, 3), 80, np.uint8), mode="RGB").save(buf, format="PNG")
    out = Image.open(BytesIO(overlay_rgba_png(buf.getvalue(), np.ones((5, 5), bool))))
    assert (np.asarray(out)[..., 3] == 255).all()
