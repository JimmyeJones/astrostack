"""Data-driven starting tone curve for the Curves op (seestack/edit/curve.py)."""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.curve import CURVE_TARGET_BG, suggest_tone_curve


def _scene(black_floor=0.10, h=120, w=160, seed=0):
    """A realistic display-space (stretched) image: a dark sky floor, a broad
    extended object filling much of the frame, and a handful of bright stars — so
    the low/median/high percentiles are well separated (dark sky → faint object →
    bright cores), the way a typical Seestar OSC stack looks after a stretch."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    sky = black_floor + rng.normal(0.0, 0.02, (h, w))
    obj = 0.4 * np.exp(-(((xx - w / 2) / 40.0) ** 2 + ((yy - h / 2) / 30.0) ** 2))
    img = sky + obj
    for _ in range(15):  # a few near-saturated stars set the highlight end
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        img[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2] = 0.95
    return np.clip(np.repeat(img[..., None], 3, axis=2), 0.0, 1.0).astype("float32")


def _is_strictly_monotone(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (all(b > a for a, b in zip(xs, xs[1:], strict=False))
            and all(b > a for a, b in zip(ys, ys[1:], strict=False)))


def test_curve_lifts_the_midtone_and_anchors_the_ends():
    pts = suggest_tone_curve(_scene(black_floor=0.10))
    assert pts is not None
    # Endpoints pinned; a strictly-monotone (never posterising/inverting) curve.
    assert pts[0] == [0.0, 0.0] and pts[-1] == [1.0, 1.0]
    assert _is_strictly_monotone(pts)
    # The sky and highlight anchors sit on the identity; the midtone is lifted.
    sky, mid, high = pts[1], pts[2], pts[3]
    assert sky[1] == sky[0]           # sky floor stays put
    assert high[1] == high[0]         # highlight shoulder rolls off (on identity)
    assert mid[1] > mid[0]            # midtone lifted upward


def test_midtone_lift_aims_toward_the_target_grey():
    pts = suggest_tone_curve(_scene(black_floor=0.10))
    assert pts is not None
    mid = pts[2]
    # The lift is gentle (a fraction of the way to the target), so the lifted
    # midtone lands strictly between the original tone and the target grey.
    assert mid[0] < mid[1] < CURVE_TARGET_BG + 1e-6


def test_points_are_clamped_and_rounded():
    pts = suggest_tone_curve(_scene())
    assert pts is not None
    for x, y in pts:
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
        assert round(x, 3) == x and round(y, 3) == y


def test_nan_uncovered_pixels_are_ignored():
    img = _scene()
    img[:20, :, :] = np.nan  # a mosaic-edge NaN band
    pts = suggest_tone_curve(img)
    assert pts is not None
    assert all(np.isfinite(x) and np.isfinite(y) for x, y in pts)


def test_returns_none_when_range_is_degenerate():
    # A flat image (no dynamic range) → anchors collide → no useful curve.
    flat = np.full((60, 60, 3), 0.3, dtype="float32")
    assert suggest_tone_curve(flat) is None
    # All-NaN (uncovered) → too few finite pixels.
    allnan = np.full((60, 60, 3), np.nan, dtype="float32")
    assert suggest_tone_curve(allnan) is None


def _sky_dominated_scene(sky=0.14, neb=0.08, h=400, w=400, seed=3):
    """A realistic S30-style stack: a bright, noisy sky filling most of the frame
    (so the *median* IS the sky), a small faint nebula, and a scatter of stars."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    img = sky + rng.normal(0.0, 0.03, (h, w))
    img += neb * np.exp(-(((xx - w / 2) / 40.0) ** 2 + ((yy - h / 2) / 40.0) ** 2))
    for _ in range(30):
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        img[max(0, cy):cy + 2, max(0, cx):cx + 2] = 0.9
    return np.clip(np.repeat(img[..., None], 3, axis=2), 0.0, 1.0).astype("float32")


def test_sky_dominated_frame_does_not_lift_the_sky():
    """Regression for the +42% background lift: on a sky-dominated frame the old
    curve anchored the sky at p1 and lifted p50 — but p50 IS the sky there, so the
    whole background rode the lift, brightening the sky and undoing the stretch's
    noise-aware target. The suggested curve must now keep the *sky* (measured on a
    known background patch) within a couple of percent of identity, whether it
    lifts faint structure or declines to the identity line."""
    from seestack.edit.ops.tone import _curves

    img = _sky_dominated_scene(sky=0.14)
    # A corner patch that is pure background (the nebula is centred, stars sparse).
    sky_patch = img[:60, :60, 1]
    sky_in = float(np.median(sky_patch))

    pts = suggest_tone_curve(img)
    if pts is not None:
        # The sky anchor sits on the identity at (or below) the sky level, and the
        # single lifted point sits strictly ABOVE the sky — never on it.
        assert pts[1][1] == pts[1][0]                      # sky anchor on identity
        assert pts[1][0] <= sky_in + 0.02                  # anchored at the sky, not above it
        mid = next(p for p in pts if p[1] > p[0])          # the one lifted point
        assert mid[0] > sky_in                             # lifts structure above the sky

    out = _curves(img, {"points": pts or [[0, 0], [1, 1]]}, None)
    sky_out = float(np.median(out[:60, :60, 1][np.isfinite(out[:60, :60, 1])]))
    assert abs(sky_out - sky_in) / sky_in < 0.03           # sky barely moves


def test_returns_none_when_typical_tone_already_at_or_above_target():
    # A bright-midtone image: the median already sits at/above the target grey,
    # so there is nothing pleasant to lift — leave the identity line.
    rng = np.random.default_rng(1)
    img = np.clip(0.6 + rng.normal(0.0, 0.02, (80, 80, 3)), 0.0, 1.0).astype("float32")
    assert suggest_tone_curve(img) is None


def test_saturated_highlight_p99_5_rounding_does_not_drop_the_curve():
    """Regression: a stretched image whose 99.5th percentile sits just below 1.0
    (0.9998) but *rounds* to 1.0 must still yield a valid midtone-lift curve — the
    high anchor is dropped (it would duplicate the pinned [1,1] endpoint), not the
    whole suggestion. Before the fix the rounded anchor collided with the endpoint
    and the strict-monotone guard bailed to None."""
    rng = np.random.default_rng(4)
    # Dark sky floor + a broad object with a bright, near-saturated highlight tail
    # so p99.5 lands at ~0.9998 (rounds to 1.0) while the median stays below target.
    yy, xx = np.mgrid[0:120, 0:160]
    img = 0.08 + rng.normal(0.0, 0.015, (120, 160))
    img += 0.30 * np.exp(-(((xx - 80) / 60.0) ** 2 + ((yy - 60) / 50.0) ** 2))
    img[50:70, 70:90] = 0.9998                  # a bright saturated patch (>0.5% of px)
    img = np.clip(np.repeat(img[..., None], 3, axis=2), 0.0, 1.0).astype("float32")
    high = float(np.percentile(img[np.isfinite(img)], 99.5))
    assert high < 1.0 and round(high, 3) == 1.0  # the exact rounding-collision case
    pts = suggest_tone_curve(img)
    assert pts is not None, "a valid curve must survive a p99.5 that rounds to 1.0"
    assert pts[0] == [0.0, 0.0] and pts[-1] == [1.0, 1.0]
    assert _is_strictly_monotone(pts)


def test_the_curve_applied_by_the_op_preserves_nan_and_stays_in_range():
    # The suggested points must produce a sane LUT through the real Curves op:
    # covered pixels stay in [0, 1] and NaN (uncovered) is preserved.
    from seestack.edit.ops.tone import _curves

    img = _scene(black_floor=0.10)
    img[:10, :, :] = np.nan
    pts = suggest_tone_curve(img)
    assert pts is not None
    out = _curves(img, {"points": pts}, None)
    covered = np.isfinite(out)
    assert np.all(out[covered] >= 0.0) and np.all(out[covered] <= 1.0)
    # NaN coverage is exactly preserved (no lost/spurious coverage).
    assert np.array_equal(np.isnan(out), np.isnan(img))


# --- The stretch's clipped shadows are not the sky (regression, external audit A1)
#
# Everything below feeds *real* ``autostretch`` output rather than a synthesised
# approximation of it. That distinction is the bug: the stretch hard-clips 1–2 %
# of the darkest pixels to exactly zero, and a fixture built as `clip(sky + noise)`
# has no such spike — so the earlier regression test for this same defect passed on
# a frame that could not exhibit it, while every real Auto picture had its sky
# lifted by around a tenth.

def _real_stretched_stack(seed: int = 7, h: int = 300, w: int = 420,
                          noise: float = 0.002, target_bg: float = 0.20) -> np.ndarray:
    """A linear OSC-like stack put through the app's own ``autostretch``.

    Faint sky + read noise, a small extended object, a scatter of stars — then the
    real display-space transform the Curves op actually receives, hard shadow clip
    and all. The top-left 60×60 corner is pure background by construction, so a
    test can measure the sky without asking the code under test where it is.
    """
    from seestack.render.thumbnail import autostretch

    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 0.02, dtype=np.float32)
    img += rng.normal(0.0, noise, img.shape).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    blob = np.exp(-(((yy - h // 2) ** 2 + (xx - w // 2) ** 2) / (2 * 35.0 ** 2)))
    img += (0.03 * blob)[..., None].astype(np.float32)
    for _ in range(50):
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        if abs(cy - h // 2) < 80 and abs(cx - w // 2) < 80:
            continue                      # keep the stars out of the object core
        img[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2] += 0.5
    return np.asarray(autostretch(np.clip(img, 0.0, None), target_bg=target_bg),
                      dtype=np.float32)


def test_the_stretched_fixture_really_does_clip_shadows_to_zero():
    """Guard on the guard: if this stops being true the tests below stop testing
    anything, exactly as the previous fixture silently did."""
    st = _real_stretched_stack()
    assert float(np.mean(st <= 0.0)) > 0.005, "no shadow clip → the bug can't appear"
    assert float(np.percentile(st, 0.5)) == 0.0


def test_sky_mode_reads_the_sky_not_the_stretchs_clipped_shadows():
    """The zero spike is one value, so it is always the tallest histogram bin —
    counting it reported the sky as ~0.0008 instead of the ~0.18 it sits at."""
    from seestack.edit.curve import _sky_mode

    st = _real_stretched_stack()
    finite = st[np.isfinite(st)]
    sky_truth = float(np.median(st[:60, :60]))
    measured = _sky_mode(finite)
    assert measured == pytest.approx(sky_truth, rel=0.05), (
        f"sky measured {measured:.4f}, background patch is {sky_truth:.4f}")


def test_a_frame_with_no_clipped_shadows_measures_exactly_as_before():
    """The no-regression half: dropping zeros can only change an image that has
    them, so an unclipped frame's sky is unchanged pixel for pixel."""
    from seestack.edit.curve import _sky_mode

    img = _sky_dominated_scene(sky=0.14)
    finite = img[np.isfinite(img)]
    assert float(finite.min()) > 0.0, "fixture must have no clipped shadows"
    lo, hi = float(np.percentile(finite, 0.5)), float(np.median(finite))
    counts, edges = np.histogram(finite, bins=128, range=(lo, hi))
    i = int(np.argmax(counts))
    assert _sky_mode(finite) == pytest.approx(float((edges[i] + edges[i + 1]) / 2.0))


def test_auto_contrast_leaves_the_sky_of_a_real_stretched_stack_alone():
    """End to end through the op the way Auto runs it. Before the fix this lifted
    the background by **+12.5 %** while giving the object **0 %** more contrast —
    brightening the sky and doing nothing for the picture, which is backwards."""
    from seestack.edit.ops.tone import _curves

    st = _real_stretched_stack()
    out = _curves(st.copy(), {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, None)

    sky_in = float(np.median(st[:60, :60]))
    sky_out = float(np.median(out[:60, :60]))
    assert abs(sky_out - sky_in) / sky_in < 0.01, (
        f"sky moved {sky_in:.4f} → {sky_out:.4f}")
    # …and the object it *should* be shaping really does gain contrast.
    h, w = st.shape[:2]
    core = (slice(h // 2 - 10, h // 2 + 10), slice(w // 2 - 10, w // 2 + 10))
    assert float(np.median(out[core])) > float(np.median(st[core])) + 1e-3
    assert np.all(np.isfinite(out)) and float(out.max()) <= 1.0 + 1e-6


def test_the_fallback_pins_the_sky_rather_than_darkening_it():
    """The other branch of the same gate. The old fixed fallback's lower control
    point (0.25 → 0.20) sits *below* a typical stretched sky, so it pulled a 0.19
    background down to ~0.15 — a fifth darker — whenever the suggestion declined.
    """
    from seestack.edit.curve import fallback_tone_curve

    st = _real_stretched_stack()
    assert suggest_tone_curve(st) is None, "this fixture must take the fallback"
    pts = fallback_tone_curve(st)
    assert _is_strictly_monotone(pts)
    assert pts[0] == [0.0, 0.0] and pts[-1] == [1.0, 1.0]

    sky_in = float(np.median(st[:60, :60]))
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    grid = np.linspace(0.0, 1.0, 256)
    after = np.interp(np.clip(st[:60, :60], 0.0, 1.0), grid, np.interp(grid, xs, ys))
    assert abs(float(np.median(after)) - sky_in) / sky_in < 0.01
    # The sky itself is a control point on the identity — not merely close to one.
    sky_pt = next(p for p in pts if abs(p[0] - sky_in) < 0.02)
    assert sky_pt[1] == sky_pt[0]


def test_the_fallback_keeps_the_old_shoulder_when_the_sky_is_black():
    """Shape continuity: at a sky of zero the re-anchored fallback *is* the old
    fixed S-curve's shoulder (0.75 → 0.82). Only the point that moved the sky is
    gone."""
    from seestack.edit.curve import fallback_tone_curve

    rng = np.random.default_rng(11)
    black = np.abs(rng.normal(0.0, 1e-5, (80, 100, 3))).astype("float32")
    black[40:45, 50:55] = 0.9                     # a little signal, so it isn't flat
    pts = fallback_tone_curve(black)
    assert [0.75, 0.82] in pts
    assert pts[0] == [0.0, 0.0] and pts[-1] == [1.0, 1.0]
    assert _is_strictly_monotone(pts)


def test_the_fallback_is_the_identity_when_there_is_no_headroom():
    """A near-white image has nowhere to put a shoulder; doing nothing beats
    moving the background."""
    from seestack.edit.curve import fallback_tone_curve

    white = np.full((60, 60, 3), 0.995, dtype="float32")
    assert fallback_tone_curve(white) == [[0.0, 0.0], [1.0, 1.0]]
    tiny = np.full((3, 3, 3), 0.2, dtype="float32")
    assert fallback_tone_curve(tiny) == [[0.0, 0.0], [1.0, 1.0]]


# --------------------------------------------------------------------------- #
# The two sweeps the audit's own numbers asked for
# --------------------------------------------------------------------------- #
#
# The tests above pin the fix on one scene at the default stretch target. The
# audit made two *quantified* claims that only a sweep can hold: the identical
# bad control point appeared at **every stack depth from 4 to 1,000 subs**, and
# the two branches were wrong in opposite directions — the lift brightening the
# sky, the fixed fallback darkening it — so which one you got depended on where
# the stretch had placed the background. A single-point test can sit on one
# branch and pass while the other rots.

@pytest.mark.parametrize("target_bg", [0.15, 0.18, 0.20, 0.22, 0.25])
def test_auto_contrast_leaves_the_sky_alone_at_every_stretch_target(target_bg):
    """Both branches, swept. The Auto recipe and the built-in presets stretch to
    0.18–0.25, and the branch taken changes across that range: at 0.25 it was the
    *fallback* that ran, darkening the background by ~20 % where the lower targets
    were brightened by the lift. Whichever fires, the sky comes out where the
    stretch put it."""
    from seestack.edit.ops.tone import _curves

    st = _real_stretched_stack(target_bg=target_bg)
    out = _curves(st.copy(), {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, None)
    sky_in = float(np.median(st[:60, :60]))
    sky_out = float(np.median(out[:60, :60]))
    assert abs(sky_out - sky_in) / sky_in < 0.02, (
        f"target_bg={target_bg}: sky moved {sky_in:.4f} → {sky_out:.4f} "
        f"({100 * (sky_out - sky_in) / sky_in:+.1f}%)")


# Sky noise across the depths the owner actually stacks at, from a handful of
# subs to a few thousand. It falls far more slowly than 1/√N would suggest — sky
# *shot* noise doesn't average away with read noise — so this is the measured
# range, not a textbook one.
@pytest.mark.parametrize("noise", [0.004, 0.002, 0.001, 0.0006],
                         ids=["shallow", "typical", "deep", "very-deep"])
def test_the_sky_stays_put_at_every_stack_depth(noise):
    """Depth was never the variable: the audit measured the same wrong control
    point on 4 subs and on 1,000, because the shadow clip takes a fixed *fraction*
    of the frame however clean the sky underneath it is (1.4 % here at the
    shallowest, still 0.5 % at the deepest). Check the fix is equally depth-blind."""
    from seestack.edit.ops.tone import _curves

    st = _real_stretched_stack(noise=noise)
    assert float(np.mean(st <= 0.0)) > 0.005, "the clip spike survives at this depth"
    out = _curves(st.copy(), {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, None)
    sky_in = float(np.median(st[:60, :60]))
    sky_out = float(np.median(out[:60, :60]))
    assert abs(sky_out - sky_in) / sky_in < 0.02
