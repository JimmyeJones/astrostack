"""STF autostretch must not blow a bright HDR core out to a flat white blob.

Owner-reported (2026-07): the centre of an M31 stack renders overblown after the
switch to the STF autostretch as the default/Auto view. Root cause: the STF
stretch hard-clipped every value above its robust 99.5th-percentile normalization
ceiling to ``1.0``, so a bright compact core (which sits *above* that ceiling)
lost all internal structure and rendered as featureless white.

These tests reproduce that on a synthetic high-dynamic-range target (a bright
compact Gaussian core on a faint extended disk on sky) and pin the fix: the
highlight rolloff keeps the core's internal gradient while leaving the sky and
mid-tones bit-for-bit unchanged.
"""

import numpy as np
import pytest

from seestack.render.thumbnail import _highlight_rolloff, autostretch


def _hdr_target(h=300, w=300):
    """Bright compact core (HDR) on a faint extended disk on a noisy sky —
    the M31-style shape that blows out."""
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = (yy - h / 2) ** 2 + (xx - w / 2) ** 2
    disk = 1500.0 * np.exp(-r2 / (2 * 60.0**2))      # faint extended disk
    core = 60000.0 * np.exp(-r2 / (2 * 4.0**2))       # bright compact core
    rng = np.random.default_rng(0)
    base = 1000.0 + disk + core + rng.normal(0.0, 20.0, size=(h, w))
    return np.stack([base, base, base], axis=-1).astype(np.float32)


def test_hard_clip_blows_the_core_to_flat_white():
    """Fail-before guard: with the rolloff disabled the core is a flat white blob
    (zero internal gradient) — the regression this fix removes."""
    out = autostretch(_hdr_target(), protect_highlights=False)[..., 0]
    core = out[146:155, 146:155]                      # central 9x9, at the peak
    assert core.max() >= 0.999                         # saturated
    assert core.std() < 1e-4                           # no structure left


def test_highlight_rolloff_recovers_core_detail():
    """With highlight protection on, the same core keeps a resolvable gradient
    and stops short of pure white."""
    img = _hdr_target()
    old = autostretch(img, protect_highlights=False)[..., 0]
    new = autostretch(img, protect_highlights=True)[..., 0]

    # Fewer pixels are pushed to pure white.
    assert np.mean(new >= 0.99) < np.mean(old >= 0.99)

    # The core region regains internal structure it had none of before.
    old_core = old[140:161, 140:161]
    new_core = new[140:161, 140:161]
    assert new_core.std() > old_core.std()
    assert new_core.std() > 1e-3

    # The brightest pixel no longer clips to exactly 1.0.
    assert new.max() < 1.0


def test_rolloff_leaves_background_and_midtones_untouched():
    """The rolloff only ever touches highlights above the knee — the sky and
    mid-tones must be bit-for-bit identical with and without it."""
    img = _hdr_target()
    old = autostretch(img, protect_highlights=False)
    new = autostretch(img, protect_highlights=True)
    # A sky corner (well below the knee) is unchanged.
    assert np.array_equal(new[:30, :30], old[:30, :30])
    # Every pixel the two differ on is a bright highlight in the old render.
    changed = np.abs(new - old).max(axis=2) > 0
    assert np.all(old[..., 0][changed] > 0.5)


def test_highlight_rolloff_helper_is_monotonic_and_bounded():
    """The rolloff maps [0, +inf) monotonically into [0, 1): below-knee passes
    through, above-knee is compressed and asymptotes to (but never reaches) 1."""
    x = np.linspace(0.0, 50.0, 5000)
    y = _highlight_rolloff(x, knee=0.7)
    assert np.all(np.diff(y) >= 0.0)                   # monotonic non-decreasing
    assert np.all(y < 1.0)                              # never reaches white
    below = x <= 0.7
    assert np.allclose(y[below], x[below])             # below-knee unchanged
    # A value far into the highlights lands very close to (but below) 1.
    assert _highlight_rolloff(np.array([1000.0]), knee=0.7)[0] > 0.999


def test_negative_inputs_floor_at_black():
    """Values below the shadow floor (negative after normalization) clamp to 0."""
    y = _highlight_rolloff(np.array([-5.0, -0.1, 0.0, 0.3]), knee=0.7)
    assert y[0] == 0.0 and y[1] == 0.0
    assert y[3] == pytest.approx(0.3)
