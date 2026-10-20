"""The Moon/Sun stacker drizzles when it is worth it (owner ask, 2026-10-20).

A lucky stack keeps hundreds of frames and seeing moves each one a fraction of
a pixel, so dropping every kept frame's *native* colour samples onto a ×1.5
grid at its measured shift recovers detail the debayer interpolates away. These
pin the three things that make it "Auto, when worth it" rather than a knob:
it is measurably sharper on a raw capture that really moved; it declines — and
says why — when there are too few frames or the frames never moved; and it is
off unless asked for, so an omitted option is the picture every earlier
version made.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.io.fits_loader import bilinear_debayer
from seestack.stack.accumulator import WeightedSumAccumulator
from seestack.video import drizzle as lucky_drizzle
from seestack.video.drizzle import (
    LUCKY_DRIZZLE_MIN_FRAMES,
    LuckyDrizzle,
    _lattice_span,
    decide,
    planned,
    sentence,
)
from seestack.video.lucky import LuckyOptions, _shift_frame
from tests.videosynth import (
    _CFA_LAYOUTS,
    JITTER_DISK_RADIUS,
    JITTER_H,
    JITTER_W,
    jitter_detail,
    solar_raw_jittered_video,
)


def _rmse_against_truth(img: np.ndarray, truth: np.ndarray, margin: int) -> float:
    g = img[margin:-margin, margin:-margin, 1]
    t = truth[margin:-margin, margin:-margin]
    ok = np.isfinite(g)
    assert ok.mean() > 0.99
    return float(np.sqrt(np.mean((g[ok] - t[ok]) ** 2)))


# --- the accumulator itself (no decoder) -------------------------------------

@pytest.mark.parametrize("pattern", ["RGGB", "BGGR", "GRBG", "GBRG"])
def test_the_debayer_keeps_every_native_sample(pattern):
    """The Bayer drizzle reads each site's own colour back out of the debayered
    frame instead of decoding twice — true only because the bilinear debayer
    fills the *missing* sites and leaves the sampled ones alone."""
    rng = np.random.default_rng(0)
    mosaic = rng.random((24, 32)).astype(np.float32)
    rgb = bilinear_debayer(mosaic, pattern=pattern)
    tl, tr, bl, br = (c.lower() for c in _CFA_LAYOUTS[pattern])
    ch = {"r": 0, "g": 1, "b": 2}
    for (oy, ox), colour in zip(((0, 0), (0, 1), (1, 0), (1, 1)), (tl, tr, bl, br), strict=True):
        np.testing.assert_array_equal(
            rgb[oy::2, ox::2, ch[colour]], mosaic[oy::2, ox::2])


def test_lattice_span_matches_brute_force():
    for start in range(-9, 12):
        for n in (0, 1, 4, 7):
            for limit in (0, 1, 5, 13):
                want = [i for i in range(n) if 0 <= start + 3 * i < limit]
                lo, hi = _lattice_span(start, n, 3, limit)
                assert list(range(lo, hi)) == want, (start, n, limit)


def test_a_jittered_raw_capture_drizzles_much_closer_to_the_truth():
    """**The point of the feature**, with the shifts known exactly so only the
    reconstruction is being measured: 250 jittered raw frames of detail finer
    than one colour's Bayer sampling. Shift-and-average of the debayered frames
    (today's path) and the ×1.5 Bayer drizzle are compared against the scene
    itself on each one's own grid."""
    h, w, pattern = 96, 128, "GBRG"
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)

    driz = LuckyDrizzle(h, w, pattern=pattern)
    plain = WeightedSumAccumulator((h, w, 3), dtype=np.float32)
    for _ in range(250):
        jy, jx = rng.uniform(-3, 3, 2)
        # A flat-transmission sensor, so every channel is the scene itself.
        mosaic = ((0.5 + 0.3 * jitter_detail(yy - jy, xx - jx))
                  + rng.normal(0, 0.02, (h, w))).astype(np.float32)
        rgb = bilinear_debayer(mosaic, pattern=pattern)
        driz.add(rgb, -jy, -jx)
        plain.add(_shift_frame(rgb, -jy, -jx))

    d = driz.result()
    assert d.shape == (144, 192, 3)
    oy, ox = np.mgrid[0:d.shape[0], 0:d.shape[1]].astype(np.float64)
    s = driz.scale
    rmse_d = _rmse_against_truth(d, 0.5 + 0.3 * jitter_detail((oy + 0.5) / s - 0.5, (ox + 0.5) / s - 0.5), 15)
    rmse_p = _rmse_against_truth(plain.result(), 0.5 + 0.3 * jitter_detail(yy, xx), 10)
    # Measured 0.050 vs 0.140: the detail's amplitude is 0.3, so the plain stack
    # has lost most of it and the drizzle kept most of it.
    assert rmse_d < 0.5 * rmse_p, (rmse_d, rmse_p)


def test_a_flat_scene_stays_flat_and_only_the_edges_go_uncovered():
    h, w = 40, 60
    driz = LuckyDrizzle(h, w, pattern="RGGB")
    rng = np.random.default_rng(2)
    frame = np.full((h, w, 3), 0.25, dtype=np.float32)
    for _ in range(30):
        driz.add(frame, *rng.uniform(-1.5, 1.5, 2))
    out = driz.result()
    finite = np.isfinite(out)
    assert finite.all(axis=-1).mean() > 0.9
    # NaN is all-or-nothing per pixel: never a pixel with one colour missing.
    assert (finite.all(axis=-1) == finite.any(axis=-1)).all()
    np.testing.assert_allclose(out[finite], 0.25, atol=1e-5)
    assert finite[5:-5, 5:-5].all()


def test_a_colour_stream_deposits_all_three_channels_everywhere():
    driz = LuckyDrizzle(20, 30, pattern=None)
    frame = np.zeros((20, 30, 3), dtype=np.float32)
    frame[..., 0], frame[..., 1], frame[..., 2] = 0.1, 0.5, 0.9
    driz.add(frame, 0.0, 0.0)
    out = driz.result()
    inner = out[3:-3, 3:-3]
    assert np.isfinite(inner).all()
    np.testing.assert_allclose(inner.reshape(-1, 3).mean(axis=0), (0.1, 0.5, 0.9), atol=1e-5)


def test_a_scale_off_the_half_pixel_lattice_is_refused():
    with pytest.raises(ValueError):
        LuckyDrizzle(10, 10, pattern=None, scale=1.3)


# --- the decision ------------------------------------------------------------

def test_what_is_known_before_pass_two():
    ok = {"enabled": True, "align": True, "n_keep": LUCKY_DRIZZLE_MIN_FRAMES,
          "height": 1080, "width": 1920}
    assert planned(**ok) is None
    assert planned(**{**ok, "enabled": False}) == lucky_drizzle.REASON_OFF
    assert planned(**{**ok, "align": False}) == lucky_drizzle.REASON_NOT_ALIGNED
    assert planned(**{**ok, "n_keep": LUCKY_DRIZZLE_MIN_FRAMES - 1}) == lucky_drizzle.REASON_TOO_FEW_FRAMES
    assert planned(**{**ok, "height": 4000, "width": 6000}) == lucky_drizzle.REASON_TOO_BIG


def test_the_decision_after_pass_two():
    rng = np.random.default_rng(3)
    n = LUCKY_DRIZZLE_MIN_FRAMES
    moved = [tuple(rng.uniform(-4, 4, 2)) for _ in range(n)]
    assert decide(moved, n_stacked=n).drizzled
    assert decide(moved, n_stacked=n).scale == 1.5
    # Whole-pixel steps only: every sample keeps one phase — no new detail.
    stepped = [(float(rng.integers(-5, 5)), float(rng.integers(-5, 5))) for _ in range(n)]
    d = decide(stepped, n_stacked=n)
    assert d.reason == lucky_drizzle.REASON_TOO_LITTLE_MOTION and d.scale == 1.0
    # Moved on one axis only is still "no" — both axes have to vary.
    one_axis = [(float(rng.uniform(-4, 4)), 0.0) for _ in range(n)]
    assert decide(one_axis, n_stacked=n).reason == lucky_drizzle.REASON_TOO_LITTLE_MOTION
    # A wobble of a few hundredths of a pixel is the aligner's own noise, not motion.
    wobble = [tuple(rng.uniform(-0.15, 0.15, 2)) for _ in range(n)]
    assert decide(wobble, n_stacked=n).reason == lucky_drizzle.REASON_TOO_LITTLE_MOTION
    assert decide(moved, n_stacked=n - 1).reason == lucky_drizzle.REASON_TOO_FEW_FRAMES


def test_each_outcome_reads_as_one_plain_sentence():
    yes = lucky_drizzle.DrizzleDecision(lucky_drizzle.REASON_DRIZZLED, 1.5, 0.29)
    assert sentence(yes, 412).startswith("Drizzled to 1.5× the camera's resolution using 412 frames")
    few = lucky_drizzle.DrizzleDecision(lucky_drizzle.REASON_TOO_FEW_FRAMES, 1.0)
    assert sentence(few, 87).startswith("Kept at camera resolution")
    assert "87" in sentence(few, 87) and str(LUCKY_DRIZZLE_MIN_FRAMES) in sentence(few, 87)
    still = lucky_drizzle.DrizzleDecision(lucky_drizzle.REASON_TOO_LITTLE_MOTION, 1.0, 0.0)
    assert "barely moved" in sentence(still, 300)
    # Off is the picture every earlier version made — nothing to explain.
    assert sentence(lucky_drizzle.DrizzleDecision(lucky_drizzle.REASON_OFF, 1.0), 300) == ""
    assert sentence(None, 300) == ""


def test_the_engine_leaves_drizzle_off_unless_asked():
    """An omitted option must reproduce the picture an earlier version made."""
    assert LuckyOptions().drizzle is False


def test_the_extra_time_estimate_scales_with_frames_and_size():
    one = lucky_drizzle.extra_seconds(100, 1080, 1920)
    assert one > 0
    assert lucky_drizzle.extra_seconds(200, 1080, 1920) == pytest.approx(2 * one)
    assert lucky_drizzle.extra_seconds(0, 1080, 1920) == 0.0


# --- through the real decoder and the real stacker ---------------------------

ffmpeg_only = pytest.mark.skipif(
    not __import__("seestack.video", fromlist=["ffmpeg_available"]).ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)

def _detail_correlation(img: np.ndarray, scale: float) -> float:
    """How faithfully a stacked still carries the fixture's surface detail.

    The disk centre is read off the picture itself (the reference frame fixes
    the framing, and which frame that is depends on grading), then the known
    detail is laid down around it on the picture's own grid and correlated
    with the green plane inside the disk."""
    g = np.nan_to_num(img[..., 1].astype(np.float64))
    oy, ox = np.mgrid[0:g.shape[0], 0:g.shape[1]].astype(np.float64)
    uy, ux = (oy + 0.5) / scale - 0.5, (ox + 0.5) / scale - 0.5   # input-pixel coords
    mask = g > 0.5 * g.max()
    cy, cx = uy[mask].mean(), ux[mask].mean()
    inside = np.hypot(uy - cy, ux - cx) < 0.7 * JITTER_DISK_RADIUS
    return float(np.corrcoef(g[inside], jitter_detail(uy - cy, ux - cx)[inside])[0, 1])


@ffmpeg_only
def test_a_long_jittery_raw_capture_drizzles_and_comes_back_sharper(tmp_path):
    """The spec's acceptance test: the lossless raw fixture with known sub-pixel
    jitter comes back ×1.5 and measurably sharper than the plain path."""
    from seestack.video.lucky import stack_video

    path = solar_raw_jittered_video(tmp_path / "Solar_video.avi", LUCKY_DRIZZLE_MIN_FRAMES + 20, jitter=3.0)
    plain = stack_video(path, LuckyOptions(keep_percent=100.0))
    driz = stack_video(path, LuckyOptions(keep_percent=100.0, drizzle=True))

    assert plain.drizzle_reason == lucky_drizzle.REASON_OFF and plain.drizzle_scale == 1.0
    assert plain.image.shape == (JITTER_H, JITTER_W, 3)
    assert driz.drizzle_reason == lucky_drizzle.REASON_DRIZZLED, driz.drizzle_reason
    assert driz.drizzle_scale == 1.5
    assert driz.image.shape == (144, 192, 3)
    assert (driz.width, driz.height) == (192, 144)
    assert driz.drizzle_note.startswith("Drizzled to 1.5×")

    c_plain = _detail_correlation(plain.image, 1.0)
    c_driz = _detail_correlation(driz.image, 1.5)
    # Measured 0.84 vs 0.98: what the stack fails to explain of the detail
    # (1 − r) drops about eightfold. Asserted as that ratio, since r is capped at 1.
    assert (1.0 - c_driz) < 0.3 * (1.0 - c_plain), (c_plain, c_driz)


@ffmpeg_only
def test_a_capture_that_never_moved_keeps_the_camera_sized_picture(tmp_path):
    """Plenty of frames, no motion: a finer grid would have nothing new in it, so
    the result is the plain stack — **bit for bit** — and says why."""
    from seestack.video.lucky import stack_video

    path = solar_raw_jittered_video(tmp_path / "Solar_video.avi", LUCKY_DRIZZLE_MIN_FRAMES + 20, jitter=0.0)
    plain = stack_video(path, LuckyOptions(keep_percent=100.0))
    asked = stack_video(path, LuckyOptions(keep_percent=100.0, drizzle=True))
    assert asked.drizzle_reason == lucky_drizzle.REASON_TOO_LITTLE_MOTION
    assert asked.drizzle_scale == 1.0
    assert "barely moved" in asked.drizzle_note
    np.testing.assert_array_equal(asked.image, plain.image)


@ffmpeg_only
def test_a_short_capture_never_builds_the_finer_canvas(tmp_path, monkeypatch):
    """Too few frames is known before pass 2, so the drizzle costs nothing."""
    from seestack.video import lucky

    def _boom(*_a, **_k):
        raise AssertionError("the finer canvas was built for a capture that can't use it")

    monkeypatch.setattr(lucky, "LuckyDrizzle", _boom)
    path = solar_raw_jittered_video(tmp_path / "Solar_video.avi", 40, jitter=3.0)
    res = lucky.stack_video(path, LuckyOptions(keep_percent=100.0, drizzle=True))
    assert res.drizzle_reason == lucky_drizzle.REASON_TOO_FEW_FRAMES
    assert res.image.shape == (JITTER_H, JITTER_W, 3)
    assert "40" in res.drizzle_note

