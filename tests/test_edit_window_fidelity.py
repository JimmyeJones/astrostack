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

**The separation is wide, so there is nothing tuned here.** Every window-faithful
op measures **exactly 0.0** except ``detail.deconvolve``, which measures float
noise (see :data:`_FLOAT_NOISE_TOL`); the three that are not span 5.0e-06 to
8.0e-03.

**v0.493.9 carried the span, which is the (a)/(b) half of that same LEAD**
(closed with it; see ``docs/SHIPPED.md`` under v0.493.9). Both
restoration ops normalise by a 0.5/1.0-99.5th percentile span of the array they
are handed, and now take it from ``ctx.fit``. For ``detail.deconvolve`` that was
its *only* whole-array measurement, so the op became window-faithful and its
declaration went: 8.5e-05 -> 9.8e-08 on this fixture's worst window, ~700x.
``detail.denoise`` stays declared, because two dependences inside skimage are
not reachable through its public API, and
:func:`test_the_carried_span_is_most_of_the_denoise_gap` pins what carrying it
bought per method -- including the one cell that got **worse**, so the entry
cannot be read as a monotone claim it is not.
"""

from __future__ import annotations

import re

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
#: op measures **exactly** 0.0 -- bar the one below -- and the smallest genuine
#: divergence is 5.0e-06.
_FAITHFUL_TOL = 1e-9

#: The one faithful op that cannot measure exactly 0.0, and why.
#: ``richardson_lucy`` convolves with ``scipy.signal.convolve``, which picks
#: ``fft`` for a 224 px window and for the 560x700 canvas alike (checked with
#: ``choose_conv_method``) -- two transforms of different size, accumulating
#: float32 in different orders. So the window carries the picture's *own* span
#: and still differs in the last couple of digits: measured **9.8e-08 / 8.7e-08 /
#: 1.4e-07** over the three windows, against **8.5e-05 / 4.4e-05 / 9.6e-05**
#: before the span was carried. The ceiling is ~14x over the worst of those and
#: ~350x under :data:`_NOT_WINDOW_FAITHFUL`'s smallest *worst-window* defect
#: (``detail.hot_pixels``, 7.2e-04), so it separates float noise from a
#: re-measurement without either margin being thin.
_FLOAT_NOISE_TOL: dict[str, float] = {"detail.deconvolve": 2e-6}

#: The same ceiling, for a *cell* of a measured table rather than a whole op —
#: see :data:`_DENOISE_SPAN_GAIN`, where carrying the span takes one window of
#: the bilateral method to 1.6e-07 and a relative band would be pinning rounding.
_NOISE_FLOOR = 1e-6

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

#: op id → ``(worst divergence, the window it is worst on, why)``. **Every entry
#: is a known defect, not a licence** — one is what the LEAD filed with v0.493.5
#: left after v0.493.9 carried the percentile span and closed it, and two are the
#: whole-array sky estimates nothing has costed yet. An op in this table is
#: asserted to be *measurably* unfaithful, so fixing one fails this file until its
#: entry goes, and an op that is **not** in it must be exact.
#:
#: **The numbers are asserted too, since v0.493.9, and that is not decoration.**
#: v0.493.6 recorded them as prose and two of the three were wrong within four
#: days — ``detail.chroma_denoise`` as "2.3e-03 on a bright core" when it is
#: 3.2e-03 on the ragged edge, ``detail.hot_pixels`` as 2.9e-04 when it is 7.2e-04
#: on the star-poor side, each understated and on the wrong window. That is this
#: file's own bug class one level down: a list was asserted and the figures
#: justifying it were not. :func:`test_the_recorded_divergence_is_the_measured_one`
#: now checks both the value and the window, so each number has exactly one home
#: and cannot drift from the thing it describes.
#:
#: **The table documents; the registry decides.** Since v0.493.7 each of these
#: ops carries the same claim as :attr:`~seestack.edit.registry.OpSpec.window_unfaithful`,
#: which is what the loupe reads to *tell the reader* which ops it cannot vouch
#: for — so the sweeps below parametrize off the registry and
#: :func:`test_the_declared_exceptions_are_the_ones_measured_here` pins the two
#: together. A fifth copy of a prose list is the bug this file exists about, and
#: an entry that goes stale is the next one: ``detail.deconvolve``'s left both
#: this table and the registry in v0.493.9 because the sweep stopped accepting it.
_NOT_WINDOW_FAITHFUL: dict[str, tuple[float, str, str]] = {
    "detail.denoise": (8.0e-03, "star-poor far side",
        "the 0.5-99.5th percentile span it normalises by *is* carried now "
        "(v0.493.9) and that was most of it — bilateral 2.9e-03 → 3.2e-05 — but "
        "two whole-array dependences inside skimage are not reachable through its "
        "public API: `denoise_tv_chambolle` stops when `|dE| < eps * E_init`, a "
        "whole-array energy, so a window converges a different number of "
        "iterations; and BayesShrink keeps its per-subband coefficient variance, "
        "and decomposes a smaller array to fewer levels. The figure is the "
        "wavelet default's; see `test_the_carried_span_is_most_of_the_denoise_gap` "
        "for the per-method table, including the one cell the carry made worse."),
    "detail.chroma_denoise": (3.2e-03, "near the ragged edge",
        "`_robust_sky` takes the whole array's luminance median and MAD to decide "
        "how much smoothing a bright pixel keeps. Not costed: its own docstring "
        "argues the number shapes a taper rather than gating anything."),
    "detail.hot_pixels": (7.2e-04, "star-poor far side",
        "`seestack.bg.hot_pixels._suppress` derives the sky level and the noise "
        "floor from the whole array, per channel. Not costed, and the obvious fix "
        "reshapes a **stack hot-path** module for the editor, which "
        "`EditContext`'s own notes rule out."),
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


def _declared_unfaithful() -> list[str]:
    """Which ops *say* a window of them is not the picture — from the registry,
    because that declaration is what the editor reads to name them on screen."""
    return sorted(s.id for s in all_specs() if s.window_unfaithful)


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
_WHOLE: dict[object, tuple[np.ndarray, dict]] = {}


def _render(op_id: str, rgb: np.ndarray, *, frozen: dict | None = None,
            params: dict | None = None):
    spec = get_op(op_id)
    display = spec.stage == "nonlinear"
    arr = np.clip(rgb, 0.0, 1.0) if display else rgb
    ctx = EditContext(proxy_scale=1.0, is_proxy=False, op_uid="u1",
                      stage=spec.stage, already_display=display, frozen_fits=frozen)
    out = spec.apply(np.ascontiguousarray(arr),
                     {**spec.defaults(), **(params or _PARAMS[op_id])}, ctx)
    return out, ctx


def _whole(op_id: str, *, params: dict | None = None) -> tuple[np.ndarray, dict]:
    """The whole-canvas render, computed once per op (and per params override, for
    the one test that sweeps an op's methods) for the whole module."""
    key = op_id if params is None else (op_id, tuple(sorted(params.items())))
    if key not in _WHOLE:
        out, ctx = _render(op_id, _CANVAS, params=params)
        _WHOLE[key] = (out, dict(ctx.fitted))
    return _WHOLE[key]


def _divergence(op_id: str, where: str, *, freeze: bool,
                params: dict | None = None) -> float:
    whole, fitted = _whole(op_id, params=params)
    y0, x0 = _WINDOWS[where]
    sl = (slice(y0, y0 + _WINDOW_PX), slice(x0, x0 + _WINDOW_PX))
    window, _ = _render(op_id, _CANVAS[sl], frozen=fitted if freeze else None,
                        params=params)
    inner = (slice(_INSET, _WINDOW_PX - _INSET), slice(_INSET, _WINDOW_PX - _INSET))
    truth = whole[sl][inner]
    cov = np.isfinite(truth).all(axis=2)
    assert cov.any(), f"the {where} window is entirely uncovered — move it"
    ref = float(np.nanpercentile(np.abs(truth[cov]), 99.0)) or 1.0
    return float(np.nanmean(np.abs(window[inner] - truth)[cov])) / ref


# --- the sweep ---------------------------------------------------------------

@pytest.mark.parametrize("where", sorted(_WINDOWS))
@pytest.mark.parametrize("op_id", [i for i in _in_scope() if i not in _declared_unfaithful()])
def test_a_frozen_window_is_the_picture(op_id, where):
    err = _divergence(op_id, where, freeze=True)
    tol = _FLOAT_NOISE_TOL.get(op_id, _FAITHFUL_TOL)
    assert err <= tol, (
        f"{op_id} renders a {where} window {err:.4e} of full scale away from the "
        f"same pixels in the whole render, with the whole render's fits frozen "
        f"onto it. Either it measures something from the whole array that it does "
        f"not carry through EditContext.fit — route it through ctx.fit, and put it "
        f"on the four lists that enumerate those ops — or, if that genuinely "
        f"cannot be done, declare OpSpec.window_unfaithful on it with the reason "
        f"(which also makes the loupe name it to the reader) and record the "
        f"number and its window in _NOT_WINDOW_FAITHFUL, the way the three "
        f"entries there do. The tolerance applied was {tol:.0e}.")


@pytest.mark.parametrize("where", sorted(_WINDOWS))
@pytest.mark.parametrize("op_id", _declared_unfaithful())
def test_an_op_that_carries_nothing_renders_the_same_either_way(op_id, where):
    """An op that takes **no** measurement through ``ctx.fit`` cannot render
    differently for having a window's fits frozen onto it: the two renders are
    the same render. Which ops those are is read off what the whole render
    actually recorded, not asserted from a list — ``detail.denoise`` was in this
    set until v0.493.9 carried its span, and a hand-kept list would have gone
    stale exactly as the figures above did. The partition itself is pinned by
    :func:`test_one_declared_op_carries_a_fit_and_it_is_the_denoise`, so a
    regression that stopped every op recording fits cannot turn this file into
    three quiet skips."""
    if _whole(op_id)[1]:
        pytest.skip(f"{op_id} does carry a fit — "
                    f"test_the_carried_span_is_most_of_the_denoise_gap owns it")
    frozen = _divergence(op_id, where, freeze=True)
    loose = _divergence(op_id, where, freeze=False)
    assert frozen == pytest.approx(loose, abs=1e-12)


def test_one_declared_op_carries_a_fit_and_it_is_the_denoise():
    """What the skip above is allowed to skip, so it cannot grow quietly."""
    carries = sorted(i for i in _declared_unfaithful() if _whole(i)[1])
    assert carries == ["detail.denoise"], carries


#: What carrying the span bought ``detail.denoise``, per method: op params →
#: ``{window: (re-measured, carried)}``. The whole point of recording it is the
#: **tv / bright core** cell, which the carry made 2 % *worse* — the LEAD that
#: filed this warned the sign was method-dependent and it was right, just not
#: about the method it named. See the test below for why that is not a reason to
#: leave the span uncarried.
_DENOISE_SPAN_GAIN: dict[str, dict[str, tuple[float, float]]] = {
    "wavelet": {"bright core": (1.04e-04, 7.00e-05),
                "near the ragged edge": (1.05e-04, 7.74e-05),
                "star-poor far side": (1.02e-02, 7.97e-03)},
    "tv": {"bright core": (5.29e-03, 5.41e-03),
           "near the ragged edge": (6.30e-03, 5.75e-03),
           "star-poor far side": (9.96e-04, 3.73e-04)},
    "bilateral": {"bright core": (2.86e-03, 3.19e-05),
                  "near the ragged edge": (2.60e-03, 3.08e-05),
                  "star-poor far side": (8.47e-04, 1.56e-07)},
}


@pytest.mark.parametrize("method", sorted(_DENOISE_SPAN_GAIN))
def test_the_carried_span_is_most_of_the_denoise_gap(method):
    """The measurement the v0.493.5 LEAD asked for, kept executable.

    ``detail.denoise`` stays declared unfaithful, so the sweep above never reaches
    it and nothing else would notice if carrying the span stopped helping — or
    started hurting. It helps a great deal and not uniformly:

    * **bilateral** 2.9e-03 → 3.2e-05, ~90x, and 8.5e-04 → 1.6e-07 on the
      star-poor window. It is the method the preview's own advisory sends the
      reader here about ("check it at full size *instead* of raising the
      strength"), so it is the one that most needed to be right.
    * **wavelet** (the default) 1.3-1.5x on every window; the rest is BayesShrink.
    * **tv** 2.7x on the star-poor window — where the span error dominates — and
      within 10 % either way on the other two, *including 2 % worse on the bright
      core*. tv's residual is its stopping energy, not its span, so carrying the
      span neither fixes that term nor reliably moves it. Leaving the span
      re-measured to protect one 2 % cell would cost bilateral its 90x, so the
      carry stays and the cell is written down instead.

    Pinned to ±30 %: these are deterministic means over ~10^5 pixels, so the band
    is for a library bump, and a library bump that moves one of these by a third
    is a thing to look at rather than to absorb.
    """
    params = dict(_PARAMS["detail.denoise"], method=method)
    for where, (want_loose, want_frozen) in _DENOISE_SPAN_GAIN[method].items():
        loose = _divergence("detail.denoise", where, freeze=False, params=params)
        frozen = _divergence("detail.denoise", where, freeze=True, params=params)
        assert loose == pytest.approx(want_loose, rel=0.30), (method, where, loose)
        if want_frozen < _NOISE_FLOOR:
            # bilateral on the star-poor window lands at 1.6e-07, which is the
            # same float noise _FLOAT_NOISE_TOL is about: a +-30 % band on a
            # number that size would be pinning rounding. Assert it is *gone*.
            assert frozen <= _NOISE_FLOOR, (method, where, frozen)
        else:
            assert frozen == pytest.approx(want_frozen, rel=0.30), (
                method, where, frozen)


def test_carrying_the_span_is_what_made_deconvolution_window_faithful(where="bright core"):
    """``detail.deconvolve``'s fail-before, kept after the fix.

    The span was this op's only whole-array measurement, so carrying it moved the
    window from *visibly* re-measured to float noise: the sweep above now covers
    the op, and this pins the size of the step it took rather than only that it
    passes today. "Deconvolution understates on the proxy" is one of the four
    preview advisories, and the loupe is where it sends the reader to judge it.
    """
    loose = _divergence("detail.deconvolve", where, freeze=False)
    frozen = _divergence("detail.deconvolve", where, freeze=True)
    assert loose > 1e-5, loose
    assert frozen <= _FLOAT_NOISE_TOL["detail.deconvolve"], frozen
    assert loose / max(frozen, 1e-12) > 100.0, (loose, frozen)
    assert get_op("detail.deconvolve").window_unfaithful is None


@pytest.mark.parametrize("op_id", _declared_unfaithful())
def test_a_documented_exception_is_still_a_real_one(op_id):
    """So a fix cannot leave a stale excuse behind: an op listed as unfaithful has
    to be measurably unfaithful on at least one of the three windows."""
    worst = max(_divergence(op_id, w, freeze=True) for w in _WINDOWS)
    assert worst > _FAITHFUL_TOL, (
        f"{op_id} now renders every window exactly like the picture — clear its "
        f"OpSpec.window_unfaithful declaration (so the editor stops warning about "
        f"it) and delete its _NOT_WINDOW_FAITHFUL entry, and the sweep above "
        f"covers it from then on.")


@pytest.mark.parametrize("op_id", sorted(_NOT_WINDOW_FAITHFUL))
def test_the_recorded_divergence_is_the_measured_one(op_id):
    """An excuse carries a figure, and the figure has to be the measurement.

    v0.493.6 wrote these as prose and two of the three were wrong inside four
    days — both understated, both naming the wrong window — which is this file's
    own bug one level down: the *membership* was asserted and the numbers
    justifying it were not. They are the only numbers anywhere now (the registry
    declarations point here rather than repeating them), so they can go wrong in
    exactly one place, and this is it.
    """
    want, want_where, _ = _NOT_WINDOW_FAITHFUL[op_id]
    measured = {w: _divergence(op_id, w, freeze=True) for w in _WINDOWS}
    where = max(measured, key=measured.get)
    assert where == want_where, (
        f"{op_id} is worst on the {where!r} window ({measured[where]:.2e}), not "
        f"on the {want_where!r} one ({measured[want_where]:.2e}). Which window a "
        f"whole-array measurement goes wrong on is the thing the entry is "
        f"explaining, so update it.")
    assert measured[where] == pytest.approx(want, rel=0.30), (
        f"{op_id} measures {measured[where]:.3e} on its worst window and its "
        f"_NOT_WINDOW_FAITHFUL entry records {want:.3e}. Update the entry — or, "
        f"if the op got better, check whether it still belongs in the table at "
        f"all.")


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


def test_the_declared_exceptions_are_the_ones_measured_here():
    """The registry's declaration and this file's table are one list.

    ``OpSpec.window_unfaithful`` is what the loupe reads to name the ops it
    cannot vouch for (v0.493.7), and this table is where the numbers behind that
    claim live. Two homes for one list is how the prose lists this whole file
    exists about came to be wrong, so: the registry must declare exactly the ops
    measured unfaithful here, and each declaration must say *why* — an empty
    string is a flag with no sentence behind it, which the editor would have to
    render as a bare name.
    """
    assert _declared_unfaithful() == sorted(_NOT_WINDOW_FAITHFUL), (
        "OpSpec.window_unfaithful and _NOT_WINDOW_FAITHFUL disagree about which "
        "ops a window of the picture cannot reproduce. The sweeps above measure "
        "the registry's answer; fix whichever of the two is wrong.")
    for op_id in _declared_unfaithful():
        assert (get_op(op_id).window_unfaithful or "").strip(), op_id
        # And the declaration explains *why* without re-quoting the figure. Two
        # of the three it used to carry had gone wrong within four days of being
        # written, which is what _NOT_WINDOW_FAITHFUL's own numbers now being
        # asserted is for: a figure with two homes drifts in one of them.
        repeated = re.findall(r"\d(?:\.\d+)?e-\d+",
                              get_op(op_id).window_unfaithful or "")
        assert not repeated, (
            f"{op_id}'s OpSpec.window_unfaithful quotes {repeated}, a second "
            f"home for a number _NOT_WINDOW_FAITHFUL already holds and asserts. "
            f"Say where the figure lives instead of repeating it.")


def test_the_ops_outside_the_sweep_are_the_two_the_loupe_handles_itself():
    """Named, so that "every other op" above is checkable. Geometry ops are
    disabled on a window render and the additive background passes have their
    field replayed — ``tests/test_edit_field_replay.py`` owns that half."""
    outside = sorted(s.id for s in all_specs() if s.id not in _in_scope())
    assert outside == ["background.final_gradient", "background.level_coverage",
                       "background.subtract", "geometry.crop", "geometry.resize",
                       "geometry.rotate"]
