"""Every number **Auto writes into the recipe** has to be one its slider can hold.

**Why this file exists.** v0.493.11 put the editor's ten "From your image" /
"From your stars" buttons on their controls' own stops and deliberately left the
on-by-default half alone: ``measured_auto_knobs`` hands ``auto_recipe``
continuous values — ``target_bg`` a bare ``np.clip`` of a measured sky,
``saturation`` a bare clip of a measured σ, the three crossfade knobs rounded to
*three* decimals on 0.05 and 0.1 grids — and ``auto_op_params`` wrote them
straight into the op params. Measured on the bundled sample through the live app:
``tone.stretch.target_bg = 0.23880698146298526`` on a 0.01-step control, and
``tone.saturation.amount = 1.248`` on a 0.05-step control whose stops are 1.20
and 1.25. So the recipe held one number, the readout beside it showed a second,
the "What Auto-process did" sentence a third, and the slider could only be a
fourth — on the picture Auto made, which is the first thing the owner opens.

Snapping them changes what every auto-edited export renders, so what this file
asserts is both halves of that: that the numbers are now settable, **and** what
landing them cost the picture — the last test renders the real recipe several
ways on four realistic canvases (two of them mosaics) and bounds the snap
against **one click of the same slider**, rather than quoting a number.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit import auto_prefs, presets
from seestack.edit.pipeline import apply_recipe
from seestack.edit.recipe import OpInstance, Recipe
from seestack.edit.registry import (
    EditContext,
    all_specs,
    param_grid,
    param_spec,
    snap_to_param,
)

# Every (op, param) ``auto_op_params`` can emit a *number* for, and the knob in
# ``auto_knob_values`` it comes from. ``radius`` has no knob — it is derived from
# the target's median FWHM — so it carries ``None``.
_EMITTED: tuple[tuple[str, str, str | None], ...] = (
    ("tone.stretch", "target_bg", "target_bg"),
    ("tone.stretch", "highlights", "highlight_protect"),
    ("tone.scnr", "amount", "scnr_amount"),
    ("tone.saturation", "amount", "saturation"),
    ("detail.denoise", "strength", "denoise_strength"),
    ("detail.chroma_denoise", "strength", "chroma_strength"),
    ("detail.sharpen", "amount", "sharpen_amount"),
    ("detail.sharpen", "radius", None),
)

# Which op parameter each taste bias moves — ``auto_prefs._PARAM_STEP``'s own
# comments, read as code so the claim below is checked rather than trusted.
_BIAS_CONTROL: dict[str, tuple[str, str]] = {
    "brightness": ("tone.stretch", "target_bg"),
    "saturation": ("tone.saturation", "amount"),
    "sharpen": ("detail.sharpen", "amount"),
    "denoise": ("detail.denoise", "strength"),
    "green": ("tone.scnr", "amount"),
    "highlights": ("tone.stretch", "highlights"),
}


def _scene(h, w, *, sigma, seed=0, panels=(1, 1)):
    """A realistic *linear* stacked canvas: sky, a faint extended object, stars,
    noise and a light-pollution ramp — and, on a mosaic, per-panel level offsets
    with the coverage map that goes with them.

    The mosaic shapes are the ones AGENTS.md §1 requires an Auto claim to be
    judged on, and the panel count matters here: the recipe gains
    ``background.level_coverage`` and the border trim, so the picture the
    snapped stretch target is measured on is a different one.
    """
    rng = np.random.default_rng(seed)
    img = np.broadcast_to(np.array([0.10, 0.12, 0.09], np.float32),
                          (h, w, 3)).astype(np.float32).copy()
    yy, xx = np.mgrid[0:h, 0:w]
    img += (np.exp(-(((xx - w / 2) / (w / 6.0)) ** 2
                     + ((yy - h / 2) / (h / 8.0)) ** 2))[..., None]
            * np.array([0.05, 0.03, 0.02])).astype(np.float32)
    for _ in range(max(60, int(h * w * 2.0e-4))):
        cy, cx = int(rng.integers(8, h - 8)), int(rng.integers(8, w - 8))
        gy, gx = np.mgrid[cy - 6:cy + 7, cx - 6:cx + 7]
        img[cy - 6:cy + 7, cx - 6:cx + 7] += (
            float(rng.uniform(0.2, 0.9))
            * np.exp(-(((gx - cx) / 1.6) ** 2 + ((gy - cy) / 1.6) ** 2))
        )[..., None].astype(np.float32)
    img += rng.normal(0.0, sigma, img.shape).astype(np.float32)
    img += (0.02 * (xx / w))[..., None].astype(np.float32)
    cov = None
    ny, nx = panels
    if (ny, nx) != (1, 1):
        cov = np.zeros((h, w), np.float32)
        offs = (-0.004, 0.0, 0.003, 0.006, -0.002, 0.005)
        depth = (22.0, 18.0, 14.0, 12.0, 20.0, 16.0)
        ph, pw = h // ny, w // nx
        for i in range(ny):
            for j in range(nx):
                k = i * nx + j
                sl = (slice(i * ph, (i + 1) * ph), slice(j * pw, (j + 1) * pw))
                img[sl] += offs[k % len(offs)]
                cov[sl] = depth[k % len(depth)]
    return img, cov


# The populations: scenes × the taste profiles that shift what Auto emits.
_SCENES = (
    ("clean single field", (140, 180), 0.004, (1, 1)),
    ("noisy single field", (140, 180), 0.02, (1, 1)),
    ("very noisy field", (140, 180), 0.06, (1, 1)),
    ("2x2 mosaic", (160, 160), 0.008, (2, 2)),
    ("2x3 mosaic", (150, 210), 0.015, (2, 3)),
)


def _profiles():
    """No profile, and every single bias at each end of its range.

    A taste bias is the other way a number reaches the op params (``target_bg``
    continuous *and* shifted), so the sweep covers it rather than only the
    never-configured library.
    """
    out: list[tuple[str, dict | None]] = [("no profile", None)]
    for param in auto_prefs._PARAM_STEP:
        for steps in (-auto_prefs.MAX_STEPS, auto_prefs.MAX_STEPS):
            prof = auto_prefs.profile_of_biases({param: steps})
            out.append((f"{param} {steps:+d}", prof))
    return out


def _emitted_numbers():
    """Every number ``auto_op_params`` emits across the whole population."""
    out = []
    for tag, (h, w), sigma, panels in _SCENES:
        img, cov = _scene(h, w, sigma=sigma, panels=panels)
        is_mosaic = panels != (1, 1)
        knobs = presets.measured_auto_knobs(img, cov if is_mosaic else None)
        for ptag, prof in _profiles():
            values = presets.auto_knob_values(knobs, prof)
            for fwhm in (None, 1.5, 3.2, 7.3):
                emitted = presets.auto_op_params(values, fwhm)
                for op_id, params in emitted.items():
                    for key, val in params.items():
                        if isinstance(val, (int, float)) and not isinstance(val, bool):
                            out.append((f"{tag}/{ptag}/fwhm={fwhm}",
                                        op_id, key, float(val)))
    assert out, "the sweep must produce something to check"
    return out


def test_every_number_auto_writes_is_one_its_own_control_can_be_set_to():
    """The hot-path half of v0.493.11's defect, for the whole population.

    Fails before the fix on ``tone.stretch.target_bg`` (a bare ``np.clip`` on a
    0.01-step control), ``tone.saturation.amount`` (a bare clip on a 0.05 grid)
    and the three crossfade knobs (three decimals on 0.05/0.1 grids).
    """
    offenders = []
    for tag, op_id, key, val in _emitted_numbers():
        p = param_spec(op_id, key)
        grid = param_grid(op_id, key)
        if p.min is not None and val < p.min - 1e-9:
            offenders.append(f"{op_id}.{key} = {val} below min {p.min} [{tag}]")
        if p.max is not None and val > p.max + 1e-9:
            offenders.append(f"{op_id}.{key} = {val} above max {p.max} [{tag}]")
        if grid and not any(abs(val - stop) <= 1e-9 for stop in grid):
            offenders.append(
                f"{op_id}.{key} = {val} is not a stop of {p.step} [{tag}]")
    assert not offenders, ("Auto wrote values its sliders cannot hold: "
                           + "; ".join(sorted(set(offenders))[:12]))


def test_every_number_auto_writes_reads_the_same_in_the_editors_readout():
    """And the "the box beside it shows a different number" half.

    ``StackOptionControl`` renders a float control's readout at
    ``decimalScale={2}`` and ``presets._auto_num`` writes the "What Auto-process
    did" sentence at the same precision, so a value carrying a third decimal is
    three numbers for one knob. Every stop of every editor control is two
    decimals or fewer (asserted in
    :func:`test_no_control_has_a_stop_the_two_decimal_readout_cannot_show`), so
    being on the grid settles this — which is why the readout was not changed.
    """
    for tag, op_id, key, val in _emitted_numbers():
        assert round(val, 2) == pytest.approx(val), (
            f"{op_id}.{key} = {val} cannot be shown in the 2-decimal readout "
            f"[{tag}]")
        assert float(presets._auto_num(val)) == pytest.approx(val), (
            f"{op_id}.{key} = {val} is not what the 'What Auto did' sentence "
            f"says [{tag}]")


def test_no_control_has_a_stop_the_two_decimal_readout_cannot_show():
    """Why the readout was left at two decimals rather than widened.

    The filed lead's option (b) was to derive ``decimalScale`` from the
    parameter's own ``step`` (or raise it) so the box could show a third
    decimal. It is unnecessary **because no control declares a step finer than
    two decimals** — so once Auto's numbers are on the grid the readout is exact
    for every value a control can hold, and an extra decimal would be a decimal
    with nothing to show. That is a property of the registry, not a fact about
    today's numbers, so it is asserted: the day a 0.001-step parameter is added,
    this fails and the readout is the thing to fix.
    """
    offenders = []
    for spec in all_specs():
        for p in spec.params:
            if p.type != "float" or not p.step:
                continue
            if round(float(p.step), 2) != pytest.approx(float(p.step)):
                offenders.append(f"{spec.id}.{p.key} step {p.step}")
    assert not offenders, ("a step the 2-decimal readout cannot show: "
                           + "; ".join(offenders))


def test_every_taste_step_is_a_whole_number_of_its_controls_own_stops():
    """Why snapping cannot swallow a feedback tap.

    ``snap_to_param`` rounds onto a grid anchored at the parameter's ``min``, so
    ``snap(v + k·step)`` is ``snap(v) + k·step`` exactly when the shift is a
    whole number of stops. Every ``auto_prefs._PARAM_STEP`` is (brightness 0.02
    on a 0.01 grid, saturation 0.05 on 0.05, sharpen 0.10 on 0.1, denoise 0.10
    on 0.05, green 0.10 on 0.05, highlights 0.25 on 0.05), and every
    ``_PARAM_RANGE`` endpoint and post-profile clamp is itself a stop — so a tap
    that moved the picture before the snap still moves it, which is what
    ``tests/test_auto_inert_cues.py`` is then entitled to assume.
    """
    bad = []
    for param, step in auto_prefs._PARAM_STEP.items():
        op_id, key = _BIAS_CONTROL[param]
        control = float(param_spec(op_id, key).step)
        n = step / control
        if abs(n - round(n)) > 1e-9:
            bad.append(f"{param} step {step} is {n:.3f} stops of {op_id}.{key}")
        for edge in auto_prefs._PARAM_RANGE[param]:
            grid = param_grid(op_id, key)
            if grid and not any(abs(edge - s) <= 1e-9 for s in grid):
                bad.append(f"{param} range edge {edge} is off {op_id}.{key}'s grid")
    for name, val, (op_id, key) in (
            ("_AUTO_DENOISE_MAX", presets._AUTO_DENOISE_MAX,
             ("detail.denoise", "strength")),
            ("_AUTO_CHROMA_MAX", presets._AUTO_CHROMA_MAX,
             ("detail.chroma_denoise", "strength"))):
        grid = param_grid(op_id, key)
        if grid and not any(abs(val - s) <= 1e-9 for s in grid):
            bad.append(f"{name} = {val} is off {op_id}.{key}'s grid")
    assert not bad, "; ".join(bad)


# --------------------------------------------------------------------------- #
# What landing them cost the picture
# --------------------------------------------------------------------------- #

def _unsnapped(recipe: Recipe, values: dict[str, float]) -> Recipe:
    """``recipe`` with each snapped param put back to the continuous value
    ``auto_knob_values`` measured — i.e. the recipe as it was before the fix."""
    byknob = {(op_id, key): knob for op_id, key, knob in _EMITTED if knob}
    ops = []
    for op in recipe.ops:
        params = dict(op.params or {})
        for key in list(params):
            knob = byknob.get((op.id, key))
            if knob is not None and isinstance(params[key], (int, float)):
                params[key] = float(values[knob])
        ops.append(OpInstance(id=op.id, params=params, enabled=op.enabled,
                              uid=op.uid))
    return Recipe(ops=ops)


def _render(img, recipe, cov):
    out = apply_recipe(img, recipe,
                       EditContext(coverage=cov, frame_coverage=cov))
    return np.clip(np.nan_to_num(out), 0.0, 1.0) * 255.0


# The canvases the *render* comparison runs on, which have to be bigger than the
# arithmetic sweep's — measured, and the reason is worth writing down. The Auto
# recipe ends in ``tone.curves`` with ``auto=True``, which derives its midtone
# lift from its own stretched input, and on a canvas of ~25 k pixels that
# derivation is unstable: on a 140×180 scene a **tenth** of a ``target_bg`` step
# (+0.001) moves the picture by 17.3 of 255 and a whole step by 19.6, so every
# change reads the same size and no comparison means anything. From ~250×320 up
# the response is proportionate again (+0.001 → 0.28, +0.002 → 0.79,
# +0.005 → 2.25, +0.01 → 4.77 at 250×320), which is AGENTS.md §1's rule arriving
# by a side door: a fixture too small to measure on is not a small version of the
# owner's data.
_RENDER_SCENES = (
    ("clean single field", (300, 400), 0.004, (1, 1)),
    ("noisy single field", (300, 400), 0.02, (1, 1)),
    ("2x2 mosaic", (320, 320), 0.008, (2, 2)),
    ("2x3 mosaic", (300, 420), 0.015, (2, 3)),
)


def _with(recipe: Recipe, changes: dict[tuple[str, str], float]) -> Recipe:
    """``recipe`` with each ``(op_id, key)`` in ``changes`` set to that value."""
    ops = []
    for op in recipe.ops:
        params = dict(op.params or {})
        for (op_id, key), val in changes.items():
            if op.id == op_id and key in params:
                params[key] = float(val)
        ops.append(OpInstance(id=op.id, params=params, enabled=op.enabled,
                              uid=op.uid))
    return Recipe(ops=ops)


def _moves(recipe: Recipe, before: Recipe):
    """What the snap did to each knob, and the one click that goes the same way.

    For each parameter the snap moved: where it ended up, the continuous value it
    came from, and the value **one click of that same control** in the direction
    the snap came from would hold. Both perturbations then point the same way
    from the shipped picture, and the click is the larger of the two by
    construction — so comparing their effect on the picture is a fair question
    rather than a chosen one.
    """
    out = []
    for a, b in zip(recipe.ops, before.ops, strict=True):
        for key in (a.params or {}):
            was, now = b.params.get(key), a.params[key]
            if was == now or not isinstance(now, (int, float)):
                continue
            step = float(param_spec(a.id, key).step)
            n = -1 if was < now else 1
            click = float(snap_to_param(a.id, key, float(now) + n * step))
            if click == now:  # the click ran into the control's own end
                click = float(snap_to_param(a.id, key, float(now) - n * step))
            out.append(((a.id, key), float(was), float(now), click))
    return out


@pytest.mark.parametrize("tag,hw,sigma,panels", _RENDER_SCENES)
def test_snapping_moves_the_picture_by_less_than_one_click_of_the_same_slider(
        tag, hw, sigma, panels):
    """The measurement AGENTS.md §1 asks for before anything on the on-by-default
    path moves — and against the yardstick that decides it.

    An absolute number of 8-bit levels is the wrong bar (FOCUS.md's own method
    note: *before trusting a sweep, ask what one unit of its metric does to the
    screen*). Snapping moves a knob by at most **half a stop**, and a stop is the
    finest distinction the control offers — so the question is not "is it zero?"
    but "is it smaller than the smallest change the owner could have asked for by
    hand?". Asserted twice over, because the recipe moves several knobs at once:

    * **per knob** — each one, alone, against one click of its own control in the
      same direction;
    * **together** — the whole snap against one click of *every* knob it moved,
      each the same way, which is the aggregate version of the same question.

    Measured when it shipped, on canvases ~6× this area (the table is in
    ``docs/SHIPPED.md`` under v0.493.14): the snap moves the picture by 1.1–2.7 of
    255 at the worst pixel and 0.17–0.39 on average, while one click of the same
    controls moves it by 5.2–17.9 at the worst pixel and shifts 5–96 % of the
    picture by a whole level against the snap's 0.001–0.7 %.
    """
    h, w = hw
    img, cov = _scene(h, w, sigma=sigma, panels=panels)
    is_mosaic = panels != (1, 1)
    knobs = presets.measured_auto_knobs(img, cov if is_mosaic else None)
    values = presets.auto_knob_values(knobs, None)
    recipe = presets.auto_recipe(img, median_fwhm=3.2, is_mosaic=is_mosaic,
                                 coverage=cov)
    before = _unsnapped(recipe, values)
    moves = _moves(recipe, before)
    # A case where the snap barely moved anything measures nothing, and that is
    # how this test would quietly go vacuous: before v0.493.14 the only
    # "movement" here was ``saturation``'s third-decimal rounding — under 1 % of
    # its step — so the comparison below was true for free. Demand that at least
    # one knob moved by a tenth of its own stop.
    real = [m for m in moves
            if abs(m[1] - m[2]) >= 0.1 * float(param_spec(*m[0]).step)]
    assert real, (f"{tag}: nothing moved by as much as a tenth of a stop, so "
                  f"this case measures nothing — moves {moves}")

    shipped = _render(img, recipe, cov)

    def delta(changes):
        d = np.abs(_render(img, _with(recipe, changes), cov) - shipped)
        return float(d.max()), float(d.mean())

    for which, was, now, click in moves:
        snap_max, snap_mean = delta({which: was})
        click_max, click_mean = delta({which: click})
        assert snap_max < click_max and snap_mean < click_mean, (
            f"{tag}: snapping {which[0]}.{which[1]} {was} -> {now} moved the "
            f"picture by {snap_max:.3f}/{snap_mean:.4f} of 255 (worst/mean), "
            f"more than its own click to {click} does "
            f"({click_max:.3f}/{click_mean:.4f})")

    all_max, all_mean = delta({w_: was for w_, was, _, _ in moves})
    clicked_max, clicked_mean = delta({w_: c for w_, _, _, c in moves})
    assert all_max < clicked_max and all_mean < clicked_mean, (
        f"{tag}: the whole snap moved the picture by {all_max:.3f}/"
        f"{all_mean:.4f} of 255, more than one click of every knob it touched "
        f"({clicked_max:.3f}/{clicked_mean:.4f}); moves {moves}")
