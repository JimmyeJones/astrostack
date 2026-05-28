"""Compare dialog — image-loading helpers (FITS + TIFF + PNG paths)."""

import os

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("PySide6")
pytest.importorskip("tifffile")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from seestack.gui.compare_dialog import _read_to_rgb_float


_app = QApplication.instance() or QApplication([])


def test_read_fits_cube(tmp_path):
    """3-channel FITS cube comes back as (H, W, 3)."""
    from astropy.io import fits

    cube = np.random.rand(3, 50, 60).astype(np.float32)
    p = tmp_path / "cube.fits"
    fits.PrimaryHDU(cube).writeto(p)
    arr = _read_to_rgb_float(p)
    assert arr.shape == (50, 60, 3)


def test_read_tiff_rgb(tmp_path):
    import tifffile

    img = (np.random.rand(40, 50, 3) * 255).astype(np.uint8)
    p = tmp_path / "x.tif"
    tifffile.imwrite(p, img)
    arr = _read_to_rgb_float(p)
    assert arr.shape == (40, 50, 3)
    assert arr.dtype == np.float32


def test_read_png_grayscale(tmp_path):
    from PIL import Image

    img = (np.random.rand(30, 40) * 255).astype(np.uint8)
    p = tmp_path / "x.png"
    Image.fromarray(img, "L").save(p)
    arr = _read_to_rgb_float(p)
    # Grayscale gets stacked to RGB.
    assert arr.shape == (30, 40, 3)
