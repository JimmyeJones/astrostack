"""The per-frame flatten's object mask must not be starved by light pollution.

`_build_object_mask_for_bg` used to threshold the luminance against *whole-frame*
sigma-clipped statistics. On the very frames the flatten exists for — a raw
Seestar sub still carrying its light-pollution gradient — the global sigma is
dominated by the gradient, so the threshold sat above the dim side and below the
bright side and the bright half was classified as "object", i.e. excluded from
the fit meant to remove it. Measured on a realistic S30 sub, mask coverage
dim->bright fifth was 0.4 %..59.7 % (a 150x skew) on an 18 % gradient; and on a
*gradient-free* sub a 2-sigma threshold plus 4 px dilation swallowed 60 % of the
frame outright.

Consequence, and why this is a stacking-engine bug and not cosmetics: the fit
never saw the gradient it was meant to remove, so every sub kept a *systematic*
same-sign residual tilt that averaging (and dither) cannot remove — the leftover
stack tilt behind the "one corner is washed out" complaint about the finished
picture.

These tests pin the three properties of the fix: local thresholding, dropping
noise-sized detections, and a block-averaged pass so an honest sky fit doesn't
eat the faint nebula it can no longer see past.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from seestack.bg.per_frame import (  # noqa: E402
    BackgroundOptions,
    _build_object_mask_for_bg,
    subtract_background,
)

SKY = (1050.0, 1650.0, 820.0)   # OSC sky level per channel (ADU), Seestar-ish
SIGMA_G = 45.0                  # per-sub noise in G


def _lp_sub(h=240, w=400, *, lp=0.18, seed=0, nebula=True, n_stars=40):
    """A realistic *raw* OSC sub: sky + light-pollution ramp + stars + nebula."""
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((h, w), dtype=np.float32)
    ramp = ((xx / (w - 1)) * 0.75 + (yy / (h - 1)) * 0.25).astype(np.float32)
    img = np.empty((h, w, 3), dtype=np.float32)
    for c, sky in enumerate(SKY):
        img[..., c] = sky * (1.0 + lp * ramp)

    prof = np.exp(-(((yy - h * 0.42) / (h * 0.16)) ** 2
                    + ((xx - w * 0.58) / (w * 0.13)) ** 2)).astype(np.float32)
    if nebula:
        for c, amp in enumerate((55.0, 18.0, 32.0)):    # faint, and strongly red
            img[..., c] += prof * amp

    r = 3
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    stamp = np.exp(-(dy * dy + dx * dx) / 2.1).astype(np.float32)
    for y, x, amp in zip(rng.integers(r, h - r, n_stars),
                         rng.integers(r, w - r, n_stars),
                         rng.uniform(400.0, 20000.0, n_stars), strict=True):
        img[y - r:y + r + 1, x - r:x + r + 1, :] += (amp * stamp)[:, :, None]

    for c, sky in enumerate(SKY):
        scale = SIGMA_G * np.sqrt(sky / SKY[1])
        img[..., c] += rng.normal(scale=scale, size=(h, w)).astype(np.float32)
    return img, prof


def _coverage_by_fifth(mask):
    edges = np.linspace(0, mask.shape[1], 6).astype(int)
    return [float(mask[:, edges[i]:edges[i + 1]].mean()) for i in range(5)]


def test_object_mask_is_not_starved_by_a_sky_gradient():
    """The bright side of a light-polluted sub must not read as 'object'.

    Before the fix this was 1 % dim vs 58 % bright on the full-size scene — the
    gradient hid from its own fit.
    """
    sub, _ = _lp_sub(lp=0.18, seed=3)
    cov = _coverage_by_fifth(_build_object_mask_for_bg(sub, 2.0, 4))
    dim, bright = cov[0], cov[-1]
    assert bright < max(2.0 * dim, 0.05), (
        f"bright fifth masked {bright:.1%} vs dim {dim:.1%}: the sky fit is "
        "starved exactly where the gradient is")


def test_object_mask_ignores_noise_sized_detections():
    """A gradient-free noisy sub must not have most of its sky masked away.

    A 2-sigma threshold flags ~2 % of pixels *anywhere*; dilating those
    single-pixel spikes by 4 px is what took the mask to 60 % of the frame.
    """
    sub, _ = _lp_sub(lp=0.0, seed=5, nebula=False)
    mask = _build_object_mask_for_bg(sub, 2.0, 4)
    assert mask.mean() < 0.35, f"mask covers {mask.mean():.1%} of a plain sky"


def test_object_mask_still_finds_the_stars_and_the_nebula():
    """Dropping noise and detrending must not stop it masking real structure."""
    sub, prof = _lp_sub(lp=0.08, seed=11)
    mask = _build_object_mask_for_bg(sub, 2.0, 4)
    # The nebula core is invisible per-pixel in one sub (well under 1 sigma); the
    # block-averaged pass is what has to catch it.
    assert mask[prof > 0.6].mean() > 0.8
    # And the brightest stars, which are far above the noise.
    bright = sub[..., 1] > np.percentile(sub[..., 1], 99.9)
    assert mask[bright].mean() > 0.9


def _sky_tilt(stack):
    """Right-eighth minus left-eighth sky median per channel, below the nebula."""
    h, w = stack.shape[:2]
    rows = slice(int(h * 0.80), int(h * 0.97))
    left, right = stack[rows, : w // 8], stack[rows, -w // 8:]
    return [float(np.median(right[..., c]) - np.median(left[..., c])) for c in range(3)]


def test_flattened_subs_stack_without_a_systematic_sky_tilt():
    """The end-to-end acceptance criterion: what survives into the stack.

    Because the per-sub fit bias is *systematic* (same sign in every sub), it
    survives averaging — so a stack of flattened subs is the honest measure of
    the mask fix. Measured on the full-size scene: |tilt| summed over R/G/B fell
    from 103 ADU to 18 ADU on an 18 % gradient.
    """
    acc = None
    for i in range(3):
        sub, _ = _lp_sub(480, 800, lp=0.18, seed=200 + i)
        flat = subtract_background(sub, BackgroundOptions(), use_gpu=False)
        acc = flat if acc is None else acc + flat
    tilt = _sky_tilt(acc / 3.0)
    # 136 ADU before the fix on this scene (a coarser mesh than the full-size
    # frame's, so the surviving mesh-scale bias is larger here than the 18 ADU
    # measured at 1080x1920 — the *starvation* half is what this pins).
    assert sum(abs(t) for t in tilt) < 90.0, f"stack still tilted {tilt} ADU"


def test_flatten_keeps_the_faint_nebula_on_a_light_polluted_sub():
    """An honest sky fit must not absorb the faint nebula it is fitting around.

    With the mask starved by the gradient the fit was garbage *and* it destroyed
    the nebula's colour (G kept ~10 % of its amplitude, R ~35 %), so the target
    came out of the flatten discoloured. The block-averaged extended pass keeps
    all three channels together.
    """
    sub, prof = _lp_sub(480, 800, lp=0.18, seed=13)
    flat = subtract_background(sub, BackgroundOptions(), use_gpu=False)
    core, sky = prof > 0.8, prof < 0.05
    for c, amp in enumerate((55.0, 18.0, 32.0)):
        kept = float(np.median(flat[..., c][core]) - np.median(flat[..., c][sky]))
        assert kept > 0.55 * amp, (
            f"channel {c} kept only {kept:.1f} of {amp:.1f} ADU of nebula")


def test_extended_pass_leaves_a_plain_gradient_sky_unmasked():
    """The extended pass must not mistake the light-pollution ramp for an object.

    Its threshold has a floor at half a sub's sigma for exactly this reason: a
    block-averaged frame has ~8x less noise, so a bare sigma threshold there
    would flag ordinary trend residual and starve the fit all over again.
    """
    sub, _ = _lp_sub(lp=0.18, seed=17, nebula=False, n_stars=5)
    mask = _build_object_mask_for_bg(sub, 2.0, 4)
    assert mask.mean() < 0.25, f"mask covers {mask.mean():.1%} of a plain LP sky"


def test_proxy_scale_survives_the_box_size_clamp():
    """``for_image_size`` must not drop a field (it hand-copied them before)."""
    opts = BackgroundOptions(box_size=512, proxy_scale=4.0, mode="luminance")
    clamped = opts.for_image_size(100, 100)
    assert clamped.box_size < 512
    assert clamped.proxy_scale == 4.0
    assert clamped.mode == "luminance"
