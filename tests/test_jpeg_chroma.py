"""Every JPEG the user keeps, shares or prints carries full-resolution colour.

Pillow encodes JPEG chroma at 4:2:0 by default — at *every* quality setting, 100
included — which halves the colour resolution in both axes. That is a good
default for a photograph of a face and a bad one for an astrophoto: a Seestar
star is 2–3 px across, so a 2×2 chroma block straddles the star and the sky
around it, smearing each star's colour outward and pulling the sky's colour in.

These tests pin `subsampling=JPEG_SUBSAMPLING` (4:4:4) on the writers, and — the
half that makes the pin mean something — *measure* that it actually recovers
star colour, on a fixture built to be able to show the defect.
"""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image, JpegImagePlugin

from seestack.stack.output import JPEG_SUBSAMPLING, png_bytes_to_jpeg, write_share_jpeg


def _sampling(data: bytes) -> int:
    """Pillow's subsampling code for encoded JPEG bytes — 0 is 4:4:4."""
    with Image.open(BytesIO(data)) as img:
        return JpegImagePlugin.get_sampling(img)


def _star_field(size: int = 256, n_stars: int = 300, sigma: float = 1.1) -> np.ndarray:
    """A synthetic OSC frame shaped like the defect: tight, *coloured* stars on a
    tinted sky.

    Both halves matter. Stars of a Seestar's own size (σ ≈ 1.1 px) are what a
    2×2 chroma block can straddle — blur them and the difference vanishes. And
    the stars must differ in colour from each other and from the sky, because
    subsampling only loses what varies *within* the block: a monochrome field
    encodes identically either way and would pass on the broken code.
    """
    rng = np.random.default_rng(3)
    img = np.zeros((size, size, 3), dtype=np.float32)
    img[..., 0], img[..., 1], img[..., 2] = 0.05, 0.06, 0.10  # a blue-ish sky
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(n_stars):
        cy, cx = rng.uniform(4, size - 4), rng.uniform(4, size - 4)
        colour = rng.uniform(0.5, 1.0, size=3)
        gauss = np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sigma ** 2)))
        img += (rng.uniform(0.3, 0.9) * gauss)[..., None] * colour
    return np.clip(img, 0.0, 1.0)


def _star_colour_error(reference_u8: np.ndarray, data: bytes) -> float:
    """RMS error in the R−B colour difference over the stars, in 8-bit ADU.

    R−B rather than a per-channel difference because it is exactly the quantity
    chroma subsampling throws away: luminance survives at full resolution, so a
    channel-mean comparison mostly measures the quality setting instead.
    """
    with Image.open(BytesIO(data)) as img:
        back = np.asarray(img.convert("RGB"), dtype=np.float32)
    ref = reference_u8.astype(np.float32)
    stars = ref.mean(axis=-1) > 40  # anything meaningfully above the sky
    err = ((ref[..., 0] - ref[..., 2]) - (back[..., 0] - back[..., 2]))[stars]
    return float(np.sqrt((err ** 2).mean()))


def test_pillow_still_defaults_to_half_resolution_colour():
    """The positive control for every assertion below.

    If Pillow ever changes its default to 4:4:4, the `subsampling=` arguments
    become no-ops and the pins would sit permanently green while checking
    nothing. This is the test that would tell us — and it is not a request to
    remove the arguments, which are what makes the behaviour *ours*.
    """
    src = Image.fromarray((_star_field(64, 40) * 255).astype(np.uint8), mode="RGB")
    buf = BytesIO()
    src.save(buf, format="JPEG", quality=95, optimize=True)
    assert _sampling(buf.getvalue()) != 0


def test_share_jpeg_keeps_full_resolution_colour(tmp_path):
    rgb = _star_field()
    out = write_share_jpeg(tmp_path / "share.jpg", rgb)
    assert _sampling(out.read_bytes()) == JPEG_SUBSAMPLING == 0


def test_jpeg_download_keeps_full_resolution_colour():
    rgb = _star_field()
    src = Image.fromarray((rgb * 255).astype(np.uint8), mode="RGB")
    buf = BytesIO()
    src.save(buf, format="PNG")
    assert _sampling(png_bytes_to_jpeg(buf.getvalue())) == 0


def test_wallpaper_keeps_full_resolution_colour():
    from seestack.wallpaper import WALLPAPER_PRESETS, render_wallpaper_jpeg

    rgb = _star_field(512)
    src = Image.fromarray((rgb * 255).astype(np.uint8), mode="RGB")
    buf = BytesIO()
    src.save(buf, format="PNG")
    jpeg = render_wallpaper_jpeg(buf.getvalue(), WALLPAPER_PRESETS["phone"])
    assert _sampling(jpeg) == 0


def test_full_resolution_colour_measurably_recovers_star_colour(tmp_path):
    """The reason the flag is set, measured rather than asserted by name.

    Same pixels, same quality, only the chroma sampling differs — so any
    improvement here is the subsampling and nothing else.
    """
    rgb = _star_field()
    reference = (rgb * 255).astype(np.uint8)
    src = Image.fromarray(reference, mode="RGB")

    smeared = BytesIO()
    src.save(smeared, format="JPEG", quality=90, optimize=True)  # Pillow's 4:2:0
    ours = (write_share_jpeg(tmp_path / "ours.jpg", rgb, quality=90)).read_bytes()

    before = _star_colour_error(reference, smeared.getvalue())
    after = _star_colour_error(reference, ours)
    # Measured at ~12.4 → ~5.0 ADU; asserted with headroom so a Pillow encoder
    # tweak can't redden this over a decimal place.
    assert before > 9.0
    assert after < 7.0
    assert after < before * 0.6


def test_the_price_is_a_modestly_bigger_file(tmp_path):
    """Full-resolution chroma costs bytes, and the trade is only defensible while
    that cost stays small — measured at ~+22 % on this fixture. Pinned loosely so
    the day it stops being a modest price, someone has to look."""
    rgb = _star_field()
    src = Image.fromarray((rgb * 255).astype(np.uint8), mode="RGB")
    smeared = BytesIO()
    src.save(smeared, format="JPEG", quality=90, optimize=True)
    ours = (write_share_jpeg(tmp_path / "ours.jpg", rgb, quality=90)).read_bytes()
    assert len(ours) < len(smeared.getvalue()) * 1.6


def test_a_picture_that_overruns_pillow_s_optimise_buffer_still_writes(tmp_path):
    """Full-resolution chroma must never cost the user their export.

    `optimize=True` makes libjpeg emit the scan in one go, into a buffer Pillow
    sizes by guessing `width x height` bytes — a guess made against 4:2:0.
    High-entropy pixels overrun it at 4:4:4 and libjpeg fails the whole save
    with `OSError: broken data stream when writing image file`; that is exactly
    how the editor's share and print exports went red the moment 4:4:4 was
    switched on, on a 480x320 noise frame. `save_display_jpeg` retries without
    `optimize` — a few per cent of file size, not the colour resolution.
    """
    from seestack.stack.output import save_display_jpeg

    noise = np.random.default_rng(0).random((320, 480, 3)).astype(np.float32)
    src = Image.fromarray((noise * 255).astype(np.uint8), mode="RGB")

    # Positive control: the naive save this replaces really does fail here, so
    # the test below is not quietly asserting nothing.
    with pytest.raises(OSError):
        src.save(tmp_path / "naive.jpg", format="JPEG", quality=90,
                 optimize=True, subsampling=0)

    out = tmp_path / "ours.jpg"
    save_display_jpeg(src, out, quality=90)
    assert _sampling(out.read_bytes()) == 0     # still full-chroma
    with Image.open(out) as img:
        assert img.size == (480, 320)           # …and a complete picture

    # A file object gets the same treatment, rewound rather than appended to —
    # a partial stream from the failed attempt would corrupt the retry.
    buf = BytesIO()
    save_display_jpeg(src, buf, quality=90)
    assert _sampling(buf.getvalue()) == 0
    with Image.open(BytesIO(buf.getvalue())) as img:
        assert img.size == (480, 320)


def test_the_share_writer_survives_the_same_frame_end_to_end(tmp_path):
    """The path the editor's "Share" button actually takes."""
    noise = np.random.default_rng(1).random((320, 480, 3)).astype(np.float32)
    out = write_share_jpeg(tmp_path / "share.jpg", noise)
    assert _sampling(out.read_bytes()) == 0


@pytest.mark.parametrize("quality", [75, 90, 92, 95])
def test_the_writer_is_full_chroma_at_every_quality_it_is_asked_for(tmp_path, quality):
    """The quality knob and the chroma choice are independent — a caller lowering
    quality for a smaller file must not silently get half-resolution colour back,
    which is exactly what Pillow's own quality presets would do."""
    out = write_share_jpeg(tmp_path / f"q{quality}.jpg", _star_field(64, 40),
                           quality=quality)
    assert _sampling(out.read_bytes()) == 0
