"""Preview↔export parity for the **whole one-click Auto recipe**, on a mosaic.

``tests/test_edit_proxy_parity.py`` measures the A2 class one op at a time: does
*this* pixel-unit parameter get scaled by the proxy factor? That is how the class
was found, and a 2026-09-09 sweep confirmed every current op passes it. But no
test ever renders the recipe Auto actually *builds* — eleven ops, several of
which measure the image and hand their answer to the next — twice, and compares
the two pictures. That composition is where the class hides next: an op can scale
its own parameter correctly and still be handed a differently-fitted input,
and a per-op assertion cannot see it.

So this file renders the same recipe on the decimated live-preview proxy and on
the native canvas, and asks whether a beginner clicking Auto is looking at the
picture they will save. AGENTS.md §1 judges every Auto/editor claim on a tiled
mosaic canvas, never on a single field, so the fixture is a ragged, unevenly-deep
mosaic strip and the proxy step is **5** — heavier than the owner's own mosaic
decimates to (a 3494x2470 canvas is step 3), because the gap grows with stride.

**What "parity" can mean here.** The two renders are of different pixel counts,
so they can never be equal: striding a star field alone moves a 99th percentile.
The bar is therefore the documented decimation floor — the two must agree on
every summary statistic to within :data:`_PARITY_BUDGET` of the display range.
Measured on this fixture today the worst statistic differs by **0.0034**, and an
A2-class defect moves it to **0.1085** — a 32x separation, which is what makes
the budget a real gate rather than a number chosen to pass.
:func:`test_the_parity_check_can_see_a_pixel_parameter_that_forgot_the_proxy_scale`
arms that trap on every run, so the guard cannot rot into an assertion that
nothing can fail.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.coverage_trim import largest_covered_rect
from seestack.edit.pipeline import apply_recipe
from seestack.edit.presets import auto_recipe
from seestack.edit.registry import EditContext
from tests.shapes import (
    assert_has_a_ragged_outline,
    assert_reference_is_the_thinnest_panel,
    peak_over_panel,
    uncovered_share,
)

#: A mosaic strip at a stride the owner's canvases reach. Small enough to render
#: at native resolution twice in a test, big enough that a 3 px star is still a
#: star and the background fit has something to fit.
_FULL_H, _FULL_W = 600, 3000
_PROXY_STEP = 5
_PANELS = 5

#: Per-panel frame depth and sky level — *uneven*, which is the owner's shape and
#: the one a rule taken from a whole-canvas number gets wrong (`tests/shapes.py`).
_PANEL_DEPTHS = (12, 12, 6, 9, 15)
_PANEL_SKY = (0.050, 0.054, 0.061, 0.049, 0.052)

#: A Seestar star is ~3 px FWHM at full resolution → sigma ≈ 1.27 px.
_STAR_SIGMA_PX = 1.27
_MEDIAN_FWHM_PX = 3.0

#: The OSC sensor's own cast, and the sky's own (warm) colour — two different
#: tints, so a colour calibration has something real to solve rather than a
#: fixture in which every path agrees.
_SENSOR_CAST = (0.82, 1.0, 1.22)
_SKY_TINT = (1.15, 1.0, 0.90)

#: How far apart the preview and the export may land on any one statistic, as a
#: fraction of the [0, 1] display range. This is the decimation floor the editor
#: has always carried (~2%), not a tolerance tuned to today's numbers: the honest
#: render measures 0.0034 against it, and the armed trap measures 0.1085.
_PARITY_BUDGET = 0.02


def _mosaic_canvas(seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """``(linear_rgb, coverage)`` for a ragged, unevenly-deep mosaic strip.

    Panels are *statistically* alike rather than positionally (`tests/shapes.py`):
    nothing here measures a seam or a gain across a join, so one shared star
    catalogue would buy nothing. What the fixture does have to carry is the
    uneven depth, the genuinely uncovered border, and a real object — the three
    things that decide which ops Auto emits at all.
    """
    rng = np.random.default_rng(seed)
    mono = np.zeros((_FULL_H, _FULL_W), dtype=np.float32)
    cov = np.zeros((_FULL_H, _FULL_W), dtype=np.float32)

    panel_w = _FULL_W // _PANELS
    for i in range(_PANELS):
        x0, x1 = i * panel_w, (i + 1) * panel_w
        mono[:, x0:x1] = _PANEL_SKY[i]
        cov[:, x0:x1] = _PANEL_DEPTHS[i]
        # Grain falls as 1/sqrt(depth), so the thin panel really is the noisy one.
        mono[:, x0:x1] += rng.normal(
            0.0, 0.0035 / np.sqrt(_PANEL_DEPTHS[i]), size=(_FULL_H, x1 - x0),
        ).astype(np.float32)

    # The union canvas' ragged, genuinely uncovered edge — NaN is "no coverage".
    mono[:18, :] = np.nan
    mono[-24:, :] = np.nan
    mono[:, :12] = np.nan
    mono[:, -30:] = np.nan
    cov[np.isnan(mono)] = 0.0

    rad = 6
    yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    kern = np.exp(-(xx ** 2 + yy ** 2) / (2 * _STAR_SIGMA_PX ** 2)).astype(np.float32)
    n_stars = 700
    ys = rng.integers(rad + 30, _FULL_H - rad - 30, n_stars)
    xs = rng.integers(rad + 40, _FULL_W - rad - 40, n_stars)
    amps = 10 ** rng.uniform(-1.5, -0.15, n_stars).astype(np.float32)
    for y, x, a in zip(ys, xs, amps, strict=True):
        mono[y - rad:y + rad + 1, x - rad:x + rad + 1] += a * kern

    # A faint extended object, so the stretch and the auto-contrast curve have
    # midtone structure to shape rather than a flat sky.
    gy, gx = np.mgrid[0:_FULL_H, 0:_FULL_W]
    mono = mono + (0.028 * np.exp(
        -(((gy - _FULL_H * 0.55) / (_FULL_H * 0.20)) ** 2
          + ((gx - _FULL_W * 0.42) / (_FULL_W * 0.06)) ** 2)
    )).astype(np.float32)

    rgb = np.empty((_FULL_H, _FULL_W, 3), dtype=np.float32)
    for c in range(3):
        rgb[..., c] = mono * _SKY_TINT[c] * _SENSOR_CAST[c]
    return np.ascontiguousarray(rgb, dtype=np.float32), cov


def _summary(img: np.ndarray) -> dict[str, float]:
    """The statistics a person would notice if they moved: how bright the sky
    sits, how the brightest structure lands, and the overall exposure."""
    flat = img.reshape(-1, 3)
    flat = flat[np.isfinite(flat).all(axis=1)]
    out: dict[str, float] = {}
    for c, name in enumerate("RGB"):
        col = flat[:, c]
        out[f"median_{name}"] = float(np.median(col))
        out[f"p01_{name}"] = float(np.percentile(col, 1))
        out[f"p99_{name}"] = float(np.percentile(col, 99))
    out["mean"] = float(flat.mean())
    return out


def _auto_from_the_proxy(canvas: tuple[np.ndarray, np.ndarray]):
    """``(recipe, proxy, cov_proxy)`` — the recipe the editor would build.

    This is the app's own order: the editor measures the recipe on the proxy it
    is previewing (``seestack.edit.proxy.build_proxy`` is a plain stride), and
    the export replays that same recipe on the native canvas.
    """
    full, cov = canvas
    proxy = np.ascontiguousarray(full[::_PROXY_STEP, ::_PROXY_STEP])
    cov_proxy = np.ascontiguousarray(cov[::_PROXY_STEP, ::_PROXY_STEP])
    recipe = auto_recipe(proxy, median_fwhm=_MEDIAN_FWHM_PX, is_mosaic=True,
                         trim_crop=largest_covered_rect(cov))
    return recipe, proxy, cov_proxy


def _render_both_ways(canvas: tuple[np.ndarray, np.ndarray]):
    """Render that one recipe on the proxy *and* on the native canvas."""
    full, cov = canvas
    recipe, proxy, cov_proxy = _auto_from_the_proxy(canvas)

    preview_errors: list[str] = []
    preview = apply_recipe(
        proxy, recipe,
        EditContext(proxy_scale=float(_PROXY_STEP), is_proxy=True,
                    coverage=cov_proxy, frame_coverage=cov_proxy),
        for_preview=True, errors=preview_errors,
    )
    export_errors: list[str] = []
    export = apply_recipe(
        full, recipe,
        EditContext(proxy_scale=1.0, is_proxy=False,
                    coverage=cov, frame_coverage=cov),
        errors=export_errors,
    )
    return recipe, preview, export, preview_errors, export_errors


def _worst_divergence(preview: np.ndarray, export: np.ndarray) -> tuple[str, float]:
    """``(statistic, gap)`` for the summary the two renders disagree on most.

    The export is strided down the same way the proxy was, so the two are
    compared as pictures of the same sky rather than at different sizes.
    """
    a = _summary(preview)
    b = _summary(export[::_PROXY_STEP, ::_PROXY_STEP])
    worst_key = max(a, key=lambda k: abs(a[k] - b[k]))
    return worst_key, abs(a[worst_key] - b[worst_key])


@pytest.fixture(scope="module")
def _canvas() -> tuple[np.ndarray, np.ndarray]:
    return _mosaic_canvas()


@pytest.fixture(scope="module")
def _honest_render(_canvas):
    """The two renders, shared: each pair costs a native-resolution render of the
    whole canvas, so the file pays for exactly two — this one and the armed
    trap's, which cannot share it because it changes the pipeline."""
    return _render_both_ways(_canvas)


def test_the_fixture_really_is_a_ragged_unevenly_deep_mosaic(_canvas):
    """State the fixture's claim and assert it (`tests/shapes.py`).

    Every one of the three findings that file records was a *fixture*
    assumption, not a code bug — so a file that says "on a mosaic" says which
    kind, in assertions. This one must be ragged (or Auto emits no crop) and
    unevenly deep (or the coverage levelling has nothing to level).

    It is deliberately **not** a fixture whose panels the depth threshold would
    discard: these five panels are each a fifth of the canvas, so the reference
    depth lands on the thinnest of them and nothing real sits below it. That is
    the claim this file needs — the trim it feeds Auto is an honest border trim,
    not the D1 shape — and `tests/shapes.py` has a separate assertion for each,
    precisely so a file cannot imply the one it does not have.
    """
    _, cov = _canvas
    assert_has_a_ragged_outline(cov, what="the Auto-parity mosaic")
    assert_reference_is_the_thinnest_panel(cov, what="the Auto-parity mosaic")
    assert peak_over_panel(cov) > 2.0, (
        "the panels should differ in depth by more than noise, or the coverage "
        "levelling in the recipe has nothing to level")
    assert 0.02 < uncovered_share(cov) < 0.25, (
        "the border should be a real ragged edge, not a hairline and not most "
        "of the canvas")


def test_auto_emits_its_mosaic_ops_on_this_canvas(_canvas):
    """The parity claim is only about the recipe Auto actually builds, so pin
    that the mosaic-only ops are in it — otherwise a future change could quietly
    reduce this file to a single-field test that still passes."""
    recipe, _, _ = _auto_from_the_proxy(_canvas)
    ids = [op.id for op in recipe.ops if op.enabled]
    assert ids[0] == "background.level_coverage", (
        f"coverage levelling must lead the mosaic recipe, got {ids}")
    assert ids[-1] == "geometry.crop", (
        f"the ragged border trim must come last, got {ids}")
    for required in ("background.final_gradient", "tone.color_calibrate",
                     "tone.stretch", "tone.scnr", "tone.saturation", "tone.curves"):
        assert required in ids, f"{required} missing from the Auto recipe: {ids}"


def test_the_auto_recipe_previews_the_picture_it_will_export(_honest_render):
    """The whole point of a live preview: what you see is what you save.

    Measured today the worst statistic differs by 0.0034 — well inside the
    decimation floor. A regression to a differently-*fitted* preview (an op
    measuring the proxy in full-resolution pixels, or handing the next op a
    differently-scaled input) shows up here as a jump of an order of magnitude,
    as the armed-trap test below demonstrates on this very fixture.
    """
    _, preview, export, preview_errors, export_errors = _honest_render

    assert preview_errors == [], f"the preview render failed ops: {preview_errors}"
    assert export_errors == [], f"the export render failed ops: {export_errors}"

    key, gap = _worst_divergence(preview, export)
    assert gap < _PARITY_BUDGET, (
        f"one-click Auto's preview and export disagree on {key} by {gap:.4f} of "
        f"the display range (budget {_PARITY_BUDGET}) — the beginner is being "
        "shown a picture they will not get")


def test_the_parity_check_can_see_a_pixel_parameter_that_forgot_the_proxy_scale(
        _canvas, monkeypatch):
    """The guard above is only worth having if it can fail, so arm the trap.

    ``EditContext.scaled_px`` is the single seam every pixel-unit parameter goes
    through to become a proxy-sized one. Making it the identity is exactly the A2
    defect — a preview that applies full-resolution pixel measures to a decimated
    image — and the fixture must register it far outside the budget rather than
    inside the decimation noise.
    """
    monkeypatch.setattr(EditContext, "scaled_px", lambda self, px: float(px))

    _, preview, export, _, _ = _render_both_ways(_canvas)
    key, gap = _worst_divergence(preview, export)

    assert gap > _PARITY_BUDGET * 2.0, (
        f"an unscaled pixel parameter moved {key} by only {gap:.4f} — this "
        "fixture cannot see the bug class it exists to guard, so the passing "
        "test above proves nothing")
