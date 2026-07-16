"""Thumbnail generation produces a valid PNG."""

import pytest

pytest.importorskip("astropy")
pytest.importorskip("PIL")

import numpy as np  # noqa: E402

from seestack.gui.thumbnail import generate_thumbnail  # noqa: E402
from seestack.render.thumbnail import _downsample_rgb  # noqa: E402
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
