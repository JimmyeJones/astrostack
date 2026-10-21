"""The automatic drizzle decision — "Auto, when worth it".

The owner asked whether drizzle is ever used (his pictures come out at the
sensor's own resolution) and chose "Auto, when worth it" when asked what he
wanted instead. These pin what *worth it* means:
:mod:`seestack.stack.autodrizzle` decides from a canvas's per-output-pixel
depth, whether the subs actually moved sub-pixel between frames, and whether
the super-resolved canvas fits the memory budget — and nothing else.

The arithmetic lives in a pure module on purpose: the run that takes the
decision, the FITS card that records it and the sentence History reads are all
driven from this one verdict, so they cannot describe three different runs.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from seestack.stack.autodrizzle import (
    AUTO_DRIZZLE_MIN_DITHER_PX,
    AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL,
    AUTO_DRIZZLE_MIN_SCALE,
    AUTO_DRIZZLE_SCALE,
    REASON_DEEP_AND_DITHERED,
    REASON_DITHER_UNKNOWN,
    REASON_NO_ROOM_IN_BUDGET,
    REASON_TOO_FEW_SAMPLES,
    REASON_TOO_LITTLE_DITHER,
    _circular_spread,
    canvas_pixel_positions,
    decide_auto_drizzle,
    dither_spread_px,
    footprint_coverage_plane,
    samples_per_output_pixel,
)

FRAME = (320, 480)          # (h, w) — the synth fixtures' Seestar-ish frame


def _dithered(n: int = 60) -> list[tuple[float, float]]:
    """``n`` sub positions whose sub-pixel phases fill the pixel."""
    return [(100.0 + i * 0.37, 50.0 + i * 0.53) for i in range(n)]


def _parked(n: int = 60) -> list[tuple[float, float]]:
    """``n`` sub positions that never moved off one phase."""
    return [(100.25, 50.75)] * n


# --------------------------------------------------------------------------
# The per-output-pixel depth: the denominator, which is the whole bug class
# this bar had to avoid (a mosaic's frame *total* says yes on exactly the
# canvas drizzle handles worst).
# --------------------------------------------------------------------------

def test_a_single_field_has_no_area_correction():
    """Canvas == one frame ⇒ ``None``, meaning "the frame count is the depth"."""
    assert samples_per_output_pixel(250, dst_shape=FRAME, ref_shape=FRAME) is None


def test_a_four_panel_mosaic_divides_the_total_by_its_four_fields():
    """800 subs over a 2×2 no-overlap raster is 200 on a pixel, not 800."""
    dst = (FRAME[0] * 2, FRAME[1] * 2)
    assert samples_per_output_pixel(800, dst_shape=dst, ref_shape=FRAME) == 200.0


def test_a_deep_mosaic_that_is_shallow_per_panel_is_not_drizzled():
    """The case the frame total gets wrong, end to end through the decision.

    900 subs is four and a half times the bar; spread over a 3×3 raster they are
    100 on any pixel, which is *half* the bar. Fails before this module existed
    in the only way that mattered — there was no decision at all, and the
    Stack-form bar quoting a frame total would have said yes here."""
    dst = (FRAME[0] * 3, FRAME[1] * 3)
    assert samples_per_output_pixel(900, dst_shape=dst, ref_shape=FRAME) == 100.0
    out = decide_auto_drizzle(n_frames=900, ref_shape=FRAME, dst_shape=dst,
                              measure_dither=lambda: dither_spread_px(_dithered()))
    assert out.drizzle is False
    assert out.reason == REASON_TOO_FEW_SAMPLES
    assert out.samples_per_pixel == 100


def test_a_degenerate_shape_measures_nothing_rather_than_dividing_by_zero():
    assert samples_per_output_pixel(10, dst_shape=(0, 0), ref_shape=FRAME) is None
    assert samples_per_output_pixel(10, dst_shape=FRAME, ref_shape=(0, 480)) is None
    assert samples_per_output_pixel(0, dst_shape=FRAME, ref_shape=FRAME) is None


# --------------------------------------------------------------------------
# The dither measurement.
# --------------------------------------------------------------------------

def test_identical_phases_spread_zero_and_uniform_ones_spread_one_over_root_twelve():
    assert _circular_spread([0.3] * 50) == 0.0
    rng = np.random.default_rng(0)
    assert _circular_spread(list(rng.random(4000))) == pytest.approx(
        1.0 / math.sqrt(12.0), abs=0.01)


def test_the_spread_wraps_round_the_pixel_boundary():
    """0.98 and 0.02 are two hundredths of a pixel apart, not 0.96.

    A plain standard deviation reads that pair at ~0.48 — nearly the uniform
    value — so a set that never moved, whose solve merely jitters across a pixel
    boundary, would read as well dithered and be drizzled. Fails before the
    circular centring."""
    phases = [0.98, 0.02] * 50
    assert _circular_spread(phases) == pytest.approx(0.02, abs=1e-6)
    assert float(np.std(phases)) > 0.45        # what the naive reading would say
    assert _circular_spread(phases) < AUTO_DRIZZLE_MIN_DITHER_PX


def test_a_set_that_never_moved_is_not_drizzled():
    out = decide_auto_drizzle(n_frames=250, ref_shape=FRAME, dst_shape=FRAME,
                              measure_dither=lambda: dither_spread_px(_parked()))
    assert out.drizzle is False
    assert out.reason == REASON_TOO_LITTLE_DITHER
    assert out.dither_px == 0.0


def test_fewer_than_two_positions_measures_nothing():
    assert dither_spread_px([]) is None
    assert dither_spread_px([(1.0, 2.0)]) is None
    nan = float("nan")
    assert dither_spread_px([(nan, nan), (1.0, 2.0)]) is None


def test_a_mosaic_is_measured_inside_its_panels_not_across_them():
    """The measurement that pooling gets backwards.

    Each panel of this raster never moved — every sub in it shares one phase —
    but the two panels sit at different sub-pixel offsets from the canvas grid,
    so the *pooled* phases look spread while no output pixel ever sees more than
    one panel. Pooled: a healthy-looking spread. Per panel: zero, which is the
    truth. Fails before the ``labels`` path."""
    pts = [(100.25, 50.25)] * 30 + [(300.75, 250.75)] * 30
    labels = [0] * 30 + [1] * 30
    pooled = dither_spread_px(pts)
    assert pooled is not None and pooled.worst > AUTO_DRIZZLE_MIN_DITHER_PX
    per_panel = dither_spread_px(pts, labels=labels, min_members=10)
    assert per_panel is not None
    assert per_panel.panels == 2
    assert per_panel.worst == 0.0


def test_the_worst_panel_decides_not_the_average():
    """One dithered panel cannot vouch for an undithered neighbour."""
    pts = _dithered(30) + [(300.5, 250.5)] * 30
    labels = [0] * 30 + [1] * 30
    out = dither_spread_px(pts, labels=labels, min_members=10)
    assert out is not None and out.worst == 0.0


def test_a_panel_too_thin_to_judge_is_left_out_of_the_verdict():
    """A half-shot panel at the edge of a raster the owner is still building
    must not answer for the whole canvas."""
    pts = _dithered(30) + [(300.5, 250.5)] * 3
    labels = [0] * 30 + [1] * 3
    out = dither_spread_px(pts, labels=labels, min_members=10)
    assert out is not None
    assert out.panels == 1 and out.n == 30
    assert out.worst > AUTO_DRIZZLE_MIN_DITHER_PX


def test_unlabelled_subs_are_left_out():
    pts = _dithered(30) + [(300.5, 250.5)] * 30
    labels = [0] * 30 + [-1] * 30
    out = dither_spread_px(pts, labels=labels, min_members=10)
    assert out is not None and out.panels == 1 and out.n == 30


def test_no_panel_big_enough_measures_nothing():
    pts = _dithered(6)
    assert dither_spread_px(pts, labels=[0] * 6, min_members=10) is None


def test_an_unmeasurable_dither_refuses_rather_than_assumes():
    """Drizzle without sub-pixel variety adds a grid instead of detail, so
    "could not tell" is a no — never a yes on the assumption it moved."""
    out = decide_auto_drizzle(n_frames=250, ref_shape=FRAME, dst_shape=FRAME,
                              measure_dither=lambda: None)
    assert out.drizzle is False
    assert out.reason == REASON_DITHER_UNKNOWN
    assert out.dither_px is None


# --------------------------------------------------------------------------
# The decision itself, and the budget ladder.
# --------------------------------------------------------------------------

def test_a_deep_dithered_single_field_drizzles_at_one_and_a_half():
    out = decide_auto_drizzle(
        n_frames=AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL, ref_shape=FRAME,
        dst_shape=FRAME, measure_dither=lambda: dither_spread_px(_dithered()))
    assert out.drizzle is True
    assert out.scale == AUTO_DRIZZLE_SCALE
    assert out.reason == REASON_DEEP_AND_DITHERED
    assert out.samples_per_pixel == AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL


def test_one_sub_below_the_bar_does_not():
    out = decide_auto_drizzle(
        n_frames=AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL - 1, ref_shape=FRAME,
        dst_shape=FRAME, measure_dither=lambda: dither_spread_px(_dithered()))
    assert out.drizzle is False and out.reason == REASON_TOO_FEW_SAMPLES


def test_an_over_budget_canvas_steps_the_scale_down():
    out = decide_auto_drizzle(
        n_frames=400, ref_shape=FRAME, dst_shape=FRAME,
        measure_dither=lambda: dither_spread_px(_dithered()),
        fits_budget=lambda s: s <= 1.3)
    assert out.drizzle is True
    assert out.scale == pytest.approx(1.3)


def test_below_the_floor_it_declines_rather_than_drizzling_a_little():
    out = decide_auto_drizzle(
        n_frames=400, ref_shape=FRAME, dst_shape=FRAME,
        measure_dither=lambda: dither_spread_px(_dithered()),
        fits_budget=lambda s: s < AUTO_DRIZZLE_MIN_SCALE)
    assert out.drizzle is False
    assert out.reason == REASON_NO_ROOM_IN_BUDGET
    # …and it still reports what it measured, so the card can say why.
    assert out.samples_per_pixel == 400
    assert out.dither_px is not None


def test_the_ladder_only_offers_stops_between_the_floor_and_the_ask():
    """Whatever the budget says, the scale is one of the offered stops — never
    a value a reader would have to guess the provenance of."""
    asked: list[float] = []

    def budget(s: float) -> bool:
        asked.append(s)
        return False

    decide_auto_drizzle(n_frames=400, ref_shape=FRAME, dst_shape=FRAME,
                        measure_dither=lambda: dither_spread_px(_dithered()),
                        fits_budget=budget)
    assert asked[0] == AUTO_DRIZZLE_SCALE
    assert min(asked) == pytest.approx(AUTO_DRIZZLE_MIN_SCALE)
    assert all(AUTO_DRIZZLE_MIN_SCALE - 1e-9 <= s <= AUTO_DRIZZLE_SCALE
               for s in asked)


def test_the_bar_is_injectable_so_an_integration_test_need_not_stack_two_hundred_subs():
    out = decide_auto_drizzle(n_frames=6, ref_shape=FRAME, dst_shape=FRAME,
                              measure_dither=lambda: dither_spread_px(_dithered()),
                              min_samples_per_pixel=5)
    assert out.drizzle is True


# --------------------------------------------------------------------------
# Reading the phases off real WCS text.
# --------------------------------------------------------------------------

def test_the_phases_come_off_each_subs_own_wcs():
    """A dithered set's measured phases spread; a set written at one pointing
    does not. This is the half that touches astropy, so it is tested against
    the same synthetic WCS the stacker fixtures use."""
    pytest.importorskip("astropy")
    from tests.synth import make_synth_wcs_text

    class _F:
        def __init__(self, dx: float, dy: float) -> None:
            self.width_px, self.height_px = FRAME[1], FRAME[0]
            self.wcs_json = make_synth_wcs_text(
                width=FRAME[1], height=FRAME[0], crpix_shift=(dx, dy))

    canvas = make_synth_wcs_text(width=FRAME[1], height=FRAME[0])
    moved = [_F(i * 0.37, i * 0.53) for i in range(40)]
    parked = [_F(0.0, 0.0) for _ in range(40)]

    pts = canvas_pixel_positions(moved, canvas_wcs_text=canvas)
    assert len(pts) == 40 and all(math.isfinite(x) for x, _ in pts)
    spread = dither_spread_px(pts)
    assert spread is not None and spread.worst > AUTO_DRIZZLE_MIN_DITHER_PX

    still = dither_spread_px(canvas_pixel_positions(
        parked, canvas_wcs_text=canvas))
    assert still is not None and still.worst == 0.0


def test_a_sub_with_no_usable_wcs_is_a_nan_rather_than_an_exception():
    pytest.importorskip("astropy")
    from tests.synth import make_synth_wcs_text

    class _F:
        wcs_json = "END"
        width_px, height_px = FRAME[1], FRAME[0]

    pts = canvas_pixel_positions([_F()], canvas_wcs_text=make_synth_wcs_text())
    assert len(pts) == 1 and math.isnan(pts[0][0])


def test_an_unusable_canvas_wcs_measures_nothing():
    pts = canvas_pixel_positions([object()], canvas_wcs_text=None)
    assert len(pts) == 1
    assert math.isnan(pts[0][0]) and math.isnan(pts[0][1])


def test_the_dither_is_not_measured_when_the_depth_bar_already_answered():
    """The ordering is contract, not an optimisation: measuring the phases is a
    WCS read per sub (plus the panel clustering on a mosaic), and most unattended
    runs are answered by arithmetic on the canvas alone. A run that paid for it
    anyway would add seconds to every shallow walk-away stack."""
    calls = []

    def measure():
        calls.append(1)
        return dither_spread_px(_dithered())

    out = decide_auto_drizzle(n_frames=5, ref_shape=FRAME, dst_shape=FRAME,
                              measure_dither=measure)
    assert out.reason == REASON_TOO_FEW_SAMPLES
    assert calls == []
    decide_auto_drizzle(n_frames=400, ref_shape=FRAME, dst_shape=FRAME,
                        measure_dither=measure)
    assert calls == [1]


# --------------------------------------------------------------------------
# An UNEVEN mosaic: the canvas average is not the depth of a typical pixel.
# Scout 2026-10-21, QA sweep (2): one deep panel (single-field nights on a
# mosaic target) lifted the bounding-box average over the 200 bar while two
# thirds or more of the picture sat under even the 100 warn bar. The shapes
# below are that probe's, at the S30's own frame size and overlap.
# --------------------------------------------------------------------------

S30 = (1920, 1080)          # (h, w) — a Seestar S30 sub, portrait


class _Sub:
    def __init__(self, text: str) -> None:
        self.wcs_json = text
        self.height_px, self.width_px = S30


def _raster(nx: int, ny: int, counts: list[int], *, seed: int = 0,
            subpixel: bool = False):
    """An ``nx``×``ny`` S30 raster at 12 % overlap, ``counts[i]`` subs on panel
    ``i`` (row-major), each dithered ±8 px — as (subs, canvas WCS, canvas shape).
    ``subpixel`` dithers by fractional pixels and gives each sub its solved
    centre, which is what the stacker's own dither measurement needs."""
    pytest.importorskip("astropy")
    import random

    from tests.synth import make_synth_wcs_text

    rng = random.Random(seed)
    fh, fw = S30
    sx, sy = round(fw * 0.88), round(fh * 0.88)
    w, h = fw + sx * (nx - 1), fh + sy * (ny - 1)
    canvas = make_synth_wcs_text(width=w, height=h, pixscale_arcsec=3.9)
    texts: dict[tuple[int, int], str] = {}
    subs = []
    for j in range(ny):
        for i in range(nx):
            for _ in range(counts[j * nx + i]):
                if subpixel:
                    ox = i * sx + rng.uniform(-8, 8)
                    oy = j * sy + rng.uniform(-8, 8)
                else:
                    ox = i * sx + rng.randint(-8, 8)
                    oy = j * sy + rng.randint(-8, 8)
                if (ox, oy) not in texts:
                    texts[(ox, oy)] = make_synth_wcs_text(
                        width=fw, height=fh, pixscale_arcsec=3.9,
                        crpix_shift=(w / 2 - ox - fw / 2, h / 2 - oy - fh / 2))
                subs.append(_Sub(texts[(ox, oy)]))
    if subpixel:
        from seestack.io.wcs_io import wcs_image_center_deg_from_text

        for sub in subs:
            sub.ra_center_deg, sub.dec_center_deg = wcs_image_center_deg_from_text(
                sub.wcs_json, width=fw, height=fh)
    return subs, canvas, (h, w)


def _decide_on(subs, canvas, shape, *, with_panel_depth: bool = True):
    from seestack.stack.stacker import coverage_panel_depth

    def panel_depth():
        plane = footprint_coverage_plane(subs, canvas_wcs_text=canvas,
                                         dst_shape=shape)
        return None if plane is None else coverage_panel_depth(plane)

    return decide_auto_drizzle(
        n_frames=len(subs), ref_shape=S30, dst_shape=shape,
        measure_dither=lambda: dither_spread_px(_dithered()),
        measure_panel_depth=panel_depth if with_panel_depth else None)


@pytest.mark.parametrize("nx, ny, counts, average", [
    (2, 2, [1500, 60, 60, 60], 475),
    (3, 3, [60, 60, 60, 60, 2000, 60, 60, 60, 60], 325),
    (3, 3, [30, 30, 30, 30, 1500, 30, 30, 30, 30], 228),
])
def test_one_deep_panel_does_not_drizzle_a_mosaic_whose_other_panels_are_thin(
        nx, ny, counts, average):
    """The bug: each of these clears the 200 bar on its canvas *average* and
    was drizzled — ×7 the stacking time — though most of the picture holds
    under a third of that. Judged on a typical panel's depth, none is."""
    subs, canvas, shape = _raster(nx, ny, counts)
    before = _decide_on(subs, canvas, shape, with_panel_depth=False)
    assert before.drizzle is True and before.samples_per_pixel == average
    out = _decide_on(subs, canvas, shape)
    assert out.drizzle is False
    assert out.reason == REASON_TOO_FEW_SAMPLES
    assert out.samples_per_pixel < 100      # under even the warn bar
    assert out.samples_per_pixel <= min(counts) * 1.0 + 1


@pytest.mark.parametrize("nx, ny, per_panel, drizzles", [
    (2, 2, 300, True),
    (3, 3, 300, True),
    (3, 3, 120, False),
])
def test_an_even_raster_keeps_its_verdict(nx, ny, per_panel, drizzles):
    """Where the average was right, the panel depth agrees with it — and the
    depth quoted on a yes is the panel's own, which is what a pixel holds."""
    subs, canvas, shape = _raster(nx, ny, [per_panel] * (nx * ny))
    before = _decide_on(subs, canvas, shape, with_panel_depth=False)
    out = _decide_on(subs, canvas, shape)
    assert before.drizzle is drizzles
    assert out.drizzle is drizzles
    if drizzles:
        assert out.samples_per_pixel == per_panel


def test_the_panel_depth_is_only_asked_once_the_average_clears_the_bar():
    """It costs a WCS read per sub, like the dither: a shallow canvas, and a
    single field (where the frame count already is the depth), never pay it."""
    calls = []

    def panel():
        calls.append(1)
        return 999.0

    dst = (FRAME[0] * 3, FRAME[1] * 3)
    decide_auto_drizzle(n_frames=900, ref_shape=FRAME, dst_shape=dst,
                        measure_dither=lambda: dither_spread_px(_dithered()),
                        measure_panel_depth=panel)
    decide_auto_drizzle(n_frames=400, ref_shape=FRAME, dst_shape=FRAME,
                        measure_dither=lambda: dither_spread_px(_dithered()),
                        measure_panel_depth=panel)
    assert calls == []
    decide_auto_drizzle(n_frames=2700, ref_shape=FRAME, dst_shape=dst,
                        measure_dither=lambda: dither_spread_px(_dithered()),
                        measure_panel_depth=panel)
    assert calls == [1]


def test_the_panel_depth_can_only_lower_the_depth_and_none_keeps_the_average():
    """A panel reading *above* the average (the overlap of a sparse raster)
    must not talk a shallow canvas into drizzling, and an unmeasurable plane
    leaves the decision exactly where the average put it."""
    dst = (FRAME[0] * 2, FRAME[1] * 2)
    kw = dict(n_frames=1000, ref_shape=FRAME, dst_shape=dst,
              measure_dither=lambda: dither_spread_px(_dithered()))
    assert decide_auto_drizzle(**kw).samples_per_pixel == 250
    assert decide_auto_drizzle(
        **kw, measure_panel_depth=lambda: 900.0).samples_per_pixel == 250
    assert decide_auto_drizzle(
        **kw, measure_panel_depth=lambda: None).samples_per_pixel == 250
    assert decide_auto_drizzle(
        **kw, measure_panel_depth=lambda: float("nan")).samples_per_pixel == 250


def test_the_footprint_fill_covers_exactly_the_pixels_inside_each_quad():
    """The scanline fill against an independent point-in-polygon test, on
    rotated quads (an alt-az sub's footprint turns through the night)."""
    from skimage.draw import polygon

    from seestack.stack.autodrizzle import _fill_quads

    rng = np.random.default_rng(7)
    quads = []
    for _ in range(60):
        cx, cy = rng.uniform(20, 110, 2)
        a = rng.uniform(0, math.pi)
        rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        quads.append(np.array([[-25, -40], [25, -40], [25, 40], [-25, 40]]) @ rot.T
                     + (cx, cy))
    quads_arr = np.array(quads)
    weights = rng.uniform(0.5, 3.0, len(quads))
    ref = np.zeros((96, 128))
    for q, wt in zip(quads_arr, weights, strict=True):
        rr, cc = polygon(q[:, 1], q[:, 0], shape=ref.shape)
        ref[rr, cc] += wt
    got = _fill_quads(ref.shape, quads_arr, weights)
    assert np.allclose(got, ref, atol=1e-4)


def test_a_sampled_plane_keeps_the_depth_of_the_whole_set():
    """Past ``max_subs`` the footprints are drawn at a stride and weighted back
    up, so the deepest targets read their real depth at a bounded cost."""
    from seestack.stack.stacker import coverage_panel_depth

    subs, canvas, shape = _raster(2, 2, [500] * 4, seed=3)
    whole = coverage_panel_depth(footprint_coverage_plane(
        subs, canvas_wcs_text=canvas, dst_shape=shape))
    sampled = coverage_panel_depth(footprint_coverage_plane(
        subs, canvas_wcs_text=canvas, dst_shape=shape, max_subs=200))
    assert whole == pytest.approx(500, rel=0.02)
    assert sampled == pytest.approx(whole, rel=0.1)


def test_no_readable_footprint_draws_no_plane():
    pytest.importorskip("astropy")
    from tests.synth import make_synth_wcs_text

    class _Bad:
        wcs_json = "END"
        width_px, height_px = FRAME[1], FRAME[0]

    canvas = make_synth_wcs_text()
    assert footprint_coverage_plane([_Bad()], canvas_wcs_text=canvas,
                                    dst_shape=FRAME) is None
    assert footprint_coverage_plane([_Bad()], canvas_wcs_text=None,
                                    dst_shape=FRAME) is None
    assert footprint_coverage_plane([], canvas_wcs_text=canvas,
                                    dst_shape=FRAME) is None


def test_the_stacker_judges_an_uneven_mosaic_on_its_panels():
    """The same uneven 2×2 through the stacker's own wiring — the dither is
    real and sub-pixel, the panels separate, the budget is the default — so
    the only thing standing between it and a ×7 drizzle is the depth."""
    from seestack.stack.stacker import _decide_auto_drizzle

    subs, canvas, shape = _raster(2, 2, [1500, 60, 60, 60], subpixel=True)
    out = _decide_auto_drizzle(
        subs, len(subs), ref_shape=S30, dst_shape=shape,
        dst_wcs_text=canvas, is_mosaic=True, memory_budget_gb=64.0)
    assert out.drizzle is False
    assert out.reason == REASON_TOO_FEW_SAMPLES
    assert out.samples_per_pixel == 60

    even, canvas, shape = _raster(2, 2, [300] * 4, subpixel=True)
    out = _decide_auto_drizzle(
        even, len(even), ref_shape=S30, dst_shape=shape,
        dst_wcs_text=canvas, is_mosaic=True, memory_budget_gb=64.0)
    assert out.drizzle is True
    assert out.samples_per_pixel == 300
