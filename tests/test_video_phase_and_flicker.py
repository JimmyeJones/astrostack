"""Moon & Sun stacker fixes from the 2026-11-26 audit.

1. A gibbous Moon with maria was aligned on the centroid of its brightest
   piece, which differs between the sharp reference and softer frames: every
   frame sat ~25 px off and the stack was a 4 px blur. The disk mask is now the
   whole lit shape.
2. Brightness flicker between frames (thin cloud, auto-exposure) printed a
   coloured 3-pixel mesh into the ×1.5 drizzle. Frames are now brought to the
   reference's level before they are added.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from seestack.video.drizzle import LUCKY_DRIZZLE_MIN_FRAMES
from seestack.video.lucky import LuckyOptions, stack_video
from tests.videosynth import solar_raw_jittered_video


def _gibbous(blur: float) -> tuple[np.ndarray, np.ndarray]:
    """A gibbous Moon luma whose maria (at 45 % of the highlands) split the
    bright highlands into pieces, plus the true lit shape."""
    h, w, r0 = 240, 320, 90
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    dy, dx = yy - h / 2, xx - w / 2
    disk = np.hypot(dx, dy) < r0
    lit = disk & (dx > -0.35 * r0 * np.sqrt(np.clip(1 - (dy / r0) ** 2, 0, 1)))
    albedo = np.ones((h, w))
    albedo[(np.abs(dx - 10) < 12) | (np.abs(dy + 15) < 10)] = 0.45   # two crossing maria
    albedo[(dx - 50) ** 2 + (dy - 30) ** 2 < 25] = 1.9                 # a bright ray crater
    img = 6 + 200 * lit * albedo
    img = gaussian_filter(img, blur) + np.random.default_rng(int(blur * 10)).normal(0, 2, img.shape)
    return img.astype(np.float32), lit


def test_the_disk_mask_is_the_whole_lit_shape_not_its_brightest_piece():
    from seestack.video.lucky import _find_disk

    for blur in (0.6, 2.5):
        img, lit = _gibbous(blur)
        d = _find_disk(img)
        assert d is not None
        covered = (d.mask & lit).sum() / lit.sum()
        # Halfway up the brightness (the bug) the maria are left out and the mask
        # is one highland piece: well under half the lit shape.
        assert covered > 0.9, (blur, covered)
        ty, tx = np.argwhere(lit).mean(axis=0)
        assert abs(d.cy - ty) < 2.0 and abs(d.cx - tx) < 2.0, (blur, d.cy, d.cx, ty, tx)


def _phase_spread(img: np.ndarray) -> float:
    """Spread of the nine 3×3 lattice-phase means of the disk's luminance,
    relative to their mean — a mesh shows up as a fixed phase pattern."""
    lum = np.nanmean(img, axis=-1)
    inside = np.isfinite(lum) & (lum > 0.5 * np.nanpercentile(lum, 99))
    means = [float(np.mean(lum[py::3, px::3][inside[py::3, px::3]]))
             for py in range(3) for px in range(3)]
    return (max(means) - min(means)) / float(np.mean(means))


def test_flicker_does_not_print_a_mesh_into_the_drizzle(tmp_path):
    path = solar_raw_jittered_video(tmp_path / "Solar_video.avi",
                                    LUCKY_DRIZZLE_MIN_FRAMES + 20,
                                    jitter=3.0, flicker=0.10, seed=3)
    res = stack_video(path, LuckyOptions(keep_percent=100, drizzle=True))
    assert res.drizzle_scale and res.drizzle_scale > 1.0
    # Unnormalised frames left ~2 % per channel here; normalised, it is noise-level.
    assert _phase_spread(res.image) < 0.008, _phase_spread(res.image)
