"""Every editor control still *does* something — the measurement a pair sweep can't make.

Two of the last three editor findings were ops that silently **stopped working**,
not ops that broke a contract:

* **v0.492.27** — a geometry op at its own defaults reshapes nothing, while two
  surfaces switched themselves off as though it had.
* **v0.492.28** — ``background.level_coverage`` is dead with an *aimed* Crop,
  Rotate or Resize above it (measured 0.142 of full scale on its own against
  **0.000000**), and nothing said so.

The 2026-10-02 sweep over all 441 ordered op *pairs* reported ``errors == []`` for
that very pair, and was right to: "the op did nothing" violates none of the
invariants a pair sweep checks (an op error, the overlay's shape, the recorded
crop, the WCS steps, NaN = no coverage). Its own record named what was missing —
*"that needs a per-op 'did appending this op change the picture?' measurement,
which is the shape of the next sweep in this family and is not written"*. This is
that measurement, written down so it runs on every commit instead of once by hand.

**What it pins.** For every registered op, with parameters chosen to be plainly
non-trivial, appending the op to a recipe moves the rendered picture by at least
:data:`_EFFECT_FLOOR` — on a **mosaic** canvas (where the owner's pictures live)
and at a **decimated proxy scale** as well as at export scale, because an op that
works on the export and is dead in the live preview is the same defect wearing the
preview↔export costume. An op that legitimately does nothing in one of those
states is listed in :data:`_INERT_BY_DESIGN` **with the surface that tells the
user so** — and is then asserted to be *exactly* inert, so a documented skip
cannot quietly disappear either.

**Why the floor is a separation and not a tuning.** Measured on this fixture, the
smallest live effect is ``detail.chroma_denoise`` on the ×4 proxy at a mean
``1.4e-3`` of full scale, and the single inert case is ``0.0`` exactly. The floor
sits ~13x under the former and infinitely above the latter; no case lies between.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.ops.geometry import GEOMETRY_OP_IDS
from seestack.edit.pipeline import apply_recipe
from seestack.edit.recipe import OpInstance, Recipe, validate_ops
from seestack.edit.registry import EditContext, all_specs, get_op
from tests.shapes import (
    assert_has_a_ragged_outline,
    assert_weighted,
    describe_coverage,
    peak_over_panel,
)
from tests.synth import make_shared_sky_field, star_catalog

#: A 2x2 mosaic whose panels really overlap, at a size two renders of it fit in a
#: test. One shared star catalog, so an overlap holds the *same* stars (the
#: `tests/shapes.py` "positionally alike" claim) — otherwise nothing measured
#: across a join exercises anything.
_PANEL_H, _PANEL_W = 180, 240
_PANEL_PITCH = 0.78          # panel pitch as a share of a panel ⇒ real overlaps

#: Uneven panel depth — the owner's shape, and the one a rule taken from a
#: whole-canvas or *peak* number gets wrong. Weighted, not integral: with
#: ``quality_weighted`` on (the walk-away default) a coverage value is a sum of
#: per-frame weights rather than a frame count.
_PANEL_DEPTHS = ((6.0, 6.0), (6.0, 3.0))
#: Each panel's own sky offset — the steps ``background.level_coverage`` exists
#: to equalise.
_PANEL_SKY_STEPS = ((0.0, 0.004), (-0.003, 0.009))

_STAR_FWHM_PX = 3.0          # a Seestar star at full resolution
_SKY_NOISE_ADU = 150.0       # real grain, so the denoise has something to remove
_SENSOR_CAST = (0.82, 1.00, 1.22)   # the OSC cast a colour calibration removes
_SKY_TINT = (1.16, 1.00, 0.90)      # light pollution is warm; the stars are not

#: The two render geometries every op is measured at: the export (native pixels)
#: and a decimated live-preview proxy at a stride the owner's mosaics reach.
_SCALES = (1.0, 4.0)

#: Mean absolute change, in display space, below which a control is "doing
#: nothing". See the module docstring for the measured margins either side.
_EFFECT_FLOOR = 1e-4

#: The stretch every op is placed on the correct side of, so an op is never
#: measured in the wrong stage (which is a different defect, with its own
#: surface — ``stageConflicts.ts`` and the editor's "No Stretch step" alert).
_STRETCH = ("tone.stretch", {"mode": "stf", "target_bg": 0.20})

#: Parameters that make each op plainly non-trivial. Not its defaults: several
#: ops default to a deliberate no-op (every geometry op does, v0.492.27) so the
#: Add menu never moves the picture before the user has aimed the control.
_EFFECT: dict[str, dict] = {
    "background.subtract": {"mode": "per_channel", "box_size": 48},
    "background.final_gradient": {"mode": "luminance", "box_size": 96},
    "background.level_coverage": {},
    "detail.hot_pixels": {"sigma": 3.0},
    "detail.denoise": {"method": "wavelet", "strength": 0.8},
    "detail.chroma_denoise": {"strength": 0.9, "radius": 10.0},
    "detail.sharpen": {"amount": 1.5, "radius": 2.0},
    "detail.deconvolve": {"iterations": 4, "psf_sigma": 1.5},
    "geometry.crop": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9},
    "geometry.rotate": {"angle": 7.0},
    "geometry.resize": {"scale": 0.5},
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

#: ``(op id, proxy scale)`` → why this control legitimately does nothing there,
#: **and where the app says so**. A new entry here is a claim that the user is
#: told; adding one without that is how v0.492.28 happened.
_INERT_BY_DESIGN: dict[tuple[str, float], str] = {
    ("detail.hot_pixels", 4.0):
        "deliberate and captioned: on a decimated proxy a star is "
        "indistinguishable from a hot pixel, so `hot_pixels_skipped_on_proxy` "
        "returns the image untouched in the live preview rather than erase the "
        "stars, and the editor carries the advisory "
        "(`hotPixelsPreview.ts`, pinned by its own vitest).",
}


def _ops(*pairs: tuple[str, dict]) -> list[OpInstance]:
    return validate_ops([OpInstance(id=i, params=dict(p)) for i, p in pairs])


def _mosaic_canvas() -> tuple[np.ndarray, np.ndarray]:
    """A linear 2x2 mosaic union canvas and its weighted coverage map.

    Built the way a stack is: each panel is a window onto one star catalog,
    overlapping pixels are the mean of the panels that cover them, and the
    coverage map is the sum of their per-frame weights. On top of that, the
    structure each op under test needs something of — a light-pollution tilt, a
    nebula, the OSC sensor cast against a warmer sky, green blotches, hot pixels,
    real grain — and NaN where nothing covers, which is this app's "no coverage".
    """
    ox = int(_PANEL_W * _PANEL_PITCH)
    oy = int(_PANEL_H * _PANEL_PITCH)
    w, h = _PANEL_W + ox, _PANEL_H + oy
    catalog = star_catalog(seed=5, width=w + 40, height=h + 40, n_stars=170,
                           star_fwhm_px_full=_STAR_FWHM_PX)
    rng = np.random.default_rng(3)

    acc = np.zeros((h, w), dtype=np.float32)
    panels = np.zeros((h, w), dtype=np.float32)
    cov = np.zeros((h, w), dtype=np.float32)
    for i in range(2):
        for j in range(2):
            y0, x0 = i * oy, j * ox
            frame = make_shared_sky_field(
                catalog, width=_PANEL_W, height=_PANEL_H, origin=(x0, y0),
                sky_level=1000.0, sky_noise=_SKY_NOISE_ADU,
                noise_seed=11 + 2 * i + j,
                star_fwhm_px_full=_STAR_FWHM_PX).astype(np.float32) / 65535.0
            box = (slice(y0, y0 + _PANEL_H), slice(x0, x0 + _PANEL_W))
            acc[box] += frame + _PANEL_SKY_STEPS[i][j]
            panels[box] += 1.0
            cov[box] += _PANEL_DEPTHS[i][j] * float(rng.uniform(0.94, 1.06))

    covered = panels > 0
    lum = np.zeros((h, w), dtype=np.float32)
    lum[covered] = acc[covered] / panels[covered]

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    lum += 0.010 * (xx / w) + 0.006 * (yy / h)          # light-pollution tilt
    cy, cx = h * 0.46, w * 0.54
    nebula = 0.045 * np.exp(-(((yy - cy) / (h * 0.20)) ** 2
                              + ((xx - cx) / (w * 0.20)) ** 2))

    rgb = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3):
        rgb[..., c] = (lum * _SKY_TINT[c] + nebula.astype(np.float32)) * _SENSOR_CAST[c]

    for _ in range(22):                                  # green blotches (SCNR)
        y = int(rng.integers(16, h - 16))
        x = int(rng.integers(16, w - 16))
        r = int(rng.integers(6, 18))
        rgb[max(0, y - r):y + r, max(0, x - r):x + r, 1] += 0.010
    for _ in range(70):                                  # stuck sensor pixels
        y = int(rng.integers(3, h - 3))
        x = int(rng.integers(3, w - 3))
        rgb[y, x, :] += 0.5

    rgb[~covered] = np.nan                               # NaN = "no coverage"
    rgb[:18, :26] = np.nan
    cov[:18, :26] = 0.0
    rgb[-22:, -30:] = np.nan                             # a ragged outline
    cov[-22:, -30:] = 0.0
    return np.ascontiguousarray(rgb, dtype=np.float32), cov


@pytest.fixture(scope="module")
def canvas() -> tuple[np.ndarray, np.ndarray]:
    return _mosaic_canvas()


def _ctx(cov: np.ndarray, scale: float) -> EditContext:
    return EditContext(coverage=cov.copy(), frame_coverage=cov.copy(),
                       proxy_scale=scale, is_proxy=scale > 1.0)


def _recipes(op_id: str, params: dict) -> tuple[Recipe, Recipe]:
    """``(without, with)`` — the op added on the correct side of the stretch."""
    spec = get_op(op_id)
    assert spec is not None, op_id
    if spec.is_stretch:
        return Recipe(ops=[]), Recipe(ops=_ops((op_id, params)))
    if spec.stage == "linear":
        return Recipe(ops=_ops(_STRETCH)), Recipe(ops=_ops((op_id, params), _STRETCH))
    return Recipe(ops=_ops(_STRETCH)), Recipe(ops=_ops(_STRETCH, (op_id, params)))


def _effect(rgb: np.ndarray, cov: np.ndarray, op_id: str, scale: float
            ) -> tuple[float, tuple[int, int], tuple[int, int]]:
    """``(mean |Δ| in display space, shape without, shape with)``.

    A reshaping op returns ``inf`` — a changed frame shape *is* the effect, and is
    pinned op-by-op in ``tests/test_edit_geometry_noop.py``.
    """
    without, with_op = _recipes(op_id, _EFFECT[op_id])
    errors: list[str] = []
    a = apply_recipe(rgb, without, _ctx(cov, scale), errors=errors)
    b = apply_recipe(rgb, with_op, _ctx(cov, scale), errors=errors)
    assert errors == [], f"{op_id} at scale {scale}: {errors}"
    if a.shape != b.shape:
        return float("inf"), a.shape[:2], b.shape[:2]
    both = np.isfinite(a).all(-1) & np.isfinite(b).all(-1)
    assert both.any(), f"{op_id} at scale {scale}: nothing finite to compare"
    return float(np.abs(a[both] - b[both]).mean()), a.shape[:2], b.shape[:2]


# --------------------------------------------------------------------------- #
# The fixture states its own claims, so a weakened fixture fails here rather
# than silently making every assertion below pass for the wrong reason.
# --------------------------------------------------------------------------- #

def test_the_fixture_is_the_mosaic_this_file_claims(canvas) -> None:
    rgb, cov = canvas
    assert_weighted(cov, what="the op-effect canvas")
    assert_has_a_ragged_outline(cov, what="the op-effect canvas")
    # A four-way corner: where the gap between "the peak" and "a panel" is widest.
    assert peak_over_panel(cov) > 3.0, describe_coverage(cov)
    assert np.isnan(rgb).any(), "no uncovered pixels: NaN semantics untested"
    assert np.isfinite(rgb).all(-1).mean() > 0.9, describe_coverage(cov)


def test_every_registered_op_declares_an_effect_case() -> None:
    """A newly-registered op has to say what makes it do something.

    The drift guard that keeps this file from going quietly out of date: without
    it a new op is simply not measured, which is the state the editor was in for
    the two findings in the module docstring.
    """
    registered = {spec.id for spec in all_specs()}
    assert set(_EFFECT) == registered, (
        f"missing: {sorted(registered - set(_EFFECT))}; "
        f"stale: {sorted(set(_EFFECT) - registered)}")


def test_inert_table_names_only_registered_ops_and_measured_scales() -> None:
    registered = {spec.id for spec in all_specs()}
    for op_id, scale in _INERT_BY_DESIGN:
        assert op_id in registered, op_id
        assert scale in _SCALES, (op_id, scale)


# --------------------------------------------------------------------------- #
# The measurement.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("scale", _SCALES)
@pytest.mark.parametrize("op_id", sorted(_EFFECT))
def test_appending_an_op_changes_the_picture(canvas, op_id: str, scale: float) -> None:
    rgb, cov = canvas
    moved, shape_a, shape_b = _effect(rgb, cov, op_id, scale)
    reason = _INERT_BY_DESIGN.get((op_id, scale))
    if reason is not None:
        pytest.skip(f"{op_id} is inert at scale {scale} by design: {reason}")
    if op_id in GEOMETRY_OP_IDS:
        assert shape_a != shape_b, (
            f"{op_id} at scale {scale} left the frame {shape_a} — an aimed "
            f"geometry op must reshape it (see tests/test_edit_geometry_noop.py)")
        return
    assert moved >= _EFFECT_FLOOR, (
        f"{op_id} at proxy scale {scale} moved the picture by only {moved:.3e} of "
        f"full scale — the control is doing nothing. Either it is broken, or it "
        f"is inert here on purpose: if so the user has to be told, and the reason "
        f"and the surface that tells them belong in _INERT_BY_DESIGN.")


@pytest.mark.parametrize(("op_id", "scale"), sorted(_INERT_BY_DESIGN))
def test_a_documented_inert_case_is_exactly_inert(canvas, op_id: str,
                                                  scale: float) -> None:
    """The other direction, so the table cannot rot.

    A documented skip that quietly starts doing something is as much a surprise
    as one that quietly stops: the app is carrying an advisory that is no longer
    true. These skips return the input array, so the honest bar is *exactly* zero.
    """
    rgb, cov = canvas
    moved, shape_a, shape_b = _effect(rgb, cov, op_id, scale)
    assert shape_a == shape_b, (op_id, scale, shape_a, shape_b)
    assert moved == 0.0, (
        f"{op_id} at proxy scale {scale} now moves the picture by {moved:.3e}, but "
        f"_INERT_BY_DESIGN still claims: {_INERT_BY_DESIGN[(op_id, scale)]}")


def test_coverage_leveling_dies_under_an_aimed_geometry_op_and_not_a_default_one(
        canvas) -> None:
    """v0.492.28's finding, pinned from the engine side.

    ``_level_coverage`` bins the image against the run's own coverage map, so once
    something above it has really reshaped the frame the two cannot be aligned and
    it skips — the control is dead. A geometry op at its **own defaults** reshapes
    nothing (v0.492.27), so the leveling still runs: that is the distinction
    ``strandedCoverageLevelingUids`` is built on, and the editor's note depends on
    it being true of the engine.
    """
    rgb, cov = canvas
    level = ("background.level_coverage", {})

    def moved(*before: tuple[str, dict]) -> float:
        base = Recipe(ops=_ops(*before, _STRETCH))
        with_level = Recipe(ops=_ops(*before, level, _STRETCH))
        errors: list[str] = []
        a = apply_recipe(rgb, base, _ctx(cov, 1.0), errors=errors)
        b = apply_recipe(rgb, with_level, _ctx(cov, 1.0), errors=errors)
        assert errors == [], errors
        assert a.shape == b.shape
        both = np.isfinite(a).all(-1) & np.isfinite(b).all(-1)
        return float(np.abs(a[both] - b[both]).mean())

    alone = moved()
    assert alone >= _EFFECT_FLOOR, alone
    for op_id in sorted(GEOMETRY_OP_IDS):
        spec = get_op(op_id)
        assert spec is not None
        at_defaults = moved((op_id, spec.defaults()))
        assert at_defaults == pytest.approx(alone, rel=1e-6), (
            f"{op_id} at its own defaults reshapes nothing, so the leveling must "
            f"still run: {at_defaults:.3e} vs {alone:.3e} on its own")
        aimed = moved((op_id, _EFFECT[op_id]))
        assert aimed == 0.0, (
            f"an aimed {op_id} above it leaves the leveling skipped (the engine "
            f"cannot align the coverage map to a reshaped frame), so this must be "
            f"exactly 0.0, not {aimed:.3e} — the editor's "
            f"`strandedCoverageLevelingUids` note is built on it")
