"""Preview↔export parity for editor ops with pixel-sized parameters.

The live preview runs on a **decimated proxy** (≤1500 px of what may be a 150 MP
mosaic), the export runs on the real pixels. Any op parameter measured in
*pixels* therefore describes a different physical size on each — so it has to be
scaled by ``EditContext.scaled_px``, or the preview shows a different picture
from the one that gets saved.

These tests measure that on a **mosaic-shaped canvas at a real proxy step**,
which is the only place the gap is visible: a 1080p single field decimates by 1
(no proxy at all) or 2, where every one of these bugs is within a fraction of a
percent. The owner shoots mosaics, so the mosaic case is the real case.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.registry import EditContext, get_op

# A Seestar star is ~3 px FWHM at full resolution → sigma ≈ 1.27 px. At proxy
# step 3 it is a single pixel, which is exactly when a full-res detection FWHM
# stops finding anything.
_STAR_SIGMA_PX = 1.27
_PROXY_STEP = 3


# The OSC sensor's own cast — what a colour calibration exists to remove.
_SENSOR_CAST = (0.80, 1.0, 1.25)
# The *sky's* own colour, which is not the stars' colour: light pollution and
# airglow are warm. This is the whole reason `gray_star` and the starless
# `background_neutral` fallback are different answers — on a sky tinted the same
# as the stars they would agree, and a fixture like that could not show the bug.
_SKY_TINT = (1.18, 1.0, 0.88)


def _synth_osc_field(h: int = 1200, w: int = 1800, n_stars: int = 55,
                     seed: int = 11) -> np.ndarray:
    """A linear OSC frame: a *tinted* noisy sky, neutral stars, and a sensor cast.

    Star counts are deliberately of a Seestar's order rather than arbitrarily
    generous: detection efficiency on a decimated proxy is what this file
    measures, and a fixture dense enough to clear the 20-star floor even at 30 %
    efficiency cannot exhibit the bug at all.
    """
    rng = np.random.default_rng(seed)
    sky = 0.05
    grey = rng.normal(0.0, 0.0015, size=(h, w)).astype(np.float32)

    # Stars: small Gaussians, brightnesses spread over a decade so the finder has
    # a real dynamic range to rank. Neutral — a star's colour is the reference.
    rad = 6
    yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    kern = np.exp(-(xx ** 2 + yy ** 2) / (2 * _STAR_SIGMA_PX ** 2)).astype(np.float32)
    stars = np.zeros((h, w), dtype=np.float32)
    ys = rng.integers(rad + 2, h - rad - 2, n_stars)
    xs = rng.integers(rad + 2, w - rad - 2, n_stars)
    amps = 10 ** rng.uniform(-1.4, -0.2, n_stars).astype(np.float32)
    for y, x, a in zip(ys, xs, amps, strict=True):
        stars[y - rad:y + rad + 1, x - rad:x + rad + 1] += a * kern

    rgb = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3):
        rgb[..., c] = (sky * _SKY_TINT[c] + grey + stars) * _SENSOR_CAST[c]
    return np.ascontiguousarray(rgb, dtype=np.float32)


def _channel_gain(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """The per-channel multiplier a calibration applied (it scales channels)."""
    return np.array([
        float(np.nanmedian(after[..., c][before[..., c] > 0]
                           / before[..., c][before[..., c] > 0]))
        for c in range(3)
    ])


def _run_color_cal(rgb: np.ndarray, proxy_scale: float) -> tuple[np.ndarray, dict]:
    op = get_op("tone.color_calibrate")
    ctx = EditContext(proxy_scale=proxy_scale, is_proxy=proxy_scale > 1.0)
    out = op.apply(rgb, {"mode": "gray_star"}, ctx)
    return out, ctx.op_notes["tone.color_calibrate"]


# --------------------------------------------------------------------------- #
# tone.color_calibrate — the instance that changes the picture's *colour*
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def _osc_field() -> np.ndarray:
    return _synth_osc_field()


def test_the_preview_white_balances_the_same_way_the_export_does(_osc_field):
    """The proxy must reach the *same* white-balance path, and land near the same
    gains — before the geometry was scaled it silently used a different one.

    The proxy's stars are ~1 px wide, so a finder still looking for the full-res
    3 px FWHM found too few, fell through to the starless background-neutral
    fallback, and showed the user a colour the export never applies.
    """
    full = _osc_field
    proxy = np.ascontiguousarray(full[::_PROXY_STEP, ::_PROXY_STEP])

    exported, export_note = _run_color_cal(full, 1.0)
    previewed, preview_note = _run_color_cal(proxy, float(_PROXY_STEP))

    assert export_note["mode_used"] == "gray_star", "the export's own path changed"
    assert preview_note["mode_used"] == export_note["mode_used"], (
        f"preview used {preview_note['mode_used']!r} but the export uses "
        f"{export_note['mode_used']!r} — the preview is showing a colour the "
        "saved picture will not have")

    g_export = _channel_gain(full, exported)
    g_preview = _channel_gain(proxy, previewed)
    ratio = g_preview / g_export
    assert np.allclose(ratio, 1.0, atol=0.06), (
        f"preview/export gain ratio {ratio} — the preview's white balance differs "
        "from the export's by more than 6%")


def test_a_preview_that_agrees_with_the_export_raises_no_divergence_flag(_osc_field):
    """The flag is for a *real* divergence only — a preview that reached the same
    white balance must not nag the user about one."""
    proxy = np.ascontiguousarray(_osc_field[::_PROXY_STEP, ::_PROXY_STEP])
    _, note = _run_color_cal(proxy, float(_PROXY_STEP))
    assert note["mode_used"] == "gray_star"
    assert note["proxy_fallback"] is False


def test_the_export_path_is_bit_for_bit_unchanged(_osc_field):
    """The no-regression half: at proxy_scale 1 the scaling is the identity, so
    the picture the owner actually saves must be untouched by this fix."""
    from seestack.post.color_cal import ColorCalibrationOptions, calibrate_color

    out_op, _ = _run_color_cal(_osc_field, 1.0)
    # The engine call with the module's own defaults — i.e. exactly what the op
    # did before it learned to scale anything.
    out_default, _ = calibrate_color(
        _osc_field, None, ColorCalibrationOptions(enabled=True, mode="gray_star"))
    assert np.array_equal(np.nan_to_num(out_op), np.nan_to_num(out_default))


def test_a_proxy_too_coarse_for_a_star_solve_says_so_instead_of_diverging():
    """Scaling closes most of the gap, not all of it: a proxy can still be too
    coarse for a star solve the export manages. That case must be *flagged*, so
    the editor can caption it, rather than quietly showing a different colour."""
    # A star-poor field: comfortably solvable at full resolution, but striding it
    # away leaves the finder below its 20-star floor.
    full = _synth_osc_field(h=600, w=900, n_stars=40, seed=5)
    _, export_note = _run_color_cal(full, 1.0)
    assert export_note["mode_used"] == "gray_star", "the export must still solve"

    proxy = np.ascontiguousarray(full[::8, ::8])
    _, note = _run_color_cal(proxy, 8.0)
    assert note["mode_used"] not in ("gray_star", "gaia")
    assert note["proxy_fallback"] is True


def test_the_full_res_render_never_claims_a_proxy_fallback(_osc_field):
    """``proxy_fallback`` is about the *preview*; an export that falls back has
    not diverged from anything, so it must never raise the flag."""
    # A featureless frame: no stars anywhere, so even full-res falls back.
    flat = np.full((64, 64, 3), 0.05, dtype=np.float32)
    _, note = _run_color_cal(flat, 1.0)
    assert note["mode_used"] != "gray_star"
    assert note["proxy_fallback"] is False


def _synth_star_field(h: int = 1200, w: int = 1800, n_stars: int = 600,
                      n_hot: int = 40, seed: int = 7):
    """A dense neutral star field plus genuine single-site hot pixels.

    Density matters the same way it did for the colour fixture, in the other
    direction: this measures how many *real* stars a preview destroys, so the
    field has to carry enough of them to count. The hot pixels are single-channel
    single-pixel lifts — what the op exists to repair.
    """
    rng = np.random.default_rng(seed)
    sky = 0.05
    rad = 6
    yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    kern = np.exp(-(xx ** 2 + yy ** 2) / (2 * _STAR_SIGMA_PX ** 2)).astype(np.float32)
    stars = np.zeros((h, w), dtype=np.float32)
    ys = rng.integers(rad + 2, h - rad - 2, n_stars)
    xs = rng.integers(rad + 2, w - rad - 2, n_stars)
    amps = 10 ** rng.uniform(-1.4, -0.2, n_stars).astype(np.float32)
    for y, x, a in zip(ys, xs, amps, strict=True):
        stars[y - rad:y + rad + 1, x - rad:x + rad + 1] += a * kern

    rgb = np.empty((h, w, 3), dtype=np.float32)
    grey = rng.normal(0.0, 0.0015, size=(h, w)).astype(np.float32)
    for c in range(3):
        rgb[..., c] = sky + grey + stars
    hot = list(zip(rng.integers(5, h - 5, n_hot), rng.integers(5, w - 5, n_hot),
                   strict=True))
    for y, x in hot:
        rgb[y, x, 1] += 0.5
    return np.ascontiguousarray(rgb), (ys, xs, amps), hot


def _apply(op_id: str, rgb: np.ndarray, proxy_scale: float, params: dict) -> np.ndarray:
    op = get_op(op_id)
    ctx = EditContext(proxy_scale=proxy_scale, is_proxy=proxy_scale > 1.0, use_gpu=False)
    merged = dict(op.defaults())
    merged.update(params)
    return op.apply(rgb.copy(), merged, ctx)


@pytest.fixture(scope="module")
def _star_field():
    return _synth_star_field()


# --------------------------------------------------------------------------- #
# detail.sharpen and stars.reduce — the ops whose numbers the proxy can't keep
# --------------------------------------------------------------------------- #

def _added_detail(base: np.ndarray, sharpened: np.ndarray) -> float:
    """How much contrast the op added, as the sigma of what it changed."""
    return float(np.nanstd(sharpened - np.clip(base, 0.0, 1.0)))


@pytest.mark.parametrize("step,floor", [(4, 0.6), (6, 0.6)])
def test_the_sharpen_preview_shows_most_of_the_export_s_sharpening(
        _star_field, step, floor):
    """Auto's own 1.5 px radius, scaled onto a decimated proxy, used to floor at
    0.05 px — a Gaussian so narrow it is a near-delta, so the preview sharpened
    essentially nothing while the export sharpened for real.

    Measured before the fix: **22 %** of the export's added detail at proxy step 4
    and **0.3 %** at step 6. Some loss is inherent (the fine detail is not in the
    proxy), but two orders of magnitude is not a preview, it is a blank.
    """
    full, _stars, _hot = _star_field
    proxy = np.ascontiguousarray(full[::step, ::step])
    params = {"radius": 1.5, "amount": 1.0}

    previewed = _apply("detail.sharpen", proxy, float(step), params)
    exported = _apply("detail.sharpen", full, 1.0, params)
    export_seen = np.ascontiguousarray(exported[::step, ::step])

    ratio = _added_detail(proxy, previewed) / _added_detail(proxy, export_seen)
    assert floor <= ratio <= 1.4, (
        f"at proxy step {step} the preview shows {ratio:.0%} of the export's "
        "sharpening — a preview that is not the picture being saved")


def test_the_sharpen_export_is_bit_for_bit_unchanged(_star_field):
    """The proxy floor must never reach the saved picture: at ``proxy_scale`` 1 a
    radius the user deliberately set — including one below the new floor — has to
    be used exactly as given."""
    full = _star_field[0][:200, :200]
    for radius in (0.2, 1.5, 2.0):
        out = _apply("detail.sharpen", full, 1.0, {"radius": radius, "amount": 1.0})
        expected = _sharpen_by_hand(full, radius, 1.0)
        assert np.allclose(np.nan_to_num(out), np.nan_to_num(expected), atol=0), (
            f"the full-res render at radius {radius} is no longer the plain "
            "unsharp mask it has always been")


def _sharpen_by_hand(rgb: np.ndarray, radius: float, amount: float) -> np.ndarray:
    """The op's documented maths, written out — so the parity test above compares
    against the contract rather than against the implementation."""
    from scipy.ndimage import gaussian_filter

    src = np.clip(rgb, 0.0, 1.0)
    out = np.empty_like(src)
    for c in range(3):
        blurred = gaussian_filter(src[..., c], sigma=radius, mode="nearest")
        out[..., c] = src[..., c] + amount * (src[..., c] - blurred)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def test_the_floor_narrows_the_gap_without_retiring_the_advisory():
    """The floor recovers most of the missing sharpening, at a slightly coarser
    physical scale than the export — so the preview is closer but still not the
    export's picture, and the advisory has to keep firing on the *requested*
    scaled radius rather than the rendered one."""
    from seestack.edit.ops.detail import sharpen_understates_on_proxy

    assert sharpen_understates_on_proxy(1.5, 4.0) is True     # 0.38 px requested
    assert sharpen_understates_on_proxy(1.5, 6.0) is True     # 0.25 px requested
    assert sharpen_understates_on_proxy(4.0, 3.0) is False    # 1.33 px — honest
    assert sharpen_understates_on_proxy(1.5, 1.0) is False    # the export


# --------------------------------------------------------------------------- #
# stars.reduce — the advisory that pointed the wrong way
# --------------------------------------------------------------------------- #

def test_the_star_reduce_advisory_may_not_claim_a_direction_the_pixels_do_not_take(
        _star_field):
    """The caption used to claim a *direction*, so measure the direction.

    The old rule fired below ``size / proxy_scale < 1``, reasoning from where the
    erosion footprint clamps, and told the user the export would keep their stars
    *larger* than the preview showed. Sweeping the parameters that actually occur
    — star sizes 1-4 against proxy steps 2-5 — the preview lands anywhere from
    0.63x to 1.58x the export's removed star flux, and at the **default** size 2
    it straddles 1.0 with no consistent sign. No threshold in ``size /
    proxy_scale`` separates the directions either: 0.5 proxy px over-reduces at
    size 1 and under-reduces at size 2. So the flag must fire on every decimated
    preview, and the caption must name no direction.
    """
    from seestack.edit.ops.stars import star_reduce_differs_on_proxy

    full, _stars, _hot = _star_field
    exports = {size: _apply("stars.reduce", full, 1.0, {"size": size, "amount": 1.0})
               for size in (1, 2, 3, 4)}

    ratios: dict[tuple[int, int], float] = {}
    for step in (2, 3, 4, 5):
        proxy = np.ascontiguousarray(full[::step, ::step])
        for size in (1, 2, 3, 4):
            previewed = _apply("stars.reduce", proxy, float(step),
                               {"size": size, "amount": 1.0})
            export_seen = np.ascontiguousarray(exports[size][::step, ::step])
            removed_export = float(np.nansum(np.clip(proxy - export_seen, 0.0, None)))
            assert removed_export > 0.0, "the export must reduce stars — fixture drift"
            ratios[(step, size)] = float(
                np.nansum(np.clip(proxy - previewed, 0.0, None))) / removed_export

    # The preview goes *both* ways across ordinary settings, which is why no
    # single-direction caption can be honest.
    assert max(ratios.values()) > 1.05 and min(ratios.values()) < 0.95, (
        f"the sweep no longer straddles parity: {ratios}")

    # The old rule's own claim, checked case by case: at least one case where it
    # said "the preview over-reduces" and the pixels went the other way. (Measured:
    # sizes 2-3 on steps 3-4 under-reduce by 5-24% while `size / step < 1`.)
    mispredicted = [
        (step, size) for (step, size), r in ratios.items()
        if (size / step < 1.0) and r < 1.0
    ]
    assert mispredicted, (
        "the old size/proxy_scale < 1 rule now predicts every direction "
        f"correctly, so this test no longer pins anything: {ratios}")

    # The rule that replaced it: every decimated preview is flagged, none of them
    # is told which way it is wrong.
    for (step, size) in ratios:
        assert star_reduce_differs_on_proxy(size, float(step)) is True


def test_the_star_reduce_flag_is_quiet_on_the_export_and_with_the_op_off():
    from seestack.edit.ops.stars import star_reduce_differs_on_proxy

    assert star_reduce_differs_on_proxy(2.0, 1.0) is False
    assert star_reduce_differs_on_proxy(0.0, 4.0) is False
    assert star_reduce_differs_on_proxy(float("nan"), 4.0) is False
    assert star_reduce_differs_on_proxy(2.0, float("inf")) is False
