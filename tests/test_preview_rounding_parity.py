"""The *display* side rounds too — so what the app shows matches what it writes.

v0.354.1 routed the six exports in :mod:`seestack.stack.output` through
:func:`~seestack.stack.output.pack_unit`, which ``np.rint``s. Every other
float→byte site in the app kept spelling ``(x * 255).astype(np.uint8)``, which
**truncates** — so from that version on the two halves disagreed:

* the **editor preview** (``webapp.routers.editor._render_png``), the gallery /
  History preview, the full-res preview render and the loupe were each up to a
  whole step **darker** than the PNG/TIFF the download button writes from the
  very same display-space pixels — a systematic ≤1/255 divergence on exactly the
  path whose whole promise is "you get what you saw";
* and :func:`seestack.printexport.render_print` — a file the owner keeps and
  sends to a print lab — was an *export* the v0.354.1 sweep simply missed,
  because it lives outside ``stack/output.py``.

Not a visible defect on its own (a fraction of a step), but it is systematic,
one-sided, and free to fix. These tests pin the rounded rule on the display
paths, and the last one pins it for the whole tree so the two halves cannot
drift apart again.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("PIL")

from astropy.io import fits  # noqa: E402
from PIL import Image  # noqa: E402

from seestack.render.orient import rotate_image_north_up  # noqa: E402
from seestack.render.thumbnail import (  # noqa: E402
    render_preview_png_full_res,
    render_stack_png,
)
from seestack.stack.output import DISPLAY_SPACE_CARD, write_full_res_png  # noqa: E402

# 152.6 steps out of 255: nearer 153, so truncation says 152 and rounding 153.
# The same level the export half of this rule is pinned at in
# `tests/test_export_rounding.py`, deliberately, so preview and export are
# compared at one number.
LEVEL = 152.6 / 255.0


def _display_space_fits(path: Path, level: float, h: int = 24, w: int = 32) -> str:
    """An editor-export FITS: already tone-mapped [0,1], so every render path
    shows it *verbatim* and the byte it produces is predictable."""
    cube = np.full((3, h, w), level, dtype=np.float32)
    hdu = fits.PrimaryHDU(data=cube)
    hdu.header[DISPLAY_SPACE_CARD] = (True, "tone-mapped display-space image")
    hdu.writeto(path, overwrite=True)
    return str(path)


def _pixels(png_bytes: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(png_bytes)) as im:
        return np.asarray(im.convert("RGB"))


def test_the_preview_and_the_download_agree_on_the_same_display_space_pixels(tmp_path):
    """The parity claim itself: one display-space stack, rendered by the preview
    path and by the download path, must land on the same byte.

    Before the fix the preview truncated to 152 while `write_full_res_png`
    rounded to 153 — the picture on screen was a step darker than the file."""
    src = _display_space_fits(tmp_path / "disp.fits", LEVEL)

    preview = _pixels(render_stack_png(src, max_width=64))
    download = np.asarray(
        Image.open(write_full_res_png(tmp_path / "full.png",
                                      np.full((24, 32, 3), LEVEL, dtype=np.float32))
                   ).convert("RGB"))

    assert np.all(preview == 153)      # truncation: 152
    assert np.all(download == 153)
    assert preview.max() == download.max()


def test_the_full_res_preview_render_rounds_too(tmp_path):
    """`render_preview_png_full_res` is the "download exactly what I saw" render
    that sits beside the export, so it must round the same way."""
    src = _display_space_fits(tmp_path / "disp.fits", LEVEL, h=40, w=48)

    assert np.all(_pixels(render_preview_png_full_res(src, max_long_edge=4096)) == 153)


def test_the_north_up_rotation_does_not_darken_the_picture_it_turns(tmp_path):
    """`rotate_image_north_up` round-trips through an 8-bit image to use PIL's
    resampler, so a truncating pack cost half a step *every time a user asked for
    North up* — a correction that is supposed to be orientation-only."""
    rgb = np.full((48, 48, 3), LEVEL, dtype=np.float32)

    # 30° is well clear of the ±1° snap tolerance, so this takes the resampling
    # path (the snapped path is a pure transpose and never packs at all).
    out = rotate_image_north_up(rgb, 30.0)

    centre = out[20:28, 20:28]                     # interior: no black corners
    assert np.allclose(centre, 153.0 / 255.0, atol=1e-6)   # truncation: 152/255


def test_the_print_export_rounds_too():
    """A print is a file the owner keeps, so it belongs to the export rule — it
    was simply outside `stack/output.py` when that rule shipped."""
    from seestack.printexport import PrintOption, render_print

    rgb = np.full((40, 40, 3), LEVEL, dtype=np.float32)
    option = PrintOption(name="test", dpi=300, width_px=40, height_px=40,
                         width_in=1.0, height_in=1.0)

    assert np.all(np.asarray(render_print(rgb, option)) == 153)   # truncation: 152


def test_the_deepening_reel_frame_rounds_too(tmp_path):
    """The "watch it get deeper" reel renders each night the same way the preview
    does; a display-space night is shown verbatim, so it is pinnable."""
    from seestack.render.deepening import render_deepening_frames

    # The reel needs at least two nights to be worth rendering, so give it the
    # same flat night twice — every frame must land on the rounded byte.
    src_a = _display_space_fits(tmp_path / "a.fits", LEVEL, h=32, w=32)
    src_b = _display_space_fits(tmp_path / "b.fits", LEVEL, h=32, w=32)

    frames = render_deepening_frames([src_a, src_b], max_width=32)

    assert frames, "the reel rendered nothing to check"
    for frame in frames:
        assert np.all(np.asarray(frame) == 153)                   # truncation: 152


def test_the_moon_still_tiff_rounds_too(tmp_path):
    """The 16-bit TIFF behind a Moon/Sun capture is the other export that lives
    outside ``stack/output.py``, so it missed the v0.354.1 sweep as well. At 16
    bits a truncated step is invisible, but this is the file the owner keeps."""
    tifffile = pytest.importorskip("tifffile")
    from webapp.video import _write_tiff16

    level = 40000.6 / 65535.0
    _write_tiff16(tmp_path / "still.tif", np.full((8, 8, 3), level, dtype=np.float64))

    assert np.all(tifffile.imread(tmp_path / "still.tif") == 40001)   # truncation: 40000


# The construct itself: ``(<anything> * 255).astype(np.uint8)`` and friends.
_TRUNCATING = ("* 255).astype(np.uint8)", "* 255.0).astype(np.uint8)",
               "* 65535).astype(np.uint16)", "* 65535.0).astype(np.uint16)")

_ROOTS = ("seestack", "webapp")


def test_no_float_to_integer_pack_truncates_anywhere_in_the_app():
    """The drift guard. Fifteen sites spelled this by hand and they disagreed for
    a version; a sixteenth would be silent, so the rule is pinned by grep.

    If this fails, the new site wants :func:`seestack.stack.output.pack_unit`
    (clip to [0,1] first — it does not clip for you). The only legitimate
    exception is a *boolean* mask promoted with ``mask.astype(np.uint8) * 255``,
    which is a different construct and does not match these needles."""
    repo = Path(__file__).resolve().parent.parent
    offenders = []
    for root in _ROOTS:
        for path in sorted((repo / root).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for needle in _TRUNCATING:
                if needle in text:
                    offenders.append(f"{path.relative_to(repo)}: {needle}")

    assert not offenders, (
        "float→integer packing must go through seestack.stack.output.pack_unit "
        "(it rounds; these truncate):\n  " + "\n  ".join(offenders))
