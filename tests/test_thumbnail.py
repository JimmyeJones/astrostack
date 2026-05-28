"""Thumbnail generation produces a valid PNG."""

import pytest

pytest.importorskip("astropy")
pytest.importorskip("PIL")

from seestack.gui.thumbnail import generate_thumbnail  # noqa: E402
from tests.synth import write_seestar_fits  # noqa: E402


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
