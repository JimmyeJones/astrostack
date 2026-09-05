"""Every file the app hands the user is *rounded* into its integer container.

``(x * MAX).astype(uintN)`` truncates toward zero, so each of the six export
paths in ``seestack.stack.output`` used to bias every pixel **downward** — by up
to a whole step and by ~½ a step on average. On the 8-bit share/print JPEG that
is ~0.2 % of full scale off every picture the owner posts; on the 16-bit
"linear" TIFF it quietly breaks the reversibility the file's own description
claims (``float = black + dn/65535·(white − black)``), because the recovered
float is systematically low by up to a full DN where rounding is honest to ±½.

Not a visible defect — it is a fraction of a step — but it is a *systematic*
one on the exact path the app advertises as the full data, and the fix is free.
``render/thumbnail.py`` already packs its alpha channel with ``np.rint``, so the
truncation elsewhere was an oversight rather than a considered choice; these
tests pin the rule for all six sites at once via the shared
:func:`~seestack.stack.output.pack_unit`.
"""

from __future__ import annotations

import numpy as np

from seestack.stack.output import (
    _to_uint16_linear,
    linear_scale_anchors,
    pack_unit,
    write_full_res_png,
    write_share_jpeg,
)


def test_pack_unit_rounds_to_the_nearest_step_not_down():
    """The whole bug in one assertion, at both bit depths."""
    # 8-bit: 100.6 steps is nearer 101. Truncation says 100.
    assert int(pack_unit(np.array([100.6 / 255.0], dtype=np.float64))[0]) == 101
    assert int(pack_unit(np.array([100.4 / 255.0], dtype=np.float64))[0]) == 100
    # 16-bit: a hair under full scale still *is* full scale. Truncation says 65534
    # — so the brightest value a stack can hold could never reach the top of the
    # file it was written into.
    assert int(pack_unit(np.array([65534.6 / 65535.0]), np.uint16)[0]) == 65535


def test_pack_unit_keeps_the_ends_exact():
    """Rounding must not cost the anchors: 0 and 1 land on 0 and MAX exactly, and
    nothing overflows the container (``rint(1.0 * MAX) == MAX``)."""
    for dtype, top in ((np.uint8, 255), (np.uint16, 65535)):
        packed = pack_unit(np.array([0.0, 1.0]), dtype)
        assert packed.dtype == dtype
        assert packed.tolist() == [0, top]


def test_the_export_no_longer_darkens_every_pixel_it_writes():
    """The bias, measured. Truncation puts the mean error at −½ a step; rounding
    puts it at zero, which is what "no stretching, full data preserved" means."""
    rng = np.random.default_rng(3)
    values = rng.random(200_000)

    error = pack_unit(values, np.uint16).astype(np.float64) - values * 65535.0
    assert abs(error.mean()) < 0.02, error.mean()      # truncation: ≈ −0.5
    assert np.abs(error).max() <= 0.5 + 1e-6           # truncation: ≈ 1.0


def test_the_linear_tiff_round_trips_within_half_a_step():
    """The file's own description promises ``float = black + dn/65535·(white −
    black)``. Under truncation the recovered float was low by up to a whole DN;
    under rounding it is honest to ±½ DN, which is the best a 16-bit container
    can do."""
    rng = np.random.default_rng(7)
    rgb = (0.02 + rng.normal(0.0, 0.004, (64, 80, 3))).astype(np.float32)
    rgb[10, 10] = 1.0                                  # a saturated star core

    lo, hi = linear_scale_anchors(rgb)
    step = (hi - lo) / 65535.0
    recovered = lo + _to_uint16_linear(rgb).astype(np.float64) / 65535.0 * (hi - lo)

    residual = recovered - rgb
    assert np.abs(residual).max() <= step / 2.0 + 1e-6  # truncation: up to `step`
    # And it is a *rounding* residual, not a one-sided one.
    assert abs(residual.mean()) < step * 0.02


def _png_pixels(path):  # noqa: ANN001, ANN202
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))


def test_the_editor_png_download_rounds_too(tmp_path):
    """`write_full_res_png` is the "download exactly what I saw" path, so a
    half-step darkening of every pixel is precisely what it must not do."""
    level = 152.6 / 255.0
    rgb = np.full((8, 8, 3), level, dtype=np.float32)
    out = write_full_res_png(tmp_path / "full.png", rgb)
    assert np.all(_png_pixels(out) == 153)             # truncation: 152


def test_the_share_jpeg_rounds_too(tmp_path):
    """The picture the owner actually posts. JPEG is lossy, so this asserts the
    level is *near* the rounded value rather than exactly it — but a whole step
    is far outside what a flat patch at quality 95 costs."""
    level = 152.6 / 255.0
    rgb = np.full((32, 32, 3), level, dtype=np.float32)
    out = write_share_jpeg(tmp_path / "share.jpg", rgb, quality=95)
    from PIL import Image

    mid = float(np.asarray(Image.open(out).convert("RGB")).mean())
    assert abs(mid - 153.0) < 0.5, mid                 # truncation: ≈ 152
