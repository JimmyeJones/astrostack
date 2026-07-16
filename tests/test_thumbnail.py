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


def test_downsample_rgb_finite_input_is_unchanged():
    """The NaN guard must be byte-for-byte transparent for ordinary inputs."""
    rng = np.random.default_rng(0)
    rgb = rng.uniform(0.0, 1.0, size=(12, 20, 3)).astype(np.float32)

    from PIL import Image

    lo, hi = float(rgb.min()), float(rgb.max())
    u8 = ((rgb - lo) / (hi - lo) * 255).astype(np.uint8)
    ref = np.asarray(
        Image.fromarray(u8, mode="RGB").resize((10, 6), Image.BOX), dtype=np.float32
    ) / 255.0
    ref = ref * (hi - lo) + lo

    np.testing.assert_array_equal(_downsample_rgb(rgb, 6, 10), ref)


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
