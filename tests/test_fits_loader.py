"""FITS loading and bilinear debayer."""

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.fits_loader import (  # noqa: E402
    bilinear_debayer,
    load_header,
    load_seestar_raw,
)
from tests.synth import write_seestar_fits  # noqa: E402


def test_load_header(tmp_path):
    p = write_seestar_fits(tmp_path / "x.fit")
    h = load_header(p)
    assert h.width_px == 480
    assert h.height_px == 320
    assert h.bayer_pattern == "RGGB"
    assert h.exposure_s == 10.0
    assert h.timestamp_utc and h.timestamp_utc.startswith("2024-09-12")


def test_load_raw_no_debayer(tmp_path):
    p = write_seestar_fits(tmp_path / "x.fit")
    img, h = load_seestar_raw(p, debayer=False)
    assert img.ndim == 2
    assert img.shape == (320, 480)
    assert img.dtype == np.float32


def test_load_raw_debayer(tmp_path):
    p = write_seestar_fits(tmp_path / "x.fit")
    img, h = load_seestar_raw(p, debayer=True)
    assert img.ndim == 3
    assert img.shape == (320, 480, 3)


def test_bilinear_debayer_constant_image():
    """A constant mosaic must debayer to that exact constant in every channel —
    borders included. A missing-sample interpolation that reached off the frame
    used to average a real edge sample against the sparse plane's zeros, darkening
    the outermost ring (~50% on edges, ~75% at the corners); the drizzle stack path
    feeds the full frame (no border inset), so that seam reached the final image."""
    for pattern in ("RGGB", "BGGR", "GRBG", "GBRG"):
        mosaic = np.full((40, 60), 1000.0, dtype=np.float32)
        rgb = bilinear_debayer(mosaic, pattern=pattern)
        assert rgb.shape == (40, 60, 3)
        # Regression: no darkened border. Every pixel of every channel is exactly
        # the input constant (the interior already was; this now holds on the ring).
        assert np.allclose(rgb, 1000.0), (
            pattern, float(rgb.min()), float(rgb.max()))


def test_bilinear_debayer_border_not_darkened():
    """The outermost ring of a bright-but-noisy field must not be systematically
    darker than the interior (the sparse-plane zero-averaging border artefact)."""
    rng = np.random.default_rng(1)
    mosaic = rng.uniform(800.0, 1200.0, size=(64, 96)).astype(np.float32)
    rgb = bilinear_debayer(mosaic, pattern="RGGB")
    interior_mean = float(np.mean(rgb[3:-3, 3:-3, :]))
    # Each border strip's mean tracks the interior mean (no ~2-4× dilution).
    for strip in (rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]):
        assert abs(float(np.mean(strip)) - interior_mean) < 60.0, float(np.mean(strip))


def test_bilinear_debayer_unsupported_pattern():
    with pytest.raises(ValueError):
        bilinear_debayer(np.zeros((10, 10), dtype=np.float32), pattern="XYZ")


def test_bilinear_debayer_non_2d():
    with pytest.raises(ValueError):
        bilinear_debayer(np.zeros((10, 10, 3), dtype=np.float32))


def test_debayer_edge_does_not_wrap_opposite_side():
    """A bright pixel on the last column must not leak into column 0 via the
    debayer neighbour average (the old np.roll-based _shift wrapped edges)."""
    mosaic = np.full((8, 8), 100.0, dtype=np.float32)
    mosaic[:, -1] = 60000.0            # bright last column
    rgb = bilinear_debayer(mosaic, pattern="RGGB")
    # Column 0 should stay near the background, not pick up the far-edge spike.
    assert float(rgb[:, 0].max()) < 1000.0
