"""Copy-friendly share blurb + social-sized JPEG writer."""

import numpy as np

from seestack.sharecard import format_duration, share_blurb
from seestack.stack.output import png_bytes_to_jpeg, write_share_jpeg


def test_format_duration_buckets():
    assert format_duration(30) == "30s"
    assert format_duration(59) == "59s"
    assert format_duration(60) == "1m"
    assert format_duration(150) == "2m"          # rounds to whole minutes
    assert format_duration(3600) == "1h"          # exact hour drops the minutes
    assert format_duration(11520) == "3h 12m"     # 152 subs × ~75.8 s ≈ 3h12m
    assert format_duration(7200 + 300) == "2h 05m"  # zero-padded minutes


def test_format_duration_empty_for_nothing():
    assert format_duration(0) == ""
    assert format_duration(None) == ""
    assert format_duration(-5) == ""


def test_share_blurb_full():
    assert share_blurb("M 42", 152, 11520) == "M 42 · 3h 12m · 152 subs"


def test_share_blurb_singular_sub():
    assert share_blurb("NGC 7000", 1, 75) == "NGC 7000 · 1m · 1 sub"


def test_share_blurb_omits_missing_parts():
    # No integration, no subs → just the name; never a dangling separator.
    assert share_blurb("M 31", None, None) == "M 31"
    assert share_blurb("M 31", 0, 0) == "M 31"
    # No name → still tidy.
    assert share_blurb("", 10, 300) == "5m · 10 subs"
    # Nothing at all.
    assert share_blurb(None, None, None) == ""


def test_write_share_jpeg_downscales_large_image(tmp_path):
    from PIL import Image

    # A 3000×1000 display-stretched image (long edge > 2048) must downscale.
    rgb = np.clip(np.random.default_rng(0).random((1000, 3000, 3)), 0, 1).astype("float32")
    out = write_share_jpeg(tmp_path / "share.jpg", rgb, max_long_edge=2048)
    with Image.open(out) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"
        assert max(img.size) == 2048           # long edge capped
        assert img.size == (2048, round(1000 * 2048 / 3000))  # aspect preserved


def test_write_share_jpeg_keeps_small_image_native_and_blackens_nan(tmp_path):
    from PIL import Image

    rgb = np.full((40, 50, 3), 0.5, dtype="float32")
    rgb[0, 0, :] = np.nan  # uncovered pixel → black, never a crash
    out = write_share_jpeg(tmp_path / "small.jpg", rgb)
    with Image.open(out) as img:
        assert img.size == (50, 40)            # not upscaled
        assert img.getpixel((0, 0)) == (0, 0, 0) or max(img.getpixel((0, 0))) < 8


def test_png_bytes_to_jpeg_transcodes_at_same_resolution(tmp_path):
    """The finished-picture JPEG download transcodes the stored preview PNG to a
    JPEG at the same size (only the container/size on disk differ)."""
    from io import BytesIO

    from PIL import Image

    # A stored preview PNG (RGB), as render writes it.
    src = Image.new("RGB", (50, 40), (30, 120, 200))
    buf = BytesIO()
    src.save(buf, format="PNG")

    jpeg = png_bytes_to_jpeg(buf.getvalue())
    assert jpeg[:2] == b"\xff\xd8"              # JPEG SOI marker
    with Image.open(BytesIO(jpeg)) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"
        assert img.size == (50, 40)             # same resolution, not resized


def test_png_bytes_to_jpeg_flattens_transparency_onto_black(tmp_path):
    """JPEG has no alpha — a transparent (uncovered) region flattens to black,
    matching the preview's own NaN→black convention, and never crashes."""
    from io import BytesIO

    from PIL import Image

    src = Image.new("RGBA", (8, 8), (200, 200, 200, 255))
    src.putpixel((0, 0), (123, 45, 67, 0))       # fully transparent corner
    buf = BytesIO()
    src.save(buf, format="PNG")

    jpeg = png_bytes_to_jpeg(buf.getvalue())
    with Image.open(BytesIO(jpeg)) as img:
        assert img.mode == "RGB"
        assert max(img.getpixel((0, 0))) < 8     # transparent → black, not the RGBA colour
