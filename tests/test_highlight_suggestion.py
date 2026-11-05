"""The "Hold back highlights" knob's from-your-image partner.

``tone.stretch``'s ``highlights`` slider only ever moved when the owner noticed a
washed-out core; ``seestack.edit.highlights`` measures whether the core really is
blown *by the stretch* (rather than saturated at capture) and solves the smallest
slider step that reopens it, so the knob gets the same one-click partner sharpen
and denoise have.
"""

import numpy as np
import pytest

from seestack.edit import highlights as hl
from seestack.edit.registry import param_grid
from seestack.render.thumbnail import asinh_stretch, autostretch


def _target(h=300, w=300, core_sigma=4.0, core_amp=60000.0, saturate_at=None):
    """Bright compact core on a faint extended disk on a noisy sky — the
    M31-style shape that blows out. ``saturate_at`` clips the *linear* data, i.e.
    a core that was already saturated at capture."""
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = (yy - h / 2) ** 2 + (xx - w / 2) ** 2
    disk = 1500.0 * np.exp(-r2 / (2 * 60.0**2))
    core = core_amp * np.exp(-r2 / (2 * core_sigma**2))
    rng = np.random.default_rng(0)
    base = 1000.0 + disk + core + rng.normal(0.0, 20.0, size=(h, w))
    if saturate_at is not None:
        base = np.minimum(base, saturate_at)
    return np.stack([base, base, base], axis=-1).astype(np.float32)


def _stf(img):
    return lambda p: autostretch(img, highlight_protect=p)


def _asinh(img):
    return lambda p: asinh_stretch(img, highlight_protect=p)


def test_suggests_a_strength_for_a_stretch_blown_core():
    """The case the knob exists for: a core with real structure in the linear
    data that the stretch renders as flat white."""
    img = _target()
    found = hl.suggest_highlight_protect(img, _stf(img))
    assert found is not None
    assert 0.0 < found.strength <= 1.0
    assert found.flat_fraction >= hl._MIN_SEVERITY
    assert found.core_px > 0


def test_the_suggested_strength_really_reopens_the_core():
    """The number is *solved*, not mapped — so applying it must do the thing the
    button promises, and the step below it must not already have."""
    img = _target()
    found = hl.suggest_highlight_protect(img, _stf(img))
    assert found is not None
    core, structure, area = hl.measure_blown_core(autostretch(img), img)

    def flat_at(p):
        return hl._recoverable_flat_fraction(
            autostretch(img, highlight_protect=p), core, structure, area)

    assert flat_at(found.strength) <= hl._TARGET_FLAT
    # Smallest step that does the job: one step down still leaves the core blown
    # (unless the suggestion is already the slider's floor).
    grid = hl._strength_grid()
    below = grid[grid.index(found.strength) - 1] if grid.index(found.strength) else None
    if below is not None:
        assert flat_at(below) > hl._TARGET_FLAT


def test_a_core_saturated_at_capture_gets_no_suggestion():
    """Holding the highlights back can't recover a gradient the data never had —
    it would only darken the core. Say nothing instead of promising a rescue."""
    img = _target(core_sigma=12.0, saturate_at=3000.0)
    assert hl.suggest_highlight_protect(img, _stf(img)) is None


def test_an_image_with_no_bright_core_gets_no_suggestion():
    """The button must self-hide rather than imply the picture has a problem."""
    img = _target(core_amp=0.0)
    assert hl.suggest_highlight_protect(img, _stf(img)) is None
    assert hl.suggest_highlight_protect(img, _asinh(img)) is None


def test_a_star_field_is_not_mistaken_for_a_blown_core():
    """Saturated *stars* are normal and are not what the knob is for — only a
    core big enough to be an object qualifies."""
    rng = np.random.default_rng(3)
    base = 1000.0 + rng.normal(0.0, 20.0, size=(300, 300))
    for _ in range(80):
        y, x = rng.integers(5, 295, 2)
        base[y - 1:y + 2, x - 1:x + 2] += 60000.0
    img = np.stack([base, base, base], axis=-1).astype(np.float32)
    assert hl.suggest_highlight_protect(img, _stf(img)) is None


def test_no_suggestion_when_the_knob_cannot_meaningfully_help():
    """A button that does nothing is worse than no button: if the strength the
    slider can reach doesn't reopen the core, say nothing.

    Stated against a stretch that ignores the strength, which is what "the knob
    can't help" *means*. It used to be stated against a very high-contrast frame
    — but that frame was the v0.424.0 bug (the midtones transfer squashed the
    whole shoulder back together), not a property of the knob, and the test below
    now pins that the same frame gets a real suggestion."""
    img = _target()
    deaf = lambda p: autostretch(img, highlight_protect=0.0)   # noqa: E731
    assert hl.suggest_highlight_protect(img, deaf) is None


def test_a_very_high_contrast_core_gets_a_suggestion_too():
    """The frame the knob is most needed for — a huge bright core over a sky at a
    ten-thousandth of the normalization ceiling — used to be the one frame where
    it was offered *nothing*, because the stretch squashed the shoulder flat
    (v0.424.0). Now the slider reopens it, so the button appears."""
    img = _target(core_sigma=22.0, core_amp=6e6)
    found = hl.suggest_highlight_protect(img, _stf(img))
    assert found is not None
    assert 0.0 < found.strength <= 1.0
    assert found.core_px > 1000
    # And it delivers: applying the suggested strength really does reopen a large
    # share of what was flat. (A core this wide is genuinely flat at its very
    # centre, so the solver's full-reopen target isn't reachable — what matters is
    # that the button now changes the picture, which is what it used to fail.)
    core, structure, area = hl.measure_blown_core(autostretch(img), img)
    flat_after = hl._recoverable_flat_fraction(
        autostretch(img, highlight_protect=found.strength), core, structure, area)
    assert found.flat_fraction - flat_after >= hl._MIN_IMPROVEMENT
    assert flat_after < 0.6 * found.flat_fraction


def test_works_on_the_manual_asinh_curve_too():
    """The blow-out is a property of the shared highlight shoulder, so the
    suggestion is not STF-only."""
    img = _target()
    found = hl.suggest_highlight_protect(img, _asinh(img))
    assert found is not None
    assert 0.0 < found.strength <= 1.0


def test_uncovered_mosaic_pixels_do_not_break_the_measurement():
    """NaN = no coverage. It must neither count as a flat core nor poison the
    gradient of its neighbours."""
    img = _target()
    img[:40, :] = np.nan
    found = hl.suggest_highlight_protect(img, _stf(img))
    assert found is not None
    assert found.core_px > 0


def test_degenerate_inputs_return_no_suggestion_rather_than_raising():
    """The proxy can be tiny, empty, or all-NaN — none of that may raise."""
    for img in (np.zeros((4, 4, 3), np.float32),
                np.full((80, 80, 3), np.nan, np.float32),
                np.ones((80, 80, 3), np.float32)):
        assert hl.suggest_highlight_protect(img, _stf(img)) is None


def test_strength_grid_is_the_ops_own_slider_steps():
    """A suggestion the slider can't represent would show as 'not at the
    suggestion' forever — so the grid is checked against the ``highlights``
    ``EditParam`` itself, not against a copy of its bounds in this module.

    That copy is what the old version of this test asserted against, which made
    it a check of the module against itself: it would have passed unchanged if
    the op's step had moved to 0.01 and every suggestion had gone off-grid. The
    wider sweep over every editor suggestion is in
    ``tests/test_edit_suggestion_grid.py``.
    """
    stops = param_grid("tone.stretch", "highlights")
    grid = hl._strength_grid()
    # Every stop the op has, except the no-op at the bottom.
    assert grid == [v for v in stops if v > 0.0]
    assert grid[0] == pytest.approx(min(v for v in stops if v > 0.0))
    assert grid[-1] == pytest.approx(max(stops))


def test_local_gradient_ignores_non_finite_neighbours():
    """A NaN neighbour contributes no information instead of making the whole
    neighbourhood NaN (which np.gradient would)."""
    values = np.array([[1.0, 1.0, 1.0],
                       [1.0, np.nan, 1.0],
                       [1.0, 1.0, 5.0]], dtype=np.float32)
    grad = hl._local_gradient(values)
    assert np.isfinite(grad).all()
    assert grad[0, 0] == pytest.approx(0.0)      # flat corner stays flat
    assert grad[2, 2] > 3.0                      # the real step is still seen


# --- the editor proxy's step (Scout 2026-10-20, QA rotation sweep (1)) ---------
#
# The suggestion is measured on the decimated editor proxy, whose step is 2 on a
# single S30 field and 3+ on a mosaic. Both flatness tests compare a one-pixel
# difference against a fixed threshold, and one proxy pixel spans ``step`` native
# ones, so the same core read ``step``× steeper there: the button weakened as the
# canvas grew (0.40 at step 3 for a core whose export needed 1.00) and went
# silent on a big canvas. ``proxy_scale`` puts the measurement per native pixel.


def _proxy_case(noise):
    """An exponential bright core on a soft disk, at native resolution, through
    the real ``tone.stretch`` op at its defaults (the Auto recipe's stretch)."""
    from seestack.edit.registry import EditContext, get_op

    h, w = 600, 900
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(yy - h / 2, xx - w / 2)
    rng = np.random.default_rng(0)
    img = (0.05 + 0.02 * np.exp(-r / 100.0) + 0.3 * np.exp(-r / 12.0)
           + rng.normal(0.0, noise, (h, w)))
    img = np.repeat(img.astype(np.float32)[..., None], 3, axis=2)
    spec = get_op("tone.stretch")
    params = dict(spec.defaults())

    def suggest(step, **kw):
        lin = np.ascontiguousarray(img[::step, ::step])   # build_proxy's decimation
        ctx = EditContext(proxy_scale=float(step), is_proxy=step > 1)
        return hl.suggest_highlight_protect(
            lin, lambda p: spec.apply(lin, {**params, "highlights": p}, ctx), **kw)

    return suggest


def test_the_suggestion_does_not_shrink_with_the_proxy_step():
    """The same core gets the same button on a single field's proxy and on a
    mosaic's: within two slider stops of the native answer at steps 2–4 (it
    reads 0.35 / 0.35 / 0.30 against 0.40). Before the fix this read 0.05, then
    nothing at all."""
    suggest = _proxy_case(noise=0.0005)
    native = suggest(1)
    assert native is not None
    stop = hl._strength_grid()[0]
    for step in (2, 3, 4):
        found = suggest(step, proxy_scale=float(step))
        assert found is not None, f"no suggestion at proxy step {step}"
        assert abs(found.strength - native.strength) <= 2 * stop + 1e-9, (
            step, found.strength, native.strength)


def test_a_noisy_core_still_gets_a_suggestion_on_a_mosaic_proxy():
    """With visible grain the per-pixel test is noisier, but a decimated proxy
    must still offer at least what the native measurement does, not fall
    silent (it returned ``None`` at every step ≥ 2 before the fix)."""
    suggest = _proxy_case(noise=0.004)
    native = suggest(1)
    assert native is not None
    for step in (2, 3, 4):
        found = suggest(step, proxy_scale=float(step))
        assert found is not None, f"no suggestion at proxy step {step}"
        assert found.strength >= native.strength


def test_proxy_scale_one_is_the_unscaled_measurement():
    """The export / an undecimated proxy is byte-for-byte what it always was."""
    img = _target()
    assert hl.suggest_highlight_protect(img, _stf(img)) == \
        hl.suggest_highlight_protect(img, _stf(img), proxy_scale=1.0)
    g = hl._local_gradient(luminance_of(img))
    assert hl._per_native_px(g, 1.0) is g
    assert hl._per_native_px(g, float("nan")) is g
    assert np.allclose(hl._per_native_px(g, 3.0), g / 3.0)


def luminance_of(img):
    from seestack.edit.registry import luminance

    return luminance(img)



# --- the size floor on a mosaic canvas (Builder 2026-11-05, v0.505.22) ----------
#
# The floor keeps a saturated *star* from being called a core. It was a share of
# the whole covered canvas, counted in proxy pixels, so on a bigger mosaic (more
# sky, and a coarser proxy step) the same blown core fell under it and the
# "Hold back highlights" nudge went silent: 91 px vs a floor of 53 on the step-1
# 2×2 dogfood sample, 24 proxy px (≈ 96 native) vs 46 on its step-2 full-size twin.


def _plateau_scene(h, w, cy, cx, radius):
    """A display with one flat-white disk of ``radius`` native px at (cy, cx)
    and a linear image with a real gradient under it (a recoverable core)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(yy - cy, xx - cx)
    rng = np.random.default_rng(0)
    lin = (0.05 + 0.5 * np.exp(-(r / (2.0 * radius)) ** 2)
           + rng.normal(0.0, 0.002, (h, w)))
    disp = np.where(r <= radius, 1.0, 0.2).astype(np.float32)
    return (np.repeat(disp[..., None], 3, axis=2),
            np.repeat(lin.astype(np.float32)[..., None], 3, axis=2))


def _verdict(h, w, radius, step, frame_px):
    disp, lin = _plateau_scene(h, w, 300, 450, radius)
    disp = np.ascontiguousarray(disp[::step, ::step])
    lin = np.ascontiguousarray(lin[::step, ::step])
    return hl.measure_blown_core(disp, lin, float(step), frame_px) is not None


@pytest.mark.parametrize("radius,expected", [(6.0, True), (2.5, False)])
def test_the_same_core_gets_the_same_verdict_on_a_bigger_mosaic_canvas(
        radius, expected):
    """One S30-like frame at step 1 vs a 2×2-frame canvas strided ×2: the same
    ~110-native-px core qualifies on both, and a ~20-px star on neither. Before
    the fix the mosaic's floor was 54 proxy px (a share of the whole canvas)
    and the core read 28 there, so the big canvas said nothing."""
    frame_px = 600 * 900
    assert _verdict(600, 900, radius, 1, frame_px) is expected
    assert _verdict(1200, 1800, radius, 2, frame_px) is expected


def test_min_core_area_is_the_old_floor_without_a_scale_or_a_frame():
    """A single field (or any caller that does not know the frame) keeps the
    floor it always had, byte for byte."""
    for n in (64, 1000, 320_000, 540_000, 2_073_600):
        old = max(hl._MIN_CORE_PX, int(hl._MIN_CORE_AREA_FRAC * n))
        assert hl._min_core_area(n) == old
        assert hl._min_core_area(n, 1.0, None) == old
        # A single field whose canvas is one frame: the frame changes nothing.
        assert hl._min_core_area(n, 1.0, float(n)) == old


def test_min_core_area_counts_native_pixels_on_a_proxy():
    """A step-2 single S30 field (one 1080×1920 frame ≈ the canvas) keeps its
    old proxy floor; the floor no longer grows past one frame's share."""
    frame = 1080.0 * 1920.0
    proxy_n = int(frame / 4)
    assert hl._min_core_area(proxy_n, 2.0, frame) == \
        max(hl._MIN_CORE_PX, int(hl._MIN_CORE_AREA_FRAC * proxy_n))
    # A 2×2 mosaic (≈ 3.5 frames of sky) on a step-3 proxy: one frame's share.
    mosaic_n = int(3.5 * frame / 9)
    assert hl._min_core_area(mosaic_n, 3.0, frame) == \
        int(hl._MIN_CORE_AREA_FRAC * frame / 9)
    # The absolute floor is native pixels: 32 native = 8 proxy px at step 2.
    assert hl._min_core_area(1000, 2.0, None) == hl._MIN_CORE_PX / 4
    # Garbage in is the unscaled, whole-canvas floor.
    assert hl._min_core_area(540_000, float("nan"), float("nan")) == 54


# --- the core's rim on a decimated proxy (Builder 2026-11-05, after v0.505.22) --
#
# Every per-pixel test reads a pixel's largest neighbour difference, so a core's
# rim is scored on the grid's own terms: one proxy pixel is ``step`` native ones,
# while the core shrinks to ``1/step²`` of its area. Measured through the real
# stretch, a small recoverable core faded (0.184 / 0.150 / 0.130 / silent at
# steps 1–4) and a core clipped at capture grew a false button (silent / 0.12 /
# 0.164 / 0.188). The fix measures the proxy's core on a *native window*.


def _rim_case(rc, amp=0.3, clip=None, noise=0.0005):
    """``suggest(step, window=True)`` for an exponential core of scale ``rc``
    native px; ``clip`` saturates the linear data (a core lost at capture)."""
    from seestack.edit.registry import EditContext, as_rgb, get_op
    from seestack.render.thumbnail import measure_stretch_stats

    h, w = 600, 900
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(yy - h / 2, xx - w / 2)
    rng = np.random.default_rng(0)
    img = (0.05 + 0.02 * np.exp(-r / 100.0) + amp * np.exp(-r / rc)
           + rng.normal(0.0, noise, (h, w)))
    if clip is not None:
        img = np.minimum(img, clip)
    img = np.repeat(img.astype(np.float32)[..., None], 3, axis=2)
    spec = get_op("tone.stretch")
    params = dict(spec.defaults())
    calls: list[tuple[int, int, int, int]] = []

    def suggest(step, window=True):
        lin = np.ascontiguousarray(img[::step, ::step])   # build_proxy's decimation
        ctx = EditContext(proxy_scale=float(step), is_proxy=step > 1)
        stats = measure_stretch_stats(as_rgb(lin))

        def native_window(y0, x0, wh, ww):
            calls.append((y0, x0, wh, ww))
            win = np.ascontiguousarray(img[y0:y0 + wh, x0:x0 + ww])
            wctx = EditContext(frozen_fits={"stretch_stats": stats})
            return win, lambda p: spec.apply(win, {**params, "highlights": p}, wctx)

        return hl.suggest_highlight_protect(
            lin, lambda p: spec.apply(lin, {**params, "highlights": p}, ctx),
            proxy_scale=float(step), native_window=native_window if window else None)

    suggest.calls = calls
    return suggest


def test_a_core_clipped_at_capture_gets_no_button_at_any_proxy_step():
    """No promise of a rescue the data can't give, however coarse the proxy."""
    suggest = _rim_case(rc=12, amp=1.0, clip=0.3)
    assert suggest(1) is None
    # The fixture shows the bug: measured on the step-3 proxy alone, the clipped
    # plateau's rim reads as "structure" and a button appears.
    assert suggest(3, window=False) is not None
    for step in (2, 3, 4):
        assert suggest(step) is None, f"false button at proxy step {step}"


def test_a_small_core_keeps_its_native_answer_at_every_proxy_step():
    """The same small core gets the native button at steps 2–4, where the proxy
    alone weakened it and then went silent."""
    suggest = _rim_case(rc=4)
    native = suggest(1)
    assert native is not None
    assert suggest(4, window=False) is None     # the fixture shows the bug
    for step in (2, 3, 4):
        found = suggest(step)
        assert found is not None, f"no suggestion at proxy step {step}"
        assert found.strength == native.strength, (step, found, native)
        assert found.flat_fraction == pytest.approx(native.flat_fraction, abs=0.01)


def test_a_bigger_core_is_steadier_on_the_native_window_too():
    suggest = _rim_case(rc=12)
    native = suggest(1)
    for step in (2, 3, 4):
        assert suggest(step).strength == native.strength, step


def test_the_window_holds_the_core_and_is_asked_only_on_a_decimated_proxy():
    suggest = _rim_case(rc=6)
    suggest(1)
    assert suggest.calls == []                   # step 1 is already native
    suggest(3)
    (y0, x0, wh, ww), = suggest.calls
    assert y0 % 3 == 0 and x0 % 3 == 0           # proxy pixels are source pixels
    assert y0 < 300 < y0 + wh and x0 < 450 < x0 + ww
    assert max(wh, ww) <= hl._NATIVE_WINDOW_MAX_PX


def test_no_window_leaves_the_proxy_answer():
    """A caller that can't render the window (``None``, or it raises an I/O
    error) gets exactly the proxy's answer, as before the window existed."""
    suggest = _rim_case(rc=12)
    proxy_only = suggest(3, window=False)
    from seestack.edit.registry import EditContext, get_op

    spec = get_op("tone.stretch")
    params = dict(spec.defaults())
    h, w = 600, 900
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(yy - h / 2, xx - w / 2)
    rng = np.random.default_rng(0)
    img = (0.05 + 0.02 * np.exp(-r / 100.0) + 0.3 * np.exp(-r / 12)
           + rng.normal(0.0, 0.0005, (h, w)))
    lin = np.repeat(img.astype(np.float32)[..., None], 3, axis=2)[::3, ::3].copy()
    ctx = EditContext(proxy_scale=3.0, is_proxy=True)

    def restretch(p):
        return spec.apply(lin, {**params, "highlights": p}, ctx)

    def refuses(*_a):
        return None

    def breaks(*_a):
        raise OSError("gone")

    for nw in (refuses, breaks):
        assert hl.suggest_highlight_protect(lin, restretch, proxy_scale=3.0,
                                            native_window=nw) == proxy_only


def test_a_big_core_measures_on_the_proxy():
    """Past the window cap the core is big, its rim a small share, and the
    proxy's answer holds — the window is not read."""
    core = np.zeros((400, 400), dtype=bool)
    core[10:390, 10:390] = True
    assert hl._native_window_bounds(core, 4.0) is None
    small = np.zeros((400, 400), dtype=bool)
    small[100:110, 200:215] = True
    assert hl._native_window_bounds(small, 4.0) == ((100 - 7) * 4, (200 - 7) * 4,
                                                    (10 + 14) * 4, (15 + 14) * 4)
