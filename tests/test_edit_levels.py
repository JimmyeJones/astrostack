"""Data-driven black/white points for the Levels op (seestack/edit/levels.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from displayspace import (  # noqa: E402
    assert_shadow_clip,
    real_stretched_stack,
    sky_truth,
)

from seestack.edit.levels import (  # noqa: E402
    GAMMA_TARGET,
    suggest_levels_gamma,
    suggest_levels_points,
)


def _scene(black_floor=0.15, bright=0.9, h=120, w=160, seed=0):
    """A display-space image: a dim sky floor with a bright blob, so the low
    percentile lands near the floor and the high one near the highlight."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    signal = (bright - black_floor) * np.exp(
        -(((xx - w / 2) / 15) ** 2 + ((yy - h / 2) / 15) ** 2))
    img = black_floor + signal[..., None] + rng.normal(0.0, 0.01, (h, w, 3))
    return np.clip(img, 0.0, 1.0).astype("float32")


def test_black_tracks_sky_and_white_tracks_highlights():
    pts = suggest_levels_points(_scene(black_floor=0.15, bright=0.9))
    assert pts is not None
    black, white = pts
    # Black lands just above the sky floor; white just below the brightest cores.
    assert 0.1 < black < 0.25
    assert 0.5 < white <= 1.0
    assert white > black


def test_brighter_sky_raises_the_black_point():
    dim = suggest_levels_points(_scene(black_floor=0.1))
    bright = suggest_levels_points(_scene(black_floor=0.35))
    assert dim is not None and bright is not None
    assert bright[0] > dim[0]


def test_points_are_clamped_and_rounded():
    black, white = suggest_levels_points(_scene())
    assert 0.0 <= black <= 1.0 and 0.0 <= white <= 1.0
    # rounded to 3 decimals
    assert round(black, 3) == black and round(white, 3) == white


def test_nan_uncovered_pixels_are_ignored():
    img = _scene()
    img[:20, :, :] = np.nan  # a mosaic-edge NaN band
    pts = suggest_levels_points(img)
    assert pts is not None
    assert np.isfinite(pts[0]) and np.isfinite(pts[1])


def test_returns_none_when_range_is_degenerate():
    # A flat image (no dynamic range) → black≈white → no useful suggestion.
    flat = np.full((60, 60, 3), 0.3, dtype="float32")
    assert suggest_levels_points(flat) is None
    # All-NaN (uncovered) → too few finite pixels.
    allnan = np.full((60, 60, 3), np.nan, dtype="float32")
    assert suggest_levels_points(allnan) is None


def test_gamma_lifts_a_dark_median_toward_the_target():
    # A dark-sky scene: the median sits near the black floor, so after the
    # black/white remap the typical tone lands low and a >1 gamma is suggested.
    img = _scene(black_floor=0.12, bright=0.9)
    pts = suggest_levels_points(img)
    assert pts is not None
    gamma = suggest_levels_gamma(img, pts[0], pts[1])
    assert gamma is not None and gamma > 1.0
    # Applying it lands the remapped median near the 0.25 target grey.
    finite = img[np.isfinite(img)]
    x_m = (float(np.median(finite)) - pts[0]) / (pts[1] - pts[0])
    assert abs(x_m ** (1.0 / gamma) - 0.25) < 0.05


def test_gamma_is_none_when_the_median_already_sits_at_or_above_target():
    # A bright-midtone image: the median already lands at/above the target after
    # the remap, so no lift is suggested (leave gamma at 1.0).
    rng = np.random.default_rng(1)
    img = np.clip(0.6 + rng.normal(0.0, 0.02, (80, 80, 3)), 0.0, 1.0).astype("float32")
    # A wide black/white range so the bright median maps high.
    assert suggest_levels_gamma(img, 0.0, 1.0) is None


def test_gamma_guards_degenerate_range_and_too_few_pixels():
    img = _scene()
    # white <= black → no range.
    assert suggest_levels_gamma(img, 0.8, 0.8) is None
    # All-NaN → too few finite pixels.
    allnan = np.full((60, 60, 3), np.nan, dtype="float32")
    assert suggest_levels_gamma(allnan, 0.1, 0.9) is None


def test_gamma_is_clamped_to_the_op_range():
    g = suggest_levels_gamma(_scene(black_floor=0.12), 0.1, 0.95)
    if g is not None:
        assert 0.1 <= g <= 5.0
        assert round(g, 3) == g


# --------------------------------------------------------------------------- #
# What the suggestion does on a picture that has really been stretched
# --------------------------------------------------------------------------- #
#
# Every fixture above is `clip(sky + noise)` — a hand-rolled stand-in for a
# stretched image, with no hard shadow clip. That is the exact shape of fixture
# that let the A1 sky-lift bug pass its own regression test for four months
# (see `tests/displayspace.py`), so the low-end behaviour of this module is
# pinned below against real `autostretch` output as well. No behaviour changed
# with these tests; they record what the code *does* on the owner's pictures,
# which is not what the synthetic fixtures show.

def test_the_black_point_is_zero_on_a_genuinely_stretched_picture():
    """And that is by construction, not by accident — recorded so nobody reads
    the synthetic fixtures above as a description of the live behaviour.

    `autostretch` clips its darkest ~1 % to exactly zero, so the 1st percentile
    this module reads *lands inside that spike*: the suggestion comes back with
    black = 0.0 on any already-stretched image. Which is the honest answer —
    the shadows are already at black and there is nothing left to clip — but on
    the synthetic `_scene()` fixture the same call returns a black point around
    0.05–0.13, so a test written only against that fixture describes a picture
    the app never produces.
    """
    st = real_stretched_stack()
    assert_shadow_clip(st)
    pts = suggest_levels_points(st)
    assert pts is not None
    black, white = pts
    assert black == 0.0, f"black point {black} — the clip spike moved"
    # The white end still does real work: it sits below the star cores and well
    # above the sky, so the suggestion is a usable auto-levels, not a no-op.
    assert 0.5 < white < 1.0
    assert white > sky_truth(st)


def test_the_gamma_suggestion_still_aims_at_the_target_grey_after_a_real_stretch():
    """The midtone half is unaffected by the clip — it reads the *median*, which
    the spike cannot reach — so the one-click suggestion still lands the typical
    tone on the target grey."""
    st = real_stretched_stack()
    black, white = suggest_levels_points(st)
    gamma = suggest_levels_gamma(st, black, white)
    assert gamma is not None and gamma > 1.0
    med = float(np.median(st[np.isfinite(st)]))
    x = np.clip((med - black) / (white - black), 0.0, 1.0)
    assert float(x ** (1.0 / gamma)) == pytest.approx(GAMMA_TARGET, abs=0.01)
