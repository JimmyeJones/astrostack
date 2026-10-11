"""A window of the picture renders like the picture — for **every** op, not for four.

The editor's "check it at full size" loupe renders one full-resolution window of
a decimated preview, because four advisories tell the reader the preview is not
the export and all four can only be judged at 1:1. What makes that window honest
is :meth:`seestack.edit.registry.EditContext.fit`: an op that first *measures the
whole image* is handed the whole-image render's measurement instead of making its
own on a 512 px crop. Which ops those are was written down in prose, in four
places — and the prose was wrong.

**v0.493.5 is why this file exists.** ``starmask.star_mask`` normalises twice
against the whole array and was on none of those lists, so the loupe built its
star mask from the window's own brightest pixel: measured here at **3.6e-01** of
full scale for ``stars.boost_nebula`` on a star-poor window, against **0.0** once
its references are frozen. Nothing was checking the list, exactly as nothing was
checking the constants v0.493.3 and v0.493.4 were wrong about. This is the list,
asserted.

**The property.** Render an op over the whole canvas; render it again over a
window of that canvas at the same scale, handed the whole render's
``fitted``; the window's pixels must be the whole render's pixels. Compared over
the window's **interior** (inset by :data:`_INSET`), because a spatial op
legitimately reaches across a window edge — that is a property of the crop, not
of the fit, and ``_INSET`` is wider than the reach of every op's parameters here.

**Scope mirrors the loupe, which is what makes "every other op" a real claim.**
``geometry.*`` ops are *disabled* on a window render (``_without_geometry``: the
window already is the region the crop selects) and the three ``background.*``
passes have the field they subtracted **replayed** onto the window rather than
re-fitted (``EditContext.replay_field``, pinned by
``tests/test_edit_field_replay.py``). Everything else is swept — and the sweep is
derived from the registry, so a newly registered op is in it the moment it
exists.

**The separation is absolute, so there is nothing tuned here.** Every op that is
window-faithful measures **exactly 0.0**; the four that are not span 8.6e-06 to
9.3e-03. The tolerance below sits ~8,600x under the smallest real divergence and
above nothing at all.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.registry import EditContext, all_specs, get_op

#: Window size and how far in from its edge the comparison is made. The inset
#: must exceed the spatial reach of every op in :data:`_PARAMS`; the widest is
#: ``detail.chroma_denoise``'s 10 px radius (~3 sigma = 30 px), then
#: ``detail.sharpen``'s 2 px and ``detail.deconvolve``'s 1.5 px PSF.
_WINDOW_PX = 224
_INSET = 56

#: A difference this small is float noise, not a re-measurement: every faithful
#: op measured **exactly** 0.0 and the smallest genuine divergence is 8.6e-06.
_FAITHFUL_TOL = 1e-9

#: Parameters chosen to be plainly non-trivial, so "the window matches" is not
#: "the op did nothing" — the same reasoning as ``tests/test_edit_op_effect.py``.
_PARAMS: dict[str, dict] = {
    "detail.hot_pixels": {"sigma": 4.0},
    "detail.denoise": {"method": "wavelet", "strength": 0.7},
    "detail.chroma_denoise": {"strength": 0.9, "radius": 10.0},
    "detail.sharpen": {"amount": 1.5, "radius": 2.0},
    "detail.deconvolve": {"iterations": 4, "psf_sigma": 1.5},
    "stars.reduce": {"amount": 0.9, "size": 3},
    "stars.boost_nebula": {"amount": 0.8, "size": 4},
    "tone.color_calibrate": {"mode": "gray_star"},
    "tone.white_balance": {"r": 1.25, "g": 1.00, "b": 0.80},
    "tone.neutralize_background": {"strength": 1.0},
    "tone.stretch": {"mode": "stf", "target_bg": 0.32},
    "tone.curves": {"points": [[0.0, 0.0], [0.25, 0.42], [0.75, 0.90], [1.0, 1.0]]},
    "tone.levels": {"black": 0.06, "white": 0.90, "gamma": 1.35},
    "tone.saturation": {"amount": 1.8},
    "tone.scnr": {"amount": 1.0, "mode": "average"},
}

#: op id → why a window of it still does not reproduce the picture, with the
#: largest divergence this fixture measures. **Every entry is a known defect, not
#: a licence** — they are the open LEAD filed with v0.493.5 (the percentile span
#: in the two restoration ops) plus the two whole-array sky estimates nothing has
#: costed yet. An op in this table is asserted to be *measurably* unfaithful, so
#: fixing one fails this file until its entry goes, and an op that is **not** in
#: it must be exact.
_NOT_WINDOW_FAITHFUL: dict[str, str] = {
    "detail.denoise":
        "the 0.5-99.5th percentile span it normalises by is a whole-image "
        "measurement that is not carried (LEAD, docs/IMPROVEMENTS.md): freezing "
        "it is a partial fix whose sign is method-dependent, because BayesShrink "
        "derives its own per-subband sigma and skimage's bilateral builds its "
        "colour LUT from the array's min/max. Worst here 9.3e-03, on a "
        "star-poor window.",
    "detail.deconvolve":
        "the same percentile span, same LEAD, and freezing it measured *worse* "
        "on two windows of three — ten Richardson-Lucy passes from a flat guess "
        "amplify even the proxy span's 0.02 % difference from the canvas's. "
        "Worst here 1.4e-04.",
    "detail.chroma_denoise":
        "`_robust_sky` takes the whole array's luminance median and MAD to decide "
        "how much smoothing a bright pixel keeps. Not costed: its own docstring "
        "argues the number shapes a taper rather than gating anything, and the "
        "worst divergence here is 2.3e-03 on a bright core.",
    "detail.hot_pixels":
        "`seestack.bg.hot_pixels._suppress` derives the sky level and the noise "
        "floor from the whole array, per channel. Not costed, and the obvious fix "
        "reshapes a **stack hot-path** module for the editor, which "
        "`EditContext`'s own notes rule out. Worst here 2.9e-04.",
}

#: Where the window is taken. A window's own statistics are least like the
#: picture's where its content is least like the picture's, so the sweep takes
#: one of each: nearly starless far side, the bright core with the star cluster,
#: and one against the ragged mosaic edge.
_WINDOWS: dict[str, tuple[int, int]] = {
    "star-poor far side": (330, 360),
    "bright core": (40, 70),
    "near the ragged edge": (60, 110),
}

_H, _W = 560, 700
_STAR_SIGMA_PX = 1.27


def _in_scope() -> list[str]:
    """Every op the loupe re-runs on its window — from the registry, not a list."""
    return sorted(s.id for s in all_specs()
                  if not s.id.startswith("geometry.") and not s.additive_field)


def _canvas() -> np.ndarray:
    """A linear OSC canvas whose content is *uneven*: a bright object with a dense
    star cluster in one corner, a nearly starless far side, green blotches, single
    hot pixels and a ragged NaN edge. A uniform field would let every window
    measure nearly the picture's own numbers and could exhibit none of this."""
    rng = np.random.default_rng(11)
    yy, xx = np.mgrid[0:_H, 0:_W].astype(np.float32)
    img = 0.045 + 0.010 * (xx / _W) + 0.006 * (yy / _H)
    img += 0.70 * np.exp(-(((yy - 130) / 80.0) ** 2 + ((xx - 170) / 95.0) ** 2))
    for cy, cx, n, amp, sig in ((130, 170, 190, 0.9, 95.0), (440, 600, 24, 0.05, 95.0)):
        ys = rng.normal(cy, sig, n)
        xs = rng.normal(cx, sig, n)
        for y, x, a in zip(ys, xs, rng.uniform(0.02, amp, n), strict=True):
            y0, x0 = int(y), int(x)
            if not (5 <= y0 < _H - 6 and 5 <= x0 < _W - 6):
                continue
            gy, gx = np.mgrid[y0 - 5:y0 + 6, x0 - 5:x0 + 6]
            img[y0 - 5:y0 + 6, x0 - 5:x0 + 6] += a * np.exp(
                -(((gy - y) ** 2 + (gx - x) ** 2) / (2 * _STAR_SIGMA_PX ** 2)))
    green = np.zeros_like(img)                       # something for SCNR to remove
    for _ in range(20):
        y = int(rng.integers(30, _H - 30))
        x = int(rng.integers(30, _W - 30))
        gy, gx = np.mgrid[y - 24:y + 25, x - 24:x + 25]
        green[y - 24:y + 25, x - 24:x + 25] += 0.004 * np.exp(
            -(((gy - y) / 12.0) ** 2 + ((gx - x) / 12.0) ** 2))
    img += rng.normal(0, 0.0016, img.shape)
    rgb = np.stack([img * 0.80, img + green, img * 1.25], axis=-1).astype(np.float32)
    for _ in range(30):                              # single-channel hot pixels
        y = int(rng.integers(5, _H - 5))
        x = int(rng.integers(5, _W - 5))
        rgb[y, x, int(rng.integers(0, 3))] += 0.5
    rgb[:45, :] = np.nan                             # a ragged mosaic edge
    rgb[:, _W - 40:] = np.nan
    return rgb


_CANVAS = _canvas()
_WHOLE: dict[str, tuple[np.ndarray, dict]] = {}


def _render(op_id: str, rgb: np.ndarray, *, frozen: dict | None = None):
    spec = get_op(op_id)
    display = spec.stage == "nonlinear"
    arr = np.clip(rgb, 0.0, 1.0) if display else rgb
    ctx = EditContext(proxy_scale=1.0, is_proxy=False, op_uid="u1",
                      stage=spec.stage, already_display=display, frozen_fits=frozen)
    out = spec.apply(np.ascontiguousarray(arr),
                     {**spec.defaults(), **_PARAMS[op_id]}, ctx)
    return out, ctx


def _whole(op_id: str) -> tuple[np.ndarray, dict]:
    """The whole-canvas render, computed once per op for the whole module."""
    if op_id not in _WHOLE:
        out, ctx = _render(op_id, _CANVAS)
        _WHOLE[op_id] = (out, dict(ctx.fitted))
    return _WHOLE[op_id]


def _divergence(op_id: str, where: str, *, freeze: bool) -> float:
    whole, fitted = _whole(op_id)
    y0, x0 = _WINDOWS[where]
    sl = (slice(y0, y0 + _WINDOW_PX), slice(x0, x0 + _WINDOW_PX))
    window, _ = _render(op_id, _CANVAS[sl], frozen=fitted if freeze else None)
    inner = (slice(_INSET, _WINDOW_PX - _INSET), slice(_INSET, _WINDOW_PX - _INSET))
    truth = whole[sl][inner]
    cov = np.isfinite(truth).all(axis=2)
    assert cov.any(), f"the {where} window is entirely uncovered — move it"
    ref = float(np.nanpercentile(np.abs(truth[cov]), 99.0)) or 1.0
    return float(np.nanmean(np.abs(window[inner] - truth)[cov])) / ref


# --- the sweep ---------------------------------------------------------------

@pytest.mark.parametrize("where", sorted(_WINDOWS))
@pytest.mark.parametrize("op_id", [i for i in _in_scope() if i not in _NOT_WINDOW_FAITHFUL])
def test_a_frozen_window_is_the_picture(op_id, where):
    err = _divergence(op_id, where, freeze=True)
    assert err <= _FAITHFUL_TOL, (
        f"{op_id} renders a {where} window {err:.4e} of full scale away from the "
        f"same pixels in the whole render, with the whole render's fits frozen "
        f"onto it. Either it measures something from the whole array that it does "
        f"not carry through EditContext.fit — route it through ctx.fit, and put it "
        f"on the four lists that enumerate those ops — or, if that genuinely "
        f"cannot be done, add it to _NOT_WINDOW_FAITHFUL with the reason and the "
        f"number, the way the four entries there do.")


@pytest.mark.parametrize("where", sorted(_WINDOWS))
@pytest.mark.parametrize("op_id", sorted(_NOT_WINDOW_FAITHFUL))
def test_the_unfaithful_ops_are_unfaithful_in_the_same_direction(op_id, where):
    """Freezing never makes one of them *worse* than re-measuring, which is the
    only claim the open LEAD rests on — and the reason none of them is simply
    left to re-measure quietly."""
    frozen = _divergence(op_id, where, freeze=True)
    loose = _divergence(op_id, where, freeze=False)
    # They record no fits at all today, so the two renders are the same render.
    assert frozen == pytest.approx(loose, abs=1e-12)


@pytest.mark.parametrize("op_id", sorted(_NOT_WINDOW_FAITHFUL))
def test_a_documented_exception_is_still_a_real_one(op_id):
    """So a fix cannot leave a stale excuse behind: an op listed as unfaithful has
    to be measurably unfaithful on at least one of the three windows."""
    worst = max(_divergence(op_id, w, freeze=True) for w in _WINDOWS)
    assert worst > _FAITHFUL_TOL, (
        f"{op_id} now renders every window exactly like the picture — delete its "
        f"_NOT_WINDOW_FAITHFUL entry so the sweep above covers it.")


# --- the sweep covers the registry, not a list -------------------------------

def test_every_op_in_scope_has_parameters_to_be_swept_with():
    missing = [i for i in _in_scope() if i not in _PARAMS]
    assert not missing, (
        f"new editor op(s) {missing} are re-run on the loupe's window and this "
        f"sweep has no parameters for them. Add non-trivial parameters to "
        f"_PARAMS; if the op measures the whole image, route that measurement "
        f"through EditContext.fit first.")


def test_the_exception_table_names_real_ops_in_scope():
    assert set(_NOT_WINDOW_FAITHFUL) <= set(_in_scope())


def test_the_ops_outside_the_sweep_are_the_two_the_loupe_handles_itself():
    """Named, so that "every other op" above is checkable. Geometry ops are
    disabled on a window render and the additive background passes have their
    field replayed — ``tests/test_edit_field_replay.py`` owns that half."""
    outside = sorted(s.id for s in all_specs() if s.id not in _in_scope())
    assert outside == ["background.final_gradient", "background.level_coverage",
                       "background.subtract", "geometry.crop", "geometry.resize",
                       "geometry.rotate"]
