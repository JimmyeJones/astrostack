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


def test_load_raw_reads_image_from_a_data_less_primary_hdu(tmp_path):
    """A multi-extension FITS with an empty primary HDU and the image in ext 1
    must load, not raise an opaque IndexError.

    Regression: ``load_seestar_raw`` read ``hdul[0]`` unconditionally, so an
    empty primary made ``np.asarray(None).shape[-1]`` raise ``IndexError: tuple
    index out of range`` *before* the intended "expected 2D" guard could fire.
    We now fall through to the first data-bearing HDU."""
    from astropy.io import fits

    data = (np.arange(320 * 480, dtype=np.uint16) % 1000).reshape(320, 480)
    ext = fits.ImageHDU(data=data)
    ext.header["BAYERPAT"] = "RGGB"
    hdul = fits.HDUList([fits.PrimaryHDU(), ext])  # primary carries no data
    p = tmp_path / "multiext.fits"
    hdul.writeto(p)

    img, info = load_seestar_raw(p, debayer=False)
    assert img.shape == (320, 480)
    assert info.width_px == 480 and info.height_px == 320
    # load_header reports the same geometry, from the same data-bearing HDU.
    h = load_header(p)
    assert h.width_px == 480 and h.height_px == 320


def test_load_raw_reads_a_compressed_fits(tmp_path):
    """An fpack'd (CompImageHDU) FITS keeps an empty primary and the pixels in a
    compressed extension. Falling through to the first data-bearing HDU lets us
    read those too instead of crashing on the empty primary."""
    from astropy.io import fits

    data = (np.arange(320 * 480, dtype=np.uint16) % 1000).reshape(320, 480)
    comp = fits.CompImageHDU(data=data)
    comp.header["BAYERPAT"] = "RGGB"
    hdul = fits.HDUList([fits.PrimaryHDU(), comp])
    p = tmp_path / "compressed.fits"
    hdul.writeto(p)

    img, info = load_seestar_raw(p, debayer=False)
    assert img.shape == (320, 480)
    assert info.bayer_pattern == "RGGB"


def test_load_raw_raises_clear_error_when_no_image_data(tmp_path):
    """A FITS with no image extension at all raises a clear ValueError, not an
    opaque IndexError."""
    from astropy.io import fits

    hdul = fits.HDUList([fits.PrimaryHDU()])  # no data anywhere
    p = tmp_path / "empty.fits"
    hdul.writeto(p)

    with pytest.raises(ValueError, match="no image data|expected 2D"):
        load_seestar_raw(p, debayer=False)


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
