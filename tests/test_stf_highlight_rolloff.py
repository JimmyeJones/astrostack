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

from seestack.render.thumbnail import (
    _HIGHLIGHT_HEADROOM_MAX, _HIGHLIGHT_KNEE, _highlight_headroom_for,
    _highlight_rolloff, _reanchor_highlights, asinh_stretch, autostretch,
    highlight_knee_for,
)


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


def test_asinh_stretch_also_protects_the_core():
    """The manual asinh stretch shares the same hard-clip and gets the same
    rolloff: an HDR core keeps internal detail and stops short of pure white,
    while the sky stays untouched and bright stars still read as (near) white."""
    img = _hdr_target()
    old = asinh_stretch(img, protect_highlights=False)[..., 0]
    new = asinh_stretch(img, protect_highlights=True)[..., 0]

    # Fewer blown pixels and the core regains structure.
    assert np.mean(new >= 0.99) < np.mean(old >= 0.99)
    assert new[140:161, 140:161].std() > old[140:161, 140:161].std()
    assert new.max() < 1.0

    # The sky corner (below the knee) is bit-for-bit unchanged.
    assert np.array_equal(new[:30, :30], old[:30, :30])


# --- "Hold back highlights": an adjustable knee on the same shoulder ---------
#
# The fixed knee above rescues an ordinary core, but a very high-dynamic-range
# target (a compact galaxy core on a faint disk) can still read as washed out.
# ``highlight_protect`` walks the knee down so the shoulder starts earlier and
# compresses more of the bright range. It is 0 (off) everywhere by default, so
# every existing render is untouched; the Adaptive-Auto "Core blown out" cue is
# what moves it.


def test_knee_for_zero_is_exactly_the_historical_knee():
    """The default must be byte-identical, not merely close — every stretch in
    the app calls through this."""
    assert highlight_knee_for(0.0) == _HIGHLIGHT_KNEE
    assert highlight_knee_for() == _HIGHLIGHT_KNEE


def test_knee_for_is_monotone_and_bounded():
    """More protection = an earlier knee, floored so the shoulder never starts
    eating ordinary nebulosity."""
    knees = [highlight_knee_for(p) for p in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert all(b < a for a, b in zip(knees, knees[1:]))
    assert knees[-1] == pytest.approx(0.25)
    # Out of range clamps rather than extrapolating past the floor.
    assert highlight_knee_for(5.0) == knees[-1]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, -0.0])
def test_knee_for_treats_unusable_input_as_off(bad):
    """The value can arrive from a stored recipe or a taste profile, so a
    non-finite / negative one degrades to "no extra protection" rather than
    raising or producing a nonsense knee."""
    assert highlight_knee_for(bad) == _HIGHLIGHT_KNEE


def test_default_protect_is_byte_for_byte_the_old_render():
    """Passing the default explicitly changes nothing, in both stretches."""
    img = _hdr_target()
    assert np.array_equal(autostretch(img), autostretch(img, highlight_protect=0.0))
    assert np.array_equal(asinh_stretch(img), asinh_stretch(img, highlight_protect=0.0))


def test_protect_recovers_more_core_detail_than_the_fixed_knee():
    """The whole point: at full strength the core keeps a much stronger internal
    gradient and nothing clips to white."""
    img = _hdr_target()
    base = autostretch(img)[..., 0]
    held = autostretch(img, highlight_protect=1.0)[..., 0]
    core = (slice(140, 161), slice(140, 161))
    assert held[core].std() > 2.0 * base[core].std()
    assert np.mean(held >= 0.99) < np.mean(base >= 0.99)
    assert held.max() < base.max()


def test_protect_leaves_the_sky_exactly_where_it_was():
    """It may only move tones *above* the knee — the sky still lands on the same
    grey, so "hold the core back" never doubles as a brightness change."""
    img = _hdr_target()
    base = autostretch(img)
    held = autostretch(img, highlight_protect=1.0)
    assert np.array_equal(held[:30, :30], base[:30, :30])
    assert np.median(held[:30, :30]) == pytest.approx(np.median(base[:30, :30]))
    # Same for the manual asinh curve.
    assert np.array_equal(
        asinh_stretch(img, highlight_protect=1.0)[:30, :30],
        asinh_stretch(img)[:30, :30],
    )


def test_protect_is_monotone_in_strength():
    """More protection never blows *more* of the core — the knob has one honest
    direction."""
    img = _hdr_target()
    blown = [
        float(np.mean(autostretch(img, highlight_protect=p)[..., 0] >= 0.99))
        for p in (0.0, 0.5, 1.0)
    ]
    assert blown[0] >= blown[1] >= blown[2]


# --- the shoulder has to survive the tone curve above it --------------------
#
# Measured (2026-09-11): on a frame whose sky sits at a ten-thousandth of the
# normalization ceiling the midtones transfer solves to m ≈ 0.001, which puts the
# knee at display 0.9996 — so the *entire* shoulder, the thing "hold back
# highlights" moves, rendered inside the last 0.0004 of the display range and the
# slider changed the picture by less than a thousandth at any strength. The knee
# walking 0.70 → 0.25 only moved that to 0.003. `_reanchor_highlights` reserves
# the shoulder a visible share of the finished range instead, taking it from the
# mid-tones and never from the sky.


def _high_contrast_target(h=300, w=300):
    """A huge bright core over a very faint sky — the shape whose sky median
    lands at a ten-thousandth of the 99.5th-percentile ceiling, which is what
    collapses the midtones transfer's top end."""
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = (yy - h / 2) ** 2 + (xx - w / 2) ** 2
    core = 6e6 * np.exp(-r2 / (2 * 22.0**2))
    rng = np.random.default_rng(0)
    base = 1000.0 + 1500.0 * np.exp(-r2 / (2 * 60.0**2)) + core
    base = base + rng.normal(0.0, 20.0, size=(h, w))
    return np.stack([base, base, base], axis=-1).astype(np.float32)


def test_protect_reopens_a_core_the_midtones_transfer_used_to_flatten():
    """The fail-before case: at strength 0 the core is a solid white plateau, and
    before this fix it stayed one at *every* strength."""
    img = _high_contrast_target()
    base = autostretch(img)[..., 0]
    held = autostretch(img, highlight_protect=1.0)[..., 0]

    # Strength 0 really is the blown picture this is about.
    assert np.mean(base >= 0.99) > 0.05
    # ...and the knob clears it. (Before: 8.65 % blown at 0, 0.5 *and* 1.0.)
    assert np.mean(held >= 0.99) < 0.01
    # The core keeps a gradient worth looking at, not a thousandth of one.
    core = (slice(120, 181), slice(120, 181))
    assert held[core].std() > 20.0 * base[core].std()
    assert held[core].max() - held[core].min() > 0.05


def test_the_shoulder_gets_its_reserved_share_of_the_display_range():
    """The promise is specific: at full strength the shoulder holds
    ``_HIGHLIGHT_HEADROOM_MAX`` of the finished range, so what was 0.0004 wide is
    now 0.20 wide."""
    img = _high_contrast_target()
    for p in (0.5, 1.0):
        held = autostretch(img, highlight_protect=p)[..., 0]
        # Nothing above the shoulder's floor, and the brightest pixel close to
        # (but below) white: the whole band is in use.
        floor = 1.0 - _highlight_headroom_for(p)
        assert held.max() < 1.0
        assert held.max() > floor
        # The core spans a real part of that band rather than sitting on it.
        core = held[120:181, 120:181]
        assert core.max() - core.min() > 0.3 * _highlight_headroom_for(p)


def test_reanchoring_never_moves_the_sky():
    """It takes its room from the mid-tones, never from the background — a sky
    corner is bit-for-bit identical at every strength."""
    img = _high_contrast_target()
    base = autostretch(img)
    for p in (0.05, 0.5, 1.0):
        held = autostretch(img, highlight_protect=p)
        assert np.array_equal(held[:40, :40], base[:40, :40])


def test_reanchoring_is_monotone_in_strength():
    """The knob keeps one honest direction on this frame too: more protection
    never blows more of the core, at every step the slider offers."""
    img = _high_contrast_target()
    prev_blown = 1.0
    for p in (0.0, 0.05, 0.25, 0.5, 0.75, 1.0):
        blown = float(np.mean(autostretch(img, highlight_protect=p)[..., 0] >= 0.99))
        assert blown <= prev_blown + 1e-12
        prev_blown = blown


def test_reanchoring_does_not_shift_the_core_s_colour():
    """Each channel is re-anchored on its own numbers (its own sky median, its own
    `m`), so the risk worth pinning is the one a per-channel curve carries: a grey
    core must stay grey, and a coloured core must get its colour *back* rather
    than swing hue.

    Measured on a core whose channels are 1.0 / 0.75 / 0.6 over unequal sky
    levels: the blown core rendered as R:G:B = 1 : 0.995 : 0.999 (i.e. white,
    which is what "blown" means) and now renders 1 : 0.987 : 0.976 — more of its
    own colour, by 0.023 at most."""
    img = _high_contrast_target()
    core = autostretch(img, highlight_protect=1.0)[120:181, 120:181]
    assert np.allclose(core[..., 0], core[..., 1], atol=1e-6)
    assert np.allclose(core[..., 1], core[..., 2], atol=1e-6)

    yy, xx = np.mgrid[0:300, 0:300]
    r2 = (yy - 150) ** 2 + (xx - 150) ** 2
    rng = np.random.default_rng(2)
    chans = [
        sky + 1500.0 * c * np.exp(-r2 / (2 * 80.0**2))
        + 40000.0 * c * np.exp(-r2 / (2 * 30.0**2))
        + rng.normal(0.0, 20.0, size=(300, 300))
        for sky, c in zip((1000.0, 1050.0, 980.0), (1.0, 0.75, 0.6))
    ]
    colour = np.stack(chans, axis=-1).astype(np.float32)

    def core_ratio(out):
        mean = out[140:161, 140:161].reshape(-1, 3).mean(axis=0)
        return mean / max(float(mean.max()), 1e-9)

    before = core_ratio(autostretch(colour))
    after = core_ratio(autostretch(colour, highlight_protect=1.0))
    assert np.max(np.abs(after - before)) < 0.05          # no hue swing
    assert after[1] < before[1] and after[2] < before[2]   # less white, more colour


def test_reanchoring_declines_when_the_shoulder_already_has_room(monkeypatch):
    """An ordinary compact-core frame already gives the shoulder a fifth of the
    display range, so there is nothing to take from the mid-tones — the render is
    byte-for-byte what the knee walk alone produces.

    Pinned against a render with the re-anchoring switched off entirely, so this
    says "it did nothing here" rather than "it did something small"."""
    from seestack.render import thumbnail

    img = _hdr_target()
    real = {p: autostretch(img, highlight_protect=p) for p in (0.25, 1.0)}
    monkeypatch.setattr(thumbnail, "_reanchor_highlights", lambda y, **kw: y)
    for p, held in real.items():
        assert np.array_equal(held, autostretch(img, highlight_protect=p))


def test_headroom_for_is_zero_off_and_clamped_on():
    """Same input contract as the knee it rides with: 0 (and anything unusable)
    reserves nothing, so the default render is byte-for-byte historical."""
    assert _highlight_headroom_for(0.0) == 0.0
    assert _highlight_headroom_for() == 0.0
    for bad in (float("nan"), float("inf"), -1.0):
        assert _highlight_headroom_for(bad) == 0.0
    assert _highlight_headroom_for(1.0) == pytest.approx(_HIGHLIGHT_HEADROOM_MAX)
    assert _highlight_headroom_for(5.0) == _highlight_headroom_for(1.0)
    assert _highlight_headroom_for(0.5) == pytest.approx(_HIGHLIGHT_HEADROOM_MAX / 2)


def test_reanchor_helper_declines_rather_than_guessing():
    """Every case where there is nothing to win, or no room to win it in, returns
    the input untouched — including the one that would divide by zero."""
    y = np.linspace(0.0, 1.0, 101)
    same = dict(knee_display=0.9996, anchor=0.26)
    # No headroom asked for.
    assert np.array_equal(_reanchor_highlights(y, headroom=0.0, **same), y)
    # The shoulder already holds more than the headroom.
    assert np.array_equal(
        _reanchor_highlights(y, knee_display=0.5, anchor=0.2, headroom=0.2), y)
    # The sky's ceiling is at or above where the shoulder starts — the only way
    # to make room would be to move the background.
    assert np.array_equal(
        _reanchor_highlights(y, knee_display=0.9996, anchor=0.9996, headroom=0.2), y)
    assert np.array_equal(
        _reanchor_highlights(y, knee_display=0.9996, anchor=0.85, headroom=0.2), y)
    # Non-finite inputs degrade to "do nothing" rather than raising.
    assert np.array_equal(
        _reanchor_highlights(y, knee_display=float("nan"), anchor=0.2,
                             headroom=0.2), y)


def test_reanchor_helper_keeps_every_pixel_in_order():
    """Ordering is the one thing a tone curve may never break — a brighter pixel
    must stay brighter, across both band joins."""
    y = np.linspace(0.0, 1.0, 20001)
    out = _reanchor_highlights(y, knee_display=0.9996, anchor=0.26, headroom=0.2)
    assert np.all(np.diff(out) >= 0.0)
    assert out.min() == 0.0 and out.max() <= 1.0


def test_reanchor_helper_is_continuous_at_both_joins():
    """A tone curve with a step in it would show as a hard edge in a smooth
    gradient — the two band joins must meet."""
    knee_d, anchor, head = 0.9996, 0.26, 0.2
    eps = 1e-7
    probe = np.array([anchor - eps, anchor, anchor + eps,
                      knee_d - eps, knee_d, knee_d + eps])
    out = _reanchor_highlights(probe, knee_display=knee_d, anchor=anchor,
                               headroom=head)
    assert out[0] == pytest.approx(anchor, abs=1e-6)
    assert out[1] == pytest.approx(anchor)          # the anchor itself is fixed
    assert out[2] == pytest.approx(anchor, abs=1e-6)
    assert out[4] == pytest.approx(1.0 - head)      # the knee lands on the floor
    assert out[3] == pytest.approx(1.0 - head, abs=1e-6)
    assert out[5] == pytest.approx(1.0 - head, abs=1e-4)
    assert np.all(np.diff(out) >= 0.0)


def test_the_asinh_curve_keeps_its_own_shoulder_and_so_declines(monkeypatch):
    """The manual curve asks the same question and gets a different answer, which
    is why the guard is shared rather than STF-only.

    Measured on the same frame that collapses the midtones transfer to a 0.0004
    shoulder: asinh is log-like, so its knee lands at display 0.60 at full
    strength and the shoulder keeps **0.40** of the range unaided. So the
    re-anchoring declines and the asinh render is exactly the knee walk — while
    the guard stays in the path, in case a stretch/black combination ever does
    squeeze the shoulder out."""
    from seestack.render import thumbnail

    img = _high_contrast_target()
    real = {p: asinh_stretch(img, highlight_protect=p) for p in (0.0, 0.5, 1.0)}
    monkeypatch.setattr(thumbnail, "_reanchor_highlights", lambda y, **kw: y)
    for p, held in real.items():
        assert np.array_equal(held, asinh_stretch(img, highlight_protect=p))
    assert np.array_equal(real[0.0], asinh_stretch(img))
