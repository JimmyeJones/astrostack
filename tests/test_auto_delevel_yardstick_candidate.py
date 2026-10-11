"""The fix filed for the ⭐ gradient/de-levelling bug, **measured before it ships**.

``docs/IMPROVEMENTS.md``'s first Bugs entry (filed with v0.493.10) reproduces a
real defect: a light-pollution ramp of only ~49 % of the sky, running *across* a
mosaic's panel strips, pushes every genuine sky level past
:data:`~seestack.edit.presets._LEVEL_MAX_SIGMA_RATIO`, so
:func:`~seestack.edit.presets._delevelled_luminance` declines, Auto reads a sky
level **2.08x** the truth and the finished mosaic comes out ~7.8 % darker. The
guard is applied to a plane that still carries the ramp, because ``analyze_proxy``
runs ``_detrended_luminance(_delevelled_luminance(...))`` in that order.

That entry then names the fix: *"judge the guard on a plane with the smooth shape
taken out — measure ``level_sigma`` (and the ``sky`` mask) on
``_detrended_luminance(lum)`` while still subtracting the step from the raw
plane"* — and says it needs the before/after re-run first, because it changes what
Auto emits for every mosaic.

**This file is that before/after, and the answer is that the candidate must not
ship as filed.** It fixes the case it was filed for, cleanly and at every
gradient strength. It also makes two other cases **worse**, one of them worse
than the bug it fixes. The candidate is kept here as a local replica so those
costs are *asserted* rather than written down — the lesson v0.493.11 drew one
subsystem over: a figure inside a prose argument has nothing checking it, so
anyone reasoning from this entry reasons from numbers a test keeps honest.

**The diagnosis, which is the part to build on.** Detrending the whole canvas
removes two different things at once: the smooth shape that is *common to every
panel* (which the guard should ignore — it is not panel structure) and the smooth
shape that *differs between panels* (which the guard must see — it is exactly the
sky difference a per-level median would otherwise swallow as a "panel step"). A
single ``level_sigma``, on any one plane, cannot tell those apart, and neither can
it tell a smooth *object* spanning a strip from smooth sky. So the quantity the
guard needs is under-determined by the measurement it is given, and the fix is
not a plane swap. Anything built here has to separate those two cases first.
"""

from __future__ import annotations

import contextlib
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from seestack.bg.coverage_leveling import _robust_stats
from seestack.edit import presets as P
from seestack.edit.noise import estimate_noise_sigma

# The fixture that reproduced the bug, reused rather than rebuilt: its panel
# steps and its coverage map describe the *same* mosaic, which is the thing that
# made the first measurement of this guard wrong (see that file's own header).
_SPEC = importlib.util.spec_from_file_location(
    "_level_sigma_fixtures",
    Path(__file__).with_name("test_auto_level_sigma_margin.py"))
_F = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_F)

_scene = _F._scene
_coverage = _F._coverage

#: A scene with no panel steps at all, measured as a single field, is the truth
#: every number below is an error against. The ramps used here run **across** the
#: strips unless stated, so they add nothing to the panel-to-panel differences and
#: the no-step scene really is the same picture.
_NO_STEPS = (0.0, 0.0, 0.0, 0.0)

#: Four seeds, because a single one cannot tell a finding from a fixture.
_SEEDS = (13, 5, 21, 3)


def _rgb(lum: np.ndarray) -> np.ndarray:
    return np.stack([lum] * 3, axis=-1)


# --------------------------------------------------------------------------- #
# The candidate, as the entry proposes it
# --------------------------------------------------------------------------- #


def _delevelled_with_detrended_yardstick(lum: np.ndarray,
                                         coverage: np.ndarray | None) -> np.ndarray:
    """:func:`seestack.edit.presets._delevelled_luminance` with **one** change.

    The guard's yardstick and the ``sky`` mask are read off a detrended copy of
    the plane; every step that is actually subtracted is still measured on the raw
    plane, exactly as the entry specifies. Everything else — the binning, the
    floors, the two passes, the reference median, the decline paths — is the
    function's own arithmetic, and
    :func:`test_the_replica_is_the_real_function_plus_one_change` holds it to that.
    """
    if coverage is None:
        return lum
    cov = np.asarray(coverage)
    if cov.ndim == 3:
        cov = cov[..., 0]
    if cov.shape != lum.shape:
        return lum
    finite = np.isfinite(lum)
    if not finite.any():
        return lum
    with np.errstate(invalid="ignore"):
        cov_int = np.rint(np.nan_to_num(cov.astype(np.float64, copy=False),
                                        nan=0.0)).astype(np.int64)
    valid = (cov_int > 0) & finite
    n_valid = int(valid.sum())
    if n_valid < 2 * P._LEVEL_MIN_PIXELS:
        return lum
    floor = max(P._LEVEL_MIN_PIXELS, int(round(P._LEVEL_MIN_SHARE * n_valid)))
    levels, counts = np.unique(cov_int[valid], return_counts=True)
    big = [int(lv) for lv, n in zip(levels, counts, strict=True) if n >= floor]
    if len(big) < 2:
        return lum
    regions = {level: (cov_int == level) & valid for level in big}

    # --- the one change: the flatness questions are asked of a detrended copy --
    yard = P._detrended_luminance(lum)

    rough = np.zeros(yard.shape, dtype=np.float32)
    for region in regions.values():
        med, _ = _robust_stats(yard[region])
        if np.isfinite(med):
            rough[region] = np.float32(med)
    destepped = yard - rough
    _med, spread = _robust_stats(destepped[valid])
    if not np.isfinite(spread) or spread <= 0:
        return lum
    yard_c = yard[valid]
    span = float(np.percentile(yard_c, 99.5) - np.percentile(yard_c, 0.5))
    unit = estimate_noise_sigma(yard)
    if unit is None or not np.isfinite(span) or span <= 0:
        return lum
    grain = float(unit) * span
    sky = valid & (destepped <= (_med + P._LEVEL_OBJECT_SIGMA * spread))

    per_level: dict[int, float] = {}
    for level, region in regions.items():
        region_sky = region & sky
        if lum[region_sky].size < P._LEVEL_MIN_PIXELS:
            continue
        _, level_sigma = _robust_stats(destepped[region_sky])
        if not np.isfinite(level_sigma) or level_sigma > P._LEVEL_MAX_SIGMA_RATIO * grain:
            continue
        med, _ = _robust_stats(lum[region_sky])   # the step stays on the raw plane
        if np.isfinite(med):
            per_level[level] = float(med)
    if len(per_level) < 2:
        return lum
    reference, _ = _robust_stats(lum[valid & sky])
    if not np.isfinite(reference):
        return lum
    out = np.array(lum, dtype=np.float32, copy=True)
    for level, med in per_level.items():
        out[regions[level]] -= np.float32(med - reference)
    return out


@contextlib.contextmanager
def _candidate():
    """Run ``analyze_proxy`` with the candidate in place of the real de-level."""
    original = P._delevelled_luminance
    P._delevelled_luminance = _delevelled_with_detrended_yardstick
    try:
        yield
    finally:
        P._delevelled_luminance = original


def _sky_errors(seed: int, **scene) -> tuple[float, float]:
    """``(today, candidate)`` reported sky level as a ratio of the truth."""
    truth = P.analyze_proxy(
        _rgb(_scene(offsets=_NO_STEPS, seed=seed, **scene)), None)["sky"]
    mosaic = _rgb(_scene(seed=seed, **scene))
    cov = _coverage()
    today = P.analyze_proxy(mosaic, cov)["sky"]
    with _candidate():
        cand = P.analyze_proxy(mosaic, cov)["sky"]
    return today / truth, cand / truth


def test_the_replica_is_the_real_function_plus_one_change():
    """On a plane with no smooth shape to remove, the detrend is a no-op, so the
    candidate must reproduce the real function's own pixels.

    This is what makes the costs below evidence about the *change* rather than
    about a hand-rolled copy that drifted from the original.
    """
    cov = _coverage()
    for seed in _SEEDS:
        lum = _scene(seed=seed)
        real = P._delevelled_luminance(lum, cov)
        cand = _delevelled_with_detrended_yardstick(lum, cov)
        # Not bit-identical: `fit_sky_poly` still fits *something* to a flat sky
        # (its own grain), which moves the mask by a handful of pixels. The step
        # it recovers is what matters, and it agrees to well under a tenth of the
        # smallest panel offset this fixture carries (0.008).
        assert np.nanmax(np.abs(real - cand)) < 8e-4, seed


# --------------------------------------------------------------------------- #
# What the candidate gets right — recorded, because the idea has real merit
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("gradient", [0.05, 0.20, 0.50])
def test_the_candidate_does_fix_the_defect_it_was_filed_for(gradient):
    """A ramp across the strips: **2.08-2.12x the truth today, 1.00-1.02x under
    the candidate**, at every strength from the boundary to half the sky.

    So the entry's diagnosis of the *cause* is right and its fix does reach it.
    Nothing below is an argument that the bug is not real.
    """
    for seed in _SEEDS:
        today, cand = _sky_errors(seed, gradient=gradient)
        assert today > 2.0, (seed, today)
        assert cand == pytest.approx(1.0, abs=0.05), (seed, cand)
        assert abs(cand - 1.0) < abs(today - 1.0) / 10.0, (seed, today, cand)


def test_the_prerequisite_the_entry_named_is_not_where_the_risk_is():
    """The entry says to bound one thing first: *"a degree-2 surface only partly
    absorbs panel steps, so the detrended plane is not a free yardstick either"*.

    Measured, that absorption is large — **~35-49 % of a 0.012 panel step** — so
    the entry is right that the detrended plane cannot be used to *measure* a
    step. But the candidate does not: it keeps every subtracted step on the raw
    plane, and swapping only the mask moves that step by **under 1 %** on a
    gradient-free mosaic. The named prerequisite is therefore satisfied, which is
    worth asserting because it is the reason the real cost had to be looked for
    somewhere else.
    """
    cov = _coverage()
    lum = _scene()
    detrended = P._detrended_luminance(lum)
    step = 0.012                                    # the fixture's panel offset

    def steps(plane, yardstick):
        cov_int = np.rint(np.nan_to_num(cov.astype(np.float64), nan=0.0)).astype(np.int64)
        valid = (cov_int > 0) & np.isfinite(plane)
        floor = max(P._LEVEL_MIN_PIXELS,
                    int(round(P._LEVEL_MIN_SHARE * int(valid.sum()))))
        lv, ct = np.unique(cov_int[valid], return_counts=True)
        regions = {int(a): (cov_int == int(a)) & valid
                   for a, n in zip(lv, ct, strict=True) if n >= floor}
        rough = np.zeros(yardstick.shape, dtype=np.float32)
        for r in regions.values():
            m, _ = _robust_stats(yardstick[r])
            if np.isfinite(m):
                rough[r] = np.float32(m)
        de = yardstick - rough
        med0, spread = _robust_stats(de[valid])
        sky = valid & (de <= (med0 + P._LEVEL_OBJECT_SIGMA * spread))
        ref, _ = _robust_stats(plane[valid & sky])
        out = {}
        for a, r in regions.items():
            rs = r & sky
            if plane[rs].size < P._LEVEL_MIN_PIXELS:
                continue
            m, _ = _robust_stats(plane[rs])
            out[a] = float(m) - float(ref)
        return out

    raw = steps(lum, lum)                            # today
    mask_swapped = steps(lum, detrended)             # the candidate
    on_detrended = steps(detrended, detrended)       # what the entry warned about
    keys = sorted(raw)
    absorbed = max(abs(on_detrended[k] - raw[k]) for k in keys)
    mask_only = max(abs(mask_swapped[k] - raw[k]) for k in keys)
    # Measuring the step on the detrended plane would be badly wrong...
    assert absorbed / step > 0.30, absorbed
    # ...and the candidate's mask-only swap is nowhere near that.
    assert mask_only / step < 0.02, mask_only
    assert mask_only < absorbed / 10.0


# --------------------------------------------------------------------------- #
# What it costs — the two regressions, which is why it must not ship as filed
# --------------------------------------------------------------------------- #


#: A ramp **along** the strips, as ``{ramp as a share of sky: (today, candidate)}``.
#: Unlike the across-strip case this ramp genuinely *does* put a different sky
#: level in each panel, so a per-level median that absorbs it is subtracting real
#: sky difference as if it were a panel step. Today's guard sees that and refuses;
#: the candidate's detrended yardstick has removed the evidence, so it levels.
_ALONG_THE_STRIPS: dict[float, tuple[float, float]] = {
    0.20: (2.09, 2.73),
    0.50: (2.09, 5.39),
}


@pytest.mark.parametrize("gradient", sorted(_ALONG_THE_STRIPS))
def test_the_candidate_regresses_a_ramp_along_the_strips(gradient):
    """And at half a sky of ramp it is **2.6x worse than the bug it fixes**."""
    want_today, want_cand = _ALONG_THE_STRIPS[gradient]
    for seed in _SEEDS:
        today, cand = _sky_errors(seed, gradient=gradient, axis="x")
        assert today == pytest.approx(want_today, rel=0.10), (seed, today)
        assert cand == pytest.approx(want_cand, rel=0.10), (seed, cand)
        assert cand > today, (seed, today, cand)


#: A canvas a faint extended object fills, as ``{amplitude: (today, candidate)}``.
#: The guard's whole purpose is to refuse these — levelling one subtracts the
#: object's own level out of a panel as if it were sky. Today it refuses from
#: amplitude ~0.10 up; the candidate's yardstick keeps these levels under the bar
#: until ~0.25, so it levels a band today correctly leaves alone.
_FAINT_FILLED_CANVAS: dict[float, tuple[float, float]] = {
    0.15: (1.45, 1.71),
    0.20: (1.31, 1.82),
}


@pytest.mark.parametrize("blob", sorted(_FAINT_FILLED_CANVAS))
def test_the_candidate_reopens_the_window_the_guard_exists_for(blob):
    """The second cost, and the one that is about the guard's own purpose."""
    want_today, want_cand = _FAINT_FILLED_CANVAS[blob]
    for seed in _SEEDS:
        today, cand = _sky_errors(seed, blob=blob)
        assert today == pytest.approx(want_today, rel=0.10), (seed, today)
        assert cand == pytest.approx(want_cand, rel=0.10), (seed, cand)
        assert cand > today, (seed, today, cand)


def test_the_two_populations_the_bar_sits_between_narrow_under_the_candidate():
    """Why the second cost happens, in the quantity the constant is compared to.

    ``tests/test_auto_level_sigma_margin.py`` measures today's separation: a
    quiet sky reads 0.89-0.95 and a filled canvas 16.4-25.5, so 3.0 sits **3.2x**
    above sky and **5.5x** below object. Under the candidate the sky end barely
    moves (it is already flat) while the object end is pulled down by the same
    detrend, and the gap closes — which is the mechanism behind the regression
    above, and the reason "just move the constant" does not rescue the candidate
    either: the two ends move together.
    """
    cov = _coverage()

    def worst(lum, yard):
        cov_int = np.rint(np.nan_to_num(cov.astype(np.float64), nan=0.0)).astype(np.int64)
        valid = (cov_int > 0) & np.isfinite(lum)
        floor = max(P._LEVEL_MIN_PIXELS,
                    int(round(P._LEVEL_MIN_SHARE * int(valid.sum()))))
        lv, ct = np.unique(cov_int[valid], return_counts=True)
        regions = [(cov_int == int(a)) & valid
                   for a, n in zip(lv, ct, strict=True) if n >= floor]
        rough = np.zeros(yard.shape, dtype=np.float32)
        for r in regions:
            m, _ = _robust_stats(yard[r])
            if np.isfinite(m):
                rough[r] = np.float32(m)
        de = yard - rough
        med0, spread = _robust_stats(de[valid])
        yc = yard[valid]
        span = float(np.percentile(yc, 99.5) - np.percentile(yc, 0.5))
        grain = float(estimate_noise_sigma(yard)) * span
        sky = valid & (de <= (med0 + P._LEVEL_OBJECT_SIGMA * spread))
        out = []
        for r in regions:
            rs = r & sky
            if yard[rs].size < P._LEVEL_MIN_PIXELS:
                continue
            _, ls = _robust_stats(de[rs])
            out.append(float(ls) / grain)
        return min(out), max(out)

    quiet = _scene()
    filled = _scene(blob=0.3)
    _, sky_today = worst(quiet, quiet)
    obj_today, _ = worst(filled, filled)
    _, sky_cand = worst(quiet, P._detrended_luminance(quiet))
    obj_cand, _ = worst(filled, P._detrended_luminance(filled))

    # Today: 3.0 has ~3.2x of headroom above sky and the faintest filled canvas
    # this records sits ~2.9x above it.
    assert obj_today / sky_today > 8.0, (sky_today, obj_today)
    # Under the candidate the separation is a third of that, and the filled
    # canvas is only ~1.3x clear of the bar.
    assert obj_cand / sky_cand == pytest.approx(3.7, rel=0.20), (sky_cand, obj_cand)
    assert obj_cand / P._LEVEL_MAX_SIGMA_RATIO < 1.5, obj_cand
    assert (obj_cand / sky_cand) < (obj_today / sky_today) / 2.0
