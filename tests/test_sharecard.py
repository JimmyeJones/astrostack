"""Copy-friendly share blurb + social-sized JPEG writer."""

import json
from pathlib import Path

import numpy as np

from seestack.sharecard import format_duration, share_blurb
from seestack.stack.output import png_bytes_to_jpeg, write_share_jpeg

# The table `frontend/src/format.test.ts` reads too — see the file's own comment.
SHARED_CASES = Path(__file__).parent / "fixtures" / "integration_format.json"


def test_format_duration_matches_the_shared_table():
    """The app has ONE integration-time vocabulary, and this is half of the pin.

    `formatIntegration` (`frontend/src/format.ts`) reads the same file in
    `format.test.ts`. Before this table existed the two disagreed on every
    picture with more than a minute of light in it — the Target page said
    "3.2 h" and the caption you copy off the Editor said "3h 12m" — so a
    beginner had two spellings of one number and no way to connect them.
    """
    cases = json.loads(SHARED_CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 10, "the shared table should not shrink"
    for seconds, expected in cases:
        assert format_duration(seconds) == expected, seconds


def test_format_duration_says_nothing_rather_than_a_placeholder():
    """The one deliberate divergence from the SPA: a stat tile can print "—",
    but a caption must drop the clause rather than post a dash to Instagram."""
    assert format_duration(0) == ""
    assert format_duration(None) == ""
    assert format_duration(-5) == ""
    assert format_duration(float("nan")) == ""
    assert format_duration(float("inf")) == ""
    assert format_duration("not a number") == ""


def test_share_blurb_full():
    assert share_blurb("M 42", 152, 11520) == "M 42 · 3.2 h · 152 subs"


def test_share_blurb_singular_sub():
    assert share_blurb("NGC 7000", 1, 75) == "NGC 7000 · 1 min · 1 sub"


def test_share_blurb_omits_missing_parts():
    # No integration, no subs → just the name; never a dangling separator.
    assert share_blurb("M 31", None, None) == "M 31"
    assert share_blurb("M 31", 0, 0) == "M 31"
    # No name → still tidy.
    assert share_blurb("", 10, 300) == "5 min · 10 subs"
    # Nothing at all.
    assert share_blurb(None, None, None) == ""


def test_share_blurb_carries_the_night_it_was_shot():
    """The Editor's copyable caption was the only one of the four with no date at
    all, while Target, History, Gallery and the baked nameplate all carried one —
    and the date is the fact a caption is *for*."""
    from seestack.nightrange import format_night_range

    assert share_blurb("M 42", 152, 11520,
                       format_night_range("2024-11-15", "2024-11-18")) == \
        "M 42 · 15–18 Nov 2024 · 3.2 h · 152 subs"
    # Second, right after the target: the object and the night before the
    # exposure arithmetic.
    assert share_blurb("M 42", None, None, "15–18 Nov 2024") == "M 42 · 15–18 Nov 2024"


def test_share_blurb_without_a_window_is_exactly_what_it_always_was():
    """Every run recorded before the app knew its capture window — and every
    caller that doesn't pass one — captions unchanged, with no empty part and no
    dangling separator."""
    assert share_blurb("M 42", 152, 11520) == share_blurb("M 42", 152, 11520, None)
    assert share_blurb("M 42", 152, 11520, "") == "M 42 · 3.2 h · 152 subs"
    assert share_blurb("M 42", 152, 11520, "   ") == "M 42 · 3.2 h · 152 subs"
    assert share_blurb(None, None, None, None) == ""


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


def test_write_share_jpeg_bakes_the_nameplate_footer_when_requested(tmp_path):
    from PIL import Image

    from seestack.nameplate import NameplateFields

    rgb = np.full((300, 400, 3), 0.5, dtype="float32")
    fields = NameplateFields(target="M 31", integration_s=11520, n_frames=152,
                             camera="ZWO Seestar S50")

    plain = write_share_jpeg(tmp_path / "plain.jpg", rgb)
    with_bar = write_share_jpeg(tmp_path / "bar.jpg", rgb, nameplate=fields)

    with Image.open(plain) as p, Image.open(with_bar) as b:
        assert p.size == b.size == (400, 300)      # same pixels, only the footer differs
        pa, ba = np.asarray(p), np.asarray(b)
        # The footer band is visibly darker with the nameplate; the top is unchanged.
        assert ba[-20:].mean() < pa[-20:].mean() - 8
        assert abs(int(ba[:20].mean()) - int(pa[:20].mean())) <= 1


def test_write_share_jpeg_without_nameplate_is_unchanged(tmp_path):
    """Passing no nameplate (the default) leaves the share pixels exactly as before."""
    from PIL import Image

    rgb = np.full((40, 50, 3), 0.5, dtype="float32")
    out = write_share_jpeg(tmp_path / "none.jpg", rgb, nameplate=None)
    with Image.open(out) as img:
        arr = np.asarray(img)
        assert arr.min() > 120 and arr.max() < 140   # uniform grey, no bar drawn


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


def test_png_bytes_to_jpeg_bakes_the_nameplate_when_requested(tmp_path):
    """The direct JPEG download can bake the same acquisition footer as the editor
    share export: passing a NameplateFields draws the caption bar, changing the
    lower rows, while the default (no nameplate) leaves the pixels untouched."""
    from io import BytesIO

    from PIL import Image

    from seestack.nameplate import NameplateFields

    src = Image.new("RGB", (400, 300), (30, 40, 60))
    buf = BytesIO()
    src.save(buf, format="PNG")
    png = buf.getvalue()

    plain = png_bytes_to_jpeg(png)
    plate = NameplateFields(target="M 31", integration_s=15150, n_frames=505,
                            sub_exposure_s=30, date_iso="2026-07-19",
                            camera="ZWO Seestar S50")
    captioned = png_bytes_to_jpeg(png, nameplate=plate)

    assert captioned[:2] == b"\xff\xd8"
    assert captioned != plain                      # the footer bar altered the pixels
    with Image.open(BytesIO(captioned)) as img:
        assert img.size == (400, 300)              # same resolution, footer overlaid
        # A dark caption bar now sits along the bottom rows (was uniform blue).
        bottom = np.asarray(img)[-8:, :, :]
        assert bottom.min() < 20

    # An empty nameplate (nothing to say) is a clean no-op transcode.
    empty = png_bytes_to_jpeg(png, nameplate=NameplateFields())
    assert empty == plain


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
