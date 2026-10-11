"""Every number the editor offers *for a slider* has to be one that slider can
hold — ``seestack.edit.registry.snap_to_param`` and each of its callers.

**Why this file exists.** Six of the editor's ten "From your image" / "From your
stars" buttons emitted a value off their op's own step grid, and five of those
printed it in the button's own label at a precision the readout beside it rounds
away: the Levels button said *"From your image (black 0.077)"* while the box next
to it showed ``0.08``, on a control whose stops are 0.07 and 0.08 and nothing
between. The bounds each one clamped to were **copies** of the op's
:class:`~seestack.edit.registry.EditParam`, kept in five modules as prose — *"kept
in step with the EditParam in seestack/edit/ops/detail.py"* — with nothing
checking a single one of them, and the one test that checked a grid at all
(``test_highlight_suggestion.py``) checked a module against its own copy of the
numbers. So the claim was asserted and the figures behind it were not.

The fix is not to correct five comments. It is to read the declaration: every
suggestion now goes through ``snap_to_param``, and this file asserts the property
the comments were promising — for the whole population, measured off real
measurements rather than off a table written here.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.highlights import suggest_highlight_protect
from seestack.edit.levels import suggest_levels_gamma, suggest_levels_points
from seestack.edit.noise import suggest_denoise_strength
from seestack.edit.presets import (
    auto_knob_values,
    auto_op_params,
    measured_auto_knobs,
)
from seestack.edit.registry import (
    all_specs,
    param_grid,
    param_spec,
    snap_to_param,
)
from seestack.edit.stretch import suggest_asinh_stretch
from seestack.render.thumbnail import autostretch

# --------------------------------------------------------------------------- #
# Scenes
# --------------------------------------------------------------------------- #


def _linear_scene(sky=1000.0, sig=40.0, star_max=25000.0, h=140, w=180, seed=0):
    """A *linear* stacked proxy: faint sky, a soft core, a star population."""
    rng = np.random.default_rng(seed)
    img = rng.normal(sky, sig, size=(h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    core = np.exp(-(((xx - w * 0.5) / 18) ** 2 + ((yy - h * 0.5) / 18) ** 2))
    img += (star_max * core)[..., None]
    for _ in range(40):
        cy = int(rng.integers(4, h - 4))
        cx = int(rng.integers(4, w - 4))
        img[cy - 2:cy + 3, cx - 2:cx + 3, :] += rng.uniform(0.3, 1.0) * star_max
    return img


def _display_scene(black_floor=0.14, bright=0.92, h=130, w=170, seed=0):
    """A display-space picture: a dim sky with a bright blob."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    signal = (bright - black_floor) * np.exp(
        -(((xx - w / 2) / 16) ** 2 + ((yy - h / 2) / 16) ** 2))
    img = black_floor + signal[..., None] + rng.normal(0.0, 0.012, (h, w, 3))
    return np.clip(img, 0.0, 1.0).astype(np.float32)


# --------------------------------------------------------------------------- #
# The helpers themselves
# --------------------------------------------------------------------------- #


def test_param_spec_reads_the_ops_own_declaration():
    p = param_spec("tone.stretch", "highlights")
    assert (p.min, p.max, p.step) == (0.0, 1.0, 0.05)
    with pytest.raises(KeyError):
        param_spec("tone.nope", "highlights")
    with pytest.raises(KeyError):
        param_spec("tone.stretch", "nope")


def test_param_grid_is_the_controls_own_stops():
    grid = param_grid("tone.stretch", "highlights")
    assert grid[0] == 0.0 and grid[-1] == 1.0 and len(grid) == 21
    # Built by walking the step, so the float fuzz that makes 0.1+7*0.1 land at
    # 0.7999999999999999 has to be rounded back out — the whole point.
    assert 0.35 in grid and 0.8 in grid
    # An int control enumerates too; a param with no step has nothing to list.
    assert param_grid("stars.reduce", "size") == [1.0, 2, 3, 4, 5, 6, 7, 8]
    assert param_grid("tone.curves", "points") == []


@pytest.mark.parametrize(("op_id", "key", "raw", "want"), [
    # Each pair is hand-checked against the EditParam in seestack/edit/ops/.
    ("tone.levels", "black", 0.077, 0.08),       # step 0.01
    ("tone.levels", "white", 0.796, 0.8),
    ("tone.levels", "gamma", 2.415, 2.4),        # step 0.05, grid anchored at 0.1
    ("tone.stretch", "stretch", 0.393, 0.39),
    ("tone.stretch", "black", 0.047, 0.05),
    ("detail.deconvolve", "psf_sigma", 1.359, 1.4),   # step 0.1
    ("detail.sharpen", "radius", 1.26, 1.5),          # step 0.5
    ("tone.saturation", "amount", 1.242, 1.25),       # step 0.05
])
def test_snap_lands_on_the_controls_own_stop(op_id, key, raw, want):
    assert snap_to_param(op_id, key, raw) == pytest.approx(want)


def test_snap_clamps_into_range_and_stays_on_the_grid():
    assert snap_to_param("tone.levels", "gamma", -5.0) == pytest.approx(0.1)
    assert snap_to_param("tone.levels", "gamma", 99.0) == pytest.approx(5.0)
    assert snap_to_param("detail.deconvolve", "psf_sigma", 0.01) == pytest.approx(0.5)
    assert snap_to_param("detail.deconvolve", "psf_sigma", 50.0) == pytest.approx(5.0)


def test_snap_honours_a_callers_own_floor_without_leaving_the_grid():
    # The denoise estimate never offers a no-op, so it asks for a floor of 0.1 —
    # which must not be able to produce a value the slider can't reach.
    assert snap_to_param("detail.denoise", "strength", 0.0, minimum=0.1) == pytest.approx(0.1)
    # A floor that is itself off the grid is moved *up* to the first real stop,
    # never left between two.
    got = snap_to_param("detail.denoise", "strength", 0.0, minimum=0.07)
    assert got == pytest.approx(0.1)
    assert got in param_grid("detail.denoise", "strength")


def test_snap_returns_an_int_for_an_int_control():
    got = snap_to_param("stars.reduce", "size", 3.4)
    assert isinstance(got, int) and got == 3
    assert snap_to_param("stars.reduce", "size", 99.0) == 8


# --------------------------------------------------------------------------- #
# The sweep: every suggestion the editor offers, measured
# --------------------------------------------------------------------------- #
#
# ``_SUGGESTIONS`` is the population, and each entry *runs the real
# measurement* rather than quoting a number — so a suggestion that stops being
# settable fails here on its own output, the way v0.493.6's window sweep fails on
# the op's own render. A new "From your image" button belongs in this list; one
# that is not in it is the next instance of the bug this file was written for.


def _stretch_values():
    out = []
    for seed, star_max in ((0, 20000.0), (1, 60000.0), (2, 150000.0)):
        sug = suggest_asinh_stretch(_linear_scene(star_max=star_max, seed=seed))
        assert sug is not None
        out += [(("tone.stretch", "stretch"), sug[0]), (("tone.stretch", "black"), sug[1])]
    return out


def _levels_values():
    out = []
    for seed, floor in ((0, 0.10), (1, 0.16), (2, 0.24)):
        img = _display_scene(black_floor=floor, seed=seed)
        pts = suggest_levels_points(img)
        assert pts is not None
        out += [(("tone.levels", "black"), pts[0]), (("tone.levels", "white"), pts[1])]
        gamma = suggest_levels_gamma(img, pts[0], pts[1])
        if gamma is not None:
            out.append((("tone.levels", "gamma"), gamma))
    return out


def _denoise_values():
    out = []
    for seed in range(3):
        img = _display_scene(seed=seed)
        img = img + np.random.default_rng(seed).normal(0.0, 0.004 * (seed + 1), img.shape)
        _, strength = suggest_denoise_strength(img.astype(np.float32))
        if strength is not None:
            out.append((("detail.denoise", "strength"), strength))
    assert out, "the fixture must produce at least one denoise suggestion"
    return out


def _blown_core(h=220, w=220, core_amp=60000.0):
    """The M31-style shape the "Hold back highlights" knob exists for: a compact
    core with real linear structure that the stretch renders flat white.

    Same construction as ``tests/test_highlight_suggestion.py::_target``, kept
    local so this file's fixtures stay readable in one place.
    """
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = (yy - h / 2) ** 2 + (xx - w / 2) ** 2
    disk = 1500.0 * np.exp(-r2 / (2 * 60.0 ** 2))
    core = core_amp * np.exp(-r2 / (2 * 4.0 ** 2))
    rng = np.random.default_rng(0)
    base = 1000.0 + disk + core + rng.normal(0.0, 20.0, size=(h, w))
    return np.stack([base, base, base], axis=-1).astype(np.float32)


def _highlight_values():
    out = []
    for amp in (40000.0, 60000.0, 90000.0):
        linear = _blown_core(core_amp=amp)
        def restretch(protect: float, img=linear):
            return autostretch(img, highlight_protect=protect)

        found = suggest_highlight_protect(linear, restretch)
        if found is not None:
            out.append((("tone.stretch", "highlights"), found.strength))
    assert out, "the fixture must produce at least one highlight suggestion"
    return out


def _from_the_stars_values():
    """The three FWHM-derived endpoint suggestions, over a real FWHM range.

    1.5 px is a sharp night on an S30, 12 px a badly soft one — the span the QC
    layer actually reports — so the sweep covers what ``median_fwhm`` can hand
    these three rather than one convenient value.
    """
    from webapp.routers.editor import (
        psf_sigma_for_fwhm,
        sharpen_radius_for_fwhm,
        star_size_for_fwhm,
    )
    out = []
    for fwhm in (1.5, 2.0, 2.7, 3.2, 4.1, 5.5, 7.3, 9.0, 12.0):
        out += [
            (("detail.deconvolve", "psf_sigma"), psf_sigma_for_fwhm(fwhm)),
            (("detail.sharpen", "radius"), sharpen_radius_for_fwhm(fwhm)),
            (("stars.reduce", "size"), star_size_for_fwhm(fwhm)),
        ]
    return out


def _all_suggested_values():
    return (_stretch_values() + _levels_values() + _denoise_values()
            + _highlight_values() + _from_the_stars_values())


def test_every_suggested_value_is_one_its_own_control_can_be_set_to():
    """The property the five prose comments were promising, for all ten buttons.

    Before the fix this failed on ``tone.levels`` black/white/gamma,
    ``tone.stretch`` strength/black and ``detail.deconvolve`` psf_sigma — six of
    the ten, every one of them a number the slider has no stop for.
    """
    offenders = []
    for (op_id, key), value in _all_suggested_values():
        p = param_spec(op_id, key)
        grid = param_grid(op_id, key)
        if p.min is not None and value < p.min - 1e-9:
            offenders.append(f"{op_id}.{key} = {value} below min {p.min}")
        if p.max is not None and value > p.max + 1e-9:
            offenders.append(f"{op_id}.{key} = {value} above max {p.max}")
        if grid and not any(abs(value - stop) <= 1e-9 for stop in grid):
            offenders.append(f"{op_id}.{key} = {value} is not a stop of {p.step}")
    assert not offenders, "suggestions the slider cannot hold: " + "; ".join(offenders)


def test_every_suggested_value_reads_the_same_in_the_editors_readout():
    """And the second half of the bug: the number the button *prints*.

    ``StackOptionControl`` renders a float control's readout at
    ``decimalScale={2}``, so a suggestion carrying a third decimal shows one
    number on the button and a different one in the box beside it. Every stop of
    every editor control is two decimals or fewer, so landing on the grid settles
    this too — which is why it is asserted here rather than fixed in the UI.
    """
    for (op_id, key), value in _all_suggested_values():
        assert round(float(value), 2) == pytest.approx(float(value)), (
            f"{op_id}.{key} = {value} cannot be shown in the 2-decimal readout")


# --------------------------------------------------------------------------- #
# The control group, and the copies that are left
# --------------------------------------------------------------------------- #


def test_every_numeric_default_is_a_value_its_own_control_can_hold():
    """The same property for the other number every op publishes — its default.

    Clean today across all 36 numeric parameters; asserted so an op added with a
    default its slider can't reach is caught at the registry rather than by
    someone noticing the readout disagrees with the picture.
    """
    offenders = []
    for spec in all_specs():
        for p in spec.params:
            if p.type not in ("float", "int") or p.default is None:
                continue
            v = float(p.default)
            grid = param_grid(spec.id, p.key)
            if p.min is not None and v < p.min - 1e-9:
                offenders.append(f"{spec.id}.{p.key} default {v} < min {p.min}")
            if p.max is not None and v > p.max + 1e-9:
                offenders.append(f"{spec.id}.{p.key} default {v} > max {p.max}")
            if grid and not any(abs(v - stop) <= 1e-9 for stop in grid):
                offenders.append(f"{spec.id}.{p.key} default {v} off the {p.step} grid")
    assert not offenders, "; ".join(offenders)


def test_no_module_keeps_a_copy_of_a_controls_bounds_any_more():
    """The fifth and last copy is gone too (**v0.493.14**), so the guard is now
    that there is nothing left to pin.

    ``seestack/edit/presets.py`` kept its own ``_SHARPEN_RADIUS_MIN/_MAX/_STEP``
    because the Auto path rounded the radius itself, and v0.493.11 left it in
    place deliberately — Auto's own arithmetic was not that change's business —
    pinning it to the declaration rather than trusting it. Auto now reads the
    declaration through ``snap_to_param`` like everything else, so the names are
    deleted; this fails the day one comes back.
    """
    from seestack.edit import presets

    left = [n for n in dir(presets) if n.startswith("_SHARPEN_RADIUS")]
    assert not left, f"a copy of a slider's bounds is back in presets.py: {left}"


def test_autos_sharpen_radius_is_the_number_the_from_your_stars_button_offers():
    """And the reason that copy mattered: two surfaces, one measurement.

    ``presets._sharpen_radius_from_fwhm`` (what Auto writes into the recipe) and
    ``editor.sharpen_radius_for_fwhm`` (what the "From your stars" button offers)
    answer the same question about the same median FWHM, and used to do it with
    two different pieces of arithmetic — one reading the declaration, one a copy
    of it. Over the whole range the QC layer reports they now agree exactly,
    which is the property the copy could only promise.
    """
    from seestack.edit import presets
    from webapp.routers.editor import sharpen_radius_for_fwhm

    for fwhm in [round(1.5 + 0.1 * i, 1) for i in range(106)]:
        assert (presets._sharpen_radius_from_fwhm(fwhm)
                == sharpen_radius_for_fwhm(fwhm)), fwhm
    # And the one case the button never sees: no FWHM at all falls back to the
    # op's own default, which is itself a stop.
    assert presets._sharpen_radius_from_fwhm(None) == param_spec(
        "detail.sharpen", "radius").default


def test_autos_own_knobs_are_on_the_grid_too_now():
    """The hot-path half of the same defect, **fixed in v0.493.14**.

    ``measured_auto_knobs`` still hands ``auto_recipe`` continuous values — the
    measurement is continuous and stays so — but ``auto_op_params`` now lands
    every one of them on its control's own stops before it reaches an op param,
    so the recipe, the readout beside it and the "What Auto did" sentence are one
    number instead of three. The whole population, the taste profiles and what
    snapping cost the picture are in ``tests/test_auto_knob_grid.py``; this is
    the line that used to assert the opposite, kept here so the two halves of
    v0.493.11's defect are answered in one place.
    """
    for seed in range(4):
        knobs = measured_auto_knobs(_linear_scene(seed=seed, star_max=30000.0))
        emitted = auto_op_params(auto_knob_values(knobs))
        for op_id, key in (("tone.stretch", "target_bg"),
                           ("tone.saturation", "amount")):
            v = float(emitted[op_id][key])
            grid = param_grid(op_id, key)
            assert any(abs(v - stop) <= 1e-9 for stop in grid), (
                f"{op_id}.{key} = {v} is not a stop of "
                f"{param_spec(op_id, key).step}")
