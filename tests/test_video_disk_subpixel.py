"""The disk aligner measures sub-pixel shifts on a raw capture (2026-10-20).

Found while building the Moon/Sun drizzle: the disk refinement in
``lucky._measure_disk_shift`` was a phase-only correlation, which on a debayered
8-bit raw frame locks onto the sensor's own stationary structure — so every
measured shift came back on a whole pixel. That blurred every lucky stack by up
to half a pixel, and would have left a drizzle no sub-pixel variety to use.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.io.fits_loader import bilinear_debayer
from tests.videosynth import cfa_gain


@pytest.mark.parametrize("fixed_pattern_dn", [0.0, 4.0])
def test_the_disk_refinement_measures_sub_pixel_shifts_on_a_raw_capture(fixed_pattern_dn):
    """**The bug the drizzle found** (2026-10-20): on a debayered 8-bit raw frame
    the phase-only refinement locked onto the sensor's stationary structure and
    came back on a whole pixel every time, so the stack was aligned to ±0.5 px
    at best and a drizzle saw no sub-pixel variety. Fails before (median error
    ≈ 0.5 px, i.e. only ever the integer centre)."""
    from seestack.video import lucky

    h, w, radius = 200, 320, 40.0
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    gain = cfa_gain(h, w, "GBRG")
    fixed = rng.normal(0.0, fixed_pattern_dn, (h, w)).astype(np.float32)

    def luma(jy, jx):
        cy, cx = h / 2 + jy, w / 2 + jx
        disk = np.clip((radius - np.hypot(xx - cx, yy - cy)) / 2.0 + 0.5, 0.0, 1.0)
        scene = 8.0 + disk * (170.0 + 30.0 * np.sin(2 * np.pi * (xx - cx) / 6.0)
                              * np.cos(2 * np.pi * (yy - cy) / 6.6))
        raw = np.clip(scene * gain + fixed + rng.normal(0.0, 1.5, scene.shape), 0, 255)
        # Exactly what ``iter_frames`` hands the stacker: an 8-bit debayer.
        return lucky.frame_luma(bilinear_debayer(raw.astype(np.uint8), pattern="GBRG"))

    ref = luma(0.0, 0.0)
    ref_disk = lucky._find_disk(ref)
    errors = []
    for _ in range(15):
        jy, jx = rng.uniform(-30, 30, 2)
        frame = luma(jy, jx)
        dy, dx = lucky._measure_disk_shift(ref, ref_disk, frame, lucky._find_disk(frame))
        errors.append(max(abs(dy + jy), abs(dx + jx)))
    assert float(np.median(errors)) < 0.15, errors
